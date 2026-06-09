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
            "line_rows": [{"Línea productiva": "ENCAJADO", "Ocupación %": 50}],
            "inputs": {
                "flow_staffing": [
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Volcado", "tipo_personal": "Directo", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Calibrador", "tipo_personal": "Directo", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Tría", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Encajado", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Loteado / paletizado", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Carretillero", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Calidad", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Encargado", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                ],
                "staff_areas": [
                    {"area": "Volcado", "tipo_personal": "Soporte", "disponible": 5, "activo": 1},
                    {"area": "Calibradores", "tipo_personal": "Soporte", "disponible": 2, "activo": 1},
                    {"area": "Tría", "tipo_personal": "Directo", "disponible": 4, "activo": 1},
                    {"area": "Encajado", "tipo_personal": "Directo", "disponible": 12, "activo": 1},
                    {"area": "Loteado", "tipo_personal": "Directo", "disponible": 2, "activo": 1},
                    {"area": "Carretilleros", "tipo_personal": "Indirecto", "disponible": 2, "activo": 1},
                    {"area": "Calidad", "tipo_personal": "Soporte", "disponible": 2, "activo": 1},
                    {"area": "Encargados", "tipo_personal": "Indirecto", "disponible": 2, "activo": 1},
                ],
                "personnel": {"personal_directo": 18, "personal_soporte": 8, "personal_indirecto": 2},
            },
        }
    )

    rows_by_area = {row["Área / puesto"]: row for row in result["rows"]}
    assert rows_by_area["Volcado"]["Tipo personal"] == "Soporte"
    assert rows_by_area["Calibrador"]["Tipo personal"] == "Soporte"
    assert rows_by_area["Tría"]["Tipo personal"] == "Directo"
    assert rows_by_area["Encajado"]["Tipo personal"] == "Directo"
    assert rows_by_area["Loteado / paletizado"]["Tipo personal"] == "Directo"
    assert rows_by_area["Carretillero"]["Tipo personal"] == "Indirecto"
    assert rows_by_area["Calidad"]["Tipo personal"] == "Soporte"
    assert rows_by_area["Encargado"]["Tipo personal"] == "Indirecto"


def test_staffing_requirements_do_not_scale_people_by_occupancy(monkeypatch):
    import sys
    import types

    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)

    from services.production_capacity_service import ProductionCapacityService

    service = ProductionCapacityService.__new__(ProductionCapacityService)
    result = service.calculate_staffing_requirements(
        {
            "line_rows": [{"Línea productiva": "ENCAJADO", "Ocupación %": 571.43}],
            "inputs": {
                "flow_staffing": [
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Encajado", "tipo_personal": "Directo", "minimo": 6, "optimo": 12, "activo": 1, "escala_con_ocupacion": 1, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Tría", "tipo_personal": "Directo", "minimo": 2, "optimo": 4, "activo": 1, "escala_con_ocupacion": 1, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Loteado", "tipo_personal": "Directo", "minimo": 1, "optimo": 2, "activo": 1, "escala_con_ocupacion": 1, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Encargado", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
                ],
                "staff_areas": [],
                "personnel": {"personal_directo": 0, "personal_soporte": 0, "personal_indirecto": 0},
            },
        }
    )

    rows_by_area = {row["Área / puesto"]: row for row in result["rows"]}
    assert rows_by_area["Encajado"]["Necesario estimado"] == 12
    assert rows_by_area["Tría"]["Necesario estimado"] == 4
    assert rows_by_area["Loteado"]["Necesario estimado"] == 2
    assert rows_by_area["Encargado"]["Necesario estimado"] == 1
    assert result["summary"]["personal_necesario_estimado"] == 19


