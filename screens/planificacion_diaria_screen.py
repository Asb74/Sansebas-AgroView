import tkinter as tk
from tkinter import ttk, messagebox

from services.planning_service import PlanningService
from widgets.data_table import DataTable
from widgets.screen_header import ScreenHeader


class PlanificacionDiariaScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.service = PlanningService()
        self.filters = {k: tk.StringVar() for k in ["campana", "cultivo", "semana", "fecha_desde", "fecha_hasta", "empresa", "variedad"]}
        self.stock_campo_rows: list[dict] = []
        self.stock_almacen_rows: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        ScreenHeader(self, title="Planificación diaria", on_back=self.on_back).grid(row=0, column=0, sticky="ew")

        filters_frame = ttk.LabelFrame(self, text="Filtros globales", padding=10)
        filters_frame.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        fields = [("Campaña", "campana"), ("Cultivo", "cultivo"), ("Semana", "semana"), ("Fecha desde", "fecha_desde"), ("Fecha hasta", "fecha_hasta"), ("Empresa", "empresa"), ("Variedad", "variedad")]
        for i, (label, key) in enumerate(fields):
            ttk.Label(filters_frame, text=label).grid(row=0, column=i, sticky="w", padx=4)
            ttk.Entry(filters_frame, textvariable=self.filters[key], width=14).grid(row=1, column=i, padx=4, sticky="ew")
            filters_frame.grid_columnconfigure(i, weight=1)
        btns = ttk.Frame(filters_frame)
        btns.grid(row=2, column=0, columnspan=7, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Cargar planificación", command=self.load_data).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Reiniciar filtros", command=self.reset_filters).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Exportar Excel", command=self.export_excel).pack(side="left")

        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=2, column=0, sticky="nsew")

        self.campo_tab = ttk.Frame(self.tabs, padding=8)
        self.almacen_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(self.campo_tab, text="Stock campo")
        self.tabs.add(self.almacen_tab, text="Stock almacén")

        self.kpi_campo = tk.StringVar(value="Kg campo total: 0 | Nº partidas: 0 | Nº variedades: 0")
        self.kpi_almacen = tk.StringVar(value="Kg stock almacén: 0 | Nº palets: 0 | Nº variedades: 0 | Nº calibres: 0")
        self.last_update = tk.StringVar(value="")

        ttk.Label(self.campo_tab, textvariable=self.kpi_campo, style="KPI.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Label(self.campo_tab, textvariable=self.last_update).pack(anchor="w", pady=(0, 6))
        self.campo_table = DataTable(self.campo_tab, ["Cultivo", "Campaña", "Fecha carga", "Semana", "Socio", "Variedad", "Boleta", "Plataforma", "Empresa", "Restricciones", "Color", "Kg campo"])
        self.campo_table.pack(fill="both", expand=True)

        ttk.Label(self.almacen_tab, textvariable=self.kpi_almacen, style="KPI.TLabel").pack(anchor="w", pady=(0, 6))
        self.almacen_table = DataTable(self.almacen_tab, ["Campaña", "Cultivo", "IdPalet", "Pedido", "Fecha almacén", "Variedad", "Calibre", "Categoría", "Marca", "IdConfeccion", "Confección", "Cajas", "Kg stock", "Estado"])
        self.almacen_table.pack(fill="both", expand=True)

    def _filters_payload(self) -> dict:
        return {k: v.get().strip() for k, v in self.filters.items()}

    def load_data(self) -> None:
        payload = self._filters_payload()
        try:
            self.stock_campo_rows, updated = self.service.load_stock_campo(payload)
            self.stock_almacen_rows = self.service.load_stock_almacen(payload)
        except Exception as exc:
            messagebox.showwarning("Planificación diaria", str(exc))
            return
        self.campo_table.set_rows(self.stock_campo_rows)
        self.almacen_table.set_rows(self.stock_almacen_rows)
        self.kpi_campo.set(
            f"Kg campo total: {sum(float(r.get('Kg campo', 0) or 0) for r in self.stock_campo_rows):,.2f} | "
            f"Nº partidas: {len(self.stock_campo_rows)} | Nº variedades: {len({r.get('Variedad') for r in self.stock_campo_rows})}"
        )
        self.kpi_almacen.set(
            f"Kg stock almacén: {sum(float(r.get('Kg stock', 0) or 0) for r in self.stock_almacen_rows):,.2f} | "
            f"Nº palets: {len({r.get('IdPalet') for r in self.stock_almacen_rows})} | "
            f"Nº variedades: {len({r.get('Variedad') for r in self.stock_almacen_rows})} | "
            f"Nº calibres: {len({r.get('Calibre') for r in self.stock_almacen_rows})}"
        )
        self.last_update.set(f"Última actualización: {updated}" if updated else "")

    def reset_filters(self) -> None:
        for v in self.filters.values():
            v.set("")

    def export_excel(self) -> None:
        tab = self.tabs.tab(self.tabs.select(), "text")
        rows = self.stock_campo_rows if tab == "Stock campo" else self.stock_almacen_rows
        path = self.service.export_rows_to_excel(rows, tab, self.filters["cultivo"].get(), self.filters["campana"].get())
        if path:
            messagebox.showinfo("Exportación", f"Archivo guardado en:\n{path}")
