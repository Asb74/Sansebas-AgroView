from __future__ import annotations

import sys
import types


def _service(monkeypatch):
    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)
    from services.production_capacity_service import ProductionCapacityService

    return ProductionCapacityService.__new__(ProductionCapacityService)


def test_encajado_required_resources_do_not_invent_encajado_or_final_linea(monkeypatch):
    service = _service(monkeypatch)
    rows = service.resolve_required_resources_for_line(
        "ENCAJADO",
        {
            "kg": 1000,
            "tipo_malla": "No aplica",
            "inputs": {
                "line_required_resources": [
                    {"linea_productiva": "ENCAJADO", "recurso_codigo": "CALIBRADOR_PRINCIPAL", "activo": 1, "reparte_kg": 0, "orden": 1}
                ],
                "physical_resources": [
                    {"codigo": "CALIBRADOR_PRINCIPAL", "tipo_recurso": "Calibrador", "capacidad_kg_h": 15000, "numero_unidades": 1, "personal_minimo": 1, "personal_optimo": 2, "activo": 1}
                ],
                "resource_compatibilities": [],
                "resource_availability": [],
                "filters": {},
            },
        },
    )

    resource_codes = {row["codigo"] for row in rows}
    incidence_text = "\n".join(inc["motivo"] for row in rows for inc in row.get("_incidencias", []))
    assert resource_codes == {"CALIBRADOR_PRINCIPAL"}
    assert "ENCAJADO" not in incidence_text
    assert "FINAL_LINEA" not in incidence_text


def test_main_productive_staff_and_families_come_from_masters(monkeypatch):
    service = _service(monkeypatch)
    inputs = {
        "line_capacity_config": [{"linea_productiva": "ENCAJADO", "puesto_productivo_principal": "Mesas encajado", "activa": 1}],
        "flow_staffing": [
            {"linea_productiva": "ENCAJADO", "area_puesto": "Encajado", "minimo": 1, "optimo": 2, "activo": 1},
            {"linea_productiva": "ENCAJADO", "area_puesto": "Mesas encajado", "minimo": 3, "optimo": 4, "activo": 1},
        ],
        "productive_families": [{"codigo": "Familia custom", "orden": 1, "activa": 1}],
        "semaphore_rules": [],
        "general_settings": {"horas_utiles_dia": 8, "numero_turnos": 1},
        "lines": [{"codigo": "ENCAJADO", "activa": 1, "numero_maquinas": 1, "capacidad_kg_h_referencia": 100, "personal_minimo": 1, "personal_optimo": 1}],
    }

    assert service._main_productive_staffing_for_line("ENCAJADO", inputs)["area_puesto"] == "Mesas encajado"
    rows = service.calculate_family_capacity(
        [{"familia": "Familia custom", "kg": 100, "horas": 1, "rendimiento": 100, "linea": "ENCAJADO", "tipo_pedido": "Real", "pedido": {}}],
        inputs,
    )
    assert [row["Familia"] for row in rows] == ["Familia custom"]


def test_staff_equivalence_tria_comes_from_master(monkeypatch):
    service = _service(monkeypatch)
    inputs = {
        "staff_area_equivalences": [
            {"area_requerida": "Tría", "area_personal": "Tría principal", "prioridad": 1, "activa": 1},
            {"area_requerida": "Tría", "area_personal": "Tría mallas", "prioridad": 2, "activa": 1},
        ]
    }
    service._current_capacity_inputs = inputs
    available, match, matched = service._available_staff_for_area(
        "Tría",
        {"tria principal": 3, "tria mallas": 2},
        {"tria principal": "Tría principal", "tria mallas": "Tría mallas"},
    )

    assert available == 5
    assert match == "equivalence"
    assert matched == "Tría principal + Tría mallas"
