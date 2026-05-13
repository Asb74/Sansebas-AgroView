from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from db.planning_repository import canonical_get, normalizar_campana


@dataclass
class PoliticaCompatibilidad:
    misma_campana_obligatoria: bool = True
    permitir_variedad_alterna: bool = False
    permitir_mismo_grupo_varietal: bool = True
    permitir_grupo_alterno: bool = False
    permitir_producto_base: bool = False
    permitir_categoria_inferior: bool = False
    permitir_categoria_superior: bool = False
    permitir_solape_parcial: bool = True
    permitir_stock_comercial: bool = False
    permitir_stock_industrial: bool = True
    permitir_campo_estimado: bool = True
    usar_reservas_amplias: bool = False


@dataclass
class DisponibilidadAtomica:
    origen: str
    tipo_stock: str
    cultivo: str
    campana: str
    producto_base: str = ""
    grupo_varietal: str = ""
    variedad: str = ""
    calibre: str = ""
    categoria: str = ""
    marca: str = ""
    id_confeccion: str = ""
    confeccion: str = ""
    palets: int = 0
    cajas: float = 0.0
    kg_brutos: float = 0.0
    kg_reservados: float = 0.0
    kg_netos: float = 0.0
    fecha_origen: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def _is_industrial(row: dict[str, Any]) -> bool:
    pedido = str(row.get("Pedido", "")).upper().replace("/", "").replace(" ", "")
    conf = canonical_get(row, "confeccion", "").upper()
    id_conf = str(canonical_get(row, "id_confeccion", "")).strip()
    return pedido in {"PRECALIBRADO", "ESTANDAR", "ESTÁNDAR"} or any(t in conf for t in ("PRECAL", "GRANEL", "GRAI")) or id_conf == "1308"


def calcular_disponibilidad_almacen(detalle_rows: list[dict[str, Any]]) -> list[DisponibilidadAtomica]:
    grouped: dict[tuple, DisponibilidadAtomica] = {}
    palets_by_key: dict[tuple, set[str]] = {}
    for row in detalle_rows:
        pedido = str(row.get("Pedido", "")).upper().replace("/", "").replace(" ", "")
        origen, tipo_stock = ("ALMACEN_COMERCIAL", "COMERCIAL") if pedido == "SP" and not _is_industrial(row) else ("ALMACEN_INDUSTRIAL", "INDUSTRIAL") if _is_industrial(row) else ("", "")
        if not origen:
            continue
        key = (
            origen,
            str(row.get("Cultivo", "")).strip(),
            normalizar_campana(canonical_get(row, "campana", row.get("Campaña", ""))),
            canonical_get(row, "grupo_varietal", row.get("GrupoVarietal", "")),
            str(row.get("Variedad", "")).strip(),
            str(row.get("Calibre", "")).strip(),
            canonical_get(row, "categoria", row.get("Categoria", "")),
            str(row.get("Marca", "")).strip(),
            str(canonical_get(row, "id_confeccion", "")).strip(),
            str(canonical_get(row, "confeccion", "")).strip(),
        )
        if key not in grouped:
            grouped[key] = DisponibilidadAtomica(origen=origen, tipo_stock=tipo_stock, cultivo=key[1], campana=key[2], grupo_varietal=key[3], variedad=key[4], calibre=key[5], categoria=key[6], marca=key[7], id_confeccion=key[8], confeccion=key[9])
            palets_by_key[key] = set()
        item = grouped[key]
        item.cajas += float(row.get("Cajas", row.get("Bultos", 0)) or 0)
        item.kg_brutos += float(canonical_get(row, "kg", row.get("Neto", 0)) or 0)
        pid = str(row.get("IdPalet", "")).strip()
        if pid:
            palets_by_key[key].add(pid)
    for k, item in grouped.items():
        item.palets = len(palets_by_key[k])
        item.kg_netos = item.kg_brutos
    return list(grouped.values())
