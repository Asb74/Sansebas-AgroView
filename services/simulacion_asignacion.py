from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import logging
import tkinter as tk
from tkinter import ttk
import unicodedata

from services.operational_quality_service import OperationalQualityService
from db.planning_repository import PlanningRepository
from widgets.data_table import DataTable


SCORING_COBERTURA = {
    "exacto": 100,
    "mismo_grupo": 80,
    "variedad_alternativa": 60,
    "calibre_agrupado": 40,
    "calibre_admitido": 30,
    "solape_parcial": 20,
    "categoria_superior": 10,
    "categoria_inferior": -20,
    "grupo_varietal_alternativo": -30,
    "campo_real": 10,
    "industrial": 0,
    "comercial": 0,
}

TIPOS_CONFECCION_FLEXIBLES = [
    "MALLA",
    "MALLAS",
]

TIPOS_CONFECCION_EXIGENTES = [
    "ENCAJADO",
    "GRANEL",
    "ALVEOLO",
    "ALVÉOLO",
    "CAJA",
    "CAJAS",
]
TOKENS_PERFIL_MALLA = ["MALLA", "MALLAS", "RED", "BOLSA"]
TOKENS_PERFIL_EXIGENTE = ["ENCAJADO", "ENCAJAR", "GRANEL", "ALVEOLO", "ALVÉOLO", "ALVEOLADO", "CAJA", "CAJAS"]

COEFICIENTES_UTILIDAD = {
    "MALLA": {"ESTANDAR": 0.95, "PRECALIBRADO": 0.90, "INDUSTRIAL": 0.90, "CAMPO_REAL": 0.75, "DESCONOCIDO": 0.80},
    "EXIGENTE": {"ESTANDAR": 0.80, "PRECALIBRADO": 0.65, "INDUSTRIAL": 0.70, "CAMPO_REAL": 0.60, "DESCONOCIDO": 0.65},
    "DESCONOCIDO": {"ESTANDAR": 0.85, "PRECALIBRADO": 0.75, "INDUSTRIAL": 0.75, "CAMPO_REAL": 0.65, "DESCONOCIDO": 0.70},
}

PENALIZACION_RIESGO = {"BAJO": 0, "MEDIO": -10, "ALTO": -25}

CONFIG_CALIDAD_OPERATIVA = {
    "CAMPO_REAL": {"primera_pct": 0.80, "segunda_pct": 0.20, "destrio_fallback_pct": 0.15, "usar_destrio_historico": True, "industria_recuperable_pct": 1.00},
    "CAMPO_ESTIMADO": {"primera_pct": 0.80, "segunda_pct": 0.20, "destrio_fallback_pct": 0.15, "usar_destrio_historico": False, "industria_recuperable_pct": 1.00},
    "ALMACEN_INDUSTRIAL": {"primera_pct": 0.80, "segunda_pct": 0.20, "destrio_fallback_pct": 0.05, "usar_destrio_historico": False, "industria_recuperable_pct": 1.00},
    "ALMACEN_COMERCIAL": {"primera_pct": 0.95, "segunda_pct": 0.05, "destrio_fallback_pct": 0.02, "usar_destrio_historico": False, "industria_recuperable_pct": 0.50},
    "DESCONOCIDO": {"primera_pct": 0.80, "segunda_pct": 0.20, "destrio_fallback_pct": 0.10, "usar_destrio_historico": False, "industria_recuperable_pct": 0.80},
}
_quality_service = OperationalQualityService()
logger = logging.getLogger(__name__)


def _norm_text(valor: object) -> str:
    txt = unicodedata.normalize("NFD", str(valor or "").strip().upper())
    txt = "".join(ch for ch in txt if unicodedata.category(ch) != "Mn")
    return " ".join(txt.split())


def _to_float(valor: object) -> float:
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    txt = str(valor).strip()
    if not txt:
        return 0.0
    txt = txt.replace(" ", " ").replace(" ", "")
    txt = txt.replace("%", "")
    txt = "".join(ch for ch in txt if ch.isdigit() or ch in ".,-")
    if not txt:
        return 0.0
    if "," in txt and "." in txt:
        if txt.rfind(",") > txt.rfind("."):
            txt = txt.replace(".", "").replace(",", ".")
        else:
            txt = txt.replace(",", "")
    elif "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except (TypeError, ValueError):
        return 0.0




def _pick_first(row: dict, keys: tuple[str, ...], default: object = "") -> object:
    for key in keys:
        val = row.get(key)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        return val
    return default


def normalizar_pool_inventario_global(row: dict) -> dict:
    origen = _pick_first(row, ("origen", "Origen"), "")
    variedad = _pick_first(row, ("variedad", "Variedad", "Variedad stock"), "")
    grupo_varietal = _pick_first(row, ("grupo_varietal", "Grupo varietal", "Grupo varietal stock", "GrupoVarietal"), "")
    calibre = _pick_first(row, ("calibre", "Calibre", "Calibre stock"), "")
    categoria = _pick_first(row, ("categoria", "Categoría", "Categoria", "Categoría stock"), "")
    kg_disponibles = _to_float(_pick_first(row, ("kg_fisicos", "Kg físicos", "Kg disponibles", "Kg stock", "kg_disponibles", "kg_stock"), 0))
    kg_utiles_finales = _to_float(_pick_first(row, ("kg_utiles_finales", "Kg útiles finales", "Kg stock total útil", "Kg libres", "Kg restante total"), kg_disponibles))

    row_norm = dict(row)
    row_norm.update({
        "Origen": str(origen or "").strip(),
        "origen": str(origen or "").strip(),
        "Variedad stock": str(variedad or "").strip(),
        "variedad": str(variedad or "").strip(),
        "Grupo varietal stock": str(grupo_varietal or "").strip(),
        "grupo_varietal": str(grupo_varietal or "").strip(),
        "Calibre stock": str(calibre or "").strip(),
        "calibre": str(calibre or "").strip(),
        "Categoría": str(categoria or "").strip(),
        "categoria": str(categoria or "").strip(),
        "Kg disponibles": kg_disponibles,
        "kg_fisicos": kg_disponibles,
        "kg_disponibles": kg_disponibles,
        "kg_stock": kg_disponibles,
        "kg_utiles_finales": kg_utiles_finales,
        "kg_utiles_estimados": kg_utiles_finales,
    })
    return row_norm

def formatear_kg(valor: object) -> str:
    num = _to_float(valor)
    return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _parse_fecha_salida(valor: object) -> date | None:
    if not valor:
        return None
    txt = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(txt[:10], fmt).date()
        except ValueError:
            continue
    return None

def _normalizar_fecha_salida(row: dict) -> date | None:
    for key in ("Fecha salida", "fecha_salida", "FechaSalida", "fecha salida", "Salida", "Fecha", "fecha", "salida"):
        if key not in row:
            continue
        valor = row.get(key)
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        fecha = _parse_fecha_salida(valor)
        if fecha:
            return fecha
    return None


def _calcular_bloque_temporal(fecha: date | None, hoy: date) -> tuple[int, str]:
    if not fecha:
        return 9999, "FUTURO"
    dias = (fecha - hoy).days
    if dias <= 0:
        return 0, "HOY"
    if dias == 1:
        return 1, "MAÑANA"
    if dias <= 7:
        return dias, f"+{dias} DÍAS"
    return dias, "FUTURO"


def _texto_fecha_horizonte(fecha_raw: object) -> str:
    fecha_dt = _parse_fecha_salida(fecha_raw)
    if not fecha_dt:
        return "Fecha no disponible"
    return fecha_dt.strftime("%d/%m/%Y")


def _bloque_temporal_horizonte(fecha_raw: object, bloque_actual: object, hoy: date) -> str:
    bloque_txt = str(bloque_actual or "").strip()
    if bloque_txt and _norm_text(bloque_txt) not in {"", "N/D", "NA", "N A", "SIN FECHA", "GENERICO", "GENERAL"}:
        return bloque_txt
    fecha_dt = _parse_fecha_salida(fecha_raw)
    if not fecha_dt:
        return "FUTURO"
    dias = (fecha_dt - hoy).days
    if dias <= 0:
        return "HOY"
    if dias == 1:
        return "MAÑANA"
    if dias <= 3:
        return "2-3 DÍAS"
    if dias <= 7:
        return "4-7 DÍAS"
    return "FUTURO"


def _build_pool_id(candidato: dict) -> str:
    campos = [
        candidato.get("Origen", candidato.get("origen", "")),
        candidato.get("Variedad stock", candidato.get("variedad_stock", candidato.get("Variedad", ""))),
        candidato.get("Grupo varietal stock", candidato.get("grupo_varietal_stock", candidato.get("Grupo varietal", ""))),
        candidato.get("Calibre stock", candidato.get("calibre_stock", candidato.get("Calibre", ""))),
        candidato.get("Categoría", candidato.get("categoria_stock", candidato.get("categoria", ""))),
        candidato.get("id_palet", candidato.get("palet", candidato.get("lote", candidato.get("boleta", "")))),
        candidato.get("id_confeccion", ""),
        candidato.get("pedido_stock", candidato.get("pedido", "")),
    ]
    partes = [_norm_text(c) for c in campos if _norm_text(c)]
    return "|".join(partes) if partes else "POOL_DESCONOCIDO"


def _compatibilidad_varietal(pedido: dict, candidato: dict) -> tuple[int, str]:
    ped_var = _norm_text(pedido.get("Variedad", pedido.get("variedad", "")))
    ped_grp = _norm_text(pedido.get("Grupo varietal", pedido.get("grupo_varietal", "")))
    cand_var = _norm_text(candidato.get("Variedad stock", candidato.get("variedad_stock", candidato.get("Variedad", ""))))
    cand_grp = _norm_text(candidato.get("Grupo varietal stock", candidato.get("grupo_varietal_stock", candidato.get("Grupo varietal", ""))))
    allow_mismo = bool(pedido.get("mismo_grupo_varietal", True) and pedido.get("permitir_variedad_alternativa", True))
    allow_alt = bool(pedido.get("permitir_grupo_varietal_alternativo", False))
    if ped_var and cand_var and ped_var == cand_var:
        return 0, "EXACTA"
    if ped_grp and cand_grp and ped_grp == cand_grp:
        return (1, "MISMO GRUPO") if allow_mismo else (99, "INCOMPATIBLE")
    return (2, "GRUPO ALTERNATIVO") if allow_alt else (99, "INCOMPATIBLE")


def detectar_perfil_confeccion(pedido: dict) -> str:
    campos = ["confeccion", "tipo_confeccion", "grupo_confeccion", "formato", "envase", "tipo_envase", "articulo", "descripcion", "producto", "cliente"]
    texto = " ".join(_norm_text(pedido.get(c, pedido.get(c.capitalize(), ""))) for c in campos)
    if any(token in texto for token in [_norm_text(v) for v in TIPOS_CONFECCION_FLEXIBLES]):
        return "MALLA"
    if any(token in texto for token in [_norm_text(v) for v in TIPOS_CONFECCION_EXIGENTES]):
        return "EXIGENTE"
    return "DESCONOCIDO"


def detectar_perfil_confeccion_desde_grupo(grupo_confeccion: object) -> str:
    grupo = _norm_text(grupo_confeccion)
    if any(token in grupo for token in TOKENS_PERFIL_MALLA):
        return "MALLA"
    if any(token in grupo for token in TOKENS_PERFIL_EXIGENTE):
        return "EXIGENTE"
    return "DESCONOCIDO"


def detectar_perfil_stock(candidato: dict) -> str:
    campos = ["origen", "Origen", "tipo_cobertura", "Tipo cobertura", "tipo cobertura", "flexibilidad", "flexibilidad_aplicada", "descripcion", "articulo", "observaciones", "lote", "tipo_stock"]
    texto = " ".join(_norm_text(candidato.get(c, "")) for c in campos)
    if any(token in texto for token in ("ALMACEN_INDUSTRIAL", "ALMACEN INDUSTRIAL", "INDUSTRIAL", "PRECALIBRADO", "ESTANDAR", "ESTÁNDAR")):
        return "ALMACEN_INDUSTRIAL"
    if any(token in texto for token in ("ALMACEN_COMERCIAL", "ALMACEN COMERCIAL", "COMERCIAL", "S/P", "SIN PEDIDO")):
        return "ALMACEN_COMERCIAL"
    if "CAMPO_REAL" in texto or "PESOSFRES" in texto:
        return "CAMPO_REAL"
    if "CAMPO_ESTIMADO" in texto or "ESTIMADO" in texto:
        return "CAMPO_ESTIMADO"
    return "DESCONOCIDO"


def _canonicalizar_origen(origen: str) -> str:
    origen_norm = _norm_text(origen)
    if origen_norm in {"CAMPO_REAL_PESOSFRES", "CAMPO_REAL_PESOS"}:
        return "CAMPO_REAL"
    if origen_norm == "STOCK_REPROCESO":
        return "ALMACEN_INDUSTRIAL"
    if origen_norm == "STOCK_COMERCIAL":
        return "ALMACEN_COMERCIAL"
    return origen_norm


def obtener_config_utilidad_stock(perfil_stock: str, candidato: dict | None = None) -> dict:
    _ = candidato  # reservado para futuras reglas dinámicas
    perfil = _canonicalizar_origen(perfil_stock or "")
    if perfil == "INDUSTRIAL":
        perfil = "ALMACEN_INDUSTRIAL"
    elif perfil == "COMERCIAL":
        perfil = "ALMACEN_COMERCIAL"
    elif perfil == "PRECALIBRADO":
        perfil = "ALMACEN_INDUSTRIAL"
    try:
        _quality_service.ensure_defaults()
        rows = _quality_service.get_settings()
        db_cfg = {str(r.get("Origen")): {
            "primera_pct": float(r.get("PrimeraPct", 0)),
            "segunda_pct": float(r.get("SegundaPct", 0)),
            "destrio_fallback_pct": float(r.get("DestrioFallbackPct", 0)),
            "usar_destrio_historico": bool(int(r.get("UsarDestrioHistorico", 0))),
            "industria_recuperable_pct": float(r.get("IndustriaRecuperablePct", 0)),
        } for r in rows}
        cfg = db_cfg.get(perfil, db_cfg.get("DESCONOCIDO"))
        if cfg:
            return dict(cfg)
    except Exception:
        pass
    return dict(CONFIG_CALIDAD_OPERATIVA.get(perfil, CONFIG_CALIDAD_OPERATIVA["DESCONOCIDO"]))


