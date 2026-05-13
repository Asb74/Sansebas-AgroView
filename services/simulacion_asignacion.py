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
    "categoria_inferior": -20,
    "grupo_varietal_alternativo": -30,
    "campo_real": 10,
}


def calcular_score_candidato(candidato: dict, scoring: dict | None = None) -> tuple[int, str]:
    scoring_cfg = scoring or SCORING_COBERTURA
    tipo = str(candidato.get("Tipo cobertura", "")).strip().lower()
    flex = str(candidato.get("Flexibilidad aplicada", "")).strip()
    origen = str(candidato.get("Origen", "")).strip().lower()

    score = 0
    motivos: list[str] = []

    if "exact" in tipo:
        score += int(scoring_cfg.get("exacto", 0))
        motivos.append("Exacto")
    if "mismo grupo" in tipo:
        score += int(scoring_cfg.get("mismo_grupo", 0))
        motivos.append("Mismo grupo")
    if "variedad alternativa" in tipo:
        score += int(scoring_cfg.get("variedad_alternativa", 0))
        motivos.append("Variedad alternativa")
    if "calibre agrup" in tipo:
        score += int(scoring_cfg.get("calibre_agrupado", 0))
        motivos.append("Calibre agrupado")
    if "calibre admitido" in tipo:
        score += int(scoring_cfg.get("calibre_admitido", 0))
        motivos.append("Calibre admitido")
    if "categoría inferior" in tipo or "categoria inferior" in tipo:
        score += int(scoring_cfg.get("categoria_inferior", 0))
        motivos.append("Categoría inferior")
    if "grupo varietal alternativo" in tipo:
        score += int(scoring_cfg.get("grupo_varietal_alternativo", 0))
        motivos.append("Grupo varietal alternativo")
    if "campo" in origen:
        score += int(scoring_cfg.get("campo_real", 0))
        motivos.append("Campo real")

    if flex:
        for part in [p.strip() for p in flex.split("+") if p.strip()]:
            if part not in motivos:
                motivos.append(part)

    if not motivos:
        motivos.append("Sin flexibilidad")

    return score, " + ".join(motivos)


def simular_asignacion_pedido(pedido: dict, candidatos: list[dict], scoring: dict | None = None) -> dict:
    kg_pend = float(pedido.get("Kg pedidos pendientes", 0) or pedido.get("kg_pendientes", 0) or 0)
    candidatos_ordenados: list[dict] = []

    for cand in deepcopy(candidatos):
        score, flex_txt = calcular_score_candidato(cand, scoring=scoring)
        cand["score_simulacion"] = score
        cand["flexibilidad_usada_simulacion"] = flex_txt
        candidatos_ordenados.append(cand)

    candidatos_ordenados.sort(key=lambda c: float(c.get("score_simulacion", 0) or 0), reverse=True)

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
        "kg_cobertura_simulada": acumulado,
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

    pedidos_cols = ["Cliente", "Variedad", "Calibre", "Categoría", "Kg pendientes", "Estado simulación", "Kg cobertura simulada"]
    pedidos_tbl = DataTable(top, pedidos_cols)
    pedidos_tbl.pack(fill="both", expand=True)

    cand_cols = ["Origen", "Tipo cobertura", "Variedad stock", "Calibre stock", "Categoría", "Kg disponibles", "Score", "Flexibilidad aplicada", "Cobertura acumulada"]
    cand_tbl = DataTable(bottom, cand_cols)
    cand_tbl.pack(fill="both", expand=True)

    simulaciones: list[dict] = []
    resumen_rows: list[dict] = []
    for pedido in pedidos:
        candidatos = get_candidatos_cb(pedido) or []
        simulacion = simular_asignacion_pedido(pedido, candidatos, scoring=scoring)
        simulaciones.append(simulacion)
        resumen_rows.append({
            "Cliente": pedido.get("Cliente", ""),
            "Variedad": pedido.get("Variedad", ""),
            "Calibre": pedido.get("Calibre", ""),
            "Categoría": pedido.get("Categoría", ""),
            "Kg pendientes": simulacion["kg_pendientes"],
            "Estado simulación": simulacion["estado"],
            "Kg cobertura simulada": simulacion["kg_cobertura_simulada"],
        })

    pedidos_tbl.set_rows(resumen_rows)

    def render_candidatos(index: int) -> None:
        if index < 0 or index >= len(simulaciones):
            cand_tbl.set_rows([])
            return
        rows = []
        for c in simulaciones[index]["candidatos"]:
            rows.append({
                "Origen": c.get("Origen", ""),
                "Tipo cobertura": c.get("Tipo cobertura", ""),
                "Variedad stock": c.get("Variedad stock", ""),
                "Calibre stock": c.get("Calibre stock", ""),
                "Categoría": c.get("Categoría", ""),
                "Kg disponibles": c.get("Kg disponibles", 0),
                "Score": c.get("score_simulacion", 0),
                "Flexibilidad aplicada": c.get("flexibilidad_usada_simulacion", ""),
                "Cobertura acumulada": c.get("cobertura_acumulada", 0),
            })
        cand_tbl.set_rows(rows)

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
