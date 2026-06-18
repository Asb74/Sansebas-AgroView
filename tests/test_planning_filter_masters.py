from pathlib import Path
import sqlite3

from db.planning_repository import PlanningRepository
from config import DB_EEPPL


def _repo_with_dbeepl(tmp_path: Path) -> PlanningRepository:
    path = tmp_path / DB_EEPPL
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE "CAMPAÑA" ("CAMPAÑA" TEXT, "CULTIVO" TEXT)')
        conn.executemany(
            'INSERT INTO "CAMPAÑA" VALUES (?, ?)',
            [("2026", "CITRICOS"), ("2026", "SANDIA"), ("2025", "CITRICOS"), (None, "VACIO"), ("2024", None)],
        )
        conn.execute('CREATE TABLE "Empresa" ("IdEmpresa" INTEGER, "Nombre" TEXT, "EXTENSO" TEXT)')
        conn.executemany(
            'INSERT INTO "Empresa" VALUES (?, ?, ?)',
            [(1, "San Sebastian S.C.A", "EXT 1"), (2, "", "Empresa extensa"), (3, None, None)],
        )
        conn.execute('CREATE TABLE "MVariedad" ("CULTIVO" TEXT, "Variedad" TEXT, "GRUPO" TEXT, "SUBGRUPO" TEXT)')
        conn.executemany(
            'INSERT INTO "MVariedad" VALUES (?, ?, ?, ?)',
            [("CITRICOS", "NAVEL", "NARANJA", "TEMPRANA"), ("SANDIA", "RAYADA", "SANDIA", "SIN PEPITA")],
        )
    return PlanningRepository(base_dir=tmp_path)


def test_planning_master_filters_load_from_dbeepl_campaign_crop_and_company(tmp_path):
    repo = _repo_with_dbeepl(tmp_path)

    masters = repo.load_master_filter_options()

    assert masters["campanas"] == ["2026", "2025"]
    assert masters["cultivos_por_campana"]["2026"] == ["CITRICOS", "SANDIA"]
    assert masters["cultivos_por_campana"]["__ALL__"] == ["CITRICOS", "SANDIA"]
    assert masters["empresas"] == ["San Sebastian S.C.A", "Empresa extensa", "3"]
    assert masters["grupos_por_cultivo"]["__ALL__"] == ["NARANJA", "SANDIA"]
    assert masters["grupos_por_cultivo"]["CITRICOS"] == ["NARANJA"]
    assert masters["variedades"] == [
        {"cultivo": "CITRICOS", "grupo": "NARANJA", "variedad": "NAVEL"},
        {"cultivo": "SANDIA", "grupo": "SANDIA", "variedad": "RAYADA"},
    ]
    assert repo.empresa_display_to_id("San Sebastian S.C.A") == "1"
    assert repo.empresa_id_to_display("1") == "San Sebastian S.C.A"


def test_planning_filter_options_ignore_own_filter_and_apply_related_campaign_crop(tmp_path):
    repo = _repo_with_dbeepl(tmp_path)

    assert repo.get_planning_filter_options("cultivo", {"campana": ["2026"], "cultivo": ["CITRICOS"]}) == ["CITRICOS", "SANDIA"]
    assert repo.get_planning_filter_options("cultivo", {"campana": [], "cultivo": ["CITRICOS"]}) == ["CITRICOS", "SANDIA"]
    assert repo.get_planning_filter_options("campana", {"campana": ["2026"], "cultivo": ["CITRICOS"]}) == ["2026", "2025"]
    assert repo.get_planning_filter_options("empresa", {"empresa": ["1"]}) == ["San Sebastian S.C.A", "Empresa extensa", "3"]
