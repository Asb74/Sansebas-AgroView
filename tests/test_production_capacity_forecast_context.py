import sys
import types


def _production_capacity_service(monkeypatch):
    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)

    import services.production_capacity_service as module

    return module, module.ProductionCapacityService.__new__(module.ProductionCapacityService)


def test_load_forecast_orders_passes_single_required_context(monkeypatch):
    module, service = _production_capacity_service(monkeypatch)
    captured = {}

    def fake_loader(filters, *, respetar_incluir, cultivo_actual, campana_actual, empresa_actual):
        captured.update(
            filters=filters,
            respetar_incluir=respetar_incluir,
            cultivo_actual=cultivo_actual,
            campana_actual=campana_actual,
            empresa_actual=empresa_actual,
        )
        return [{"id_previsto": "PV-1"}]

    monkeypatch.setattr(module, "cargar_pedidos_previstos_filtrados", fake_loader)
    filters = {"campana": ["2026"], "cultivo": ["CITRICOS"], "empresa": [""]}

    assert service._load_forecast_orders(filters) == [{"id_previsto": "PV-1"}]
    assert captured == {
        "filters": filters,
        "respetar_incluir": True,
        "cultivo_actual": "CITRICOS",
        "campana_actual": "2026",
        "empresa_actual": "",
    }


def test_load_forecast_orders_does_not_inherit_context_for_multiple_or_todos(monkeypatch):
    module, service = _production_capacity_service(monkeypatch)
    captured = {}

    def fake_loader(filters, *, respetar_incluir, cultivo_actual, campana_actual, empresa_actual):
        captured.update(
            cultivo_actual=cultivo_actual,
            campana_actual=campana_actual,
            empresa_actual=empresa_actual,
        )
        return []

    monkeypatch.setattr(module, "cargar_pedidos_previstos_filtrados", fake_loader)

    service._load_forecast_orders(
        {"campana": ["2025", "2026"], "cultivo": ["TODOS"], "empresa": ["SANSEBAS", "OTRA"]}
    )

    assert captured == {
        "cultivo_actual": "",
        "campana_actual": "",
        "empresa_actual": "",
    }
