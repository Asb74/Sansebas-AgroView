from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import ttk
import unicodedata

from services.operational_quality_service import OperationalQualityService
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


def _norm_text(valor: object) -> str:
    txt = unicodedata.normalize("NFD", str(valor or "").strip().upper())
    txt = "".join(ch for ch in txt if unicodedata.category(ch) != "Mn")
    return " ".join(txt.split())


def _to_float(valor: object) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def formatear_kg(valor: object) -> str:
    num = _to_float(valor)
    return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
            "activo": bool(int(r.get("Activo", 1))),
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
            -_to_float(c.get("score_total", 0)),
            -_to_float(c.get("score_simulacion", 0)),
            prioridad_riesgo.get(str(c.get("riesgo_operativo", "ALTO")), 9),
            -_to_float(c.get("kg_utiles_estimados", 0)),
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


def abrir_simulacion_asignacion(parent: tk.Misc, pedidos: list[dict], get_candidatos_cb, scoring: dict | None = None) -> None:
    popup = tk.Toplevel(parent)
    popup.title("Simulación de asignación")
    popup.geometry("1300x750")

    top = ttk.LabelFrame(popup, text="Pedidos pendientes", padding=8)
    top.pack(fill="both", expand=True, padx=8, pady=(8, 4))
    bottom = ttk.LabelFrame(popup, text="Candidatos de cobertura", padding=8)
    bottom.pack(fill="both", expand=True, padx=8, pady=(4, 8))

    pedidos_cols = ["Cliente", "Variedad", "Calibre", "Categoría", "Grupo confección", "Perfil confección", "Kg pendientes", "Estado simulación", "Kg cobertura simulada", "Kg potencial físico", "Kg potencial útil"]
    pedidos_tbl = DataTable(top, pedidos_cols)
    pedidos_tbl.pack(fill="both", expand=True)

    cand_cols = ["Origen", "Tipo cobertura", "Variedad stock", "Calibre stock", "Categoría", "Kg físicos", "% destrío", "Kg destrío", "% primera", "Kg primera", "% segunda", "Kg segunda", "Kg industria", "Kg podrido", "Kg útiles finales", "Riesgo", "Motivo riesgo", "Score compat.", "Score total", "Flexibilidad aplicada", "Cobertura acumulada"]
    cand_tbl = DataTable(bottom, cand_cols)
    cand_tbl.pack(fill="both", expand=True)

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

    simulaciones: list[dict] = []
    resumen_rows: list[dict] = []
    def _grupo_pedido(p: dict) -> str:
        return _norm_text(p.get("grupo_confeccion") or p.get("GrupoConfeccion") or p.get("GRUPO") or p.get("grupo")) or "DESCONOCIDO"

    def _perfil_pedido(p: dict, grupo: str) -> str:
        return _norm_text(p.get("perfil_confeccion")) or detectar_perfil_confeccion_desde_grupo(grupo) or "DESCONOCIDO"

    for pedido in pedidos:
        candidatos = get_candidatos_cb(pedido) or []
        simulacion = simular_asignacion_pedido(pedido, candidatos, scoring=scoring)
        simulaciones.append(simulacion)
        estado = simulacion["estado"]
        tag_estado = "estado_total" if estado == "TOTAL" else "estado_parcial" if estado == "PARCIAL" else "estado_insuf"
        grupo_conf = _grupo_pedido(pedido)
        perfil_conf = _perfil_pedido(pedido, grupo_conf)
        resumen_rows.append({
            "Cliente": pedido.get("Cliente", ""),
            "Variedad": pedido.get("Variedad", ""),
            "Calibre": pedido.get("Calibre", ""),
            "Categoría": pedido.get("Categoría", ""),
            "Grupo confección": grupo_conf,
            "Perfil confección": perfil_conf,
            "Kg pendientes": formatear_kg(simulacion["kg_pendientes"]),
            "Estado simulación": estado,
            "Kg cobertura simulada": formatear_kg(simulacion["kg_cobertura_simulada"]),
            "Kg potencial físico": formatear_kg(simulacion["kg_potencial_fisico"]),
            "Kg potencial útil": formatear_kg(simulacion["kg_potencial_util"]),
            "__tags__": (tag_estado,),
        })

    total_pedidos = len(simulaciones)
    totales = sum(1 for s in simulaciones if s["estado"] == "TOTAL")
    parciales = sum(1 for s in simulaciones if s["estado"] == "PARCIAL")
    insuficientes = sum(1 for s in simulaciones if s["estado"] == "INSUFICIENTE")
    resumen.configure(text=f"Pedidos: {total_pedidos}   Totales: {totales}   Parciales: {parciales}   Insuficientes: {insuficientes}")

    pedidos_tbl.set_rows(resumen_rows)

    def render_candidatos(index: int) -> None:
        if index < 0 or index >= len(simulaciones):
            cand_tbl.set_rows([])
            return
        rows = []
        for c in simulaciones[index]["candidatos"]:
            riesgo = c.get("riesgo_operativo", "ALTO")
            tag_score = "riesgo_bajo" if riesgo == "BAJO" else "riesgo_medio" if riesgo == "MEDIO" else "riesgo_alto"
            rows.append({
                "Origen": c.get("Origen", ""),
                "Tipo cobertura": c.get("Tipo cobertura", ""),
                "Variedad stock": c.get("Variedad stock", ""),
                "Calibre stock": c.get("Calibre stock", ""),
                "Categoría": c.get("Categoría", ""),
                "Kg físicos": formatear_kg(c.get("kg_fisicos", 0)),
                "% destrío": f"{(_to_float(c.get('porcentaje_destrio', 0))*100):.0f}%",
                "Kg destrío": formatear_kg(c.get("kg_destrio_estimado", 0)),
                "% primera": f"{(_to_float(c.get('primera_pct', 0))*100):.0f}%",
                "Kg primera": formatear_kg(c.get("kg_primera_estimado", 0)),
                "% segunda": f"{(_to_float(c.get('segunda_pct', 0))*100):.0f}%",
                "Kg segunda": formatear_kg(c.get("kg_segunda_estimado", 0)),
                "Kg industria": formatear_kg(c.get("kg_industria_estimado", 0)),
                "Kg podrido": formatear_kg(c.get("kg_podrido_estimado", 0)),
                "Kg útiles finales": formatear_kg(c.get("kg_utiles_estimados", 0)),
                "Riesgo": riesgo,
                "Motivo riesgo": c.get("motivo_riesgo", ""),
                "Score compat.": int(_to_float(c.get("score_simulacion", 0))),
                "Score total": int(_to_float(c.get("score_total", 0))),
                "Flexibilidad aplicada": c.get("flexibilidad_usada_simulacion", ""),
                "Cobertura acumulada": formatear_kg(c.get("cobertura_acumulada", 0)),
                "__tags__": (tag_score,),
            })
        cand_tbl.set_rows(rows)
        sim = simulaciones[index]
        grupo_conf = _grupo_pedido(sim.get("pedido", {}))
        perfil_conf = _perfil_pedido(sim.get("pedido", {}), grupo_conf)
        detalle.configure(
            text=(
                f"Id confección: {sim.get('pedido', {}).get('id_confeccion', '')} · "
                f"Nombre confección: {sim.get('pedido', {}).get('nombre_confeccion', '')} · "
                f"Pedido seleccionado · Kg pendientes: {formatear_kg(sim['kg_pendientes'])} · "
                f"Kg cobertura simulada: {formatear_kg(sim['kg_cobertura_simulada'])} · "
                f"Kg potencial físico: {formatear_kg(sim['kg_potencial_fisico'])} · "
                f"Kg potencial útil: {formatear_kg(sim['kg_potencial_util'])} · "
                f"Estado: {sim['estado']} · Grupo confección: {grupo_conf} · Perfil confección: {perfil_conf}"
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
