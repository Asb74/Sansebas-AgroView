import sqlite3

import db.connection as connection
from db.planning_repository import PlanningRepository


def test_upsert_estimado_agrupado_reparte_lineas_y_actualiza_resumen(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    repo = PlanningRepository(base_dir=tmp_path)

    ids = repo.upsert_aprovechamiento_estimado(
        {
            "Boleta": "2052",
            "Campana": "2026",
            "Cultivo": "NECTARINA",
            "Variedad": "VAR",
            "GrupoVarietal": "GRUPO",
            "Categoria": "NORMAL",
            "Calibre": "CAL 1-2",
            "KgCampoAplicado": 10000,
            "Porcentaje": 80,
            "Observaciones": "manual",
        }
    )

    assert len(ids) == 2
    rows = repo.get_aprovechamientos_estimados_por_boleta("2052")
    assert [r["Calibre"] for r in rows] == ["CAL 1", "CAL 2"]
    assert [r["KgEstimado"] for r in rows] == [4000, 4000]

    stock_campo = [
        {
            "Cultivo": "NECTARINA",
            "Campaña": "2026",
            "Grupo varietal": "GRUPO",
            "Variedad": "VAR",
            "Boleta": "2052",
            "Kg campo": 10000,
        }
    ]
    resumen, detalle = repo.build_aprovechamiento_stock_campo(stock_campo, {})

    key = repo._stock_campo_partida_key(stock_campo[0])
    assert resumen[key]["Estado aprovechamiento"] == "Estimado Manual"
    assert resumen[key]["Nº calibres aprovechamiento"] == 2
    assert resumen[key]["Kg estimados calculados"] == 8000
    assert {r["Origen"] for r in detalle["2052"]} == {"CAMPO_ESTIMADO_MANUAL"}



def test_resumen_stock_campo_se_calcula_por_partida_no_por_boleta(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(tmp_path, [{"Boleta": "2050", "AlbaranDef": "A1", "Neto": 1000, "NetoPartida": 1000, "Cal1": 500, "Cal2": 500}])
    repo = PlanningRepository(base_dir=tmp_path)
    stock_campo = [
        {"Cultivo": "NECTARINA", "Campaña": "2026", "Fecha carga": "2026-01-01", "Socio": "SOC", "Variedad": "VAR", "Grupo varietal": "GRUPO", "Boleta": "2050", "Kg campo": 14048},
        {"Cultivo": "NECTARINA", "Campaña": "2026", "Fecha carga": "2026-01-01", "Socio": "SOC", "Variedad": "VAR", "Grupo varietal": "GRUPO", "Boleta": "2050", "Kg campo": 6945},
    ]

    resumen, detalle = repo.build_aprovechamiento_stock_campo(stock_campo, {})

    assert resumen[repo._stock_campo_partida_key(stock_campo[0])]["Kg estimados calculados"] == 14048
    assert resumen[repo._stock_campo_partida_key(stock_campo[1])]["Kg estimados calculados"] == 6945
    assert {row["Kg campo origen"] for row in detalle["2050"]} == {14048.0, 6945.0}

def test_delete_estimado_desactiva_linea(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    repo = PlanningRepository(base_dir=tmp_path)
    ids = repo.upsert_aprovechamiento_estimado(
        {
            "Boleta": "1",
            "Calibre": "1",
            "KgCampoAplicado": 100,
            "Porcentaje": 50,
        }
    )

    repo.delete_aprovechamiento_estimado(ids[0])

    assert repo.get_aprovechamientos_estimados_por_boleta("1") == []
    with sqlite3.connect(tmp_path / "app_config.sqlite") as conn:
        activo = conn.execute("SELECT Activo FROM AprovechamientosEstimados WHERE Id = ?", (ids[0],)).fetchone()[0]
    assert activo == 0


def _stock(boleta="2052", kg=1000):
    return [{"Cultivo": "NECTARINA", "Campaña": "2026", "Grupo varietal": "GRUPO", "Variedad": "VAR", "Boleta": boleta, "Kg campo": kg}]


def _crear_pesosfres(path, rows):
    with sqlite3.connect(path / "DBfruta.sqlite") as conn:
        conn.execute('CREATE TABLE PesosFres (Boleta TEXT, AlbaranDef TEXT, "CAMPAÑA" TEXT, CULTIVO TEXT, Socio TEXT, Variedad TEXT, Fcarga TEXT, Neto REAL, NetoPartida REAL, Categoria TEXT, Cal0 REAL, Cal1 REAL, Cal2 REAL, Cal3 REAL, Cal4 REAL, Cal5 REAL, Cal6 REAL, Cal7 REAL, Cal8 REAL, Cal9 REAL, Cal10 REAL, Cal11 REAL)')
        for row in rows:
            vals = {f"Cal{i}": 0 for i in range(12)}
            vals.update(row)
            conn.execute('INSERT INTO PesosFres VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (
                vals.get("Boleta"), vals.get("AlbaranDef", vals.get("Boleta")), "2026", "NECTARINA", "SOC", "VAR", "2026-01-01", vals.get("Neto", 1000), vals.get("NetoPartida", 1000), "NORMAL",
                vals["Cal0"], vals["Cal1"], vals["Cal2"], vals["Cal3"], vals["Cal4"], vals["Cal5"], vals["Cal6"], vals["Cal7"], vals["Cal8"], vals["Cal9"], vals["Cal10"], vals["Cal11"]
            ))


def _crear_loteado(path, lote_rows):
    with sqlite3.connect(path / "bdloteado.sqlite") as conn:
        conn.execute('CREATE TABLE Loteado (IdPalet TEXT, Campaña TEXT, CULTIVO TEXT, EMPRESA TEXT, Estado TEXT, Terminado TEXT, Pedido TEXT, FechaAlmacen TEXT)')
        conn.execute('CREATE TABLE Lote (IdPalet TEXT, IdLote TEXT, Neto REAL, Calibre TEXT, Variedad TEXT, Lote TEXT)')
        for idx, row in enumerate(lote_rows, start=1):
            palet = row.get("IdPalet", f"P{idx}")
            conn.execute('INSERT INTO Loteado VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (palet, row.get("Campaña", "2026"), row.get("Cultivo", "NECTARINA"), row.get("Empresa", "EMP"), "STOCK", "S", "X", "2026-01-02"))
            conn.execute('INSERT INTO Lote VALUES (?, ?, ?, ?, ?, ?)', (palet, row.get("IdLote"), row.get("Neto"), row.get("Calibre"), "VAR", row.get("Categoria", "NORMAL")))


def test_normalizar_calibres_rangos_y_piezas(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    repo = PlanningRepository(base_dir=tmp_path)
    assert repo.normalizar_calibre_a_set("1/3") == {"1", "2", "3"}
    assert repo.normalizar_calibre_a_set("1-3") == {"1", "2", "3"}
    assert repo.normalizar_calibre_a_set("1.3") == {"1", "2", "3"}
    assert repo.normalizar_calibre_a_set("CAL 2/3") == {"2", "3"}
    assert repo.normalizar_calibre_a_set("4/6") == {"4", "5", "6"}
    assert repo.normalizar_calibre_a_set("6/10 PZ") == {"6"}


def test_pesosfres_validez_por_numero_de_calibres():
    assert not PlanningRepository._es_pesosfres_aprovechamiento_valido({"CAL 1": 1})
    assert PlanningRepository._es_pesosfres_aprovechamiento_valido({"CAL 1": 1, "CAL 2": 1})


def test_loteado_reparte_calibres_compuestos():
    assert PlanningRepository._repartir_kg_loteado_por_calibres(100, ["2", "3"]) == {"CAL 2": 50, "CAL 3": 50}
    assert PlanningRepository._expandir_calibre_loteado("1/3") == ["1", "2", "3"]


def test_loteado_insuficiente_se_usa_como_distribucion_porcentual(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(tmp_path, [{"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 1000}])
    _crear_loteado(tmp_path, [{"IdLote": "A1", "Neto": 50, "Calibre": "2"}])
    repo = PlanningRepository(base_dir=tmp_path)

    rows, _ = repo._get_campo_disponibilidad_aprovechamiento(_stock("B1", 1000), {})

    assert {r["Origen aprovechamiento"] for r in rows} == {"LOTEADO"}
    assert rows[0]["Calibre"] == "CAL 2"
    assert rows[0]["Kg disponibles"] == 1000
    assert rows[0]["Kg campo origen"] == 1000



def test_loteado_aplica_filtros_sql_de_boleta_campana_cultivo_empresa(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(
        tmp_path,
        [
            {"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 1000},
            {"Boleta": "B2", "AlbaranDef": "A2", "Cal1": 1000},
            {"Boleta": "B3", "AlbaranDef": "A3", "Cal1": 1000},
            {"Boleta": "B4", "AlbaranDef": "A4", "Cal1": 1000},
        ],
    )
    _crear_loteado(
        tmp_path,
        [
            {"IdLote": "A1", "Neto": 900, "Calibre": "1/3", "Campaña": "2026", "Cultivo": "NECTARINA", "Empresa": "EMP"},
            {"IdLote": "A2", "Neto": 900, "Calibre": "4", "Campaña": "2025", "Cultivo": "NECTARINA", "Empresa": "EMP"},
            {"IdLote": "A3", "Neto": 900, "Calibre": "5", "Campaña": "2026", "Cultivo": "MELOCOTON", "Empresa": "EMP"},
            {"IdLote": "A4", "Neto": 900, "Calibre": "6", "Campaña": "2026", "Cultivo": "NECTARINA", "Empresa": "OTRA"},
        ],
    )
    repo = PlanningRepository(base_dir=tmp_path)

    rows, sin_datos = repo._get_loteado_campo_disponibilidad_real(
        _stock("B1", 1000) + _stock("B2", 1000) + _stock("B3", 1000) + _stock("B4", 1000),
        {"campana": ["2026"], "cultivo": ["NECTARINA"], "empresa": ["EMP"]},
    )

    assert {r["Boleta"] for r in rows} == {"B1"}
    assert {r["Calibre"] for r in rows} == {"CAL 1", "CAL 2", "CAL 3"}
    assert sin_datos == 3


def test_prioridad_pesosfres_valido_gana_a_loteado(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(tmp_path, [{"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 500, "Cal2": 500}])
    _crear_loteado(tmp_path, [{"IdLote": "A1", "Neto": 900, "Calibre": "3"}])
    repo = PlanningRepository(base_dir=tmp_path)
    rows, _ = repo._get_campo_disponibilidad_aprovechamiento(_stock("B1", 1000), {})
    assert {r["Origen aprovechamiento"] for r in rows} == {"REAL_PESOSFRES"}


def test_prioridad_pesosfres_invalido_pasa_a_loteado(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(tmp_path, [{"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 1000}])
    _crear_loteado(tmp_path, [{"IdLote": "A1", "Neto": 900, "Calibre": "1/3"}])
    repo = PlanningRepository(base_dir=tmp_path)
    rows, _ = repo._get_campo_disponibilidad_aprovechamiento(_stock("B1", 1000), {})
    assert {r["Origen aprovechamiento"] for r in rows} == {"LOTEADO"}
    assert {r["Calibre"] for r in rows} == {"CAL 1", "CAL 2", "CAL 3"}


def test_prioridad_sin_real_ni_loteado_usa_estimado_manual(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    repo = PlanningRepository(base_dir=tmp_path)
    repo.upsert_aprovechamiento_estimado({"Boleta": "B1", "Calibre": "2", "KgCampoAplicado": 1000, "Porcentaje": 40})
    rows, _ = repo._get_campo_disponibilidad_aprovechamiento(_stock("B1", 1000), {})
    assert {r["Origen aprovechamiento"] for r in rows} == {"ESTIMADO_MANUAL"}


def test_loteado_deduplica_pesosfres_por_albaran_y_boleta(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(
        tmp_path,
        [
            {"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 1000},
            {"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 1000},
        ],
    )
    _crear_loteado(tmp_path, [{"IdPalet": "P1", "IdLote": "A1", "Neto": 900, "Calibre": "1/3"}])
    repo = PlanningRepository(base_dir=tmp_path)

    rows, sin_datos = repo._get_loteado_campo_disponibilidad_real(_stock("B1", 1000), {})

    assert sin_datos == 0
    assert round(sum(float(r["Kg disponibles"]) for r in rows), 2) == 900
    assert {r["Calibre"] for r in rows} == {"CAL 1", "CAL 2", "CAL 3"}


def test_loteado_historico_mayor_que_partida_se_aplica_como_porcentaje(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(tmp_path, [{"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 1000}])
    _crear_loteado(tmp_path, [{"IdPalet": "P1", "IdLote": "A1", "Neto": 1100, "Calibre": "1/2"}])
    repo = PlanningRepository(base_dir=tmp_path)
    repo.upsert_aprovechamiento_estimado({"Boleta": "B1", "Calibre": "3", "KgCampoAplicado": 1000, "Porcentaje": 40})

    rows, _ = repo._get_campo_disponibilidad_aprovechamiento(_stock("B1", 1000), {})

    assert {r["Origen aprovechamiento"] for r in rows} == {"LOTEADO"}
    assert {r["Calibre"] for r in rows} == {"CAL 1", "CAL 2"}
    assert round(sum(float(r["Kg disponibles"]) for r in rows), 2) == 1000
    assert {r["Kg campo origen"] for r in rows} == {1000}


def test_pesosfres_historicos_generan_una_distribucion_y_se_aplican_a_cada_partida(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(
        tmp_path,
        [
            {"Boleta": "B1", "AlbaranDef": "A1", "Neto": 1000, "NetoPartida": 1000, "Cal0": 100, "Cal1": 900},
            {"Boleta": "B1", "AlbaranDef": "A2", "Neto": 1000, "NetoPartida": 1000, "Cal0": 300, "Cal1": 700},
        ],
    )
    repo = PlanningRepository(base_dir=tmp_path)

    rows, _ = repo._get_campo_disponibilidad_aprovechamiento(_stock("B1", 1500), {})

    assert {r["Origen aprovechamiento"] for r in rows} == {"REAL_PESOSFRES"}
    assert [r["Calibre"] for r in rows] == ["CAL 0", "CAL 1"]
    assert [r["% aprovechamiento"] for r in rows] == [20.0, 80.0]
    assert [r["Kg disponibles"] for r in rows] == [300.0, 1200.0]
    assert {r["Kg campo origen"] for r in rows} == {1500}
    assert round(sum(float(r["Kg disponibles"]) for r in rows), 2) == 1500
