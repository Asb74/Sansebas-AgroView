from services.availability_engine import PoliticaCompatibilidad, calcular_disponibilidad_almacen
from db.planning_repository import PlanningRepository


def test_compatibilidad_default():
    repo = PlanningRepository()
    pedido = {"cultivo": "CITRICOS", "campana": "2026", "grupo": "BLANCA TARDIA", "variedad": "VALENCIA LATE", "calibre": "7/8", "categoria": "I"}
    stock = {"cultivo": "CITRICOS", "campana": "2026", "grupo": "BLANCA TARDIA", "variedad": "VALENCIA DELTA", "calibre": "CAL 8", "categoria": "I"}
    pol = PoliticaCompatibilidad()
    assert pol.permitir_mismo_grupo_varietal
    assert repo.comparar_calibres_para_cobertura(pedido["calibre"], stock["calibre"])["tipo"] in {"CALIBRE_ADMITIDO", "EXACTA", "AGRUPADA", "SOLAPE_PARCIAL"}


def test_disponibilidad_almacen_basica():
    rows = [{"Pedido": "PRECALIBRADO", "Cultivo": "CITRICOS", "Campaña": 2026, "GrupoVarietal": "BLANCA TARDIA", "Variedad": "VALENCIA", "Calibre": "CAL 8", "Categoria": "I", "IdConfeccion": "1308", "Confeccion": "GRANEL", "IdPalet": "P1", "Cajas": 10, "Neto": 100.0}]
    out = calcular_disponibilidad_almacen(rows)
    assert len(out) == 1
    assert out[0].origen == "ALMACEN_INDUSTRIAL"
    assert out[0].campana == "2026"
