import json
import logging
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

from services.planning_service import PlanningService
from widgets.data_table import DataTable
from widgets.screen_header import ScreenHeader
from widgets.date_picker import DatePickerPopup
from widgets.multi_select_filter import MultiSelectFilter


class PlanificacionDiariaScreen(ttk.Frame):
    FILTERS_FILE = Path("config") / "planificacion_diaria_filters.json"
    FILTER_KEYS = ["campana", "cultivo", "empresa", "semana", "var_coop", "grupo_varietal", "marca"]

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
        self.stock_almacen_detalle_rows: list[dict] = []
        self.pedidos_pendientes_rows: list[dict] = []
        self._build_ui()
        self._load_filter_options()
        self._load_filters()
        self.load_data(save_filters=False)

    def _load_filter_options(self) -> None:
        diag = self.service.diagnose_loteado_tables()
        if diag.get("warning"):
            logging.getLogger(__name__).warning(diag["warning"])
        for key in ("campana", "cultivo", "empresa", "semana", "var_coop", "grupo_varietal", "marca"):
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
        fields = [("Campaña", "campana"), ("Cultivo", "cultivo"), ("Semana", "semana"), ("Fecha desde", "fecha_desde"), ("Fecha hasta", "fecha_hasta"), ("Empresa", "empresa"), ("Variedad Coop", "var_coop"), ("Grupo varietal", "grupo_varietal"), ("Marca", "marca")]
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
        btns.grid(row=2, column=0, columnspan=9, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Aplicar filtros", command=lambda: self.load_data(save_filters=True)).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Limpiar filtros", command=self.reset_filters).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Reaplicar filtros", command=lambda: self.load_data(save_filters=True)).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Exportar Excel", command=self.export_excel).pack(side="left")
        ttk.Label(filters_frame, textvariable=self.filters_status_var).grid(row=3, column=0, columnspan=9, sticky="w", padx=4, pady=(6, 0))

        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=2, column=0, sticky="nsew")

        self.campo_tab = ttk.Frame(self.tabs, padding=8)
        self.almacen_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(self.campo_tab, text="Stock campo")
        self.tabs.add(self.almacen_tab, text="Stock almacén")
        self.pedidos_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(self.pedidos_tab, text="Pedidos pendientes")

        self.kpi_campo = tk.StringVar(value="Kg campo total: 0 | Nº partidas: 0 | Nº variedades: 0")
        self.kpi_almacen = tk.StringVar(value="Kg stock almacén: 0 | Nº grupos: 0 | Nº variedades: 0 | Nº calibres: 0")
        self.last_update = tk.StringVar(value="")
        self.kpi_pedidos = tk.StringVar(value="Kg pedido teórico total: 0 | Kg hecho real total: 0 | Kg pendiente total: 0 | Nº pedidos: 0 | Nº líneas: 0 | Nº líneas sin datos: 0 | Nº líneas parciales: 0")

        ttk.Label(self.campo_tab, textvariable=self.kpi_campo, style="KPI.TLabel").pack(anchor="w", pady=(0, 2))
        ttk.Label(self.campo_tab, textvariable=self.last_update).pack(anchor="w", pady=(0, 6))
        self.campo_table = DataTable(self.campo_tab, ["Cultivo", "Campaña", "Fecha carga", "Semana", "Socio", "Variedad", "Grupo varietal", "Boleta", "Plataforma", "Empresa", "Restricciones", "Color", "Kg campo"])
        self.campo_table.pack(fill="both", expand=True)

        header_almacen = ttk.Frame(self.almacen_tab)
        header_almacen.pack(fill="x", pady=(0, 6))
        ttk.Label(header_almacen, textvariable=self.kpi_almacen, style="KPI.TLabel").pack(side="left")
        ttk.Button(header_almacen, text="Ver detalle palets", command=self.show_detalle_palets).pack(side="right")
        self.almacen_table = DataTable(self.almacen_tab, ["Cultivo", "Campaña", "Variedad", "Grupo varietal", "Calibre", "Categoría", "Marca", "IdConfeccion", "Confección", "Palets", "Cajas", "Kg stock", "Agrupado"])
        self.almacen_table.pack(fill="both", expand=True)

        ttk.Label(self.pedidos_tab, textvariable=self.kpi_pedidos, style="KPI.TLabel").pack(anchor="w", pady=(0, 6))
        self.pedidos_table = DataTable(
            self.pedidos_tab,
            ["Semana", "Fecha salida", "Cliente", "IdPedidoLora", "Línea", "Cultivo", "Campaña", "Variedad Coop", "Grupo varietal", "Calibre", "Categoría", "Marca", "Confección", "Cajas pedido", "Cajas hechas", "Cajas pendientes", "Kg pedido teórico", "Kg hecho real", "Kg pendiente", "% hecho", "Estado", "Aviso"],
        )
        self.pedidos_table.pack(fill="both", expand=True)

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
            "grupo_varietal": self.filter_widgets["grupo_varietal"].get_selected(),
            "marca": self.filter_widgets["marca"].get_selected(),
            "fecha_desde": self.fecha_desde_var.get().strip(),
            "fecha_hasta": self.fecha_hasta_var.get().strip(),
        }

    def load_data(self, save_filters: bool = True) -> None:
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
            self.stock_almacen_detalle_rows = self.service.load_stock_almacen_detalle_palets(payload)
            if almacen_warning:
                messagebox.showwarning("Planificación diaria", almacen_warning)
        except Exception as exc:
            self.stock_almacen_rows = []
            self.stock_almacen_detalle_rows = []
            logging.getLogger(__name__).warning("No se pudo cargar stock almacén: %s", exc)
            messagebox.showwarning("Planificación diaria", f"No se pudo cargar stock almacén: {exc}")
        pedidos_kpi = {}
        try:
            self.pedidos_pendientes_rows, pedidos_kpi = self.service.get_pedidos_pendientes(payload, modo="10_dias")
        except Exception as exc:
            self.pedidos_pendientes_rows = []
            logging.getLogger(__name__).warning("No se pudieron cargar pedidos pendientes: %s", exc)
            messagebox.showwarning("Planificación diaria", f"No se pudieron cargar pedidos pendientes: {exc}")
        self.campo_table.set_rows(self.stock_campo_rows)
        self.almacen_table.set_rows(self.stock_almacen_rows)
        self.pedidos_table.set_rows(self.pedidos_pendientes_rows)
        self.kpi_campo.set(
            f"Kg campo total: {sum(float(r.get('Kg campo', 0) or 0) for r in self.stock_campo_rows):,.2f} | "
            f"Nº partidas: {len(self.stock_campo_rows)} | Nº variedades: {len({r.get('Variedad') for r in self.stock_campo_rows})}"
        )
        self.kpi_almacen.set(
            f"Kg stock almacén: {sum(float(r.get('Kg stock', 0) or 0) for r in self.stock_almacen_rows):,.2f} | "
            f"Nº grupos: {len(self.stock_almacen_rows)} | "
            f"Nº variedades: {len({r.get('Variedad') for r in self.stock_almacen_rows})} | "
            f"Nº calibres: {len({r.get('Calibre') for r in self.stock_almacen_rows})}"
        )
        self.last_update.set(f"Última actualización: {updated}" if updated else "Última actualización: No disponible")
        self.kpi_pedidos.set(
            f"Kg pedido teórico total: {float(pedidos_kpi.get('Kg pedido teórico total', 0) or 0):,.2f} | "
            f"Kg hecho real total: {float(pedidos_kpi.get('Kg hecho real total', 0) or 0):,.2f} | "
            f"Kg pendiente total: {float(pedidos_kpi.get('Kg pendiente total', 0) or 0):,.2f} | "
            f"Nº pedidos: {int(pedidos_kpi.get('Nº pedidos', 0) or 0)} | "
            f"Nº líneas: {int(pedidos_kpi.get('Nº líneas', 0) or 0)} | "
            f"Nº líneas sin datos: {int(pedidos_kpi.get('Nº líneas sin datos', 0) or 0)} | "
            f"Nº líneas parciales: {int(pedidos_kpi.get('Nº líneas parciales', 0) or 0)}"
        )
        if update_warning:
            messagebox.showwarning("Planificación diaria", "No se pudo leer un archivo auxiliar de actualización. Se continuará sin ese dato.")
        if save_filters:
            self._save_filters(payload)
        self.filters_status_var.set(self._format_filters_status(payload))

    def reset_filters(self) -> None:
        for widget in self.filter_widgets.values():
            widget.clear()
        self.fecha_desde_var.set("")
        self.fecha_hasta_var.set("")
        self._clear_saved_filters()
        self.filters_status_var.set("Sin filtros activos")

    def export_excel(self) -> None:
        tab = self.tabs.tab(self.tabs.select(), "text")
        rows = self.stock_campo_rows if tab == "Stock campo" else self.stock_almacen_rows
        cultivos = self.filter_widgets["cultivo"].get_selected()
        campanas = self.filter_widgets["campana"].get_selected()
        path = self.service.export_rows_to_excel(rows, tab, cultivos, campanas)
        if path:
            messagebox.showinfo("Exportación", f"Archivo guardado en:\n{path}")


    def _format_filters_status(self, payload: dict) -> str:
        labels = {
            "campana": "Campaña",
            "cultivo": "Cultivo",
            "empresa": "Empresa",
            "semana": "Semana",
            "var_coop": "Variedad Coop",
            "grupo_varietal": "Grupo varietal",
            "marca": "Marca",
            "fecha_desde": "Fecha desde",
            "fecha_hasta": "Fecha hasta",
        }
        has_values = any(payload.get(k) for k in labels)
        if not has_values:
            return "Sin filtros activos"
        parts: list[str] = []
        for key in ("campana", "cultivo", "empresa", "semana", "var_coop", "grupo_varietal", "marca", "fecha_desde", "fecha_hasta"):
            value = payload.get(key, []) if key in self.FILTER_KEYS else payload.get(key, "")
            if isinstance(value, list):
                display = ",".join(value) if value else "Todos"
            else:
                display = str(value).strip() or "Todos"
            parts.append(f"{labels[key]}={display}")
        return "Filtros activos: " + " | ".join(parts)

    def _save_filters(self, payload: dict) -> None:
        self.FILTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.FILTERS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_filters(self) -> None:
        if not self.FILTERS_FILE.exists():
            self.filters_status_var.set("Sin filtros activos")
            return
        try:
            payload = json.loads(self.FILTERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        for key in self.FILTER_KEYS:
            raw = payload.get(key, [])
            values = raw if isinstance(raw, list) else ([str(raw)] if str(raw or "").strip() else [])
            self.filter_widgets[key].set_selected([str(v).strip() for v in values if str(v or "").strip()])
        self.fecha_desde_var.set(str(payload.get("fecha_desde", "") or "").strip())
        self.fecha_hasta_var.set(str(payload.get("fecha_hasta", "") or "").strip())
        self.filters_status_var.set(self._format_filters_status(self._filters_payload()))

    def _clear_saved_filters(self) -> None:
        if self.FILTERS_FILE.exists():
            self.FILTERS_FILE.unlink()

    def show_detalle_palets(self) -> None:
        if not self.stock_almacen_detalle_rows:
            messagebox.showinfo("Planificación diaria", "No hay detalle de palets para los filtros actuales.")
            return
        modal = tk.Toplevel(self)
        modal.title("Detalle palets - Stock almacén")
        modal.geometry("1320x620")
        modal.transient(self.winfo_toplevel())
        modal.grab_set()
        table = DataTable(
            modal,
            ["IdPalet", "Pedido", "FechaAlmacen", "Estado", "Terminado", "Variedad", "Grupo varietal", "Calibre", "Categoria", "Marca", "IdConfeccion", "Confeccion", "Cajas", "Neto"],
        )
        table.pack(fill="both", expand=True, padx=10, pady=10)
        rows = []
        for row in self.stock_almacen_detalle_rows:
            rows.append(
                {
                    "IdPalet": row.get("IdPalet", ""),
                    "Pedido": row.get("Pedido", ""),
                    "FechaAlmacen": row.get("FechaAlmacen", ""),
                    "Estado": row.get("Estado", ""),
                    "Terminado": row.get("Terminado", ""),
                    "Variedad": row.get("Variedad", ""),
                    "Grupo varietal": row.get("GrupoVarietal", ""),
                    "Calibre": row.get("Calibre", ""),
                    "Categoria": row.get("Categoria", ""),
                    "Marca": row.get("Marca", ""),
                    "IdConfeccion": row.get("IdConfeccion", ""),
                    "Confeccion": row.get("Confeccion", ""),
                    "Cajas": round(float(row.get("Cajas") or 0), 2),
                    "Neto": round(float(row.get("Neto") or 0), 2),
                }
            )
        table.set_rows(rows)
