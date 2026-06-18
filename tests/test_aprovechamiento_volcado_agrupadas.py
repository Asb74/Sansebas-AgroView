import sqlite3

from config import DB_FRUTA
from db.planning_repository import PlanningRepository


def test_partidas_agrupadas_volcado_usa_partidas_y_trazabilidad_pesosfres(tmp_path):
    repo = PlanningRepository(base_dir=tmp_path)
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE Partidas (
                IdPartidaP TEXT, IdPartida0 TEXT, IdPartida1 TEXT, IdPartida2 TEXT,
                kgP REAL, kg0 REAL, kg1 REAL, kg2 REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO Partidas VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("P1", "P1", "A1", "A2", 3000, 1000, 900, 1100),
        )
        conn.execute(
            """
            CREATE TABLE PesosFres (
                AlbaranDef TEXT, Boleta TEXT, IdSocio TEXT, Socio TEXT, FCarga TEXT, Apodo TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO PesosFres VALUES (?, ?, ?, ?, ?, ?)",
            ("A1", "NO_USAR_BDCALIDAD", "NO_USAR", "NO USAR BDCALIDAD", "2026-01-01", "1"),
        )

        fruta_path = tmp_path / DB_FRUTA
        with sqlite3.connect(fruta_path) as conn_fruta:
            conn_fruta.execute(
                """
                CREATE TABLE PesosFres (
                    AlbaranDef TEXT, AlbaranD TEXT, Boleta TEXT, IdSocio TEXT,
                    Socio TEXT, Fcarga TEXT, Apodo TEXT
                )
                """
            )
            conn_fruta.executemany(
                "INSERT INTO PesosFres VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("P1", "NO_USAR", "2052", "1234", "CANO MANZANARES, LUIS", "2026-06-13", "24"),
                    (" a 1 ", "NO_USAR", "2053", "1235", "AGRICULTOR A", "13/06/2026", "24"),
                    ("A2", "NO_USAR", "2054", "1236", "AGRICULTOR B", "2026-06-14", "25"),
                ],
            )

        rows, summary = repo._get_partidas_agrupadas_volcado(conn, ["P1", "P2"], {"P2": 500})

    assert rows == [
        {"Partida principal": "P1", "Partida incluida": "A1", "Kg asociado": 900.0, "Tipo": "Agrupada", "Boleta": "2053", "Socio": "1235", "Nombre socio": "AGRICULTOR A", "Fecha carga": "13/06/2026", "Semana": "24"},
        {"Partida principal": "P1", "Partida incluida": "A2", "Kg asociado": 1100.0, "Tipo": "Agrupada", "Boleta": "2054", "Socio": "1236", "Nombre socio": "AGRICULTOR B", "Fecha carga": "14/06/2026", "Semana": "25"},
        {"Partida principal": "P1", "Partida incluida": "P1", "Kg asociado": 1000.0, "Tipo": "Principal", "Boleta": "2052", "Socio": "1234", "Nombre socio": "CANO MANZANARES, LUIS", "Fecha carga": "13/06/2026", "Semana": "24"},
        {"Partida principal": "P2", "Partida incluida": "P2", "Kg asociado": 500.0, "Tipo": "Principal sin agrupación", "Boleta": "NO ENCONTRADA", "Socio": "NO ENCONTRADO", "Nombre socio": "NO ENCONTRADO", "Fecha carga": "-", "Semana": "-"},
    ]
    assert summary == {"principales": 2, "incluidas": 4, "adicionales": 2, "kg_total": 3000.0}


def test_aprovechamiento_volcado_filtra_datoscalibre_por_cultivo2(tmp_path):
    from datetime import datetime
    from config import DB_CALIDAD, DB_EEPPL, DB_LOTEADO, DB_PEDIDOS

    repo = PlanningRepository(base_dir=tmp_path)
    with sqlite3.connect(tmp_path / DB_CALIDAD) as conn:
        conn.execute(
            """
            CREATE TABLE DatosCalibre (
                IdPartida TEXT, Fecha TEXT, Campaña TEXT, Cultivo TEXT, Cultivo2 TEXT,
                EMPRESA TEXT, KgPartida REAL, Neto REAL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO DatosCalibre VALUES
            ('P1', '2026-06-17', '2026', 'CITRICOS', 'NARANJA', 'EMP', 1000, 0)
            """
        )
        conn.execute(
            """
            CREATE TABLE Partidas (
                IdPartidaP TEXT, IdPartida0 TEXT, kgP REAL, kg0 REAL
            )
            """
        )
        conn.execute("INSERT INTO Partidas VALUES ('P1', 'P1', 1000, 1000)")

    with sqlite3.connect(tmp_path / DB_LOTEADO) as conn:
        conn.execute("CREATE TABLE Loteado (IdPalet TEXT, CULTIVO TEXT)")
        conn.execute("CREATE TABLE Lote (IdLote TEXT, IdPalet TEXT, Calibre TEXT, Lote TEXT, Neto REAL, Cajas REAL, IdConfeccion TEXT, Confeccion TEXT, Variedad TEXT)")

    with sqlite3.connect(tmp_path / DB_PEDIDOS) as conn:
        conn.execute("CREATE TABLE MConfecciones (CODIGO TEXT, GRUPO TEXT)")

    with sqlite3.connect(tmp_path / DB_EEPPL) as conn:
        conn.execute("CREATE TABLE MVariedad (Variedad TEXT, CULTIVO TEXT, GRUPO TEXT, SUBGRUPO TEXT)")

    result_cultivo2 = repo.get_aprovechamiento_volcado({"cultivo": "NARANJA"}, today=datetime(2026, 6, 18))
    result_cultivo = repo.get_aprovechamiento_volcado({"cultivo": "CITRICOS"}, today=datetime(2026, 6, 18))

    assert result_cultivo2["summary"]["partidas"] == 1
    assert result_cultivo2["grouped_summary"]["principales"] == 1
    assert result_cultivo["summary"] == {}
    assert result_cultivo["grouped_summary"]["principales"] == 0
