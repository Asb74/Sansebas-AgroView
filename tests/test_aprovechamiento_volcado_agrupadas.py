import sqlite3

from db.planning_repository import PlanningRepository


def test_partidas_agrupadas_volcado_usa_partidas_solo_como_trazabilidad(tmp_path):
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

        rows, summary = repo._get_partidas_agrupadas_volcado(conn, ["P1", "P2"], {"P2": 500})

    assert rows == [
        {"Partida principal": "P1", "Partida incluida": "P1", "Kg asociado": 1000.0, "Tipo": "Principal"},
        {"Partida principal": "P1", "Partida incluida": "A1", "Kg asociado": 900.0, "Tipo": "Agrupada"},
        {"Partida principal": "P1", "Partida incluida": "A2", "Kg asociado": 1100.0, "Tipo": "Agrupada"},
        {"Partida principal": "P2", "Partida incluida": "P2", "Kg asociado": 500.0, "Tipo": "Principal sin agrupación"},
    ]
    assert summary == {"principales": 2, "incluidas": 4, "adicionales": 2, "kg_total": 3000.0}
