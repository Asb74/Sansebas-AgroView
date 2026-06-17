import sqlite3

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
                AlbaranDef TEXT, AlbaranD TEXT, Boleta TEXT, Socio TEXT,
                NombreSocio TEXT, Fcarga TEXT, Apodo TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO PesosFres VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("P1", "NO_USAR", "2052", "1234", "CANO MANZANARES, LUIS", "2026-06-13", "24"),
                ("A1", "NO_USAR", "2053", "1235", "AGRICULTOR A", "13/06/2026", "24"),
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
