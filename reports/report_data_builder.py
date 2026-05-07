from __future__ import annotations

from datetime import datetime
from typing import Any


def format_filters(filters: dict[str, Any]) -> list[tuple[str, str]]:
    labels = {
        "campana": "Campaña",
        "cultivo": "Cultivo",
        "empresa": "Empresa",
        "semana": "Semana",
        "fecha_desde": "Fecha desde",
        "fecha_hasta": "Fecha hasta",
        "cliente": "Cliente",
        "pais": "País",
        "var_coop": "Variedad Coop",
        "var_cliente": "Variedad Cliente",
        "calibre": "Calibre",
        "categoria": "Categoría",
        "marca": "Marca",
    }
    out: list[tuple[str, str]] = []
    for k, label in labels.items():
        raw = filters.get(k)
        if isinstance(raw, list):
            value = ", ".join([str(v).strip() for v in raw if str(v).strip()])
        else:
            value = str(raw or "").strip()
        if value:
            out.append((label, value))
    return out


def default_report_dict(title: str, filters: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": title,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "filters": format_filters(filters),
        "kpis": [],
        "tables": [],
        "chart_images": [],
    }
