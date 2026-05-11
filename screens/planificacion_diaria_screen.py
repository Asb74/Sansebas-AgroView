import tkinter as tk
from tkinter import ttk, messagebox
import logging

from services.planning_service import PlanningService
from widgets.data_table import DataTable
from widgets.screen_header import ScreenHeader
from widgets.date_picker import DatePickerPopup
from widgets.multi_select_filter import MultiSelectFilter


class PlanificacionDiariaScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.service = PlanningService()
        self.fecha_desde_var = tk.StringVar()
        self.fecha_hasta_var = tk.StringVar()
        self.filter_widgets: dict[str, MultiSelectFilter] = {}
        self.filters_status_var = tk.StringVar(value="Sin filtros activos")
        self.stock_campo_rows: list[dict] = []
        self.stock_almacen_rows: list[dict] = []
        self._build_ui()
        self._load_filter_options()

    def _load_filter_options(self) -> None:
        diag = self.service.diagnose_loteado_tables()
        if diag.get("warning"):
            logging.getLogger(__name__).warning(diag["warning"])
        for key in ("campana", "cultivo", "empresa", "semana", "var_coop", "marca"):
            try:
                self.filter_widgets[key].set_options(self.service.get_filter_options(key))
            except Exception as exc:
                logging.getLogger(__name__).warning("No se pudo cargar opciones de filtro %s: %s", key, exc)
                self.filter_widgets[key].set_options([])

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        ScreenHeader(self, title="Planificación diaria", on_back=self.on_back).grid(row=0, column=0, sticky="ew")

        filters_frame = ttk.LabelFrame(self, text="Filtros globales", padding=10)
        filters_frame.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        fields = [("Campaña", "campana"), ("Cultivo", "cultivo"), ("Semana", "semana"), ("Fecha desde", "fecha_desde"), ("Fecha hasta", "fecha_hasta"), ("Empresa", "empresa"), ("Variedad Coop", "var_coop"), ("Marca", "marca")]
        for i, (label, key) in enumerate(fields):
            ttk.Label(filters_frame, text=label).grid(row=0, column=i, sticky="w", padx=4)
            if key == "fecha_desde":
                self._build_date_field(filters_frame, 1, i, self.fecha_desde_var)
            elif key == "fecha_hasta":
                self._build_date_field(filters_frame, 1, i, self.fecha_hasta_var)
            else:
                widget = MultiSelectFilter(filters_frame, title=label, width=16)
                widget.grid(row=1, column=i, padx=4, sticky="ew")
                self.filter_widgets[key] = widget
            filters_frame.grid_columnconfigure(i, weight=1)
        btns = ttk.Frame(filters_frame)
        btns.grid(row=2, column=0, columnspan=8, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Aplicar filtros", command=self.load_data).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Limpiar filtros", command=self.reset_filters).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Reaplicar filtros", command=self.load_data).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Exportar Excel", command=self.export_excel).pack(side="left")
        ttk.Label(filters_frame, textvariable=self.filters_status_var).grid(row=3, column=0, columnspan=8, sticky="w", padx=4, pady=(6, 0))

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

    def _build_date_field(self, parent: ttk.Frame, row: int, col: int, var: tk.StringVar) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=col, sticky="ew", padx=4)
        frame.grid_columnconfigure(0, weight=1)
        ttk.Entry(frame, textvariable=var).grid(row=0, column=0, sticky="ew")
        btn = ttk.Button(frame, text="...", width=3)
        btn.configure(command=lambda v=var, b=btn: DatePickerPopup(self, target_var=v, anchor_widget=b))
        btn.grid(row=0, column=1, padx=(4, 0))

    def _filters_payload(self) -> dict:
        return {
            "campana": self.filter_widgets["campana"].get_selected(),
            "cultivo": self.filter_widgets["cultivo"].get_selected(),
            "empresa": self.filter_widgets["empresa"].get_selected(),
            "semana": self.filter_widgets["semana"].get_selected(),
            "var_coop": self.filter_widgets["var_coop"].get_selected(),
            "marca": self.filter_widgets["marca"].get_selected(),
            "fecha_desde": self.fecha_desde_var.get().strip(),
            "fecha_hasta": self.fecha_hasta_var.get().strip(),
        }

    def load_data(self) -> None:
        payload = self._filters_payload()
        updated = None
        update_warning = False
        try:
            self.stock_campo_rows, updated, update_warning = self.service.load_stock_campo(payload)
        except Exception as exc:
            self.stock_campo_rows = []
            messagebox.showwarning("Planificación diaria", f"No se pudo cargar stock campo: {exc}")
        try:
            self.stock_almacen_rows, almacen_warning = self.service.load_stock_almacen(payload)
            if almacen_warning:
                messagebox.showwarning("Planificación diaria", almacen_warning)
        except Exception as exc:
            self.stock_almacen_rows = []
            logging.getLogger(__name__).warning("No se pudo cargar stock almacén: %s", exc)
            messagebox.showwarning("Planificación diaria", "No se pudo cargar stock almacén. Se continuará con stock campo.")
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
        self.last_update.set(f"Última actualización: {updated}" if updated else "Última actualización: No disponible")
        if update_warning:
            messagebox.showwarning("Planificación diaria", "No se pudo leer un archivo auxiliar de actualización. Se continuará sin ese dato.")
        self.filters_status_var.set(f"Filtros activos: {payload}")

    def reset_filters(self) -> None:
        for widget in self.filter_widgets.values():
            widget.clear()
        self.fecha_desde_var.set("")
        self.fecha_hasta_var.set("")
        self.filters_status_var.set("Sin filtros activos")

    def export_excel(self) -> None:
        tab = self.tabs.tab(self.tabs.select(), "text")
        rows = self.stock_campo_rows if tab == "Stock campo" else self.stock_almacen_rows
        cultivo = ",".join(self.filter_widgets["cultivo"].get_selected())
        campana = ",".join(self.filter_widgets["campana"].get_selected())
        path = self.service.export_rows_to_excel(rows, tab, cultivo, campana)
        if path:
            messagebox.showinfo("Exportación", f"Archivo guardado en:\n{path}")
