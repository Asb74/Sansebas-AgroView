import sys
import types

openpyxl = types.ModuleType("openpyxl")
openpyxl.Workbook = object
openpyxl_styles = types.ModuleType("openpyxl.styles")
openpyxl_styles.Font = object
sys.modules.setdefault("openpyxl", openpyxl)
sys.modules.setdefault("openpyxl.styles", openpyxl_styles)

from services.production_capacity_service import ProductionCapacityService


def _inputs():
    return {
        "packaging_mapping": [
            {"codigo_mconfeccion": "100", "familia_productiva": "Citricos", "linea_productiva": "MALLAS_GIRSAC"}
        ],
        "base_packaging": [
            {"codigo": "BASE", "grupo_confeccion": "MALLA", "perfil_confeccion": "GIRSAC", "familia_productiva": "Citricos", "linea_productiva": "MALLAS_GIRSAC", "activo": 1}
        ],
        "filters": {"cultivo": ["SANDIA"]},
        "cultivo_actual": "SANDIA",
    }


def test_fase1_sandia_requires_explicit_productive_crop_mapping():
    service = ProductionCapacityService()
    mapped, incidencias = service._map_orders_to_lines_fase1(
        [{"IdPedidoLora": "P-SANDIA", "IdConfeccion": "100", "Kg pendiente": 1250, "Cultivo": "SANDIA"}],
        _inputs(),
    )

    assert mapped == []
    assert incidencias[0]["Tipo incidencia"] == "No confeccionable"
    assert incidencias[0]["Motivo"] == "Pedido SANDIA sin línea productiva compatible configurada"
    assert incidencias[0]["kg"] == 1250


def test_fase1_sandia_can_map_when_config_declares_crop():
    service = ProductionCapacityService()
    inputs = _inputs()
    inputs["packaging_mapping"][0]["cultivo"] = "SANDIA"

    mapped, incidencias = service._map_orders_to_lines_fase1(
        [{"IdPedidoLora": "P-SANDIA", "IdConfeccion": "100", "Kg pendiente": 1250, "Cultivo": "SANDIA"}],
        inputs,
    )

    assert incidencias == []
    assert mapped[0]["linea"] == "MALLAS_GIRSAC"


def test_full_mapping_does_not_use_generic_fallback_for_sandia():
    service = ProductionCapacityService()
    inputs = _inputs() | {
        "caliber_factors": [],
        "lines": [],
    }

    mapped, incidencias = service.map_orders_to_productive_config(
        [{"IdPedidoLora": "P-SANDIA", "grupo_confeccion": "MALLA", "perfil_confeccion": "GIRSAC", "Kg pendiente": 1250, "Cultivo": "SANDIA"}],
        [],
        inputs,
    )

    assert mapped == []
    assert [inc["Tipo incidencia"] for inc in incidencias] == ["No confeccionable"]
    assert inputs["pedidos_no_confeccionables"] == 1
    assert inputs["kg_no_confeccionables"] == 1250