def test_family_personnel_estimate_uses_staffing_requirements_instead_of_hour_scaling(monkeypatch, caplog):
    import logging
    import sys
    import types

    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)

    from services.production_capacity_service import ProductionCapacityService

    service = ProductionCapacityService.__new__(ProductionCapacityService)
    mapped = [
        {
            "tipo_pedido": "Real",
            "pedido": {"IdConfeccion": "E1"},
            "kg": 7000,
            "familia": "Encajado",
            "linea": "ENCAJADO",
            "rendimiento": 100,
            "horas": 70,
        }
    ]
    inputs = {
        "lines": [
            {
                "codigo": "ENCAJADO",
                "activa": 1,
                "numero_maquinas": 1,
                "personal_minimo": 6,
                "personal_optimo": 12,
            }
        ],
        "general_settings": {"horas_utiles_dia": 7.5, "numero_turnos": 1},
        "semaphore_rules": [],
    }
    staffing_rows = [
        {"Línea productiva": "ENCAJADO", "Área / puesto": "Encajado", "Necesario estimado": 12},
        {"Línea productiva": "ENCAJADO", "Área / puesto": "Tría", "Necesario estimado": 4},
        {"Línea productiva": "ENCAJADO", "Área / puesto": "Loteado", "Necesario estimado": 2},
        {"Línea productiva": "ENCAJADO", "Área / puesto": "Encargado", "Necesario estimado": 1},
    ]

    with caplog.at_level(logging.INFO, logger="services.production_capacity_service"):
        result = service.calculate_family_capacity(mapped, inputs, staffing_rows)

    rows_by_family = {row["Familia"]: row for row in result}
    assert rows_by_family["Encajado"]["Personal estimado"] == 19
    assert rows_by_family["Encajado"]["Personal estimado"] != 112
    assert "CAPACIDAD FAMILIA" in caplog.text
    assert "familia=Encajado" in caplog.text
    assert "personal_estimado_familia=112" in caplog.text
    assert "personal_estimado_staffing=19" in caplog.text


