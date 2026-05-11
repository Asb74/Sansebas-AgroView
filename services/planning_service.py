from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
import re
from tkinter import filedialog

from openpyxl import Workbook
from openpyxl.styles import Font

from db.planning_repository import PlanningRepository


class PlanningService:
    def __init__(self) -> None:
        self.repo = PlanningRepository()

    def load_stock_campo(self, filters: dict) -> tuple[list[dict], str | None, bool]:
        return self.repo.get_stock_campo(filters)

    def load_stock_almacen(self, filters: dict) -> tuple[list[dict], str | None]:
        return self.repo.get_stock_almacen(filters)

    def load_stock_almacen_detalle_palets(self, filters: dict) -> list[dict]:
        return self.repo.get_stock_almacen_detalle_palets(filters)

    def get_aprovechamientos_reales(self, filters: dict) -> list[dict]:
        return self.repo.get_aprovechamientos_reales(filters)

    def diagnose_loteado_tables(self) -> dict:
        return self.repo.diagnose_loteado_tables()

    def get_filter_options(self, key: str) -> list[str]:
        return self.repo.get_filter_options(key)

    def get_correspondencias_calibres(self, cultivo: str) -> list[dict]:
        return self.repo.get_correspondencias_calibres(cultivo)

    def aggregate_stock_campo(self, rows: list[dict]) -> list[dict]:
        agg: dict[tuple, float] = defaultdict(float)
        for r in rows:
            key = (r.get("Cultivo", ""), r.get("Variedad", ""), r.get("Grupo varietal", ""), r.get("Semana", ""))
            agg[key] += float(r.get("Kg campo", 0) or 0)
        return [{"Cultivo": k[0], "Variedad": k[1], "Grupo varietal": k[2], "Semana": k[3], "Kg campo": round(v, 2)} for k, v in agg.items()]

    def aggregate_stock_almacen(self, rows: list[dict]) -> list[dict]:
        agg: dict[tuple, float] = defaultdict(float)
        for r in rows:
            key = (r.get("Cultivo", ""), r.get("Variedad", ""), r.get("Calibre", ""), r.get("Categoría", ""), r.get("IdConfeccion", ""))
            agg[key] += float(r.get("Kg stock", 0) or 0)
        return [{"Cultivo": k[0], "Variedad": k[1], "Calibre": k[2], "Categoría": k[3], "IdConfeccion": k[4], "Kg stock": round(v, 2)} for k, v in agg.items()]

    def export_rows_to_excel(self, rows: list[dict], tab_name: str, cultivos: list[str], campanas: list[str]) -> str | None:
        if not rows:
            return None
        suffix = "Stock_campo" if tab_name == "Stock campo" else "Stock_almacen"
        fecha = datetime.now().strftime("%Y%m%d")
        cultivo_txt = "_".join(cultivos) if cultivos else "TODOS"
        campana_txt = "_".join(campanas) if campanas else "TODOS"
        base = f"{fecha} {suffix}_{cultivo_txt}_{campana_txt} hechos disponibles"
        safe_base = re.sub(r'[\\/:*?"<>|]', "_", base)
        default_name = f"{safe_base}.xlsx"
        target = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile=default_name, filetypes=[("Excel", "*.xlsx")])
        if not target:
            return None
        wb = Workbook()
        ws = wb.active
        ws.title = tab_name
        headers = list(rows[0].keys())
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True)
        for row in rows:
            ws.append([row.get(h, "") for h in headers])
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"
        for col in ws.columns:
            width = max(len(str(cell.value or "")) for cell in col) + 2
            ws.column_dimensions[col[0].column_letter].width = min(width, 30)
        kg_col_idx = None
        for i, h in enumerate(headers, start=1):
            if h in ("Kg campo", "Kg stock"):
                kg_col_idx = i
        if kg_col_idx:
            for r in range(2, ws.max_row + 1):
                ws.cell(r, kg_col_idx).number_format = "#,##0.00"
        wb.save(Path(target))
        return target
