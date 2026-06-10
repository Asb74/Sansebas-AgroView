from __future__ import annotations

import sys
import types


def _service(monkeypatch):
    planning_service = types.ModuleType("services.planning_service")
    planning_service.PlanningService = object
    monkeypatch.setitem(sys.modules, "services.planning_service", planning_service)
    from services.production_capacity_service import ProductionCapacityService

    return ProductionCapacityService.__new__(ProductionCapacityService)


def _staffing(monkeypatch, flow_staffing, staff_areas, staff_polyvalence=None, staff_area_equivalences=None):
    service = _service(monkeypatch)
    return service.calculate_staffing_requirements(
        {
            "line_rows": [{"Línea productiva": "ENCAJADO", "Ocupación %": 10}],
            "inputs": {
                "flow_staffing": flow_staffing,
                "staff_areas": staff_areas,
                "staff_polyvalence": staff_polyvalence or [],
                "staff_area_equivalences": staff_area_equivalences or [],
                "production_staff_area_equivalences": staff_area_equivalences or [],
            },
        }
    )


def test_staff_polyvalence_is_not_used_without_deficit(monkeypatch):
    result = _staffing(
        monkeypatch,
        [
            {"linea_productiva": "ENCAJADO", "area_puesto": "Carretillero", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
            {"linea_productiva": "ENCAJADO", "area_puesto": "Encargado", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
        ],
        [
            {"area": "Carretillero", "tipo_personal": "Indirecto", "disponible": 1, "activo": 1},
            {"area": "Encargado", "tipo_personal": "Indirecto", "disponible": 3, "activo": 1},
        ],
        [{"puesto_origen": "Encargado", "puesto_destino": "Carretillero", "prioridad": 1, "factor_productividad": 100, "activa": 1}],
    )

    row = {r["Área / puesto"]: r for r in result["rows"]}["Carretillero"]
    assert row["Disponible base"] == 1
    assert row["Polivalente"] == 0
    assert row["Disponible efectivo"] == 1
    assert row["Estado"] == "Verde"
    assert not any(inc["Tipo incidencia"] == "Déficit cubierto por polivalencia" for inc in result["incidencias"])


def test_staff_polyvalence_covers_required_forklift_from_manager_surplus(monkeypatch):
    result = _staffing(
        monkeypatch,
        [
            {"linea_productiva": "ENCAJADO", "area_puesto": "Carretillero", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
            {"linea_productiva": "ENCAJADO", "area_puesto": "Encargado", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
        ],
        [
            {"area": "Carretillero", "tipo_personal": "Indirecto", "disponible": 0, "activo": 1},
            {"area": "Encargado", "tipo_personal": "Indirecto", "disponible": 3, "activo": 1},
        ],
        [{"puesto_origen": "Encargado", "puesto_destino": "Carretillero", "prioridad": 1, "factor_productividad": 100, "activa": 1}],
    )

    row = {r["Área / puesto"]: r for r in result["rows"]}["Carretillero"]
    assert row["Disponible base"] == 0
    assert row["Polivalente"] == 1
    assert row["Disponible efectivo"] == 1
    assert row["Estado"] == "Verde"
    assert not any(inc["Tipo incidencia"] in {"Falta personal mínimo", "Dotación obligatoria no cubierta"} and inc["Confección"] == "Carretillero" for inc in result["incidencias"])
    assert any(inc["Tipo incidencia"] == "Déficit cubierto por polivalencia" and inc["Confección"] == "Carretillero" for inc in result["incidencias"])


def test_staff_polyvalence_does_not_consume_origin_below_minimum(monkeypatch):
    result = _staffing(
        monkeypatch,
        [
            {"linea_productiva": "ENCAJADO", "area_puesto": "Carretillero", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
            {"linea_productiva": "ENCAJADO", "area_puesto": "Encargado", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
        ],
        [
            {"area": "Carretillero", "tipo_personal": "Indirecto", "disponible": 0, "activo": 1},
            {"area": "Encargado", "tipo_personal": "Indirecto", "disponible": 1, "activo": 1},
        ],
        [{"puesto_origen": "Encargado", "puesto_destino": "Carretillero", "prioridad": 1, "factor_productividad": 100, "activa": 1}],
    )

    row = {r["Área / puesto"]: r for r in result["rows"]}["Carretillero"]
    assert row["Polivalente"] == 0
    assert row["Disponible efectivo"] == 0
    assert row["Estado"] == "Rojo"
    assert any(inc["Tipo incidencia"] == "Falta personal mínimo" and inc["Confección"] == "Carretillero" for inc in result["incidencias"])


def test_staff_polyvalence_does_not_duplicate_origin_consumption(monkeypatch):
    result = _staffing(
        monkeypatch,
        [
            {"linea_productiva": "ENCAJADO", "area_puesto": "Carretillero", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
            {"linea_productiva": "ENCAJADO", "area_puesto": "Volcador", "tipo_personal": "Soporte", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
            {"linea_productiva": "ENCAJADO", "area_puesto": "Encargado", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
        ],
        [
            {"area": "Carretillero", "tipo_personal": "Indirecto", "disponible": 0, "activo": 1},
            {"area": "Volcador", "tipo_personal": "Soporte", "disponible": 0, "activo": 1},
            {"area": "Encargado", "tipo_personal": "Indirecto", "disponible": 2, "activo": 1},
        ],
        [
            {"puesto_origen": "Encargado", "puesto_destino": "Carretillero", "prioridad": 1, "factor_productividad": 100, "activa": 1},
            {"puesto_origen": "Encargado", "puesto_destino": "Volcador", "prioridad": 1, "factor_productividad": 100, "activa": 1},
        ],
    )

    rows = {r["Área / puesto"]: r for r in result["rows"]}
    assert rows["Carretillero"]["Disponible efectivo"] == 1
    assert rows["Volcador"]["Disponible efectivo"] == 0
    assert rows["Volcador"]["Estado"] == "Rojo"


def test_staff_polyvalence_productivity_factor_is_conservative_for_minimum(monkeypatch):
    result = _staffing(
        monkeypatch,
        [
            {"linea_productiva": "ENCAJADO", "area_puesto": "Loteado", "tipo_personal": "Directo", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
            {"linea_productiva": "ENCAJADO", "area_puesto": "Etiquetado", "tipo_personal": "Directo", "minimo": 0, "optimo": 0, "activo": 1, "obligatorio": 0},
        ],
        [
            {"area": "Loteado", "tipo_personal": "Directo", "disponible": 0, "activo": 1},
            {"area": "Etiquetado", "tipo_personal": "Directo", "disponible": 1, "activo": 1},
        ],
        [{"puesto_origen": "Etiquetado", "puesto_destino": "Loteado", "prioridad": 1, "factor_productividad": 0.8, "activa": 1}],
    )

    row = {r["Área / puesto"]: r for r in result["rows"]}["Loteado"]
    assert row["Polivalente"] == 0.8
    assert row["Disponible efectivo"] == 0.8
    assert row["Estado"] == "Rojo"
    assert any(inc["Tipo incidencia"] == "Falta personal mínimo" and inc["Confección"] == "Loteado" for inc in result["incidencias"])


def test_staff_polyvalence_resolves_source_and_target_equivalences(monkeypatch):
    result = _staffing(
        monkeypatch,
        [
            {"linea_productiva": "ENCAJADO", "area_puesto": "Carretillero", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
            {"linea_productiva": "ENCAJADO", "area_puesto": "Encargado", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
        ],
        [
            {"area": "Carretilleros", "tipo_personal": "Indirecto", "disponible": 0, "activo": 1},
            {"area": "Encargados", "tipo_personal": "Indirecto", "disponible": 3, "activo": 1},
        ],
        [{"puesto_origen": "Encargado", "puesto_destino": "Carretillero", "prioridad": 1, "factor_productividad": 80, "activa": 1}],
        [
            {"area_requerida": "Encargado", "area_personal": "Encargados", "prioridad": 1, "activa": 1},
            {"area_requerida": "Carretillero", "area_personal": "Carretilleros", "prioridad": 1, "activa": 1},
        ],
    )

    rows = {r["Área / puesto"]: r for r in result["rows"]}
    assert rows["Encargado"]["Disponible base"] == 3
    assert rows["Carretillero"]["Disponible base"] == 0
    assert rows["Carretillero"]["Polivalente"] == 1.6
    assert rows["Carretillero"]["Disponible efectivo"] == 1.6
    assert rows["Carretillero"]["Estado"] == "Verde"


def test_staff_polyvalence_target_rule_matches_real_equivalent_area(monkeypatch):
    result = _staffing(
        monkeypatch,
        [
            {"linea_productiva": "ENCAJADO", "area_puesto": "Carretilleros", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
            {"linea_productiva": "ENCAJADO", "area_puesto": "Encargado", "tipo_personal": "Indirecto", "minimo": 1, "optimo": 1, "activo": 1, "obligatorio": 1},
        ],
        [
            {"area": "Carretilleros", "tipo_personal": "Indirecto", "disponible": 0, "activo": 1},
            {"area": "Encargados", "tipo_personal": "Indirecto", "disponible": 3, "activo": 1},
        ],
        [{"puesto_origen": "Encargado", "puesto_destino": "Carretillero", "prioridad": 1, "factor_productividad": 100, "activa": 1}],
        [
            {"area_requerida": "Encargado", "area_personal": "Encargados", "prioridad": 1, "activa": 1},
            {"area_requerida": "Carretillero", "area_personal": "Carretilleros", "prioridad": 1, "activa": 1},
        ],
    )

    row = {r["Área / puesto"]: r for r in result["rows"]}["Carretilleros"]
    assert row["Polivalente"] == 1
    assert row["Disponible efectivo"] == 1
    assert row["Estado"] == "Verde"
