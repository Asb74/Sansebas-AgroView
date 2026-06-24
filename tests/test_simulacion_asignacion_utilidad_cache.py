from __future__ import annotations

import sys
import types


class _QualityServiceStub:
    def __init__(self) -> None:
        self.ensure_defaults_calls = 0
        self.get_settings_calls = 0
        self.primera_pct = 0.91

    def ensure_defaults(self) -> None:
        self.ensure_defaults_calls += 1

    def get_settings(self) -> list[dict]:
        self.get_settings_calls += 1
        return [
            {
                "Origen": "ALMACEN_COMERCIAL",
                "PrimeraPct": self.primera_pct,
                "SegundaPct": 0.07,
                "DestrioFallbackPct": 0.02,
                "UsarDestrioHistorico": 0,
                "IndustriaRecuperablePct": 0.50,
            },
            {
                "Origen": "DESCONOCIDO",
                "PrimeraPct": 0.80,
                "SegundaPct": 0.20,
                "DestrioFallbackPct": 0.10,
                "UsarDestrioHistorico": 0,
                "IndustriaRecuperablePct": 0.80,
            },
        ]


def test_obtener_config_utilidad_stock_cachea_settings_y_permite_invalidar(monkeypatch):
    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)

    from services import simulacion_asignacion as sim

    quality_service = _QualityServiceStub()
    monkeypatch.setattr(sim, "_quality_service", quality_service)
    sim.invalidar_cache_utilidad_stock()

    primera = sim.obtener_config_utilidad_stock("COMERCIAL")
    segunda = sim.obtener_config_utilidad_stock("ALMACEN_COMERCIAL")
    tercera = sim.obtener_config_utilidad_stock("STOCK_COMERCIAL")

    assert primera["primera_pct"] == 0.91
    assert segunda["primera_pct"] == 0.91
    assert tercera["primera_pct"] == 0.91
    assert quality_service.ensure_defaults_calls == 1
    assert quality_service.get_settings_calls == 1

    quality_service.primera_pct = 0.93
    sim.invalidar_cache_utilidad_stock()
    recargada = sim.obtener_config_utilidad_stock("ALMACEN_COMERCIAL")

    assert recargada["primera_pct"] == 0.93
    assert quality_service.ensure_defaults_calls == 2
    assert quality_service.get_settings_calls == 2

    sim.invalidar_cache_utilidad_stock()
