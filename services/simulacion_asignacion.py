from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import ttk
import unicodedata

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

COEFICIENTES_UTILIDAD = {
    "MALLA": {"ESTANDAR": 0.95, "PRECALIBRADO": 0.90, "INDUSTRIAL": 0.90, "CAMPO_REAL": 0.75, "DESCONOCIDO": 0.80},
    "EXIGENTE": {"ESTANDAR": 0.80, "PRECALIBRADO": 0.65, "INDUSTRIAL": 0.70, "CAMPO_REAL": 0.60, "DESCONOCIDO": 0.65},
    "DESCONOCIDO": {"ESTANDAR": 0.85, "PRECALIBRADO": 0.75, "INDUSTRIAL": 0.75, "CAMPO_REAL": 0.65, "DESCONOCIDO": 0.70},
}

PENALIZACION_RIESGO = {"BAJO": 0, "MEDIO": -10, "ALTO": -25}

PORCENTAJE_DESTRIO_ESTIMADO = {"ESTANDAR": 0.03, "PRECALIBRADO": 0.08, "INDUSTRIAL": 0.10, "CAMPO_REAL": 0.15, "DESCONOCIDO": 0.10}


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


def detectar_perfil_stock(candidato: dict) -> str:
    campos = ["origen", "Origen", "tipo_cobertura", "Tipo cobertura", "tipo cobertura", "flexibilidad", "flexibilidad_aplicada", "descripcion", "articulo", "observaciones", "lote", "tipo_stock"]
    texto = " ".join(_norm_text(candidato.get(c, "")) for c in campos)
    if "CAMPO_REAL" in texto or "PESOSFRES" in texto:
        return "CAMPO_REAL"
    if "PRECALIBRADO" in texto or "PRE-CALIBRADO" in texto:
        return "PRECALIBRADO"
    if "ESTANDAR" in texto:
        return "ESTANDAR"
    if "INDUSTRIAL" in texto or "ALMACEN_INDUSTRIAL" in texto:
        return "INDUSTRIAL"
    return "DESCONOCIDO"


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
    perfil_confeccion = detectar_perfil_confeccion(pedido)
    perfil_stock = detectar_perfil_stock(candidato)
    coef_utilidad = float(COEFICIENTES_UTILIDAD.get(perfil_confeccion, COEFICIENTES_UTILIDAD["DESCONOCIDO"]).get(perfil_stock, 0.70))
    kg_fisicos = _to_float(candidato.get("Kg disponibles", candidato.get("kg_disponibles", 0)))
    kg_utiles_categoria = kg_fisicos * coef_utilidad
    porcentaje_destrio = float(PORCENTAJE_DESTRIO_ESTIMADO.get(perfil_stock, PORCENTAJE_DESTRIO_ESTIMADO["DESCONOCIDO"]))
    kg_destrio_estimado = kg_utiles_categoria * porcentaje_destrio
    kg_utiles_estimados = kg_utiles_categoria - kg_destrio_estimado
    riesgo = _riesgo_desde_coef(coef_utilidad)
    if porcentaje_destrio >= 0.12:
        riesgo = _subir_riesgo(riesgo)
    if perfil_confeccion == "MALLA" and perfil_stock in ("INDUSTRIAL", "PRECALIBRADO"):
        motivo = "Malla admite mezcla I/II; destrío estimado bajo"
    elif perfil_confeccion == "EXIGENTE" and perfil_stock == "PRECALIBRADO":
        motivo = "Pedido exigente: precalibrado puede contener categoría II y destrío"
    elif perfil_confeccion == "EXIGENTE" and perfil_stock == "INDUSTRIAL":
        motivo = "Pedido exigente: stock industrial puede requerir separación I/II y generar destrío"
    elif perfil_confeccion == "EXIGENTE" and perfil_stock == "CAMPO_REAL":
        motivo = "Campo real pendiente de confección; destrío estimado elevado"
    elif perfil_confeccion == "DESCONOCIDO" or perfil_stock == "DESCONOCIDO":
        motivo = "Perfil no detectado; coeficientes conservadores con destrío estimado"
    else:
        motivo = "Coeficiente según perfil de confección y stock"
    return {
        "perfil_confeccion": perfil_confeccion,
        "perfil_stock": perfil_stock,
        "coef_utilidad": coef_utilidad,
        "kg_fisicos": kg_fisicos,
        "kg_utiles_categoria": kg_utiles_categoria,
        "porcentaje_destrio": porcentaje_destrio,
        "kg_destrio_estimado": kg_destrio_estimado,
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
    return {
        "pedido": dict(pedido),
        "kg_pendientes": kg_pend,
        "estado": estado,
        "kg_cobertura_simulada": min(acumulado, kg_pend),
        "kg_potencial_encontrado": acumulado,
        "kg_potencial_fisico": kg_potencial_fisico,
        "kg_potencial_util": acumulado,
        "perfil_confeccion": detectar_perfil_confeccion(pedido),
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

    pedidos_cols = ["Cliente", "Variedad", "Calibre", "Categoría", "Kg pendientes", "Estado simulación", "Kg cobertura simulada", "Kg potencial físico", "Kg potencial útil"]
    pedidos_tbl = DataTable(top, pedidos_cols)
    pedidos_tbl.pack(fill="both", expand=True)

    cand_cols = ["Origen", "Tipo cobertura", "Variedad stock", "Calibre stock", "Categoría", "Kg físicos", "Coef. categoría", "Kg útiles categoría", "% destrío", "Kg destrío estimado", "Kg útiles finales", "Riesgo", "Motivo riesgo", "Score compat.", "Score total", "Flexibilidad aplicada", "Cobertura acumulada"]
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
    for pedido in pedidos:
        candidatos = get_candidatos_cb(pedido) or []
        simulacion = simular_asignacion_pedido(pedido, candidatos, scoring=scoring)
        simulaciones.append(simulacion)
        estado = simulacion["estado"]
        tag_estado = "estado_total" if estado == "TOTAL" else "estado_parcial" if estado == "PARCIAL" else "estado_insuf"
        resumen_rows.append({
            "Cliente": pedido.get("Cliente", ""),
            "Variedad": pedido.get("Variedad", ""),
            "Calibre": pedido.get("Calibre", ""),
            "Categoría": pedido.get("Categoría", ""),
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
                "Coef. categoría": f"{(_to_float(c.get('coef_utilidad', 0))*100):.0f}%",
                "Kg útiles categoría": formatear_kg(c.get("kg_utiles_categoria", 0)),
                "% destrío": f"{(_to_float(c.get('porcentaje_destrio', 0))*100):.0f}%",
                "Kg destrío estimado": formatear_kg(c.get("kg_destrio_estimado", 0)),
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
        detalle.configure(
            text=(
                f"Pedido seleccionado · Kg pendientes: {formatear_kg(sim['kg_pendientes'])} · "
                f"Kg cobertura simulada: {formatear_kg(sim['kg_cobertura_simulada'])} · "
                f"Kg potencial físico: {formatear_kg(sim['kg_potencial_fisico'])} · "
                f"Kg potencial útil: {formatear_kg(sim['kg_potencial_util'])} · "
                f"Estado: {sim['estado']} · Perfil confección: {sim.get('perfil_confeccion', 'DESCONOCIDO')}"
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
