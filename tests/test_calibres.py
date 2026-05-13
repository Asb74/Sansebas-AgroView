from db.planning_repository import PlanningRepository, canonical_get


def test_normalizar_calibre_a_set():
    assert PlanningRepository.normalizar_calibre_a_set("7/8") == {"7", "8"}
    assert PlanningRepository.normalizar_calibre_a_set("CAL 8") == {"8"}
    assert PlanningRepository.normalizar_calibre_a_set("0/1/2/3") == {"0", "1", "2", "3"}
    assert PlanningRepository.normalizar_calibre_a_set("1/36 pz") == {"1"}
    assert PlanningRepository.normalizar_calibre_a_set("1/36") == {"1"}
    assert PlanningRepository.normalizar_calibre_a_set("1/20 pz") == {"1"}
    assert PlanningRepository.normalizar_calibre_a_set("1/22 pz") == {"1"}
    assert PlanningRepository.normalizar_calibre_a_set("1/2") == {"1", "2"}


def test_comparar_calibres_para_cobertura():
    repo = PlanningRepository()
    r = repo.comparar_calibres_para_cobertura("7/8", "CAL 8")
    assert r["tipo"] == "CALIBRE_ADMITIDO" and r["coincidentes"] == ["8"]
    r = repo.comparar_calibres_para_cobertura("7/8", "CAL 6/7")
    assert r["tipo"] == "SOLAPE_PARCIAL" and r["coincidentes"] == ["7"]
    r = repo.comparar_calibres_para_cobertura("CAL 1/2", "0/1/2/3")
    assert r["tipo"] == "AGRUPADA" and r["coincidentes"] == ["1", "2"]
    r = repo.comparar_calibres_para_cobertura("CAL 1/2", "CAL 3")
    assert r["tipo"] == "SIN_COBERTURA"
    r = repo.comparar_calibres_para_cobertura("1/2", "1/20 pz")
    assert r["tipo"] == "CALIBRE_ADMITIDO" and r["coincidentes"] == ["1"]
    r = repo.comparar_calibres_para_cobertura("1/2", "1/22 pz")
    assert r["tipo"] == "CALIBRE_ADMITIDO" and r["coincidentes"] == ["1"]


def test_canonical_get():
    assert canonical_get({"Campaña": 2026}, "campana") == "2026"
    assert canonical_get({"Campana": "2026"}, "campana") == "2026"
    assert canonical_get({"Categoría": "I"}, "categoria") == "I"


def test_normalizar_calibre_compuesto_con_rangos():
    assert PlanningRepository.normalizar_calibre_a_set("3/4-4/5") == {"3", "4", "5"}
    assert PlanningRepository.normalizar_calibre_a_set("1/2-2/3") == {"1", "2", "3"}
    assert PlanningRepository.normalizar_calibre_a_set("CAL 3/4-4/5") == {"3", "4", "5"}
