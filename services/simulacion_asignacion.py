from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import ttk

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


def _norm_text(valor: object) -> str:
    return str(valor or "").strip().upper().replace("  ", " ")


def formatear_kg(valor: object) -> str:
    try:
        num = float(valor or 0)
    except (TypeError, ValueError):
        num = 0.0
    return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
    def prioridad_origen(origen: str) -> int:
        o = _norm_text(origen)
        if "CAMPO_REAL" in o or "PESOSFRES" in o:
            return 1
        return 0

    return sorted(
        candidatos,
        key=lambda c: (
            -float(c.get("score_simulacion", 0) or 0),
            prioridad_origen(c.get("Origen", c.get("origen", ""))),
            -float(c.get("Kg disponibles", 0) or 0),
        ),
    )


def simular_asignacion_pedido(pedido: dict, candidatos: list[dict], scoring: dict | None = None) -> dict:
    kg_pend = float(pedido.get("Kg pedidos pendientes", 0) or pedido.get("kg_pendientes", 0) or 0)
    candidatos_ordenados: list[dict] = []

    for cand in deepcopy(candidatos):
        score, flex_txt = calcular_score_candidato(cand, pedido=pedido, scoring=scoring)
        cand["score_simulacion"] = score
        cand["flexibilidad_usada_simulacion"] = flex_txt
        candidatos_ordenados.append(cand)

    candidatos_ordenados = ordenar_candidatos_simulacion(candidatos_ordenados)

    acumulado = 0.0
    for cand in candidatos_ordenados:
        acumulado += float(cand.get("Kg disponibles", 0) or 0)
        cand["cobertura_acumulada"] = acumulado

    if acumulado >= kg_pend and kg_pend > 0:
        estado = "TOTAL"
    elif acumulado > 0:
        estado = "PARCIAL"
    else:
        estado = "INSUFICIENTE"

    return {
        "pedido": dict(pedido),
        "kg_pendientes": kg_pend,
        "estado": estado,
        "kg_cobertura_simulada": min(acumulado, kg_pend),
        "kg_potencial_encontrado": acumulado,
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

    pedidos_cols = ["Cliente", "Variedad", "Calibre", "Categoría", "Kg pendientes", "Estado simulación", "Kg cobertura simulada", "Kg potencial encontrados"]
    pedidos_tbl = DataTable(top, pedidos_cols)
    pedidos_tbl.pack(fill="both", expand=True)

    cand_cols = ["Origen", "Tipo cobertura", "Variedad stock", "Calibre stock", "Categoría", "Kg disponibles", "Score", "Flexibilidad aplicada", "Cobertura acumulada"]
    cand_tbl = DataTable(bottom, cand_cols)
    cand_tbl.pack(fill="both", expand=True)

    resumen = ttk.Label(popup, text="", anchor="w")
    resumen.pack(fill="x", padx=10, pady=(0, 4))
    detalle = ttk.Label(popup, text="", anchor="w")
    detalle.pack(fill="x", padx=10, pady=(0, 8))

    pedidos_tbl.tree.tag_configure("estado_total", background="#dcedc8")
    pedidos_tbl.tree.tag_configure("estado_parcial", background="#fff3cd")
    pedidos_tbl.tree.tag_configure("estado_insuf", background="#f8d7da")
    cand_tbl.tree.tag_configure("score_top", background="#d0f0c0")
    cand_tbl.tree.tag_configure("score_mid", background="#d9edf7")
    cand_tbl.tree.tag_configure("score_low", background="#fff8b3")
    cand_tbl.tree.tag_configure("score_min", background="#eeeeee")

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
            "Kg potencial encontrados": formatear_kg(simulacion["kg_potencial_encontrado"]),
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
            score = float(c.get("score_simulacion", 0) or 0)
            tag_score = "score_top" if score >= 100 else "score_mid" if score >= 60 else "score_low" if score >= 30 else "score_min"
            rows.append({
                "Origen": c.get("Origen", ""),
                "Tipo cobertura": c.get("Tipo cobertura", ""),
                "Variedad stock": c.get("Variedad stock", ""),
                "Calibre stock": c.get("Calibre stock", ""),
                "Categoría": c.get("Categoría", ""),
                "Kg disponibles": formatear_kg(c.get("Kg disponibles", 0)),
                "Score": c.get("score_simulacion", 0),
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
                f"Kg potencial encontrados: {formatear_kg(sim['kg_potencial_encontrado'])} · Estado: {sim['estado']}"
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