def _parse_percent_like(valor: object) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, str):
        txt = valor.strip().replace(",", ".")
        if not txt:
            return None
        txt = txt.replace("%", "")
        try:
            num = float(txt)
        except ValueError:
            return None
    else:
        try:
            num = float(valor)
        except (TypeError, ValueError):
            return None
    if num > 1:
        num = num / 100.0
    if num < 0:
        return None
    return min(num, 1.0)


def extraer_porcentaje_destrio_historico(candidato: dict) -> float | None:
    for key in ("porcentaje_destrio_real", "destrio_real"):
        parsed = _parse_percent_like(candidato.get(key))
        if parsed is not None:
            return parsed

    componentes = ("destrio_mesa", "destrio_linea", "podrido")
    porcentajes = []
    for key in ("porcentaje_destrio_mesa", "porcentaje_destrio_linea", "porcentaje_podrido"):
        parsed = _parse_percent_like(candidato.get(key))
        if parsed is not None:
            porcentajes.append(parsed)
    if porcentajes:
        return min(sum(porcentajes), 1.0)

    if all(candidato.get(k) is not None for k in componentes):
        kg_total = _to_float(candidato.get("kg_total", candidato.get("kg_campo", candidato.get("Kg disponibles", candidato.get("kg_disponibles", 0)))))
        if kg_total > 0:
            destrio_kg = sum(_to_float(candidato.get(k, 0)) for k in componentes)
            return min(max(destrio_kg / kg_total, 0.0), 1.0)

    for key in ("destrio_total",):
        parsed = _parse_percent_like(candidato.get(key))
        if parsed is not None:
            return parsed
    return None


def extraer_componentes_destrio_historico(candidato: dict) -> tuple[float | None, float | None, float | None]:
    podrido = _parse_percent_like(candidato.get("porcentaje_podrido", candidato.get("%Podrido")))
    des_linea = _parse_percent_like(candidato.get("porcentaje_destrio_linea", candidato.get("%DesLinea")))
    des_mesa = _parse_percent_like(candidato.get("porcentaje_destrio_mesa", candidato.get("%DesMesa")))
    return podrido, des_linea, des_mesa


def _riesgo_desde_coef(coef: float) -> str:
    if coef >= 0.85:
        return "BAJO"
    if coef >= 0.70:
        return "MEDIO"
    return "ALTO"


def _subir_riesgo(riesgo: str) -> str:
    if riesgo == "BAJO":
        return "MEDIO"
    if riesgo == "MEDIO":
        return "ALTO"
    return "ALTO"


def calcular_utilidad_operativa(pedido: dict, candidato: dict) -> dict:
    perfil_confeccion = _norm_text(pedido.get("perfil_confeccion", "")) or detectar_perfil_confeccion(pedido)
    perfil_stock = detectar_perfil_stock(candidato)
    cfg = obtener_config_utilidad_stock(perfil_stock, candidato=candidato)
    texto_candidato = " ".join(_norm_text(candidato.get(c, "")) for c in ("origen", "Origen", "tipo_cobertura", "Tipo cobertura", "tipo", "pedido", "descripcion", "observaciones"))
    es_estandar = "ESTANDAR" in texto_candidato or "ESTÁNDAR" in texto_candidato
    es_precalibrado = "PRECALIBRADO" in texto_candidato
    primera_pct = float(cfg.get("primera_pct", 0.80))
    segunda_pct = float(cfg.get("segunda_pct", 0.20))
    if es_estandar and perfil_stock == "ALMACEN_INDUSTRIAL":
        primera_pct = 0.0
        segunda_pct = 1.0
    porcentaje_destrio = float(cfg.get("destrio_fallback_pct", 0.10))
    usar_destrio_historico = bool(cfg.get("usar_destrio_historico", False))
    kg_fisicos = _to_float(candidato.get("Kg disponibles", candidato.get("kg_disponibles", 0)))
    destrio_historico = extraer_porcentaje_destrio_historico(candidato) if (perfil_stock == "CAMPO_REAL" and usar_destrio_historico) else None
    podrido_pct_hist, deslinea_pct_hist, desmesa_pct_hist = extraer_componentes_destrio_historico(candidato) if perfil_stock == "CAMPO_REAL" else (None, None, None)

    texto_cobertura = _norm_text(candidato.get("Tipo cobertura", candidato.get("tipo_cobertura", "")))
    ya_neto_flag = candidato.get("kg_campo_real_ya_neto")
    if isinstance(ya_neto_flag, str):
        ya_neto = _norm_text(ya_neto_flag) in ("TRUE", "SI", "YES", "1")
    else:
        ya_neto = bool(ya_neto_flag)
    if perfil_stock == "CAMPO_REAL" and ya_neto_flag is None and "ENTRADA ESTIMADA REAL" in texto_cobertura:
        ya_neto = True

    if destrio_historico is not None:
        porcentaje_destrio = destrio_historico
    podrido_pct = podrido_pct_hist if podrido_pct_hist is not None else 0.0
    deslinea_pct = deslinea_pct_hist if deslinea_pct_hist is not None else 0.0
    desmesa_pct = desmesa_pct_hist if desmesa_pct_hist is not None else 0.0
    if destrio_historico is None:
        podrido_pct = porcentaje_destrio
        deslinea_pct = 0.0
        desmesa_pct = 0.0

    industria_pct = deslinea_pct + desmesa_pct
    kg_podrido_estimado = kg_fisicos * podrido_pct
    kg_industria_estimado = kg_fisicos * industria_pct
    kg_destrio_estimado = kg_fisicos * porcentaje_destrio
    kg_comercial_util = kg_fisicos - kg_destrio_estimado
    kg_primera_estimado = kg_comercial_util * primera_pct
    kg_segunda_estimado = kg_comercial_util * segunda_pct
    kg_utiles_categoria = kg_comercial_util
    kg_utiles_estimados = kg_primera_estimado + kg_segunda_estimado if perfil_confeccion == "MALLA" else kg_primera_estimado
    coef_utilidad = primera_pct

    if perfil_stock == "CAMPO_REAL":
        if destrio_historico is not None:
            riesgo = "BAJO" if porcentaje_destrio <= 0.05 else ("MEDIO" if porcentaje_destrio <= 0.12 else "ALTO")
            motivo = f"CAMPO_REAL: histórico PesosFres; primera estimada {primera_pct*100:.0f}%"
        else:
            riesgo = "ALTO"
            motivo = f"Sin histórico de destrío; usando fallback {porcentaje_destrio*100:.0f}%"
    elif perfil_stock == "CAMPO_ESTIMADO":
        riesgo = "MEDIO"
        motivo = "CAMPO_ESTIMADO: valores estimados configurados"
    elif perfil_stock == "ALMACEN_INDUSTRIAL":
        riesgo = "ALTO" if porcentaje_destrio > 0.10 else "MEDIO"
        if es_estandar:
            motivo = "Estándar: regla negocio, 100% segunda"
        elif es_precalibrado:
            motivo = "PRECALIBRADO: usa configuración de ALMACEN_INDUSTRIAL"
        else:
            motivo = "ALMACEN_INDUSTRIAL: primera/segunda configuradas; destrío configurable"
    elif perfil_stock == "ALMACEN_COMERCIAL":
        riesgo = "BAJO" if porcentaje_destrio <= 0.02 else "MEDIO"
        motivo = "ALMACEN_COMERCIAL: producto terminado"
    else:
        riesgo = "MEDIO" if porcentaje_destrio <= 0.10 else "ALTO"
        motivo = "Origen desconocido: valores conservadores"
    if perfil_confeccion == "MALLA":
        motivo += "; Malla: se admite primera + segunda"
    else:
        motivo += "; Exigente/desconocido: solo se considera primera útil"

    return {
        "perfil_confeccion": perfil_confeccion,
        "perfil_stock": perfil_stock,
        "coef_utilidad": coef_utilidad,
        "kg_fisicos": kg_fisicos,
        "kg_utiles_categoria": kg_utiles_categoria,
        "porcentaje_destrio": porcentaje_destrio,
        "kg_destrio_estimado": kg_destrio_estimado,
        "kg_comercial_util": kg_comercial_util,
        "primera_pct": primera_pct,
        "segunda_pct": segunda_pct,
        "kg_primera_estimado": kg_primera_estimado,
        "kg_segunda_estimado": kg_segunda_estimado,
        "podrido_pct": podrido_pct,
        "deslinea_pct": deslinea_pct,
        "desmesa_pct": desmesa_pct,
        "industria_pct": industria_pct,
        "kg_podrido_estimado": kg_podrido_estimado,
        "kg_industria_estimado": kg_industria_estimado,
        "kg_utiles_estimados": kg_utiles_estimados,
        "riesgo_operativo": riesgo,
        "penalizacion_riesgo": PENALIZACION_RIESGO.get(riesgo, 0),
        "motivo_riesgo": motivo,
    }


def calcular_score_candidato(candidato: dict, pedido: dict | None = None, scoring: dict | None = None) -> tuple[int, str]:
    scoring_cfg = scoring or SCORING_COBERTURA
    tipo = _norm_text(candidato.get("Tipo cobertura", candidato.get("tipo_cobertura", "")))
    flex = _norm_text(candidato.get("Flexibilidad aplicada", candidato.get("flexibilidad_aplicada", candidato.get("flexibilidad", ""))))
    origen = _norm_text(candidato.get("Origen", candidato.get("origen", "")))
    coincidencia = _norm_text(candidato.get("coincidencia", ""))

    cand_var = _norm_text(candidato.get("Variedad stock", candidato.get("variedad_stock", "")))
    cand_cal = _norm_text(candidato.get("Calibre stock", candidato.get("calibre_stock", "")))
    cand_cat = _norm_text(candidato.get("Categoría", candidato.get("categoria_stock", "")))

    ped_var = _norm_text((pedido or {}).get("Variedad", (pedido or {}).get("variedad", "")))
    ped_cal = _norm_text((pedido or {}).get("Calibre", (pedido or {}).get("calibre", "")))
    ped_cat = _norm_text((pedido or {}).get("Categoría", (pedido or {}).get("categoria", "")))

    score = 0
    motivos: list[str] = []

    def add_motivo(clave: str, texto: str) -> None:
        nonlocal score
        score += int(scoring_cfg.get(clave, 0))
        if texto not in motivos:
            motivos.append(texto)

    tokens = " ".join([tipo, flex, coincidencia])

    if ped_var and ped_cal and ped_cat and ped_var == cand_var and ped_cal == cand_cal and ped_cat == cand_cat:
        add_motivo("exacto", "Exacto")

    if "CAMPO_REAL" in origen or "PESOSFRES" in origen:
        add_motivo("campo_real", "Campo real")
    if "INDUSTRIAL" in origen:
        add_motivo("industrial", "Industrial")
    if "COMERCIAL" in origen:
        add_motivo("comercial", "Comercial")

    if "CALIBRE_ADMITIDO" in tokens:
        add_motivo("calibre_admitido", "Calibre admitido")
    if "AGRUPADA" in tokens or "AGRUPADO" in tokens:
        add_motivo("calibre_agrupado", "Calibre agrupado")
    if "SOLAPE_PARCIAL" in tokens:
        add_motivo("solape_parcial", "Solape parcial")
    if "GRUPO_ALTERNATIVO" in tokens or "GRUPO VARIETAL ALTERNATIVO" in tokens:
        add_motivo("grupo_varietal_alternativo", "Grupo varietal alternativo")
    if "VARIEDAD_ALTERNATIVA" in tokens or "VARIEDAD ALTERNATIVA" in tokens:
        add_motivo("variedad_alternativa", "Variedad alternativa")
    if "MISMO_GRUPO" in tokens or "MISMO GRUPO" in tokens:
        add_motivo("mismo_grupo", "Mismo grupo")
    if "CATEGORIA_INFERIOR" in tokens or "CATEGORÍA INFERIOR" in tokens:
        add_motivo("categoria_inferior", "Categoría inferior")
    if "CATEGORIA_SUPERIOR" in tokens or "CATEGORÍA SUPERIOR" in tokens:
        add_motivo("categoria_superior", "Categoría superior")

    if not motivos:
        motivos.append("Sin flexibilidad")

    return score, " + ".join(motivos)


def ordenar_candidatos_simulacion(candidatos: list[dict]) -> list[dict]:
    prioridad_riesgo = {"BAJO": 0, "MEDIO": 1, "ALTO": 2}

    return sorted(
        candidatos,
        key=lambda c: (
            int(_to_float(c.get("compatibilidad_varietal_rank", 99))),
            -_to_float(c.get("score_total", 0)),
            prioridad_riesgo.get(str(c.get("riesgo_operativo", "ALTO")), 9),
            -_to_float(c.get("kg_utiles_finales", c.get("kg_utiles_estimados", 0))),
        ),
    )


