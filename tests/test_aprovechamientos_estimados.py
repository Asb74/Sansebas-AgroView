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


def _crear_calidad_loteado(path):
    with sqlite3.connect(path / "BdCalidad.sqlite") as conn:
        conn.execute(
            "CREATE TABLE Partidas (IdPartidaP TEXT, IdPartida0 TEXT, kg0 REAL, IdPartida1 TEXT, kg1 REAL, "
            "IdPartida2 TEXT, kg2 REAL, IdPartida3 TEXT, kg3 REAL, IdPartida4 TEXT, kg4 REAL, "
            "IdPartida5 TEXT, kg5 REAL, IdPartida6 TEXT, kg6 REAL, IdPartida7 TEXT, kg7 REAL, "
            "IdPartida8 TEXT, kg8 REAL, IdPartida9 TEXT, kg9 REAL)"
        )
        conn.execute(
            "CREATE TABLE DatosCalibre (IdPartida TEXT, Neto REAL, Podrido REAL, DLinea REAL, DMesa REAL, Inutil REAL, Piquera REAL, VerdeR REAL)"
        )
        conn.execute(
            "INSERT INTO Partidas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("PQUAL", "L1", 1000, "L2", 1000, "", None, "", None, "", None, "", None, "", None, "", None, "", None, "", None),
        )
        conn.execute("INSERT INTO DatosCalibre VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("PQUAL", 2000, 100, 120, 80, 0, 0, 0))


def test_loteado_ajusta_calibres_con_destrio_industria_de_calidad(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_loteado(
        tmp_path,
        [
            {"IdPalet": "P1", "IdLote": "L1", "Neto": 400, "Calibre": "2"},
            {"IdPalet": "P2", "IdLote": "L2", "Neto": 600, "Calibre": "3"},
        ],
    )
    _crear_calidad_loteado(tmp_path)
    repo = PlanningRepository(base_dir=tmp_path)

    rows = repo._get_loteado_aprovechamiento_por_boleta("B1", ["L1", "L2"], {})

    assert [(r["Calibre"], r["% loteado bruto"], r["% aprovechamiento"]) for r in rows] == [
        ("CAL 2", 40.0, 34.0),
        ("CAL 3", 60.0, 51.0),
    ]
    assert {r["Destrío %"] for r in rows} == {5.0}
    assert {r["Industria %"] for r in rows} == {10.0}
    assert {r["Comercial %"] for r in rows} == {85.0}


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


def test_harvestsync_expande_grupos_calibre():
    assert PlanningRepository.expandir_grupo_calibre_harvestsync("Cal 0-1") == ["CAL 0", "CAL 1"]
    assert PlanningRepository.expandir_grupo_calibre_harvestsync("Cal 1-3") == ["CAL 1", "CAL 2", "CAL 3"]
    assert PlanningRepository.expandir_grupo_calibre_harvestsync("Cal 6-10") == ["CAL 6", "CAL 7", "CAL 8", "CAL 9", "CAL 10"]
    assert PlanningRepository.expandir_grupo_calibre_harvestsync("Fuera Cal") == []


class _FakeDoc:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return dict(self._data)

    def get(self):
        return self


class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def where(self, *_args):
        return self

    def stream(self):
        return [_FakeDoc(d) for d in self._docs]


class _FakeCollection:
    def __init__(self, docs=None, templates=None):
        self._docs = docs or []
        self._templates = templates or {}

    def document(self, name):
        data = self._templates.get(name)
        return _FakeDoc(data or {}, exists=data is not None)

    def where(self, *_args):
        return _FakeQuery(self._docs)


class _FakeFirestore:
    def __init__(self, muestras):
        self.muestras = muestras

    def collection(self, name):
        if name == "PlantillasCalibre":
            return _FakeCollection(templates={"NECTARINA": {"CAMPO": ["Cal 1-3", "Cal 6-10", "Fuera Cal"]}})
        if name == "PlantillasAprovechamiento":
            return _FakeCollection(templates={"NECTARINA": {"CAMPO": ["Destrio", "Industria", "Categoria I", "Categoria II"]}})
        return _FakeCollection(docs=self.muestras)


def test_harvestsync_calcula_fruta_comercial_y_media_simple(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    muestras = [
        {"Boleta": "B1", "CULTIVO": "NECTARINA", "FechaHora": "2026-01-01", "Cal 1-3": 60, "Cal 6-10": 40, "Fuera Cal": 99, "Destrio": 5, "Industria": 15},
        {"Boleta": "B1", "CULTIVO": "NECTARINA", "FechaHora": "2026-01-02", "Cal 1-3": "30", "Cal 6-10": "70", "Fuera Cal": 99, "Destrio": "5", "Industria": "15"},
    ]
    repo = PlanningRepository(base_dir=tmp_path)
    monkeypatch.setattr(repo, "_get_harvestsync_client", lambda: _FakeFirestore(muestras))

    rows = repo._get_harvestsync_aprovechamiento_por_partida({"Boleta": "B1", "Cultivo": "NECTARINA", "Fecha carga": "2026-01-02"})

    assert {r["Origen aprovechamiento"] for r in rows} == {"HARVESTSYNC"}
    assert {r["Categoría"] for r in rows} == {"NORMAL"}
    assert round(sum(r["% aprovechamiento"] for r in rows), 2) == 80
    assert {r["Calibre"] for r in rows} == {"CAL 1", "CAL 2", "CAL 3", "CAL 6", "CAL 7", "CAL 8", "CAL 9", "CAL 10"}
    assert next(r for r in rows if r["Calibre"] == "CAL 1")["% aprovechamiento"] == 12
    assert next(r for r in rows if r["Calibre"] == "CAL 6")["% aprovechamiento"] == 8.8


def test_prioridad_harvestsync_antes_de_manual_y_despues_de_reales(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    repo = PlanningRepository(base_dir=tmp_path)
    repo.upsert_aprovechamiento_estimado({"Boleta": "B1", "Calibre": "2", "KgCampoAplicado": 1000, "Porcentaje": 40})
    monkeypatch.setattr(
        repo,
        "_get_harvestsync_aprovechamiento_por_partida",
        lambda partida: [{"Origen": "CAMPO_ESTIMADO_HARVESTSYNC", "Calibre": "CAL 1", "Categoría": "NORMAL", "% aprovechamiento": 80, "Origen aprovechamiento": "HARVESTSYNC", "Explicación": "Estimación media HarvestSync últimos 3 días"}],
    )
    rows, _ = repo._get_campo_disponibilidad_aprovechamiento([{"Cultivo": "NECTARINA", "Campaña": "2026", "Fecha carga": "2026-01-02", "Grupo varietal": "GRUPO", "Variedad": "VAR", "Boleta": "B1", "Kg campo": 1000}], {})
    assert {r["Origen aprovechamiento"] for r in rows} == {"HARVESTSYNC"}

    repo2 = PlanningRepository(base_dir=tmp_path)
    repo2.upsert_aprovechamiento_estimado({"Boleta": "B2", "Calibre": "2", "KgCampoAplicado": 1000, "Porcentaje": 40})
    monkeypatch.setattr(repo2, "_get_harvestsync_aprovechamiento_por_partida", lambda partida: [])
    rows, _ = repo2._get_campo_disponibilidad_aprovechamiento(_stock("B2", 1000), {})
    assert {r["Origen aprovechamiento"] for r in rows} == {"ESTIMADO_MANUAL"}


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


def test_loteado_bulk_calidad_varias_boletas_una_llamada(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(
        tmp_path,
        [
            {"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 1000},
            {"Boleta": "B2", "AlbaranDef": "A2", "Cal1": 1000},
        ],
    )
    _crear_loteado(
        tmp_path,
        [
            {"IdLote": "A1", "Neto": 1000, "Calibre": "2"},
            {"IdLote": "A2", "Neto": 1000, "Calibre": "3"},
        ],
    )
    with sqlite3.connect(tmp_path / "BdCalidad.sqlite") as conn:
        conn.execute(
            "CREATE TABLE Partidas (IdPartidaP TEXT, IdPartida0 TEXT, kg0 REAL, IdPartida1 TEXT, kg1 REAL, "
            "IdPartida2 TEXT, kg2 REAL, IdPartida3 TEXT, kg3 REAL, IdPartida4 TEXT, kg4 REAL, "
            "IdPartida5 TEXT, kg5 REAL, IdPartida6 TEXT, kg6 REAL, IdPartida7 TEXT, kg7 REAL, "
            "IdPartida8 TEXT, kg8 REAL, IdPartida9 TEXT, kg9 REAL)"
        )
        conn.execute(
            "CREATE TABLE DatosCalibre (IdPartida TEXT, Neto REAL, Podrido REAL, DLinea REAL, DMesa REAL, Inutil REAL, Piquera REAL, VerdeR REAL)"
        )
        conn.execute(
            "INSERT INTO Partidas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("PQUAL1", "A1", 1000, "", None, "", None, "", None, "", None, "", None, "", None, "", None, "", None, "", None),
        )
        conn.execute(
            "INSERT INTO Partidas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("PQUAL2", "A2", 1000, "", None, "", None, "", None, "", None, "", None, "", None, "", None, "", None, "", None),
        )
        conn.execute("INSERT INTO DatosCalibre VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("PQUAL1", 1000, 50, 100, 0, 0, 0, 0))
        conn.execute("INSERT INTO DatosCalibre VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("PQUAL2", 1000, 100, 200, 0, 0, 0, 0))
    repo = PlanningRepository(base_dir=tmp_path)
    original_bulk = repo._get_loteado_calidad_pcts_por_boleta_bulk
    llamadas = 0

    def wrapped_bulk(boleta_to_id_lotes):
        nonlocal llamadas
        llamadas += 1
        return original_bulk(boleta_to_id_lotes)

    monkeypatch.setattr(repo, "_get_loteado_calidad_pcts_por_boleta_bulk", wrapped_bulk)

    rows, _ = repo._get_campo_disponibilidad_aprovechamiento(_stock("B1", 1000) + _stock("B2", 1000), {})

    assert llamadas == 1
    por_boleta = {boleta: next(r for r in rows if r["Boleta"] == boleta) for boleta in ("B1", "B2")}
    assert (por_boleta["B1"]["Destrío %"], por_boleta["B1"]["Industria %"], por_boleta["B1"]["Comercial %"]) == (5.0, 10.0, 85.0)
    assert (por_boleta["B2"]["Destrío %"], por_boleta["B2"]["Industria %"], por_boleta["B2"]["Comercial %"]) == (10.0, 20.0, 70.0)


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


def test_loteado_bulk_varias_boletas_varios_lotes_aplica_calidad_por_boleta(tmp_path, monkeypatch):
    monkeypatch.setattr(connection, "APP_DB_PATH", tmp_path / "app_config.sqlite")
    _crear_pesosfres(
        tmp_path,
        [
            {"Boleta": "B1", "AlbaranDef": "A1", "Cal1": 1000},
            {"Boleta": "B1", "AlbaranDef": "A2", "Cal1": 1000},
            {"Boleta": "B2", "AlbaranDef": "A3", "Cal1": 1000},
            {"Boleta": "B2", "AlbaranDef": "A4", "Cal1": 1000},
        ],
    )
    _crear_loteado(
        tmp_path,
        [
            {"IdPalet": "P1", "IdLote": "A1", "Neto": 300, "Calibre": "1"},
            {"IdPalet": "P2", "IdLote": "A2", "Neto": 700, "Calibre": "2"},
            {"IdPalet": "P3", "IdLote": "A3", "Neto": 250, "Calibre": "3"},
            {"IdPalet": "P4", "IdLote": "A4", "Neto": 750, "Calibre": "4"},
        ],
    )
    with sqlite3.connect(tmp_path / "BdCalidad.sqlite") as conn:
        conn.execute(
            "CREATE TABLE Partidas (IdPartidaP TEXT, IdPartida0 TEXT, kg0 REAL, IdPartida1 TEXT, kg1 REAL, "
            "IdPartida2 TEXT, kg2 REAL, IdPartida3 TEXT, kg3 REAL, IdPartida4 TEXT, kg4 REAL, "
            "IdPartida5 TEXT, kg5 REAL, IdPartida6 TEXT, kg6 REAL, IdPartida7 TEXT, kg7 REAL, "
            "IdPartida8 TEXT, kg8 REAL, IdPartida9 TEXT, kg9 REAL)"
        )
        conn.execute("CREATE TABLE DatosCalibre (IdPartida TEXT, Neto REAL, Podrido REAL, DLinea REAL, DMesa REAL, Inutil REAL, Piquera REAL, VerdeR REAL)")
        conn.execute(
            "INSERT INTO Partidas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Q1", "A1", 300, "A2", 700, "", None, "", None, "", None, "", None, "", None, "", None, "", None, "", None),
        )
        conn.execute(
            "INSERT INTO Partidas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Q2", "A3", 250, "A4", 750, "", None, "", None, "", None, "", None, "", None, "", None, "", None, "", None),
        )
        conn.execute("INSERT INTO DatosCalibre VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("Q1", 1000, 100, 100, 0, 0, 0, 0))
        conn.execute("INSERT INTO DatosCalibre VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("Q2", 1000, 50, 150, 0, 0, 0, 0))

    repo = PlanningRepository(base_dir=tmp_path)
    llamadas_bulk = 0
    original_bulk = repo._get_loteado_aprovechamiento_por_boleta_bulk

    def wrapped_loteado_bulk(*args, **kwargs):
        nonlocal llamadas_bulk
        llamadas_bulk += 1
        return original_bulk(*args, **kwargs)

    def forbidden_single(*args, **kwargs):
        raise AssertionError("la ruta principal no debe consultar loteado boleta a boleta")

    monkeypatch.setattr(repo, "_get_loteado_aprovechamiento_por_boleta_bulk", wrapped_loteado_bulk)
    monkeypatch.setattr(repo, "_get_loteado_aprovechamiento_por_boleta", forbidden_single)

    rows, _ = repo._get_campo_disponibilidad_aprovechamiento(_stock("B1", 1000) + _stock("B2", 1000), {})

    assert llamadas_bulk == 1
    por_boleta_calibre = {(r["Boleta"], r["Calibre"]): r for r in rows}
    assert por_boleta_calibre[("B1", "CAL 1")]["% aprovechamiento"] == 24.0
    assert por_boleta_calibre[("B1", "CAL 2")]["% aprovechamiento"] == 56.0
    assert por_boleta_calibre[("B2", "CAL 3")]["% aprovechamiento"] == 20.0
    assert por_boleta_calibre[("B2", "CAL 4")]["% aprovechamiento"] == 60.0
    assert {r["Comercial %"] for r in rows if r["Boleta"] == "B1"} == {80.0}
    assert {r["Comercial %"] for r in rows if r["Boleta"] == "B2"} == {80.0}
    assert {r["Destrío %"] for r in rows if r["Boleta"] == "B1"} == {10.0}
    assert {r["Industria %"] for r in rows if r["Boleta"] == "B2"} == {15.0}
