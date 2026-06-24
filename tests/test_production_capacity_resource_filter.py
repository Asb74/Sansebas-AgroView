from __future__ import annotations

import sys
import types


def _service(monkeypatch):
    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)
    from services.production_capacity_service import ProductionCapacityService

    return ProductionCapacityService.__new__(ProductionCapacityService)


def _base_inputs():
    return {
        "filters": {"cultivo": ["CROP_X"]},
        "cultivo_actual": "CROP_X",
        "lines": [{"codigo": "LINE_A", "activa": 1}, {"codigo": "LINE_B", "activa": 1}],
        "packaging_mapping": [
            {"codigo_mconfeccion": "1", "linea_productiva": "LINE_A", "cultivo": "CROP_X"},
            {"codigo_mconfeccion": "2", "linea_productiva": "LINE_B", "cultivo": "OTHER_CROP"},
        ],
        "base_packaging": [],
        "line_required_resources": [
            {"linea_productiva": "LINE_A", "recurso_codigo": "RES_OK", "activo": 1},
            {"linea_productiva": "LINE_B", "recurso_codigo": "RES_OTHER", "activo": 1},
        ],
        "resource_compatibilities": [],
        "resource_availability": [],
    }


def test_resource_is_compatible_with_current_crop_uses_flow_masters(monkeypatch):
    service = _service(monkeypatch)
    inputs = _base_inputs()

    assert service.resource_is_compatible_with_current_crop({"codigo": "RES_OK", "activo": 1}, inputs)
    assert not service.resource_is_compatible_with_current_crop({"codigo": "RES_OTHER", "activo": 1}, inputs)


def test_resource_filter_honors_operational_availability(monkeypatch):
    service = _service(monkeypatch)
    inputs = _base_inputs()
    inputs["resource_availability"] = [{"recurso_codigo": "RES_OK", "contexto": "CROP_X", "disponible": 0, "motivo": "Parado"}]

    assert not service.resource_is_compatible_with_current_crop({"codigo": "RES_OK", "activo": 1}, inputs)
