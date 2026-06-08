from db.production_settings_repository import ProductionSettingsRepository, infer_default_staff_type, staff_type_flags


def test_staff_type_flags_follow_tipo_personal_only():
    assert staff_type_flags("Soporte") == {"Directo": 0, "Soporte": 1, "Indirecto": 0}
    assert staff_type_flags("Directo") == {"Directo": 1, "Soporte": 0, "Indirecto": 0}
    assert staff_type_flags("Indirecto") == {"Directo": 0, "Soporte": 0, "Indirecto": 1}


def test_default_staff_classification_matches_recommended_areas():
    assert infer_default_staff_type("Volcado") == "Soporte"
    assert infer_default_staff_type("Loteado") == "Directo"
    assert infer_default_staff_type("Carretilleros") == "Indirecto"


def test_staff_summary_totals_use_active_areas_and_tipo_personal():
    repo = ProductionSettingsRepository.__new__(ProductionSettingsRepository)
    totals = repo._calculate_staff_totals(
        [
            {"area": "Soporte incoherente", "tipo_personal": "Soporte", "disponible": 3, "activo": 1, "Directo": 1},
            {"area": "Directo activo", "tipo_personal": "Directo", "disponible": 5, "activo": 1},
            {"area": "Indirecto inactivo", "tipo_personal": "Indirecto", "disponible": 7, "activo": 0},
        ]
    )

    assert totals == {
        "personal_directo": 5,
        "personal_soporte": 3,
        "personal_indirecto": 0,
        "personal_total": 8,
    }