def simular_asignacion_pedido(pedido: dict, candidatos: list[dict], scoring: dict | None = None) -> dict:
    kg_pend = _to_float(pedido.get("Kg pedidos pendientes", 0) or pedido.get("kg_pendientes", 0) or 0)
    candidatos_ordenados: list[dict] = []

    for cand in deepcopy(candidatos):
        score, flex_txt = calcular_score_candidato(cand, pedido=pedido, scoring=scoring)
        utilidad = calcular_utilidad_operativa(pedido, cand)
        cand["score_simulacion"] = score
        cand["flexibilidad_usada_simulacion"] = flex_txt
        cand.update(utilidad)
        cand["score_total"] = score + int(cand.get("penalizacion_riesgo", 0) or 0)
        candidatos_ordenados.append(cand)

    candidatos_ordenados = ordenar_candidatos_simulacion(candidatos_ordenados)

    acumulado = 0.0
    for cand in candidatos_ordenados:
        acumulado += _to_float(cand.get("kg_utiles_estimados", 0))
        cand["cobertura_acumulada"] = acumulado

    if acumulado >= kg_pend and kg_pend > 0:
        estado = "TOTAL"
    elif acumulado > 0:
        estado = "PARCIAL"
    else:
        estado = "INSUFICIENTE"

    kg_potencial_fisico = sum(_to_float(c.get("kg_fisicos", 0)) for c in candidatos_ordenados)
    perfil_confeccion = _norm_text(pedido.get("perfil_confeccion", "")) or detectar_perfil_confeccion(pedido)
    return {
        "pedido": dict(pedido),
        "kg_pendientes": kg_pend,
        "estado": estado,
        "kg_cobertura_simulada": min(acumulado, kg_pend),
        "kg_potencial_encontrado": acumulado,
        "kg_potencial_fisico": kg_potencial_fisico,
        "kg_potencial_util": acumulado,
        "perfil_confeccion": perfil_confeccion,
        "candidatos": candidatos_ordenados,
    }


def simular_asignacion_global(pedidos: list[dict], get_candidatos_cb, scoring: dict | None = None) -> tuple[list[dict], list[dict], dict]:
    hoy = date.today()
    pedidos_meta = []
    for pedido_raw in pedidos:
        pedido = normalizar_pedido_para_simulacion(pedido_raw)
        fecha_salida = _normalizar_fecha_salida(pedido)
        dias_hasta, bloque = _calcular_bloque_temporal(fecha_salida, hoy)
        prioridad_manual = int(_to_float(pedido.get("prioridad_manual", 0)))
        item = dict(pedido)
        item["fecha_salida"] = fecha_salida.isoformat() if fecha_salida else ""
        item["dias_hasta_salida"] = dias_hasta
        item["bloque_temporal"] = bloque
        item["prioridad_fecha"] = dias_hasta
        item["prioridad_manual"] = prioridad_manual
        pedidos_meta.append(item)
    pedidos_meta.sort(
        key=lambda p: (
            p.get("dias_hasta_salida", 9999),
            -int(_to_float(p.get("prioridad_manual", 0))),
            str(p.get("IdPedidoLora", p.get("id_pedido", ""))),
            int(_to_float(p.get("Línea", p.get("linea", 0)))),
        )
    )

    stock_simulado: dict[str, dict] = {}
    asignaciones: list[dict] = []
    simulaciones: list[dict] = []

    for pedido in pedidos_meta:
        candidatos_raw = get_candidatos_cb(pedido) or []
        candidatos: list[dict] = []
        for cand in deepcopy(candidatos_raw):
            score, flex_txt = calcular_score_candidato(cand, pedido=pedido, scoring=scoring)
            utilidad = calcular_utilidad_operativa(pedido, cand)
            cand.update(utilidad)
            rank_var, txt_var = _compatibilidad_varietal(pedido, cand)
            cand["compatibilidad_varietal_rank"] = rank_var
            cand["compatibilidad_varietal"] = txt_var
            cand["Grupo varietal stock"] = cand.get("Grupo varietal stock", cand.get("grupo_varietal_stock", cand.get("Grupo varietal", "")))
            cand["Grupo varietal pedido"] = pedido.get("Grupo varietal", pedido.get("grupo_varietal", ""))
            cand["score_simulacion"] = score
            cand["flexibilidad_usada_simulacion"] = ("Variedad exacta" if rank_var == 0 else "Mismo grupo varietal" if rank_var == 1 else "Grupo varietal alternativo" if rank_var == 2 else "Incompatible")
            cand["score_total"] = score + int(cand.get("penalizacion_riesgo", 0) or 0)
            if rank_var >= 99:
                continue
            perfil_stock = cand.get("perfil_stock", "")
            perfil_conf = _norm_text(pedido.get("perfil_confeccion", "")) or detectar_perfil_confeccion(pedido)
            cat_pedido = _norm_text(pedido.get("Categoría", pedido.get("categoria", "")))
            subcands: list[dict] = []
            if perfil_stock == "ALMACEN_INDUSTRIAL":
                if perfil_conf == "EXIGENTE" and cat_pedido == "I":
                    subcands = [dict(cand, subpool_calidad="PRIMERA", categoria_util="I", kg_utiles_finales=_to_float(cand.get("kg_primera_estimado", 0)))]
                elif perfil_conf == "MALLA":
                    subcands = [
                        dict(cand, subpool_calidad="SEGUNDA", categoria_util="II", kg_utiles_finales=_to_float(cand.get("kg_segunda_estimado", 0))),
                        dict(cand, subpool_calidad="PRIMERA", categoria_util="I", kg_utiles_finales=_to_float(cand.get("kg_primera_estimado", 0))),
                    ]
                elif cat_pedido == "II":
                    subcands = [dict(cand, subpool_calidad="SEGUNDA", categoria_util="II", kg_utiles_finales=_to_float(cand.get("kg_segunda_estimado", 0)))]
                else:
                    subcands = [dict(cand, subpool_calidad="PRIMERA", categoria_util="I", kg_utiles_finales=_to_float(cand.get("kg_primera_estimado", 0)))]
            else:
                subcands = [dict(cand, subpool_calidad="MIXTO", categoria_util=cand.get("Categoría", ""), kg_utiles_finales=_to_float(cand.get("kg_utiles_estimados", 0)))]

            for sc in subcands:
                pool_id = _build_pool_id(sc) + f"|{_norm_text(sc.get('subpool_calidad', 'MIXTO'))}"
                sc["pool_id"] = pool_id
                if pool_id not in stock_simulado:
                    stock_simulado[pool_id] = {
                        "kg_fisicos": _to_float(sc.get("kg_fisicos", 0)),
                        "kg_primera_inicial": _to_float(sc.get("kg_primera_estimado", 0)),
                        "kg_segunda_inicial": _to_float(sc.get("kg_segunda_estimado", 0)),
                        "kg_utiles_finales": _to_float(sc.get("kg_utiles_finales", 0)),
                        "kg_restante_simulado": _to_float(sc.get("kg_utiles_finales", 0)),
                        "origen": sc.get("Origen", sc.get("origen", "")),
                        "variedad": sc.get("Variedad stock", sc.get("variedad_stock", "")),
                        "grupo_varietal": sc.get("Grupo varietal stock", ""),
                        "calibre": sc.get("Calibre stock", sc.get("calibre_stock", "")),
                        "categoria": sc.get("Categoría", sc.get("categoria_stock", "")),
                        "subpool_calidad": sc.get("subpool_calidad", "MIXTO"),
                    }
                candidatos.append(sc)
        candidatos = ordenar_candidatos_simulacion(candidatos)
        acumulado_potencial = 0.0
        for cand in candidatos:
            acumulado_potencial += _to_float(cand.get("kg_utiles_finales", 0))
            cand["cobertura_acumulada"] = acumulado_potencial

        kg_necesario = _kg_pendiente_linea(pedido)
        pendiente = kg_necesario
        asignado = 0.0
        for cand in candidatos:
            if pendiente <= 0:
                break
            pool = stock_simulado.get(cand["pool_id"], {})
            antes = _to_float(pool.get("kg_restante_simulado", 0))
            kg_asign = min(pendiente, antes)
            despues = max(0.0, antes - kg_asign)
            pool["kg_restante_simulado"] = despues
            cand["kg_restante_antes"] = antes
            cand["kg_asignado_simulado"] = kg_asign
            cand["kg_restante_despues"] = despues
            pendiente -= kg_asign
            asignado += kg_asign
            if kg_asign > 0:
                asignaciones.append({"pedido_id": pedido.get("IdPedidoLora", pedido.get("id_pedido", "")), "pool_id": cand["pool_id"], "kg_asignados": kg_asign, "origen": cand.get("Origen", ""), "tipo_cobertura": cand.get("Tipo cobertura", ""), "score": cand.get("score_total", 0), "riesgo": cand.get("riesgo_operativo", "")})

        estado_global = "TOTAL" if asignado >= kg_necesario and kg_necesario > 0 else "PARCIAL" if asignado > 0 else "INSUFICIENTE"
        simulaciones.append({"pedido": pedido, "kg_necesario": kg_necesario, "kg_pendientes": kg_necesario, "estado": estado_global, "kg_cobertura_simulada": asignado, "kg_asignado_simulado": asignado, "kg_faltante_simulado": max(0.0, kg_necesario - asignado), "estado_global": estado_global, "kg_potencial_fisico": sum(_to_float(c.get("kg_fisicos", 0)) for c in candidatos), "kg_potencial_util": acumulado_potencial, "candidatos": candidatos})

    conteo_pooles: dict[str, int] = {}
    for sim in simulaciones:
        for c in sim["candidatos"]:
            conteo_pooles[c["pool_id"]] = conteo_pooles.get(c["pool_id"], 0) + 1
    for sim in simulaciones:
        for c in sim["candidatos"]:
            c["compartido"] = "Sí" if conteo_pooles.get(c["pool_id"], 0) > 1 else "No"
    return simulaciones, asignaciones, stock_simulado


def _clasificar_perfil_calibre(cal_set: set[str]) -> str:
    altos = {"7", "8", "9", "10"}
    medios = {"4", "5", "6"}
    bajos = {"0", "1", "2", "3"}
    grupos = set()
    if cal_set & altos:
        grupos.add("gruesa")
    if cal_set & medios:
        grupos.add("media")
    if cal_set & bajos:
        grupos.add("fina")
    if not grupos:
        return "Sin histórico suficiente"
    if len(grupos) == 1:
        return {"gruesa": "Fruta gruesa", "media": "Fruta media", "fina": "Fruta fina"}[next(iter(grupos))]
    return "Fruta media/fina" if grupos == {"media", "fina"} else "Perfil mixto"


def _calcular_necesidades(simulaciones: list[dict]) -> tuple[list[dict], dict]:
    agrupado: dict[tuple, dict] = {}
    for sim in simulaciones:
        falt = _to_float(sim.get("kg_faltante_simulado", 0))
        if falt <= 0:
            continue
        p = sim.get("pedido", {})
        variedad = p.get("Variedad", "")
        grupo_var = p.get("Grupo varietal", p.get("grupo_varietal", ""))
        calibre = p.get("Calibre", "")
        categoria = p.get("Categoría", "")
        grupo_conf = p.get("grupo_confeccion") or p.get("GrupoConfeccion") or p.get("GRUPO") or p.get("grupo") or "DESCONOCIDO"
        perfil_conf = _norm_text(p.get("perfil_confeccion")) or detectar_perfil_confeccion_desde_grupo(grupo_conf)
        key = (p.get("fecha_salida", ""), p.get("bloque_temporal", ""), variedad, grupo_var, calibre, categoria, grupo_conf, perfil_conf)
        if key not in agrupado:
            agrupado[key] = {"kg_utiles_faltantes": 0.0, "pedidos_afectados": 0, "prioridad_fecha": int(_to_float(p.get("prioridad_fecha", 9999))), "candidatos": []}
        agrupado[key]["kg_utiles_faltantes"] += falt
        agrupado[key]["pedidos_afectados"] += 1
        agrupado[key]["candidatos"].extend([c for c in sim.get("candidatos", []) if detectar_perfil_stock(c) == "CAMPO_REAL"])

    rows = []
    for key, acc in sorted(agrupado.items(), key=lambda kv: kv[1]["prioridad_fecha"]):
        fecha, bloque, variedad, grupo_var, calibre, categoria, grupo_conf, perfil_conf = key
        cal_set = PlanningRepository.normalizar_calibre_a_set(calibre)
        perfil_recomendado = _clasificar_perfil_calibre(cal_set)
        kg_falt = acc["kg_utiles_faltantes"]
        hist = acc["candidatos"]
        pct_cal = None
        pct_destrio = None
        primera_pct = 0.80
        if hist and cal_set:
            peso = sum(max(_to_float(c.get("kg_fisicos", 0)), 1.0) for c in hist)
            if peso > 0:
                sum_cal = 0.0
                sum_destrio = 0.0
                for c in hist:
                    w = max(_to_float(c.get("kg_fisicos", 0)), 1.0)
                    cal_part = sum(_parse_percent_like(c.get(f"%Cal{n}")) or 0.0 for n in cal_set)
                    sum_cal += cal_part * w
                    podr, lin, mesa = extraer_componentes_destrio_historico(c)
                    sum_destrio += ((podr or 0.0) + (lin or 0.0) + (mesa or 0.0)) * w
                pct_cal = sum_cal / peso
                pct_destrio = min(max(sum_destrio / peso, 0.0), 1.0)
        aprove = None
        kg_campo = None
        if pct_cal is not None and pct_destrio is not None:
            factor_conf = 1.0 if perfil_conf == "MALLA" else primera_pct
            aprove = pct_cal * (1 - pct_destrio) * factor_conf
            if aprove > 0:
                kg_campo = kg_falt / aprove
        rows.append({
            "Prioridad temporal": bloque,
            "Fecha límite": fecha,
            "Variedad": variedad,
            "Grupo varietal": grupo_var,
            "Calibre necesario": calibre,
            "Categoría": categoria,
            "Calidad necesaria": "PRIMERA+SEGUNDA" if perfil_conf == "MALLA" else ("PRIMERA" if _norm_text(categoria) == "I" else "SEGUNDA"),
            "Grupo confección": grupo_conf,
            "Perfil confección": perfil_conf,
            "Kg útiles faltantes": formatear_kg(kg_falt),
            "Kg campo estimados": formatear_kg(kg_campo) if kg_campo is not None else "Sin histórico",
            "% aprovechamiento esperado": f"{(aprove*100):.1f}%" if aprove is not None else "Sin histórico",
            "% destrío esperado": f"{(pct_destrio*100):.1f}%" if pct_destrio is not None else "Sin histórico",
            "Perfil recomendado": perfil_recomendado if kg_campo is not None else "Sin histórico suficiente",
            "Pedidos afectados": int(acc["pedidos_afectados"]),
            "__prioridad__": acc["prioridad_fecha"],
            "__tags__": ("prio_hoy",) if acc["prioridad_fecha"] <= 1 else ("prio_23",) if acc["prioridad_fecha"] <= 3 else ("prio_future",),
        })
    total_falt = sum(_to_float(r["Kg útiles faltantes"].replace(".", "").replace(",", ".")) for r in rows) if rows else 0.0
    total_campo = sum(_to_float(r["Kg campo estimados"].replace(".", "").replace(",", ".")) for r in rows if r["Kg campo estimados"] != "Sin histórico")
    return rows, {"n": len(rows), "kg_falt": total_falt, "kg_campo": total_campo}


