import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from services.forfait_service import ForfaitService
from widgets.data_table import DataTable


class MapForfaitScreen(ttk.Frame):
    TABLE_COLUMNS = [
        "Campaña", "Cultivo", "Variedad", "Condicion1", "IdConfeccion", "NombreConfeccion",
        "GrupoConfeccion", "Marca", "CosteMaterialEurKg", "CosteManoObraEurKg", "CosteTotalEurKg", "Estado", "OrigenCoste",
    ]

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.service = ForfaitService()
        self.cultivo_var = tk.StringVar(value="CITRICOS")
        self.campana_var = tk.StringVar(value="2025")
        self.only_missing_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="")
        self.rows: list[dict[str, Any]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Control cobertura industrial", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Volver", command=self.on_back).grid(row=0, column=1, sticky="e")

        controls = ttk.LabelFrame(self, text="Filtro obligatorio", padding=12)
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        ttk.Label(controls, text="Cultivo").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(controls, textvariable=self.cultivo_var, width=18).grid(row=0, column=1, sticky="w", padx=(0, 12))
        ttk.Label(controls, text="Campaña").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(controls, textvariable=self.campana_var, width=18).grid(row=0, column=3, sticky="w", padx=(0, 12))
        ttk.Button(controls, text="Cargar cobertura", command=self.load_rows).grid(row=0, column=4, padx=(0, 8))
        ttk.Checkbutton(controls, text="Mostrar solo sin forfait", variable=self.only_missing_var, command=self.load_rows).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(controls, text="Exportar pendientes", command=self.export_pending).grid(row=0, column=6)

        self.table = DataTable(self, columns=self.TABLE_COLUMNS)
        self.table.grid(row=2, column=0, sticky="nsew")
        ttk.Label(self, textvariable=self.status_var).grid(row=3, column=0, sticky="w", pady=(8, 0))

    def load_rows(self) -> None:
        cultivo = self.cultivo_var.get().strip()
        campana = self.campana_var.get().strip()
        if not cultivo or not campana:
            messagebox.showwarning("Filtro obligatorio", "Indica cultivo y campaña.", parent=self)
            return
        try:
            self.rows = self.service.fetch_coverage_rows(cultivo, campana, self.only_missing_var.get())
        except Exception as exc:
            messagebox.showerror("Cobertura industrial", str(exc), parent=self)
            return
        self.table.set_rows(self._map_rows(self.rows))
        self._set_counter_status()

    def export_pending(self) -> None:
        pending = [r for r in self.rows if str(r.get("OrigenCoste") or "") == "SIN_FORFAIT"]
        if not pending:
            self.status_var.set("No hay pendientes SIN_FORFAIT para exportar.")
            return
        out_path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", filetypes=[("CSV", "*.csv")], title="Exportar pendientes")
        if not out_path:
            return
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.TABLE_COLUMNS)
            writer.writeheader()
            for r in self._map_rows(pending):
                writer.writerow({k: r.get(k, "") for k in self.TABLE_COLUMNS})
        self.status_var.set(f"Pendientes exportados: {len(pending)}")

    def _set_counter_status(self) -> None:
        exactos = sum(1 for r in self.rows if r.get("OrigenCoste") == "EXACTO")
        aprox = sum(1 for r in self.rows if r.get("OrigenCoste") in {"VARIEDAD_TODAS", "CONDICION_TODAS", "TODAS", "MANUAL"})
        sinf = sum(1 for r in self.rows if r.get("OrigenCoste") == "SIN_FORFAIT")
        self.status_var.set(f"Confecciones usadas: {len(self.rows)} | Con coste exacto: {exactos} | Aproximadas: {aprox} | Sin forfait: {sinf}")

    def _map_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for row in rows:
            estado = str(row.get("Estado") or "")
            if estado in {"", "IMPORTADO"}:
                estado = "OK" if row.get("OrigenCoste") == "EXACTO" else ("APROXIMADO" if row.get("OrigenCoste") != "SIN_FORFAIT" else "SIN_FORFAIT")
            tag = "tag_green" if estado == "OK" else ("tag_red" if estado == "SIN_FORFAIT" else ("tag_orange" if estado == "REVISAR" else "tag_yellow"))
            out.append({
                "Campaña": row.get("Campaña", ""),
                "Cultivo": row.get("Cultivo", ""),
                "Variedad": row.get("Variedad", ""),
                "Condicion1": row.get("Condicion1", ""),
                "IdConfeccion": row.get("IdConfeccion", ""),
                "NombreConfeccion": row.get("NombreConfeccion", ""),
                "GrupoConfeccion": row.get("GrupoConfeccion", ""),
                "Marca": row.get("Marca", ""),
                "CosteMaterialEurKg": self._fmt_optional(row.get("CosteMaterialEurKg"), 4),
                "CosteManoObraEurKg": self._fmt_optional(row.get("CosteManoObraEurKg"), 4),
                "CosteTotalEurKg": self._fmt_optional(row.get("CosteTotalEurKg"), 4),
                "Estado": estado,
                "OrigenCoste": row.get("OrigenCoste", "SIN_FORFAIT"),
                "__tags__": tag,
            })
        return out

    @staticmethod
    def _fmt_optional(value: Any, decimals: int) -> str:
        if value is None or value == "":
            return ""
        try:
            return f"{float(value):,.{decimals}f}"
        except (TypeError, ValueError):
            return ""
