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

    assert resumen["2052"]["Estado aprovechamiento"] == "Estimado Manual"
    assert resumen["2052"]["Nº calibres aprovechamiento"] == 2
    assert resumen["2052"]["Kg estimados calculados"] == 8000
    assert {r["Origen"] for r in detalle["2052"]} == {"CAMPO_ESTIMADO_MANUAL"}


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
            conn.execute('INSERT INTO Loteado VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (palet, "2026", "NECTARINA", "EMP", "STOCK", "S", "X", "2026-01-02"))
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


def test_loteado_insuficiente_no_se_usa(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(tmp_path, [{"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 1000}])
    _crear_loteado(tmp_path, [{"IdLote": "A1", "Neto": 50, "Calibre": "2"}])
    repo = PlanningRepository(base_dir=tmp_path)
    rows, _ = repo._get_campo_disponibilidad_aprovechamiento(_stock("B1", 1000), {})
    assert rows == []


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