def generar_diagnostico_operativo(pedidos_resultado: list[dict], necesidades: list[dict], sobrantes: list[dict]) -> dict:
    total_pedidos = len(pedidos_resultado)
    total_cubiertos = sum(1 for p in pedidos_resultado if p.get("Estado global") == "TOTAL")
    total_parciales = sum(1 for p in pedidos_resultado if p.get("Estado global") == "PARCIAL")
    total_insuficientes = sum(1 for p in pedidos_resultado if p.get("Estado global") == "INSUFICIENTE")
    kg_faltantes = sum(_to_float(r.get("Kg útiles faltantes", 0)) for r in necesidades)
    kg_sobrantes = sum(_to_float(r.get("Kg restante total", 0)) for r in sobrantes)

    def _top(rows: list[dict], key: str, kg_key: str, limit: int = 3) -> list[str]:
        agg: dict[str, float] = {}
        for row in rows:
            k = _norm_text(row.get(key, "")) or "N/D"
            agg[k] = agg.get(k, 0.0) + _to_float(row.get(kg_key, 0))
        return [k for k, _ in sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:limit]]

    diagnostico = {
        "total_pedidos": total_pedidos,
        "total_cubiertos": total_cubiertos,
        "total_parciales": total_parciales,
        "total_insuficientes": total_insuficientes,
        "kg_faltantes": kg_faltantes,
        "kg_sobrantes": kg_sobrantes,
        "calibres_con_mas_sobrante": _top(sobrantes, "Calibre", "Kg restante total"),
        "calibres_con_mas_faltante": _top(necesidades, "Calibre necesario", "Kg útiles faltantes"),
        "variedades_con_mas_sobrante": _top(sobrantes, "Variedad", "Kg restante total"),
        "variedades_con_mas_faltante": _top(necesidades, "Variedad", "Kg útiles faltantes"),
    }

    alertas: list[str] = []
    recomendaciones_comerciales: list[str] = []
    recomendaciones_campo: list[str] = []
    recomendaciones_produccion: list[str] = []
    if kg_faltantes == 0:
        diagnostico["estado_general"] = "OK"
        diagnostico["resumen"] = "No es necesario recolectar para cubrir los pedidos seleccionados."
    else:
        diagnostico["estado_general"] = "FALTANCIAS"
        diagnostico["resumen"] = "Hay pedidos que no quedan cubiertos con el stock simulado."
        alertas.append("Falta fruta para cubrir todos los pedidos.")
        recomendaciones_campo.append("Conviene recolectar fruta del perfil de mayor faltante.")

    if kg_sobrantes > 0:
        alertas.append("Existe sobrante útil tras cubrir pedidos.")
    if kg_sobrantes > 0 and kg_faltantes == 0:
        recomendaciones_comerciales.append("Buscar salida comercial para los sobrantes principales.")

    origenes = {_canonicalizar_origen(r.get("Origen", "")) for r in sobrantes}
    if "ALMACEN_INDUSTRIAL" in origenes:
        recomendaciones_produccion.append("Priorizar salida de almacén industrial para evitar deterioro.")
    if "CAMPO_REAL" in origenes:
        recomendaciones_campo.append("Evitar recolectar ese perfil si no hay nuevos pedidos.")

    diagnostico["alertas"] = alertas
    diagnostico["recomendaciones_comerciales"] = recomendaciones_comerciales
    diagnostico["recomendaciones_campo"] = recomendaciones_campo
    diagnostico["recomendaciones_produccion"] = recomendaciones_produccion
    return diagnostico


def generar_acciones_sugeridas(diagnostico: dict) -> list[str]:
    acciones: list[str] = []
    if diagnostico.get("kg_faltantes", 0) > 0:
        top_cal = (diagnostico.get("calibres_con_mas_faltante") or ["perfil prioritario"])[0]
        acciones.extend([
            f"Recolectar partidas con predominio {top_cal}.",
            "Revisar si se permite variedad alternativa dentro del grupo.",
            "No aceptar nuevos pedidos de este calibre hasta confirmar disponibilidad.",
        ])
    elif diagnostico.get("kg_sobrantes", 0) > 0:
        top_var = (diagnostico.get("variedades_con_mas_sobrante") or ["variedad principal"])[0]
        top_cal = (diagnostico.get("calibres_con_mas_sobrante") or ["calibre principal"])[0]
        acciones.extend([
            f"Captar pedidos para {top_var} {top_cal}.",
            "Revisar oportunidades de malla para calibres con segunda disponible.",
            "Priorizar salida de ALMACEN_INDUSTRIAL.",
        ])
    else:
        acciones.append("La planificación actual cubre los pedidos sin necesidad de recolección adicional.")
    return acciones


def construir_inventario_global_simulado(candidatos_globales: list[dict]) -> dict[str, dict]:
    inventario: dict[str, dict] = {}
    rows = deepcopy(candidatos_globales or [])
    logger.info("Inventario global raw ejemplo=%s", rows[0] if rows else None)
    pools_normalizados = [normalizar_pool_inventario_global(c) for c in rows]
    logger.info(
        "Inventario global normalizado pools=%s total_kg=%s calibres=%s grupos=%s origenes=%s",
        len(pools_normalizados),
        sum(float(p.get("Kg disponibles", 0) or 0) for p in pools_normalizados),
        sorted(set(str(p.get("Calibre stock", "")) for p in pools_normalizados)),
        sorted(set(str(p.get("Grupo varietal stock", "")) for p in pools_normalizados)),
        sorted(set(str(p.get("Origen", "")) for p in pools_normalizados)),
    )
    for cand in pools_normalizados:
        origen = _canonicalizar_origen(cand.get("Origen", cand.get("origen", "")))
        kg_fisicos = _to_float(
            cand.get(
                "Kg disponibles",
                cand.get("kg_disponibles", cand.get("kg_fisicos", cand.get("Kg stock", 0))),
            )
        )
        if kg_fisicos <= 0:
            continue
        cand["Origen"] = origen
        cand["origen"] = origen
        pool_id = _build_pool_id(cand) + "|FISICO"
        if pool_id not in inventario:
            inventario[pool_id] = {
                "kg_fisicos": 0.0,
                "kg_primera_inicial": 0.0,
                "kg_segunda_inicial": 0.0,
                "kg_utiles_finales": 0.0,
                "kg_restante_simulado": 0.0,
                "origen": origen,
                "variedad": cand.get("Variedad stock", cand.get("variedad_stock", "")),
                "grupo_varietal": cand.get("Grupo varietal stock", cand.get("Grupo varietal", cand.get("GrupoVarietal", cand.get("grupo_varietal", "")))),
                "calibre": cand.get("Calibre stock", cand.get("calibre_stock", "")),
                "categoria": cand.get("Categoría", cand.get("categoria_stock", "")),
                "subpool_calidad": "FISICO",
            }
        inventario[pool_id]["kg_fisicos"] += kg_fisicos
        inventario[pool_id]["kg_utiles_finales"] += kg_fisicos
        inventario[pool_id]["kg_restante_simulado"] += kg_fisicos
    logger.info(
        "Inventario físico global construido: pools=%s kg_total=%s kg_libre=%s calibres=%s origenes=%s",
        len(inventario),
        sum(_to_float(p.get("kg_fisicos", 0)) for p in inventario.values()),
        sum(_to_float(p.get("kg_restante_simulado", 0)) for p in inventario.values()),
        sorted(set(str(p.get("calibre", "")) for p in inventario.values())),
        sorted(set(str(p.get("origen", "")) for p in inventario.values())),
    )
    return inventario


def _pool_id_fisico(pool_id: str) -> str:
    pid = str(pool_id or "")
    for sufijo in ("|PRIMERA", "|SEGUNDA", "|MIXTO", "|FISICO"):
        if pid.endswith(sufijo):
            return pid[: -len(sufijo)] + "|FISICO"
    return pid + "|FISICO" if pid else ""


def _kg_pendiente_linea(pedido: dict) -> float:
    for key in (
        "Kg pendiente",
        "Kg pendientes",
        "Kg pedidos pendientes",
        "kg_pendiente",
        "kg_pendientes",
        "Kg pedido teórico",
    ):
        if key in pedido and pedido.get(key) not in (None, ""):
            return _to_float(pedido.get(key, 0))
    return 0.0


def normalizar_pedido_para_simulacion(pedido: dict) -> dict:
    item = dict(pedido or {})
    item["Variedad"] = item.get("Variedad") or item.get("Variedad Coop") or item.get("variedad", "")
    item["Grupo varietal"] = item.get("Grupo varietal") or item.get("grupo_varietal", "")
    item["Categoría"] = item.get("Categoría") or item.get("Categoria") or item.get("categoria", "")
    kg_pend = _kg_pendiente_linea(item)
    item["Kg pedidos pendientes"] = kg_pend
    item["Kg pendiente"] = kg_pend
    item["kg_pendiente"] = kg_pend
    item["kg_pendientes"] = kg_pend
    item["Tipo línea"] = "Pedido"
    return item


def _pedido_unico_key(pedido: dict) -> str:
    pedido_id = str(pedido.get("IdPedidoLora", "") or "").strip()
    if pedido_id:
        return f"ID:{pedido_id}"
    fecha = str(pedido.get("Fecha salida", pedido.get("fecha_salida", pedido.get("FechaSalida", ""))) or "").strip()
    cliente = str(pedido.get("Cliente", "") or "").strip()
    variedad = str(pedido.get("Variedad", "") or "").strip()
    calibre = str(pedido.get("Calibre", "") or "").strip()
    linea = str(pedido.get("Línea", pedido.get("Linea", pedido.get("linea", ""))) or "").strip()
    return f"FB:{fecha}|{cliente}|{variedad}|{calibre}|{linea}"