def test_encajado_capacity_uses_real_available_main_productive_people(monkeypatch):
    import sys
    import types

    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)

    from services.production_capacity_service import ProductionCapacityService

    service = ProductionCapacityService.__new__(ProductionCapacityService)
    flow_staffing = [
        {"linea_productiva": "ENCAJADO", "area_puesto": "Volcado", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
        {"linea_productiva": "ENCAJADO", "area_puesto": "Calibrador", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
        {"linea_productiva": "ENCAJADO", "area_puesto": "Tría", "tipo_personal": "Directo", "minimo": 2, "optimo": 4, "activo": 1, "escala_con_ocupacion": 1, "factor_ocupacion": 1, "obligatorio": 1},
        {"linea_productiva": "ENCAJADO", "area_puesto": "Encajado", "tipo_personal": "Directo", "minimo": 6, "optimo": 12, "activo": 1, "escala_con_ocupacion": 1, "factor_ocupacion": 1, "obligatorio": 1},
        {"linea_productiva": "ENCAJADO", "area_puesto": "Loteado / paletizado", "tipo_personal": "Directo", "minimo": 1, "optimo": 2, "activo": 1, "escala_con_ocupacion": 1, "factor_ocupacion": 1, "obligatorio": 1},
        {"linea_productiva": "ENCAJADO", "area_puesto": "Carretillero", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
        {"linea_productiva": "ENCAJADO", "area_puesto": "Calidad", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
        {"linea_productiva": "ENCAJADO", "area_puesto": "Encargado", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "escala_con_ocupacion": 0, "factor_ocupacion": 1, "obligatorio": 1},
    ]
    inputs = {
        "packaging_mapping": [
            {"codigo_mconfeccion": "ENCAJADO_10KG", "familia_productiva": "Encajado", "linea_productiva": "ENCAJADO", "tipo_malla": "No aplica", "subtipo_productivo": "Caja cartón"}
        ],
        "base_packaging": [],
        "caliber_factors": [],
        "lines": [
            {"codigo": "ENCAJADO", "activa": 1, "numero_maquinas": 1, "capacidad_kg_h_referencia": 250, "personal_minimo": 1, "personal_optimo": 23}
        ],
        "flow_staffing": flow_staffing,
        "staff_areas": [
            {"area": "Volcado", "tipo_personal": "Soporte", "disponible": 1, "activo": 1},
            {"area": "Calibrador", "tipo_personal": "Soporte", "disponible": 1, "activo": 1},
            {"area": "Tría", "tipo_personal": "Directo", "disponible": 2, "activo": 1},
            {"area": "Encajado", "tipo_personal": "Directo", "disponible": 8, "activo": 1},
            {"area": "Loteado / paletizado", "tipo_personal": "Directo", "disponible": 2, "activo": 1},
            {"area": "Carretillero", "tipo_personal": "Indirecto", "disponible": 1, "activo": 1},
            {"area": "Calidad", "tipo_personal": "Soporte", "disponible": 1, "activo": 1},
            {"area": "Encargado", "tipo_personal": "Indirecto", "disponible": 1, "activo": 1},
        ],
        "personnel": {"personal_total": 23, "personal_directo": 18, "personal_soporte": 3, "personal_indirecto": 2},
        "general_settings": {"horas_utiles_dia": 7, "numero_turnos": 1},
        "semaphore_rules": [],
    }

    mapped, incidencias = service.map_orders_to_productive_config(
        [{"IdPedidoLora": "P1", "IdConfeccion": "ENCAJADO_10KG", "Kg pendiente": 10000, "Calibre": "4"}],
        [],
        inputs,
    )
    line_rows = service.calculate_line_capacity(mapped, inputs)
    staffing = service.calculate_staffing_requirements({"line_rows": line_rows, "inputs": inputs})
    family_rows = service.calculate_family_capacity(mapped, inputs, staffing["rows"])
    summary = service.calculate_capacity_summary(mapped, family_rows, line_rows, inputs)

    assert incidencias == []
    assert len(mapped) == 1
    assert mapped[0]["rendimiento_base_kg_h_persona"] == 250
    assert mapped[0]["personas_productivas_principales"] == 8
    assert mapped[0]["personas_productivas_principales_optimo"] == 12
    assert mapped[0]["capacidad_real_kg_h"] == 2000
    assert round(mapped[0]["horas"], 2) == 5.00

    assert line_rows[0]["Horas necesarias"] == 5.00
    assert line_rows[0]["Horas disponibles línea"] == 7
    assert line_rows[0]["Ocupación %"] == 71.43
    assert line_rows[0]["Rendimiento base kg/h/persona"] == 250
    assert line_rows[0]["Personas productivas principales"] == 8
    assert line_rows[0]["Capacidad real kg/h"] == 2000

    rows_by_family = {row["Familia"]: row for row in family_rows}
    assert rows_by_family["Encajado"]["Horas necesarias"] == 5.00
    assert rows_by_family["Encajado"]["Ocupación %"] == 71.43
    assert rows_by_family["Encajado"]["Personal estimado"] == 23

    staffing_by_area = {row["Área / puesto"]: row for row in staffing["rows"]}
    assert staffing_by_area["Encajado"]["Necesario estimado"] == 12
    assert staffing_by_area["Encajado"]["Disponible"] == 8
    assert staffing_by_area["Encajado"]["Diferencia"] == -4
    assert staffing_by_area["Tría"]["Disponible"] == 2
    assert summary["turnos_equivalentes"] == 0.71
    assert summary["Ocupación %"] == 71.43
    assert summary["Horas necesarias estimadas"] != 40


def test_staffing_requirements_do_not_fallback_available_by_tipo_personal(monkeypatch):
    import sys
    import types

    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)

    from services.production_capacity_service import ProductionCapacityService

    service = ProductionCapacityService.__new__(ProductionCapacityService)
    result = service.calculate_staffing_requirements(
        {
            "line_rows": [{"Línea productiva": "ENCAJADO", "Ocupación %": 71.43}],
            "inputs": {
                "flow_staffing": [
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Tría", "tipo_personal": "Directo", "minimo": 2, "optimo": 4, "activo": 1, "escala_con_ocupacion": 1, "factor_ocupacion": 1, "obligatorio": 1},
                    {"linea_productiva": "ENCAJADO", "area_puesto": "Encajado", "tipo_personal": "Directo", "minimo": 6, "optimo": 12, "activo": 1, "escala_con_ocupacion": 1, "factor_ocupacion": 1, "obligatorio": 1},
                ],
                "staff_areas": [
                    {"area": "Encajado", "tipo_personal": "Directo", "disponible": 8, "activo": 1},
                    {"area": "Otra área directa", "tipo_personal": "Directo", "disponible": 18, "activo": 1},
                ],
                "personnel": {"personal_directo": 18, "personal_soporte": 0, "personal_indirecto": 0},
            },
        }
    )

    rows_by_area = {row["Área / puesto"]: row for row in result["rows"]}
    assert rows_by_area["Encajado"]["Disponible"] == 8
    assert rows_by_area["Tría"]["Disponible"] == 0
    assert rows_by_area["Tría"]["Disponible"] != 18
    assert any(inc["Tipo incidencia"] == "Área sin personal configurado" and inc["Confección"] == "Tría" for inc in result["incidencias"])
