from __future__ import annotations

import sys
import types


def _service(monkeypatch):
    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)
    from services.production_capacity_service import ProductionCapacityService

    return ProductionCapacityService.__new__(ProductionCapacityService)


def _capacity_result(staffing_rows):
    return {
        "line_rows": [{"Línea productiva": "ENCAJADO", "Kg": 10000, "Horas necesarias": 10}],
        "mapped": [
            {
                "linea": "ENCAJADO",
                "kg": 10000,
                "rendimiento_base_kg_h_persona": 250,
                "personas_productivas_principales_optimo": 4,
                "puesto_productivo_principal": "Tría",
            }
        ],
        "staffing_rows": staffing_rows,
    }


def _staff(area, minimo, optimo, base, polivalente=0, tipo="Directo"):
    return {
        "Línea productiva": "ENCAJADO",
        "Área / puesto": area,
        "Tipo personal": tipo,
        "Mínimo": minimo,
        "Óptimo": optimo,
        "Disponible base": base,
        "Polivalente": polivalente,
        "Disponible efectivo": base + polivalente,
    }


def test_bottleneck_is_lowest_available_over_optimum(monkeypatch):
    service = _service(monkeypatch)

    rows = service.calculate_bottlenecks(
        _capacity_result(
            [
                _staff("Tría", 2, 4, 3),
                _staff("Encajado", 6, 12, 8),
                _staff("Loteado / paletizado", 1, 2, 1),
                _staff("Carretillero", 1, 1, 1),
            ]
        )
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["Puesto limitante"] == "Loteado / paletizado"
    assert row["Factor capacidad %"] == 50
    assert row["Kg alcanzables estimados"] == 5000
    assert row["Kg no cubiertos estimados"] == 5000
    assert row["Estado"] == "Amarillo"
    assert row["Acción sugerida"] == "Reforzar puesto para alcanzar rendimiento óptimo"


def test_bottleneck_red_when_effective_below_minimum(monkeypatch):
    service = _service(monkeypatch)

    row = service.calculate_bottlenecks(_capacity_result([_staff("Loteado / paletizado", 1, 2, 0)]))[0]

    assert row["Estado"] == "Rojo"
    assert row["Acción sugerida"] == "Cubrir dotación mínima antes de lanzar el flujo"


def test_bottleneck_yellow_when_effective_between_minimum_and_optimum(monkeypatch):
    service = _service(monkeypatch)

    row = service.calculate_bottlenecks(_capacity_result([_staff("Encajado", 6, 12, 8)]))[0]

    assert row["Estado"] == "Amarillo"


def test_bottleneck_green_when_effective_reaches_optimum(monkeypatch):
    service = _service(monkeypatch)

    row = service.calculate_bottlenecks(_capacity_result([_staff("Carretillero", 1, 1, 1)]))[0]

    assert row["Estado"] == "Verde"
    assert row["Acción sugerida"] == "Sin acción requerida"


def test_bottleneck_uses_effective_availability_with_polyvalence(monkeypatch):
    service = _service(monkeypatch)

    row = service.calculate_bottlenecks(_capacity_result([_staff("Encajado", 6, 12, 6, polivalente=2)]))[0]

    assert row["Disponible efectivo"] == 8
    assert row["Factor capacidad %"] == 66.67
    assert row["Kg alcanzables estimados"] == 6666.67


def test_bottleneck_calculates_reachable_kg_from_line_kg_and_factor(monkeypatch):
    service = _service(monkeypatch)

    row = service.calculate_bottlenecks(_capacity_result([_staff("Tría", 2, 4, 3)]))[0]

    assert row["Factor capacidad %"] == 75
    assert row["Kg alcanzables estimados"] == 7500
    assert row["Kg no cubiertos estimados"] == 2500


def test_bottleneck_ignores_zero_optimum(monkeypatch):
    service = _service(monkeypatch)

    rows = service.calculate_bottlenecks(_capacity_result([_staff("Etiquetado", 0, 0, 0)]))

    assert rows == []