def calcular_horizonte_cobertura(
    pedidos: list[dict],
    inventario_global: dict[str, dict],
    get_candidatos_cb,
    scoring: dict | None = None,
    policy: dict | None = None,
) -> dict:
    politica = dict(policy or {})
    incluir_campo_real = bool(politica.get("allow_campo_real", True))
    incluir_campo_estimado = bool(politica.get("allow_campo_estimado", False))
    logger.info(
        "Horizonte input: pedidos=%s inventario_pools=%s kg_pedidos=%s",
        len(pedidos or []),
        len(inventario_global or {}),
        sum(_kg_pendiente_linea(p) for p in (pedidos or [])),
    )
    simulaciones, _asignaciones, stock_simulado = simular_asignacion_global(pedidos, get_candidatos_cb, scoring=scoring)
    logger.info(
        "Horizonte simulaciones: pedidos=%s kg_necesario=%s kg_asignado=%s kg_faltante=%s",
        len(simulaciones),
        sum(_to_float(s.get("kg_necesario", 0)) for s in simulaciones),
        sum(_to_float(s.get("kg_asignado_simulado", 0)) for s in simulaciones),
        sum(_to_float(s.get("kg_faltante_simulado", 0)) for s in simulaciones),
    )
    kg_pend_total = sum(_to_float(s.get("kg_necesario", 0)) for s in simulaciones)
    kg_asig_total = sum(_to_float(s.get("kg_asignado_simulado", 0)) for s in simulaciones)
    kg_falt_total = sum(_to_float(s.get("kg_faltante_simulado", 0)) for s in simulaciones)
    resumen_fecha: dict[tuple[str, str], dict] = {}
    primer_fallo = None
    faltantes: dict[tuple[str, str, str, str, str, str], dict] = {}
    for sim in simulaciones:
        ped = sim.get("pedido", {})
        fecha_dt = _normalizar_fecha_salida(ped)
        fecha = fecha_dt.isoformat() if fecha_dt else ""
        fecha_raw = ped.get("fecha_salida") or ped.get("Fecha salida") or ped.get("FechaSalida") or ped.get("fecha") or ped.get("salida")
        bloque = _bloque_temporal_horizonte(fecha_raw, ped.get("bloque_temporal", ""), date.today())
        key = (fecha, bloque)
        reg = resumen_fecha.setdefault(key, {"Fecha salida": fecha, "Bloque temporal": bloque, "Nº pedidos": 0, "Nº líneas": 0, "Kg pedidos": 0.0, "Kg cubiertos": 0.0, "Kg faltantes": 0.0, "Calibre crítico": "", "Grupo varietal crítico": "", "Grupo confección crítico": "", "Acción sugerida": "", "_fecha_critica": None, "_pedidos_unicos": set()})
        reg["Nº líneas"] += 1
        reg["_pedidos_unicos"].add(_pedido_unico_key(ped))
        reg["Kg pedidos"] += _kg_pendiente_linea(ped)
        reg["Kg cubiertos"] += _to_float(sim.get("kg_asignado_simulado", 0))
        falt = _to_float(sim.get("kg_faltante_simulado", 0))
        reg["Kg faltantes"] += falt
        if falt > _to_float(reg.get("Kg faltantes", 0)):
            reg["Calibre crítico"] = str(ped.get("Calibre", ""))
            reg["Grupo varietal crítico"] = str(ped.get("Grupo varietal", ped.get("grupo_varietal", "")))
            reg["Grupo confección crítico"] = str(ped.get("grupo_confeccion", ped.get("GrupoConfeccion", "")))
            reg["_fecha_critica"] = fecha
        if falt > 0 and not primer_fallo:
            primer_fallo = {"Fecha salida": fecha, "Cliente": ped.get("Cliente", ""), "Variedad": ped.get("Variedad", ""), "Grupo varietal": ped.get("Grupo varietal", ped.get("grupo_varietal", "")), "Calibre": ped.get("Calibre", ""), "Categoría": ped.get("Categoría", ""), "Grupo confección": ped.get("grupo_confeccion", ped.get("GrupoConfeccion", "")), "Kg faltantes": falt, "Motivo probable": f"Falta {ped.get('Calibre', '')} {ped.get('Categoría', '')} en {ped.get('Grupo varietal', ped.get('grupo_varietal', ''))}"}
        if falt > 0:
            perfil_key = (str(ped.get("Grupo varietal", ped.get("grupo_varietal", ""))), str(ped.get("Variedad", "")), str(ped.get("Calibre", "")), "PRIMERA" if _norm_text(ped.get("Categoría", "")) == "I" else "SEGUNDA", str(ped.get("Categoría", "")), str(ped.get("grupo_confeccion", ped.get("GrupoConfeccion", ""))))
            agg = faltantes.setdefault(perfil_key, {"Kg faltantes": 0.0, "Primera fecha afectada": fecha or "", "Nº pedidos afectados": 0})
            agg["Kg faltantes"] += falt
            agg["Nº pedidos afectados"] += 1
            if fecha and (not agg["Primera fecha afectada"] or fecha < agg["Primera fecha afectada"]):
                agg["Primera fecha afectada"] = fecha
    resumen_por_fecha = []
    fechas_ordenadas = sorted(resumen_fecha.items(), key=lambda x: x[0][0] or "9999-99-99")
    fecha_limite = None
    fecha_limite_dt = None
    dias_cubiertos = 0
    hay_fechas_validas = False
    hoy = date.today()
    for (fecha, _bloque), reg in fechas_ordenadas:
        reg["Nº pedidos"] = len(reg.pop("_pedidos_unicos", set()))
        fecha_dt = _parse_fecha_salida(fecha)
        if fecha_dt:
            hay_fechas_validas = True
        if reg["Kg faltantes"] <= 0:
            estado = "OK"
            fecha_limite = fecha or fecha_limite
            if fecha_dt:
                dias_cubiertos += 1
                fecha_limite_dt = fecha_dt
        elif reg["Kg cubiertos"] > 0:
            estado = "PARCIAL"
        else:
            estado = "INSUFICIENTE"
        reg["Estado día"] = estado
        if reg["Kg faltantes"] <= 0:
            reg["Acción sugerida"] = "Día cubierto con stock actual"
        elif "6/7" in _norm_text(reg.get("Calibre crítico", "")):
            reg["Acción sugerida"] = "Recolectar o buscar stock compatible CAL 6/7"
        elif "MALLA" in _norm_text(reg.get("Grupo confección crítico", "")):
            reg["Acción sugerida"] = "Puede revisarse uso de primera + segunda"
        elif estado == "PARCIAL":
            reg["Acción sugerida"] = "Revisar faltantes / recolectar calibre crítico"
        else:
            reg["Acción sugerida"] = "Recolectar / buscar alternativa"
        reg.pop("_fecha_critica", None)
        logger.info(
            "Horizonte fecha=%s pedidos=%s lineas=%s kg_pedidos=%s kg_cubiertos=%s kg_faltantes=%s estado=%s",
            fecha,
            reg.get("Nº pedidos", 0),
            reg.get("Nº líneas", 0),
            reg.get("Kg pedidos", 0.0),
            reg.get("Kg cubiertos", 0.0),
            reg.get("Kg faltantes", 0.0),
            reg.get("Estado día", ""),
        )
        resumen_por_fecha.append(reg)
    limite_date = _parse_fecha_salida(fecha_limite) if fecha_limite else None
    if hay_fechas_validas:
        dias_autonomia = dias_cubiertos
    else:
        dias_autonomia = None
    fecha_limite_display = fecha_limite_dt.strftime("%d/%m/%Y") if fecha_limite_dt else ("Fecha no disponible" if not hay_fechas_validas else "")
    estado_horizonte = "OK" if kg_falt_total <= 0 else "RIESGO" if kg_asig_total > 0 else "INSUFICIENTE"
    faltantes_rows = []
    for k, v in faltantes.items():
        gvar, var, cal, calidad, cat, gconf = k
        accion = "Recolectar/seleccionar fruta con mayor porcentaje de primera" if calidad == "PRIMERA" else "Usar segunda disponible o estándar"
        if "MALLA" in _norm_text(gconf):
            accion = "Puede cubrirse con primera + segunda"
        faltantes_rows.append({"Grupo varietal": gvar, "Variedad": var, "Calibre": cal, "Calidad necesaria": calidad, "Categoría": cat, "Grupo confección": gconf, "Kg faltantes": v["Kg faltantes"], "Primera fecha afectada": v["Primera fecha afectada"], "Nº pedidos afectados": v["Nº pedidos afectados"], "Acción sugerida": accion})
    stock_restante = []
    for pool_id, pool in (stock_simulado or {}).items():
        kg_ini = _to_float(pool.get("kg_utiles_finales", pool.get("kg_fisicos", 0)))
        kg_res = _to_float(pool.get("kg_restante_simulado", kg_ini))
        kg_asig = max(0.0, kg_ini - kg_res)
        stock_restante.append({"Origen": pool.get("origen", ""), "Grupo varietal": pool.get("grupo_varietal", ""), "Variedad": pool.get("variedad", ""), "Calibre": pool.get("calibre", ""), "Calidad útil / FISICO": pool.get("subpool_calidad", "FISICO"), "Kg iniciales": kg_ini, "Kg asignados": kg_asig, "Kg restantes": kg_res, "% restante": (kg_res / kg_ini * 100.0) if kg_ini > 0 else 0.0, "Pool ID": pool_id})
    recomendaciones = []
    if kg_falt_total > 0:
        recomendaciones.append("Sí, se requiere recolección para ampliar cobertura.")
    else:
        recomendaciones.append("No es necesario recolectar para cubrir los pedidos seleccionados.")
    recomendaciones.append(f"Política campo real: {'habilitado' if incluir_campo_real else 'deshabilitado'}")
    recomendaciones.append(f"Política campo estimado: {'habilitado' if incluir_campo_estimado else 'deshabilitado'}")
    logger.info(
        "Horizonte resumen fechas=%s",
        [(r["Fecha salida"], r["Kg pedidos"], r["Estado día"]) for r in resumen_por_fecha],
    )
    return {"fecha_limite_cubierta": fecha_limite_display, "dias_autonomia": dias_autonomia, "estado_horizonte": estado_horizonte, "pedidos_cubiertos": sum(1 for s in simulaciones if s.get('estado_global') == 'TOTAL'), "pedidos_parciales": sum(1 for s in simulaciones if s.get('estado_global') == 'PARCIAL'), "pedidos_insuficientes": sum(1 for s in simulaciones if s.get('estado_global') == 'INSUFICIENTE'), "kg_pendientes_total": kg_pend_total, "kg_asignados_total": kg_asig_total, "kg_faltantes_total": kg_falt_total, "primer_fallo": primer_fallo or {}, "resumen_por_fecha": resumen_por_fecha, "faltantes_por_calibre": sorted(faltantes_rows, key=lambda r: (r["Primera fecha afectada"] or "9999-99-99", -r["Kg faltantes"])), "stock_restante_por_calibre": stock_restante, "recomendaciones": recomendaciones, "hay_fechas_validas": hay_fechas_validas}


