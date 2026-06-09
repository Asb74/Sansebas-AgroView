from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
PEDIDOS_PREVISTOS_PATH = Path("runtime_config/pedidos_previstos.json")


def default_pedidos_previstos_payload() -> dict:
    return {"incluir_en_simulacion": True, "pedidos": []}


def cargar_pedidos_previstos() -> dict:
    payload = default_pedidos_previstos_payload()
    try:
        if not PEDIDOS_PREVISTOS_PATH.exists():
            return payload
        raw = json.loads(PEDIDOS_PREVISTOS_PATH.read_text(encoding="utf-8")) or {}
        payload["incluir_en_simulacion"] = bool(raw.get("incluir_en_simulacion", True))
        payload["pedidos"] = list(raw.get("pedidos", []))
    except Exception:
        logger.exception("No se pudieron cargar pedidos previstos")
    logger.info("Pedidos previstos cargados: %s", len(payload["pedidos"]))
    return payload


def guardar_pedidos_previstos(payload: dict) -> None:
    PEDIDOS_PREVISTOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PEDIDOS_PREVISTOS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(str(value).replace(".", "").replace(",", ".")) if isinstance(value, str) and "," in value else float(value)
    except Exception:
        return 0.0


def _parse_fecha(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _filter_values(filters: dict, key: str) -> set[str]:
    raw = filters.get(key, [])
    if not isinstance(raw, list):
        raw = [raw]
    return {_norm(v) for v in raw if _norm(v) and _norm(v) != "TODOS"}


def _semana_fecha(fecha_salida: Any) -> str:
    fecha_dt = _parse_fecha(fecha_salida)
    if not fecha_dt:
        return ""
    iso = fecha_dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def pedido_previsto_a_demanda(p: dict, cultivo_actual: str = "", campana_actual: str = "", empresa_actual: str = "") -> dict:
    kg = _to_float(p.get("kg_estimados", 0))
    cultivo = str(p.get("cultivo", p.get("Cultivo", "")) or "").strip() or str(cultivo_actual or "").strip()
    campana = str(p.get("campana", p.get("Campaña", p.get("Campana", ""))) or "").strip() or str(campana_actual or "").strip()
    empresa = str(p.get("empresa", p.get("EMPRESA", p.get("Empresa", ""))) or "").strip() or str(empresa_actual or "").strip()
    grupo_confeccion = str(p.get("grupo_confeccion", p.get("Grupo confección", p.get("GrupoConfeccion", ""))) or "").strip()
    perfil_confeccion = str(p.get("perfil_confeccion", p.get("Perfil confección", "")) or "").strip()
    fecha_salida = str(p.get("fecha_salida", p.get("Fecha salida", p.get("FechaSalida", ""))) or "").strip()
    return {
        "IdPedidoLora": p.get("id_previsto", ""),
        "Fecha salida": fecha_salida,
        "FechaSalida": fecha_salida,
        "fecha_salida": fecha_salida,
        "Semana": _semana_fecha(fecha_salida),
        "Cultivo": cultivo,
        "cultivo": cultivo,
        "Campaña": campana,
        "Campana": campana,
        "campana": campana,
        "EMPRESA": empresa,
        "Empresa": empresa,
        "Cliente": p.get("cliente", ""),
        "Grupo varietal": p.get("grupo_varietal", ""),
        "Variedad": p.get("variedad", ""),
        "Variedad Coop": p.get("variedad", ""),
        "Calibre": p.get("calibre", ""),
        "Categoría": p.get("categoria", ""),
        "Categoria": p.get("categoria", ""),
        "Marca": p.get("marca", ""),
        "IdConfeccion": p.get("codigo_base_packaging", ""),
        "Confección": p.get("confeccion_prevista", p.get("descripcion_base_packaging", "")),
        "Grupo confección": grupo_confeccion,
        "GrupoConfeccion": grupo_confeccion,
        "grupo_confeccion": grupo_confeccion,
        "Perfil confección": perfil_confeccion,
        "perfil_confeccion": perfil_confeccion,
        "Kg pendientes": kg,
        "Kg pendiente": kg,
        "Kg pedidos pendientes": kg,
        "kg_pendiente": kg,
        "kg_pendientes": kg,
        "Línea": 0,
        "origen_demanda": "PREVISTO",
        "Tipo línea": "Pedido previsto",
        "kg_necesario": kg,
        **p,
    }



def _pedido_previsto_log_context(row: dict) -> dict[str, Any]:
    return {
        "id": row.get("id_previsto", row.get("IdPedidoLora", "")),
        "cliente": row.get("cliente", row.get("Cliente", "")),
        "kg": row.get("kg_estimados", row.get("Kg pendientes", "")),
        "cultivo": row.get("cultivo", row.get("Cultivo", "")),
        "campana": row.get("campana", row.get("Campaña", "")),
        "empresa": row.get("empresa", row.get("Empresa", row.get("EMPRESA", ""))),
        "semana": row.get("semana", row.get("Semana", "")),
    }


def _log_pedido_previsto_incluido(row: dict) -> None:
    ctx = _pedido_previsto_log_context(row)
    logger.debug(
        "PREVISTO INCLUIDO | id=%s | cliente=%s | kg_estimados=%s | cultivo=%s | campaña=%s | empresa=%s | semana=%s",
        ctx["id"],
        ctx["cliente"],
        ctx["kg"],
        ctx["cultivo"],
        ctx["campana"],
        ctx["empresa"],
        ctx["semana"],
    )


def _log_pedido_previsto_descartado(row: dict, motivo: str, valor_pedido: Any, filtro: Any) -> None:
    ctx = _pedido_previsto_log_context(row)
    logger.debug(
        "PREVISTO DESCARTADO | id=%s | cliente=%s | kg_estimados=%s | cultivo=%s | campaña=%s | empresa=%s | semana=%s | motivo=%s | valor_pedido=%r | filtro=%r",
        ctx["id"],
        ctx["cliente"],
        ctx["kg"],
        ctx["cultivo"],
        ctx["campana"],
        ctx["empresa"],
        ctx["semana"],
        motivo,
        valor_pedido,
        filtro,
    )

def filtrar_pedidos_previstos(pedidos: list[dict], filters: dict | None = None, *, cultivo_actual: str = "", campana_actual: str = "", empresa_actual: str = "", incluir_descartados: bool = False) -> list[dict]:
    filters = filters or {}
    desde = _parse_fecha(filters.get("fecha_desde"))
    hasta = _parse_fecha(filters.get("fecha_hasta"))
    selected = {k: _filter_values(filters, k) for k in ("campana", "cultivo", "empresa", "semana", "var_coop", "grupo_varietal", "marca")}
    out: list[dict] = []
    for pedido in pedidos:
        row = pedido_previsto_a_demanda(pedido, cultivo_actual=cultivo_actual, campana_actual=campana_actual, empresa_actual=empresa_actual)
        if not incluir_descartados and _norm(pedido.get("estado", "")) == "DESCARTADO":
            _log_pedido_previsto_descartado(row, "estado", pedido.get("estado", ""), "DESCARTADO")
            continue
        fecha_dt = _parse_fecha(row.get("Fecha salida"))
        if desde and (not fecha_dt or fecha_dt < desde):
            _log_pedido_previsto_descartado(row, "fecha_desde", row.get("Fecha salida", ""), filters.get("fecha_desde"))
            continue
        if hasta and (not fecha_dt or fecha_dt > hasta):
            _log_pedido_previsto_descartado(row, "fecha_hasta", row.get("Fecha salida", ""), filters.get("fecha_hasta"))
            continue
        checks = {
            "campana": row.get("Campaña", ""),
            "cultivo": row.get("Cultivo", ""),
            "empresa": row.get("Empresa", ""),
            "semana": row.get("Semana", ""),
            "var_coop": row.get("Variedad Coop", ""),
            "grupo_varietal": row.get("Grupo varietal", ""),
            "marca": row.get("Marca", ""),
        }
        descartado = False
        for key, vals in selected.items():
            if vals and _norm(checks[key]) not in vals:
                _log_pedido_previsto_descartado(row, key, checks[key], ",".join(sorted(vals)))
                descartado = True
                break
        if descartado:
            continue
        _log_pedido_previsto_incluido(row)
        out.append(row)
    return out


def cargar_pedidos_previstos_filtrados(filters: dict | None = None, *, respetar_incluir: bool = True, cultivo_actual: str = "", campana_actual: str = "", empresa_actual: str = "") -> list[dict]:
    payload = cargar_pedidos_previstos()
    if respetar_incluir and not payload.get("incluir_en_simulacion", True):
        return []
    return filtrar_pedidos_previstos(payload.get("pedidos", []), filters, cultivo_actual=cultivo_actual, campana_actual=campana_actual, empresa_actual=empresa_actual)
