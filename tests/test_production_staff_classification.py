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


def test_staffing_requirements_prefer_staff_area_tipo_personal_over_flow_staffing(monkeypatch):
    import sys
    import types

    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)

    from services.production_capacity_service import ProductionCapacityService

    service = ProductionCapacityService.__new__(ProductionCapacityService)
    result = service.calculate_staffing_requirements(
        {
            "line_rows": [{"Línea productiva": "MALLAS_TRADICIONAL", "Ocupación %": 50}],
            "inputs": {
                "flow_staffing": [
                    {"linea_productiva": "MALLAS_TRADICIONAL", "area_puesto": "Volcado", "tipo_personal": "Directo", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "MALLAS_TRADICIONAL", "area_puesto": "Calidad", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "MALLAS_TRADICIONAL", "area_puesto": "Carretillero", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                ],
                "staff_areas": [
                    {"area": "Volcado", "tipo_personal": "Soporte", "disponible": 5, "activo": 1},
                    {"area": "Calidad", "tipo_personal": "Soporte", "disponible": 2, "activo": 1},
                    {"area": "Carretilleros", "tipo_personal": "Indirecto", "disponible": 2, "activo": 1},
                ],
                "personnel": {"personal_directo": 18, "personal_soporte": 8, "personal_indirecto": 2},
            },
        }
    )

    rows_by_area = {row["Área / puesto"]: row for row in result["rows"]}
    assert rows_by_area["Volcado"]["Tipo personal"] == "Soporte"
    assert rows_by_area["Calidad"]["Tipo personal"] == "Soporte"
    assert rows_by_area["Carretillero"]["Tipo personal"] == "Indirecto"