def abrir_simulacion_asignacion(parent: tk.Misc, pedidos: list[dict], get_candidatos_cb, scoring: dict | None = None, get_inventario_global_cb=None, pedidos_detalle_horizonte: list[dict] | None = None) -> None:
    popup = tk.Toplevel(parent)
    popup.title("Simulación de asignación")
    popup.geometry("1300x750")

    def _abrir_leyenda() -> None:
        dlg = tk.Toplevel(popup)
        dlg.title("Leyenda de simulación")
        dlg.geometry("760x560")
        dlg.transient(popup)
        dlg.grab_set()
        txt = tk.Text(dlg, wrap="word", padx=12, pady=12)
        txt.pack(fill="both", expand=True)
        leyenda = (
            "A) Colores por origen\n"
            "• Amarillo: ALMACEN_INDUSTRIAL\n"
            "• Verde: ALMACEN_COMERCIAL\n"
            "• Azul: CAMPO_REAL\n"
            "• Morado: CAMPO_ESTIMADO\n"
            "• Gris: DESCONOCIDO\n\n"
            "B) Estados de cobertura\n"
            "• Verde: OK / cubierto\n"
            "• Amarillo: PARCIAL / vigilar\n"
            "• Rojo: INSUFICIENTE / falta fruta\n\n"
            "C) Estados comerciales\n"
            "• NORMAL: stock sin alerta\n"
            "• VIGILAR: stock relevante pendiente de salida\n"
            "• SOBRANTE ALTO: mucho stock libre\n"
            "• ROTACIÓN PRIORITARIA: stock industrial que conviene mover\n\n"
            "D) Conceptos\n"
            "• Kg stock total útil: stock disponible usado para la simulación.\n"
            "• Kg asignados: kilos consumidos virtualmente por pedidos simulados.\n"
            "• Kg libres: stock restante tras la simulación.\n"
            "• % libre: porcentaje que queda sin asignar.\n"
            "• Calidad útil: FISICO, PRIMERA, SEGUNDA o MIXTO según el contexto.\n"
            "• Origen: procedencia operativa del stock.\n\n"
            "E) Nota importante\n"
            "La simulación no descuenta stock real ni reserva fruta. Solo ayuda a decidir.\n"
        )
        txt.insert("1.0", leyenda)
        txt.configure(state="disabled")
        ttk.Button(dlg, text="Cerrar", command=dlg.destroy).pack(pady=(0, 10))

    top_actions = ttk.Frame(popup, padding=(8, 8, 8, 0))
    top_actions.pack(fill="x")
    ttk.Button(top_actions, text="Leyenda", command=_abrir_leyenda).pack(side="right")

    top = ttk.LabelFrame(popup, text="Pedidos pendientes", padding=8)
    top.pack(fill="both", expand=True, padx=8, pady=(8, 4))
    notebook = ttk.Notebook(popup)
    notebook.pack(fill="both", expand=True, padx=8, pady=(4, 8))
    resumen_tab = ttk.Frame(notebook, padding=8)
    horizonte_tab = ttk.Frame(notebook, padding=8)
    sobrantes_tab = ttk.Frame(notebook, padding=8)
    necesidades_tab = ttk.Frame(notebook, padding=8)
    plan_operativo_tab = ttk.Frame(notebook, padding=8)
    riesgos_tab = ttk.Frame(notebook, padding=8)
    tecnico_tab = ttk.Frame(notebook, padding=8)

    pedidos_cols = ["Fecha salida", "Bloque temporal", "Prioridad manual", "Cliente", "Variedad", "Calibre", "Categoría", "Grupo confección", "Perfil confección", "Kg pendientes", "Estado simulación", "Kg cobertura simulada", "Kg asignado global", "Kg faltante global", "Estado global", "Kg potencial físico", "Kg potencial útil"]
    pedidos_tbl = DataTable(top, pedidos_cols)
    pedidos_tbl.pack(fill="both", expand=True)
    pedidos_op_cols = ["Fecha salida", "Bloque temporal", "Variedad", "Calibre", "Categoría", "Grupo confección", "Kg pendientes", "Kg asignado global", "Kg faltante global", "Estado global"]
    pedidos_op_tbl = DataTable(tecnico_tab, pedidos_op_cols)
    pedidos_op_tbl.pack(fill="both", expand=True)

    cand_cols = ["Origen", "Tipo cobertura", "Variedad stock", "Grupo varietal stock", "Grupo varietal pedido", "Compatibilidad variedad", "Calibre stock", "Categoría", "Subpool calidad", "Kg físicos", "% destrío", "Kg destrío", "% primera", "Kg primera", "% segunda", "Kg segunda", "Kg industria", "Kg podrido", "Kg útiles finales", "Kg restante antes", "Kg asignado simulado", "Kg restante después", "Pool ID", "Compartido", "Riesgo", "Motivo riesgo", "Score compat.", "Score total", "Flexibilidad aplicada", "Cobertura acumulada"]
    ttk.Label(tecnico_tab, text="Vista técnica para revisión y depuración.", anchor="w", foreground="#666666").pack(fill="x", pady=(0, 6))
    cand_tbl = DataTable(tecnico_tab, cand_cols)
    cand_tbl.pack(fill="both", expand=True, pady=(0, 6))
    needs_cols = ["Prioridad temporal", "Fecha límite", "Variedad", "Grupo varietal", "Calibre necesario", "Categoría", "Calidad necesaria", "Grupo confección", "Perfil confección", "Kg útiles faltantes", "Kg campo estimados", "% aprovechamiento esperado", "% destrío esperado", "Perfil recomendado", "Pedidos afectados"]
    needs_tbl = DataTable(necesidades_tab, needs_cols)
    needs_tbl.pack(fill="both", expand=True)
    sobrantes_cols = ["Origen", "Variedad", "Grupo varietal", "Calibre", "Categoría stock", "Calidad útil", "Kg físicos iniciales", "Kg primera inicial", "Kg segunda inicial", "Kg asignados primera", "Kg asignados segunda", "Kg restante primera", "Kg restante segunda", "Kg restante total", "% restante", "Pool ID"]
    sobrantes_tbl = DataTable(sobrantes_tab, sobrantes_cols)
    sobrantes_tbl.pack(fill="both", expand=True)
    plan_resumen_box = ttk.LabelFrame(plan_operativo_tab, text="Plan operativo", padding=8)
    plan_resumen_box.pack(fill="x", pady=(0, 6))
    plan_resumen_lbl = ttk.Label(plan_resumen_box, text="", anchor="w", justify="left")
    plan_resumen_lbl.pack(fill="x")
    plan_cols = ["Prioridad", "Tipo acción", "Origen", "Grupo varietal", "Variedad", "Calibre", "Kg afectados", "Fecha límite", "Motivo", "Acción recomendada"]
    plan_tbl = DataTable(plan_operativo_tab, plan_cols)
    plan_tbl.pack(fill="both", expand=True)

    resumen = ttk.Label(popup, text="", anchor="w")
    resumen.pack(fill="x", padx=10, pady=(0, 4))
    detalle = ttk.Label(popup, text="", anchor="w")
    detalle.pack(fill="x", padx=10, pady=(0, 8))
    pedidos_tbl.tree.tag_configure("estado_total", background="#dcedc8")
    pedidos_tbl.tree.tag_configure("estado_parcial", background="#fff3cd")
    pedidos_tbl.tree.tag_configure("estado_insuf", background="#f8d7da")
    cand_tbl.tree.tag_configure("riesgo_bajo", background="#d0f0c0")
    cand_tbl.tree.tag_configure("riesgo_medio", background="#fff8b3")
    cand_tbl.tree.tag_configure("riesgo_alto", background="#f8d7da")

    simulaciones, asignaciones_simuladas, _stock_simulado = simular_asignacion_global(pedidos, get_candidatos_cb, scoring=scoring)
    inventario_global_simulado = dict(_stock_simulado)
    calibres_tecnicos = sorted({
        str(p.get("calibre", "")).strip()
        for p in inventario_global_simulado.values()
        if str(p.get("calibre", "")).strip()
    })
    logger.debug(
        "[DEBUG] pools_tecnicos=%s calibres_tecnicos=%s",
        len(inventario_global_simulado),
        calibres_tecnicos,
    )
    if callable(get_inventario_global_cb):
        inventario_global_simulado = construir_inventario_global_simulado(get_inventario_global_cb() or [])
        calibres_globales = sorted({
            str(p.get("calibre", "")).strip()
            for p in inventario_global_simulado.values()
            if str(p.get("calibre", "")).strip()
        })
        logger.debug(
            "[DEBUG] pools_inventario_global=%s calibres_globales=%s",
            len(inventario_global_simulado),
            calibres_globales,
        )
        for asign in asignaciones_simuladas:
            pool_id_fisico = _pool_id_fisico(asign.get("pool_id", ""))
            pool = inventario_global_simulado.get(pool_id_fisico)
            if not pool:
                logger.warning("No se encontró pool físico para asignación pool_id=%s pool_id_fisico=%s", asign.get("pool_id", ""), pool_id_fisico)
                continue
            pool["kg_restante_simulado"] = max(0.0, _to_float(pool.get("kg_restante_simulado", 0)) - _to_float(asign.get("kg_asignados", 0)))
        kg_total = sum(_to_float(p.get("kg_fisicos", 0)) for p in inventario_global_simulado.values())
        kg_libre = sum(_to_float(p.get("kg_restante_simulado", 0)) for p in inventario_global_simulado.values())
        kg_asignado = max(0.0, kg_total - kg_libre)
        logger.info(
            "Inventario físico tras asignaciones: kg_total=%s kg_asignado=%s kg_libre=%s",
            kg_total,
            kg_asignado,
            kg_libre,
        )
    necesidades_rows, need_tot = _calcular_necesidades(simulaciones)
    resumen_rows: list[dict] = []
    def _grupo_pedido(p: dict) -> str:
        return _norm_text(p.get("grupo_confeccion") or p.get("GrupoConfeccion") or p.get("GRUPO") or p.get("grupo")) or "DESCONOCIDO"

    def _perfil_pedido(p: dict, grupo: str) -> str:
        return _norm_text(p.get("perfil_confeccion")) or detectar_perfil_confeccion_desde_grupo(grupo) or "DESCONOCIDO"

    for simulacion in simulaciones:
        pedido = simulacion["pedido"]
        estado = simulacion["estado_global"]
        tag_estado = "estado_total" if estado == "TOTAL" else "estado_parcial" if estado == "PARCIAL" else "estado_insuf"
        grupo_conf = _grupo_pedido(pedido)
        perfil_conf = _perfil_pedido(pedido, grupo_conf)
        resumen_rows.append({
            "Fecha salida": pedido.get("fecha_salida", pedido.get("Fecha salida", "")),
            "Bloque temporal": pedido.get("bloque_temporal", ""),
            "Prioridad manual": int(_to_float(pedido.get("prioridad_manual", 0))),
            "Cliente": pedido.get("Cliente", ""),
            "Variedad": pedido.get("Variedad", ""),
            "Calibre": pedido.get("Calibre", ""),
            "Categoría": pedido.get("Categoría", ""),
            "Grupo confección": grupo_conf,
            "Perfil confección": perfil_conf,
            "Kg pendientes": formatear_kg(simulacion["kg_pendientes"]),
            "Estado simulación": simulacion.get("estado", "N/A"),
            "Kg cobertura simulada": formatear_kg(simulacion.get("kg_cobertura_simulada", 0)),
            "Kg asignado global": formatear_kg(simulacion["kg_asignado_simulado"]),
            "Kg faltante global": formatear_kg(simulacion["kg_faltante_simulado"]),
            "Estado global": estado,
            "Kg potencial físico": formatear_kg(simulacion["kg_potencial_fisico"]),
            "Kg potencial útil": formatear_kg(simulacion["kg_potencial_util"]),
            "__tags__": (tag_estado,),
        })

    total_pedidos = len(simulaciones)
    totales = sum(1 for s in simulaciones if s["estado_global"] == "TOTAL")
    parciales = sum(1 for s in simulaciones if s["estado_global"] == "PARCIAL")
    insuficientes = sum(1 for s in simulaciones if s["estado_global"] == "INSUFICIENTE")
    kg_pend_total = sum(_to_float(s["kg_necesario"]) for s in simulaciones)
    kg_asig_total = sum(_to_float(s["kg_asignado_simulado"]) for s in simulaciones)
    kg_falt_total = sum(_to_float(s["kg_faltante_simulado"]) for s in simulaciones)
    sobrantes_rows = []
    sob_total = 0.0
    sob_origenes = set()
    for pool_id, pool in inventario_global_simulado.items():
        restante = _to_float(pool.get("kg_restante_simulado", 0))
        inicial = _to_float(pool.get("kg_utiles_finales", 0))
        if restante <= 0:
            continue
        origen = pool.get("origen", "")
        sob_total += restante
        sob_origenes.add(origen)
        pct_rest = (restante / inicial * 100.0) if inicial > 0 else 0.0
        tag = "origen_desconocido"
        o = _canonicalizar_origen(origen)
        if o == "ALMACEN_COMERCIAL":
            tag = "origen_comercial"
        elif o == "ALMACEN_INDUSTRIAL":
            tag = "origen_industrial"
        elif o == "CAMPO_REAL":
            tag = "origen_campo_real"
        elif o == "CAMPO_ESTIMADO":
            tag = "origen_campo_estimado"
        sobrantes_rows.append({
            "Origen": origen,
            "Variedad": pool.get("variedad", ""),
            "Grupo varietal": pool.get("grupo_varietal", ""),
            "Calibre": pool.get("calibre", ""),
            "Categoría stock": pool.get("categoria", ""),
            "Calidad útil": pool.get("subpool_calidad", "MIXTO"),
            "Kg físicos iniciales": formatear_kg(pool.get("kg_fisicos", 0)),
            "Kg primera inicial": formatear_kg(pool.get("kg_primera_inicial", 0)),
            "Kg segunda inicial": formatear_kg(pool.get("kg_segunda_inicial", 0)),
            "Kg asignados primera": formatear_kg(0),
            "Kg asignados segunda": formatear_kg(0),
            "Kg restante primera": formatear_kg(0),
            "Kg restante segunda": formatear_kg(0),
            "Kg restante total": formatear_kg(restante),
            "% restante": f"{pct_rest:.1f}%",
            "Pool ID": pool_id,
            "__tags__": (tag,),
        })
    calibres_sobrantes = sorted({
        str(r.get("Calibre", "")).strip()
        for r in sobrantes_rows
        if str(r.get("Calibre", "")).strip()
    })
    logger.debug(
        "[DEBUG] pools_sobrantes=%s calibres_sobrantes=%s",
        len(sobrantes_rows),
        calibres_sobrantes,
    )
    resumen.configure(text=f"Cobertura global · Pedidos: {total_pedidos} · Totales: {totales} · Parciales: {parciales} · Insuficientes: {insuficientes} · Kg asignados simulados: {formatear_kg(kg_asig_total)} · Kg faltantes simulados: {formatear_kg(kg_falt_total)} · Kg sobrantes útiles: {formatear_kg(sob_total)}")
    detalle.configure(text=f"Necesidad recolección · Nº necesidades: {need_tot['n']} · Kg útiles faltantes: {formatear_kg(need_tot['kg_falt'])} · Kg campo estimados total: {formatear_kg(need_tot['kg_campo'])} · Sobrantes · Kg útiles sobrantes: {formatear_kg(sob_total)} · Orígenes con sobrante: {len(sob_origenes)}")

    pedidos_tbl.set_rows(resumen_rows)
    pedidos_op_tbl.set_rows([{k: r.get(k, "") for k in pedidos_op_cols} for r in resumen_rows])
    needs_tbl.set_rows(necesidades_rows)
    sobrantes_tbl.set_rows(sobrantes_rows)
    needs_tbl.tree.tag_configure("prio_hoy", background="#f8d7da")
    needs_tbl.tree.tag_configure("prio_23", background="#fff3cd")
    needs_tbl.tree.tag_configure("prio_future", background="#dff0d8")
    for tbl in (sobrantes_tbl, cand_tbl):
        tbl.tree.tag_configure("origen_industrial", background="#fff3cd")
        tbl.tree.tag_configure("origen_comercial", background="#dff0d8")
        tbl.tree.tag_configure("origen_campo_real", background="#d9edf7")
        tbl.tree.tag_configure("origen_campo_estimado", background="#e7d9f7")
        tbl.tree.tag_configure("origen_desconocido", background="#eeeeee")

    pedidos_horizonte = list(pedidos_detalle_horizonte or pedidos)
    logger.info(
        "Horizonte pedidos entrada: filas=%s fechas=%s kg_total=%s",
        len(pedidos_horizonte),
        sorted(set(str(p.get("Fecha salida", p.get("fecha_salida", ""))) for p in pedidos_horizonte)),
        sum(_kg_pendiente_linea(p) for p in pedidos_horizonte),
    )
    horizonte = calcular_horizonte_cobertura(
        pedidos=pedidos_horizonte,
        inventario_global=inventario_global_simulado,
        get_candidatos_cb=get_candidatos_cb,
        scoring=scoring,
    )
    diagnostico = generar_diagnostico_operativo(resumen_rows, necesidades_rows, sobrantes_rows)
    acciones = generar_acciones_sugeridas(diagnostico)

    horizonte_frame = ttk.LabelFrame(horizonte_tab, text="Horizonte de cobertura", padding=8)
    horizonte_frame.pack(fill="x", pady=(0, 6))
    hoy_estado = "OK"
    if horizonte.get("resumen_por_fecha"):
        hoy_rows = [r for r in horizonte["resumen_por_fecha"] if _norm_text(r.get("Bloque temporal", "")) == "HOY"]
        if hoy_rows:
            if any(_to_float(r.get("Kg faltantes", 0)) > 0 and _to_float(r.get("Kg cubiertos", 0)) <= 0 for r in hoy_rows):
                hoy_estado = "FALTA"
            elif any(_to_float(r.get("Kg faltantes", 0)) > 0 for r in hoy_rows):
                hoy_estado = "PARCIAL"
            else:
                hoy_estado = "OK"
    primer_fallo = horizonte.get("primer_fallo", {})
    autonomia_txt = f"{horizonte.get('dias_autonomia', 0)} días" if horizonte.get("dias_autonomia") is not None else "No calculable por falta de fecha"
    primer_fallo_txt = "Sin fallo en el rango seleccionado"
    if primer_fallo:
        primer_fallo_txt = (
            f"{_texto_fecha_horizonte(primer_fallo.get('Fecha salida'))} · "
            f"{primer_fallo.get('Calibre', '')} · {primer_fallo.get('Grupo varietal', '')} · "
            f"faltan {formatear_kg(primer_fallo.get('Kg faltantes', 0))} kg"
        )
    kg_falt_10 = sum(_to_float(r.get("Kg faltantes", 0)) for r in horizonte.get("resumen_por_fecha", [])[:10])
    resumen_labels = [
        f"Pedidos hoy: {hoy_estado}",
        f"Autonomía estimada: {autonomia_txt}",
        f"Cubierto hasta: {horizonte.get('fecha_limite_cubierta') or 'Fecha no disponible'}",
        f"Primer fallo: {primer_fallo_txt}",
        f"Kg faltantes próximos 10 días: {formatear_kg(kg_falt_10)}",
        f"Recolección necesaria: {'Sí' if horizonte.get('kg_faltantes_total', 0) > 0 else 'No'}",
    ]
    for idx, txt in enumerate(resumen_labels):
        ttk.Label(horizonte_frame, text=txt).grid(row=idx // 2, column=idx % 2, sticky="w", padx=(0, 16), pady=2)
    horizon_tbl = DataTable(
        horizonte_tab,
        ["Fecha salida", "Bloque temporal", "Nº pedidos", "Nº líneas", "Kg pedidos", "Kg cubiertos", "Kg faltantes", "Estado", "Calibre crítico", "Grupo varietal crítico", "Acción sugerida"],
    )
    horizon_tbl.pack(fill="both", expand=True, pady=(6, 0))
    horizon_tbl.tree.tag_configure("estado_ok", background="#DDF4DD")
    horizon_tbl.tree.tag_configure("estado_parcial", background="#FFF3C4")
    horizon_tbl.tree.tag_configure("estado_insuf", background="#F8D7DA")

    filtros_exec = ttk.LabelFrame(sobrantes_tab, text="Configuración sobrantes", padding=8)
    filtros_exec.pack(fill="x", pady=(0, 6))
    ttk.Label(filtros_exec, text="Agrupar sobrantes por:").grid(row=0, column=0, sticky="w")
    agrupar_sobrantes_var = tk.StringVar(value="Grupo varietal")
    agrupar_sobrantes_combo = ttk.Combobox(
        filtros_exec,
        state="readonly",
        textvariable=agrupar_sobrantes_var,
        values=["Grupo varietal", "Variedad"],
        width=18,
    )
    agrupar_sobrantes_combo.grid(row=0, column=1, sticky="w", padx=(8, 16))
    ttk.Label(filtros_exec, text="Origen sobrantes:").grid(row=0, column=2, sticky="w")
    origen_sobrantes_var = tk.StringVar(value="Todos")
    origen_sobrantes_combo = ttk.Combobox(
        filtros_exec,
        state="readonly",
        textvariable=origen_sobrantes_var,
        values=["Todos", "ALMACEN_INDUSTRIAL", "ALMACEN_COMERCIAL", "CAMPO_REAL", "CAMPO_ESTIMADO", "DESCONOCIDO"],
        width=22,
    )
    origen_sobrantes_combo.grid(row=0, column=3, sticky="w", padx=(8, 16))
    mostrar_detalle_tecnico_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(filtros_exec, text="Mostrar detalle técnico", variable=mostrar_detalle_tecnico_var).grid(row=0, column=4, sticky="w")

    exec_estado = ttk.LabelFrame(resumen_tab, text="Estado global", padding=8)
    exec_estado.pack(fill="x", pady=(0, 6))
    estado_lbl = ttk.Label(exec_estado, text="", foreground=("#2e7d32" if diagnostico["kg_faltantes"] == 0 else "#c62828"))
    estado_lbl.pack(anchor="w")
    diag_frame = ttk.LabelFrame(resumen_tab, text="Diagnóstico automático resumido", padding=8)
    diag_frame.pack(fill="x", pady=(0, 6))
    diag_lines = [diagnostico.get("resumen", "")] + diagnostico.get("alertas", [])
    ttk.Label(diag_frame, text="\n".join([f"• {x}" for x in diag_lines if x])).pack(anchor="w")

    tablas_exec = ttk.Frame(sobrantes_tab)
    tablas_exec.pack(fill="both", expand=True)
    top_sob_tbl = DataTable(tablas_exec, ["Agrupación", "Calibre", "Calidad útil", "Origen", "Kg stock total útil", "Kg asignados", "Kg libres", "% libre", "Estado comercial", "Acción sugerida"])
    top_nec_tbl = DataTable(tablas_exec, ["Variedad", "Grupo varietal", "Calibre necesario", "Calidad necesaria", "Kg faltantes", "Kg campo estimados", "Prioridad temporal", "Acción sugerida"])
    top_sob_tbl.pack(fill="both", expand=True, pady=(0, 4))
    top_nec_tbl.pack_forget()
    top_sob_tbl.tree.tag_configure("origen_industrial", background="#fff3cd")
    top_sob_tbl.tree.tag_configure("origen_comercial", background="#dff0d8")
    top_sob_tbl.tree.tag_configure("origen_campo_real", background="#d9edf7")
    top_sob_tbl.tree.tag_configure("origen_campo_estimado", background="#e7d9f7")
    top_sob_tbl.tree.tag_configure("origen_desconocido", background="#eeeeee")
    top_sob_tbl.tree.tag_configure("estado_normal", background="#DDF4DD")
    top_sob_tbl.tree.tag_configure("estado_vigilar", background="#FFF3C4")
    top_sob_tbl.tree.tag_configure("estado_sobrante_alto", background="#FFE4B5")
    top_sob_tbl.tree.tag_configure("estado_rotacion_prioritaria", background="#FFDDAA")
    acciones_box = ttk.LabelFrame(resumen_tab, text="Acciones sugeridas principales", padding=8)
    acciones_box.pack(fill="x", pady=(6, 0))
    ttk.Label(acciones_box, text="\n".join([f"- {a}" for a in acciones])).pack(anchor="w")
    timeline_rows = []
    for r in horizonte.get("resumen_por_fecha", []):
        estado = r.get("Estado día", "")
        tag = "estado_ok" if estado == "OK" else "estado_parcial" if estado == "PARCIAL" else "estado_insuf"
        timeline_rows.append({
            "Fecha salida": r.get("Fecha salida", ""),
            "Bloque temporal": r.get("Bloque temporal", ""),
            "Nº pedidos": r.get("Nº pedidos", 0),
            "Nº líneas": r.get("Nº líneas", 0),
            "Kg pedidos": formatear_kg(r.get("Kg pedidos", 0)),
            "Kg cubiertos": formatear_kg(r.get("Kg cubiertos", 0)),
            "Kg faltantes": formatear_kg(r.get("Kg faltantes", 0)),
            "Estado": estado,
            "Calibre crítico": r.get("Calibre crítico", ""),
            "Grupo varietal crítico": r.get("Grupo varietal crítico", ""),
            "Acción sugerida": r.get("Acción sugerida", ""),
            "__tags__": (tag,),
        })
    horizon_tbl.set_rows(timeline_rows)

    recolectar_frame = ttk.LabelFrame(horizonte_tab, text="Necesidad de recolección para ampliar cobertura", padding=8)
    recolectar_frame.pack(fill="both", expand=False, pady=(6, 0))
    recolectar_cols = ["Grupo varietal", "Variedad", "Calibre objetivo", "Calidad necesaria", "Kg útiles faltantes", "Primera fecha afectada", "Prioridad", "Acción"]
    recolectar_tbl = DataTable(recolectar_frame, recolectar_cols)
    recolectar_tbl.pack(fill="both", expand=True)
    faltantes_rows = horizonte.get("faltantes_por_calibre", [])
    if faltantes_rows:
        recolectar_tbl.set_rows([{
            "Grupo varietal": r.get("Grupo varietal", ""),
            "Variedad": r.get("Variedad", ""),
            "Calibre objetivo": r.get("Calibre", ""),
            "Calidad necesaria": r.get("Calidad necesaria", ""),
            "Kg útiles faltantes": formatear_kg(r.get("Kg faltantes", 0)),
            "Primera fecha afectada": _texto_fecha_horizonte(r.get("Primera fecha afectada")),
            "Prioridad": "ALTA" if _parse_fecha_salida(r.get("Primera fecha afectada")) and (_parse_fecha_salida(r.get("Primera fecha afectada")) - date.today()).days <= 1 else "MEDIA",
            "Acción": r.get("Acción sugerida", ""),
        } for r in faltantes_rows])
    else:
        recolectar_tbl.set_rows([{"Grupo varietal": "No es necesario recolectar para cubrir los pedidos incluidos en la simulación.", "Variedad": "", "Calibre objetivo": "", "Calidad necesaria": "", "Kg útiles faltantes": "", "Primera fecha afectada": "", "Prioridad": "", "Acción": ""}])

    def _accion_sobrante(calidad_util: str, origen: str) -> str:
        calidad_norm = _norm_text(calidad_util)
        origen_norm = _canonicalizar_origen(origen)
        partes = ["Buscar mallas o pedidos categoría II" if calidad_norm == "SEGUNDA" else "Buscar pedidos exigentes o comerciales" if calidad_norm == "PRIMERA" else "Buscar pedido compatible por calidad mixta"]
        if origen_norm == "ALMACEN_INDUSTRIAL":
            partes.append("Priorizar salida/reproceso")
        elif origen_norm == "ALMACEN_COMERCIAL":
            partes.append("Buscar pedido compatible")
        elif origen_norm == "CAMPO_REAL":
            partes.append("No recolectar salvo nuevo pedido")
        return " · ".join(partes)

    logger.info(
        "Sobrantes ejecutivos rows=%s kg_total=%s kg_libre=%s",
        len(sobrantes_rows),
        sum(_to_float(r.get("Kg stock total útil", _to_float(r.get("Kg asignados primera", 0)) + _to_float(r.get("Kg asignados segunda", 0)) + _to_float(r.get("Kg restante total", 0)))) for r in sobrantes_rows),
        sum(_to_float(r.get("Kg libres", r.get("Kg restante total", 0))) for r in sobrantes_rows),
    )

    def _refresh_resumen_ejecutivo(*_args) -> None:
        origen_filtro = _norm_text(origen_sobrantes_var.get())
        agrupar_por_grupo = _norm_text(agrupar_sobrantes_var.get()) != "VARIEDAD"
        sobrantes_filtrados = []
        for r in sobrantes_rows:
            origen_row = _canonicalizar_origen(r.get("Origen", ""))
            if origen_filtro != "TODOS" and origen_row != origen_filtro:
                continue
            sobrantes_filtrados.append(r)
        calibres_ejecutivo = sorted({
            str(r.get("Calibre", "")).strip()
            for r in sobrantes_filtrados
            if str(r.get("Calibre", "")).strip()
        })
        logger.debug(
            "[DEBUG] pools_ejecutivo=%s origen_filtro=%s agrupar_por_grupo=%s calibres_ejecutivo=%s",
            len(sobrantes_filtrados),
            origen_filtro,
            agrupar_por_grupo,
            calibres_ejecutivo,
        )
        kg_sobrantes_utiles = sum(_to_float(r.get("Kg restante total", 0)) for r in sobrantes_filtrados)
        kg_stock_total = sum(_to_float(r.get("Kg físicos iniciales", 0)) for r in sobrantes_filtrados)
        kg_asignado = max(0.0, kg_stock_total - kg_sobrantes_utiles)
        estado_txt = (
            f"Pedidos: {diagnostico['total_cubiertos']} cubiertos · {diagnostico['total_parciales']} parciales · {diagnostico['total_insuficientes']} insuficientes\n"
            f"Sobrante operativo: {formatear_kg(sum(_to_float(r.get('Kg restante total', 0)) for r in sobrantes_rows))}\n"
            f"Stock libre total: {formatear_kg(kg_sobrantes_utiles)} · Stock total útil: {formatear_kg(kg_stock_total)} · Stock asignado: {formatear_kg(kg_asignado)}\n"
            f"Estado: {'SIN NECESIDAD DE RECOLECCIÓN' if diagnostico['kg_faltantes'] == 0 else 'FALTA FRUTA'}"
        )
        estado_lbl.configure(text=estado_txt)
        group_key = "Grupo varietal" if agrupar_por_grupo else "Variedad"
        top_sob_tbl.tree.heading("Agrupación", text=group_key)
        agrupados: dict[tuple, dict[str, float]] = {}
        for row in sobrantes_filtrados:
            key = (row.get(group_key, ""), row.get("Calibre", ""), row.get("Calidad útil", ""), _canonicalizar_origen(row.get("Origen", "")))
            rec = agrupados.setdefault(key, {"total": 0.0, "libre": 0.0})
            asign = max(0.0, _to_float(row.get("Kg físicos iniciales", 0)) - _to_float(row.get("Kg restante total", 0)))
            libre = _to_float(row.get("Kg restante total", 0))
            rec["total"] += asign + libre
            rec["libre"] += libre
        top_sobrantes = []
        for (agrupador, calibre, calidad, origen), valores in sorted(agrupados.items(), key=lambda it: it[1]["libre"], reverse=True):
            kg_total = valores["total"]
            kg_libre = valores["libre"]
            kg_asig = max(0.0, kg_total - kg_libre)
            pct_libre = (kg_libre / kg_total * 100.0) if kg_total > 0 else 0.0
            estado_comercial = "NORMAL"
            if _canonicalizar_origen(origen) == "ALMACEN_INDUSTRIAL" and kg_libre > 30000:
                estado_comercial = "ROTACIÓN PRIORITARIA"
            elif kg_libre > 50000 and pct_libre > 80:
                estado_comercial = "SOBRANTE ALTO"
            elif kg_libre > 10000:
                estado_comercial = "VIGILAR"
            estado_tag = "estado_normal"
            if estado_comercial == "VIGILAR":
                estado_tag = "estado_vigilar"
            elif estado_comercial == "SOBRANTE ALTO":
                estado_tag = "estado_sobrante_alto"
            elif estado_comercial == "ROTACIÓN PRIORITARIA":
                estado_tag = "estado_rotacion_prioritaria"
            origen_tag = "origen_desconocido"
            oc = _canonicalizar_origen(origen)
            if oc == "ALMACEN_COMERCIAL":
                origen_tag = "origen_comercial"
            elif oc == "ALMACEN_INDUSTRIAL":
                origen_tag = "origen_industrial"
            elif oc == "CAMPO_REAL":
                origen_tag = "origen_campo_real"
            elif oc == "CAMPO_ESTIMADO":
                origen_tag = "origen_campo_estimado"
            top_sobrantes.append({
                group_key: agrupador,
                "Agrupación": agrupador,
                "Calibre": calibre,
                "Calidad útil": calidad,
                "Origen": origen,
                "Kg stock total útil": formatear_kg(kg_total),
                "Kg asignados": formatear_kg(kg_asig),
                "Kg libres": formatear_kg(kg_libre),
                "% libre": f"{pct_libre:.1f}%",
                "Estado comercial": estado_comercial,
                "Acción sugerida": _accion_sobrante(calidad, origen),
                "__tags__": (estado_tag, origen_tag),
            })
        top_sob_tbl.set_rows(top_sobrantes)

    def _toggle_detalle_tecnico(*_args) -> None:
        if mostrar_detalle_tecnico_var.get():
            if not sobrantes_tbl.winfo_manager():
                sobrantes_tbl.pack(fill="both", expand=True, pady=(4, 0))
        else:
            if sobrantes_tbl.winfo_manager():
                sobrantes_tbl.pack_forget()

    _toggle_detalle_tecnico()
    mostrar_detalle_tecnico_var.trace_add("write", _toggle_detalle_tecnico)

    agrupar_sobrantes_combo.bind("<<ComboboxSelected>>", _refresh_resumen_ejecutivo)
    origen_sobrantes_combo.bind("<<ComboboxSelected>>", _refresh_resumen_ejecutivo)
    _refresh_resumen_ejecutivo()
    top_necesidades = []
    for row in sorted(necesidades_rows, key=lambda r: _to_float(r.get("Kg útiles faltantes", 0)), reverse=True)[:5]:
        accion = "Recolectar/seleccionar fruta con mayor primera" if _norm_text(row.get("Calidad necesaria", "")) == "PRIMERA" else "Usar segunda disponible o estándar"
        if _norm_text(row.get("Grupo confección", "")) == "MALLA":
            accion = "Puede cubrirse con primera + segunda"
        top_necesidades.append({"Variedad": row.get("Variedad", ""), "Grupo varietal": row.get("Grupo varietal", ""), "Calibre necesario": row.get("Calibre necesario", ""), "Calidad necesaria": row.get("Calidad necesaria", ""), "Kg faltantes": row.get("Kg útiles faltantes", ""), "Kg campo estimados": row.get("Kg campo estimados", ""), "Prioridad temporal": row.get("Prioridad temporal", ""), "Acción sugerida": accion})
    if top_necesidades:
        top_nec_tbl.set_rows(top_necesidades)
    else:
        top_nec_tbl.set_rows([{"Variedad": "No hay necesidades de recolección para los pedidos incluidos en la simulación.", "Grupo varietal": "", "Calibre necesario": "", "Calidad necesaria": "", "Kg faltantes": "", "Kg campo estimados": "", "Prioridad temporal": "", "Acción sugerida": ""}])

    plan_actions = []
    for need in necesidades_rows:
        kg_falt = _to_float(need.get("Kg útiles faltantes", 0))
        if kg_falt > 0:
            plan_actions.append({
                "Prioridad": "ALTA",
                "Tipo acción": "RECOLECTAR",
                "Origen": "CAMPO_ESTIMADO",
                "Grupo varietal": need.get("Grupo varietal", ""),
                "Variedad": need.get("Variedad", ""),
                "Calibre": need.get("Calibre necesario", ""),
                "Kg afectados": formatear_kg(kg_falt),
                "Fecha límite": need.get("Fecha límite", ""),
                "Motivo": "Faltantes en horizonte/necesidades",
                "Acción recomendada": f"Recolectar {need.get('Grupo varietal', '')} / {need.get('Variedad', '')} / CAL {need.get('Calibre necesario', '')}",
            })
    for r in sobrantes_rows:
        kg_libre = _to_float(r.get("Kg restante total", 0))
        kg_total = _to_float(r.get("Kg físicos iniciales", 0))
        pct_libre = (kg_libre / kg_total * 100.0) if kg_total > 0 else 0.0
        origen = _canonicalizar_origen(r.get("Origen", ""))
        if kg_libre > 50000 and pct_libre > 80:
            plan_actions.append({"Prioridad": "MEDIA", "Tipo acción": "NO RECOLECTAR", "Origen": r.get("Origen", ""), "Grupo varietal": r.get("Grupo varietal", ""), "Variedad": r.get("Variedad", ""), "Calibre": r.get("Calibre", ""), "Kg afectados": formatear_kg(kg_libre), "Fecha límite": "", "Motivo": "Stock libre suficiente", "Acción recomendada": "Evitar recolectar más de este perfil salvo necesidad comercial."})
        if (origen == "ALMACEN_INDUSTRIAL" and kg_libre > 50000) or (kg_libre > 50000 and pct_libre > 80):
            prioridad = "ALTA" if origen == "ALMACEN_INDUSTRIAL" and kg_libre > 50000 else "MEDIA"
            plan_actions.append({"Prioridad": prioridad, "Tipo acción": "DAR SALIDA", "Origen": r.get("Origen", ""), "Grupo varietal": r.get("Grupo varietal", ""), "Variedad": r.get("Variedad", ""), "Calibre": r.get("Calibre", ""), "Kg afectados": formatear_kg(kg_libre), "Fecha límite": "", "Motivo": "ROTACIÓN PRIORITARIA" if prioridad == "ALTA" else "SOBRANTE ALTO", "Acción recomendada": f"Priorizar salida {r.get('Origen', '')} · {r.get('Grupo varietal', '')} · CAL {r.get('Calibre', '')} · {formatear_kg(kg_libre)} libres."})
        if 10000 <= kg_libre <= 50000:
            plan_actions.append({"Prioridad": "MEDIA", "Tipo acción": "VIGILAR", "Origen": r.get("Origen", ""), "Grupo varietal": r.get("Grupo varietal", ""), "Variedad": r.get("Variedad", ""), "Calibre": r.get("Calibre", ""), "Kg afectados": formatear_kg(kg_libre), "Fecha límite": "", "Motivo": "Sobrante medio", "Acción recomendada": f"Vigilar CAL {r.get('Calibre', '')}: stock libre alto y pocos pedidos próximos."})
        if kg_libre > 10000:
            calidad = _norm_text(r.get("Calidad útil", ""))
            accion = "Revisar salida compatible por calibre."
            if calidad == "SEGUNDA":
                accion = "Buscar pedidos categoría II o malla."
            elif calidad == "PRIMERA":
                accion = "Buscar pedidos exigentes o comerciales."
            plan_actions.append({"Prioridad": "MEDIA", "Tipo acción": "OPORTUNIDAD", "Origen": r.get("Origen", ""), "Grupo varietal": r.get("Grupo varietal", ""), "Variedad": r.get("Variedad", ""), "Calibre": r.get("Calibre", ""), "Kg afectados": formatear_kg(kg_libre), "Fecha límite": "", "Motivo": "Sobrante aprovechable", "Acción recomendada": accion})
    if not any(a.get("Tipo acción") == "RECOLECTAR" for a in plan_actions):
        plan_actions.append({"Prioridad": "BAJA", "Tipo acción": "RECOLECTAR", "Origen": "", "Grupo varietal": "", "Variedad": "", "Calibre": "", "Kg afectados": "0", "Fecha límite": "", "Motivo": "Sin faltantes", "Acción recomendada": "No es necesario recolectar para cubrir los pedidos seleccionados."})
    plan_actions.sort(key=lambda r: ({"ALTA": 0, "MEDIA": 1, "BAJA": 2}.get(r.get("Prioridad", "BAJA"), 9), {"RECOLECTAR": 0, "NO RECOLECTAR": 1, "DAR SALIDA": 2, "VIGILAR": 3, "OPORTUNIDAD": 4}.get(r.get("Tipo acción", ""), 9)))
    plan_tbl.set_rows(plan_actions)
    plan_tbl.tree.tag_configure("accion_recolectar", background="#FFE0B2")
    plan_tbl.tree.tag_configure("accion_no_recolectar", background="#E3EDF7")
    plan_tbl.tree.tag_configure("accion_dar_salida", background="#FFF9C4")
    plan_tbl.tree.tag_configure("accion_vigilar", background="#D9EDF7")
    plan_tbl.tree.tag_configure("accion_oportunidad", background="#DFF0D8")
    for item in plan_tbl.tree.get_children():
        vals = plan_tbl.tree.item(item, "values")
        t = vals[1] if len(vals) > 1 else ""
        tag = "accion_oportunidad"
        if t == "RECOLECTAR":
            tag = "accion_recolectar"
        elif t == "NO RECOLECTAR":
            tag = "accion_no_recolectar"
        elif t == "DAR SALIDA":
            tag = "accion_dar_salida"
        elif t == "VIGILAR":
            tag = "accion_vigilar"
        plan_tbl.tree.item(item, tags=(tag,))
    sobrante_principal = max(sobrantes_rows, key=lambda rr: _to_float(rr.get("Kg restante total", 0)), default={})
    primer_riesgo = horizonte.get("primer_fallo", {})
    plan_resumen_lbl.configure(text="Plan operativo generado a partir de pedidos, horizonte y sobrantes.\n"
                                   f"Recolección necesaria: {'Sí' if any(a.get('Tipo acción') == 'RECOLECTAR' and _to_float(a.get('Kg afectados', 0)) > 0 for a in plan_actions) else 'No'}\n"
                                   f"Acciones prioritarias: {sum(1 for a in plan_actions if a.get('Prioridad') == 'ALTA')}\n"
                                   f"Sobrante principal: {sobrante_principal.get('Calibre', '-')} / {sobrante_principal.get('Grupo varietal', '-')}\n"
                                   f"Primer riesgo: {primer_riesgo.get('Fecha salida', 'Sin riesgo') if primer_riesgo else 'Sin riesgo'}")

    riesgos_box = ttk.LabelFrame(riesgos_tab, text="Diagnóstico automático completo", padding=8)
    riesgos_box.pack(fill="both", expand=True)
    riesgos_texto = [diagnostico.get("resumen", "")]
    riesgos_texto.extend([f"Alerta: {x}" for x in diagnostico.get("alertas", [])])
    riesgos_texto.extend([f"Comercial: {x}" for x in diagnostico.get("recomendaciones_comerciales", [])])
    riesgos_texto.extend([f"Campo: {x}" for x in diagnostico.get("recomendaciones_campo", [])])
    riesgos_texto.extend([f"Producción: {x}" for x in diagnostico.get("recomendaciones_produccion", [])])
    ttk.Label(riesgos_box, text="\n".join([f"• {x}" for x in riesgos_texto if x]), justify="left").pack(anchor="w")

    notebook.add(resumen_tab, text="Resumen")
    notebook.add(horizonte_tab, text="Horizonte")
    notebook.add(plan_operativo_tab, text="Plan operativo")
    notebook.add(sobrantes_tab, text="Sobrantes")
    notebook.add(necesidades_tab, text="Necesidades")
    notebook.add(riesgos_tab, text="Riesgos / Diagnóstico")
    notebook.add(tecnico_tab, text="Técnico")

    def render_candidatos(index: int) -> None:
        if index < 0 or index >= len(simulaciones):
            cand_tbl.set_rows([])
            return
        rows = []
        for c in simulaciones[index]["candidatos"]:
            riesgo = c.get("riesgo_operativo", "ALTO")
            tag_score = "riesgo_bajo" if riesgo == "BAJO" else "riesgo_medio" if riesgo == "MEDIO" else "riesgo_alto"
            origen_tag = "origen_desconocido"
            origen_canon = _canonicalizar_origen(c.get("Origen", ""))
            if origen_canon == "ALMACEN_INDUSTRIAL":
                origen_tag = "origen_industrial"
            elif origen_canon == "ALMACEN_COMERCIAL":
                origen_tag = "origen_comercial"
            elif origen_canon == "CAMPO_REAL":
                origen_tag = "origen_campo_real"
            elif origen_canon == "CAMPO_ESTIMADO":
                origen_tag = "origen_campo_estimado"
            rows.append({
                "Origen": c.get("Origen", ""),
                "Tipo cobertura": c.get("Tipo cobertura", ""),
                "Variedad stock": c.get("Variedad stock", ""),
                "Grupo varietal stock": c.get("Grupo varietal stock", ""),
                "Grupo varietal pedido": c.get("Grupo varietal pedido", ""),
                "Compatibilidad variedad": c.get("compatibilidad_varietal", ""),
                "Calibre stock": c.get("Calibre stock", ""),
                "Categoría": c.get("Categoría", ""),
                "Subpool calidad": c.get("subpool_calidad", "MIXTO"),
                "Kg físicos": formatear_kg(c.get("kg_fisicos", 0)),
                "% destrío": f"{(_to_float(c.get('porcentaje_destrio', 0))*100):.0f}%",
                "Kg destrío": formatear_kg(c.get("kg_destrio_estimado", 0)),
                "% primera": f"{(_to_float(c.get('primera_pct', 0))*100):.0f}%",
                "Kg primera": formatear_kg(c.get("kg_primera_estimado", 0)),
                "% segunda": f"{(_to_float(c.get('segunda_pct', 0))*100):.0f}%",
                "Kg segunda": formatear_kg(c.get("kg_segunda_estimado", 0)),
                "Kg industria": formatear_kg(c.get("kg_industria_estimado", 0)),
                "Kg podrido": formatear_kg(c.get("kg_podrido_estimado", 0)),
                "Kg útiles finales": formatear_kg(c.get("kg_utiles_finales", c.get("kg_utiles_estimados", 0))),
                "Kg restante antes": formatear_kg(c.get("kg_restante_antes", c.get("kg_utiles_finales", c.get("kg_utiles_estimados", 0)))),
                "Kg asignado simulado": formatear_kg(c.get("kg_asignado_simulado", 0)),
                "Kg restante después": formatear_kg(c.get("kg_restante_despues", c.get("kg_utiles_finales", c.get("kg_utiles_estimados", 0)))),
                "Pool ID": c.get("pool_id", ""),
                "Compartido": c.get("compartido", "No"),
                "Riesgo": riesgo,
                "Motivo riesgo": c.get("motivo_riesgo", ""),
                "Score compat.": int(_to_float(c.get("score_simulacion", 0))),
                "Score total": int(_to_float(c.get("score_total", 0))),
                "Flexibilidad aplicada": c.get("flexibilidad_usada_simulacion", ""),
                "Cobertura acumulada": formatear_kg(c.get("cobertura_acumulada", 0)),
                "__tags__": (tag_score, origen_tag),
            })
        cand_tbl.set_rows(rows)
        sim = simulaciones[index]
        grupo_conf = _grupo_pedido(sim.get("pedido", {}))
        perfil_conf = _perfil_pedido(sim.get("pedido", {}), grupo_conf)
        detalle.configure(
            text=(
                f"Id confección: {sim.get('pedido', {}).get('id_confeccion', '')} · "
                f"Nombre confección: {sim.get('pedido', {}).get('nombre_confeccion', '')} · "
                f"Pedido seleccionado · Fecha salida: {sim.get('pedido', {}).get('fecha_salida', '')} · "
                f"Bloque temporal: {sim.get('pedido', {}).get('bloque_temporal', '')} · "
                f"Kg pendiente: {formatear_kg(sim['kg_necesario'])} · "
                f"Kg asignado global: {formatear_kg(sim['kg_asignado_simulado'])} · "
                f"Kg faltante global: {formatear_kg(sim['kg_faltante_simulado'])} · "
                f"Estado global: {sim['estado_global']} · Grupo confección: {grupo_conf} · Perfil confección: {perfil_conf}"
            )
        )

    def on_select(_event=None) -> None:
        sel = pedidos_tbl.tree.selection()
        if not sel:
            return
        idx = pedidos_tbl.tree.index(sel[0])
        render_candidatos(idx)

    pedidos_tbl.tree.bind("<<TreeviewSelect>>", on_select)
    if resumen_rows:
        first = pedidos_tbl.tree.get_children()
        if first:
            pedidos_tbl.tree.selection_set(first[0])
            render_candidatos(0)
