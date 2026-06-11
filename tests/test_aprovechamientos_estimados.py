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
