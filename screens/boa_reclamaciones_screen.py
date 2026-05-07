import logging
import tkinter as tk
from tkinter import ttk
from tempfile import NamedTemporaryFile
from typing import Any

from reports.report_data_builder import default_report_dict
from services.comercial_service import ComercialService
from widgets.analysis_help_button import AnalysisHelpButton
from widgets.chart_tooltips import ChartTooltipController
from widgets.data_table import DataTable
from widgets.report_button import ReportButton
from widgets.table_chart_view import TableChartView

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except Exception:
    FigureCanvasTkAgg = None
    Figure = None

logger = logging.getLogger(__name__)


class BOAReclamacionesScreen(ttk.Frame):
    TABLE_DETALLE_COLUMNS = [
        "IdPedido", "Linea", "FechaSalida", "Fecha reclamacion", "Campana", "Cultivo", "EMPRESA", "Semana",
        "Cliente", "Pais", "VarCoop", "VarCliente", "Calibre", "Categoria", "Marca", "Causa",
        "Neto reclamado", "Importe reclamado", "Medida", "Observaciones",
    ]
    TABLE_CAUSA_COLUMNS = ["Causa", "N reclamaciones", "Importe reclamado", "Neto reclamado", "N clientes", "N pedidos"]
    TABLE_CLIENTE_COLUMNS = ["Cliente", "Pais", "N reclamaciones", "Importe reclamado", "Neto reclamado", "N pedidos reclamados", "Causa principal"]

    def __init__(self, master: tk.Misc, service: ComercialService, get_filters) -> None:
        super().__init__(master)
        self.service = service
        self.get_filters = get_filters
        self.status_var = tk.StringVar(value="")
        self.latest_payload: dict[str, Any] = {}
        self.kpi_vars = {
            "pedidos": tk.StringVar(value="N pedidos reclamados: 0"),
            "lineas": tk.StringVar(value="N lineas reclamadas: 0"),
            "importe": tk.StringVar(value="Importe reclamado: 0.00 EUR"),
            "kg": tk.StringVar(value="Kg reclamados: 0.00"),
            "pct_pedidos": tk.StringVar(value="% pedidos reclamados: 0.00%"),
            "pct_importe": tk.StringVar(value="% importe reclamado: 0.00%"),
            "cliente_top": tk.StringVar(value="Cliente con mas reclamacion: -"),
            "causa_top": tk.StringVar(value="Causa principal: -"),
        }
        self.figure = None
        self.ax = None
        self.chart = None
        self.tooltip_controller = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Reclamaciones", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        AnalysisHelpButton(header, "reclamaciones").grid(row=0, column=1, sticky="e", padx=(0, 8))
        ReportButton(header, title_provider=lambda: "Informe BOA Reclamaciones", data_provider=self._build_report_payload).grid(row=0, column=2, sticky="e")

        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        resumen_tab = ttk.Frame(self.tabs, padding=8)
        AnalysisHelpButton(resumen_tab, "reclamaciones").pack(anchor="e", pady=(0, 6))
        kpi_frame = ttk.Frame(resumen_tab)
        kpi_frame.pack(fill="x", anchor="w")
        for i, key in enumerate(self.kpi_vars):
            ttk.Label(kpi_frame, textvariable=self.kpi_vars[key], style="KPI.TLabel").grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=(0, 6))
        self.tabs.add(resumen_tab, text="Resumen reclamaciones")

        detalle_tab = ttk.Frame(self.tabs, padding=8)
        detalle_tab.grid_rowconfigure(1, weight=1)
        detalle_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(detalle_tab, "reclamaciones").grid(row=0, column=0, sticky="e", pady=(0, 6))
        self.detalle_table = DataTable(detalle_tab, columns=self.TABLE_DETALLE_COLUMNS)
        self.detalle_table.grid(row=1, column=0, sticky="nsew")
        self.tabs.add(detalle_tab, text="Detalle reclamaciones")

        causa_tab = ttk.Frame(self.tabs, padding=8)
        causa_tab.grid_rowconfigure(1, weight=1)
        causa_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(causa_tab, "reclamaciones_por_causa").grid(row=0, column=0, sticky="e", pady=(0, 6))
        self.causa_table = TableChartView(causa_tab, columns=self.TABLE_CAUSA_COLUMNS)
        self.causa_table.grid(row=1, column=0, sticky="nsew")
        self.tabs.add(causa_tab, text="Por causa")

        cliente_tab = ttk.Frame(self.tabs, padding=8)
        cliente_tab.grid_rowconfigure(1, weight=1)
        cliente_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(cliente_tab, "reclamaciones_por_cliente").grid(row=0, column=0, sticky="e", pady=(0, 6))
        self.cliente_table = TableChartView(cliente_tab, columns=self.TABLE_CLIENTE_COLUMNS)
        self.cliente_table.grid(row=1, column=0, sticky="nsew")
        self.tabs.add(cliente_tab, text="Por cliente")

        graf_tab = ttk.Frame(self.tabs, padding=8)
        graf_tab.grid_rowconfigure(1, weight=1)
        graf_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(graf_tab, "reclamaciones_por_causa").grid(row=0, column=0, sticky="e", pady=(0, 6))
        if Figure is None or FigureCanvasTkAgg is None:
            logger.info("Matplotlib disponible para reclamaciones: False")
            ttk.Label(graf_tab, text="Matplotlib no disponible. Instalar con: c:/python313/python.exe -m pip install matplotlib").grid(row=1, column=0, sticky="w")
        else:
            logger.info("Matplotlib disponible para reclamaciones: True")
            self.figure = Figure(figsize=(8, 5), dpi=100)
            self.ax = self.figure.add_subplot(111)
            self.chart = FigureCanvasTkAgg(self.figure, master=graf_tab)
            self.chart.get_tk_widget().grid(row=1, column=0, sticky="nsew")
            self.tooltip_controller = ChartTooltipController(self.ax, self.chart, self._format_tooltip)
        self.tabs.add(graf_tab, text="Grafica reclamaciones")

        ttk.Label(self, textvariable=self.status_var, foreground="#b00020").grid(row=2, column=0, sticky="w", pady=(8, 0))

    def refresh(self) -> None:
        payload = self.service.get_analisis_reclamaciones(self.get_filters())
        self.latest_payload = payload
        resumen = payload.get("resumen", {})
        self.kpi_vars["pedidos"].set(f'N pedidos reclamados: {int(resumen.get("pedidos_reclamados", 0)):,}')
        self.kpi_vars["lineas"].set(f'N lineas reclamadas: {int(resumen.get("lineas_reclamadas", 0)):,}')
        self.kpi_vars["importe"].set(f'Importe reclamado: {float(resumen.get("importe_reclamado", 0) or 0):,.2f} EUR')
        self.kpi_vars["kg"].set(f'Kg reclamados: {float(resumen.get("kg_reclamados", 0) or 0):,.2f}')
        self.kpi_vars["pct_pedidos"].set(f'% pedidos reclamados: {float(resumen.get("pct_pedidos_reclamados", 0) or 0):,.2f}%')
        self.kpi_vars["pct_importe"].set(f'% importe reclamado: {float(resumen.get("pct_importe_reclamado", 0) or 0):,.2f}%')
        self.kpi_vars["cliente_top"].set(f'Cliente con mas reclamacion: {resumen.get("cliente_top_reclamacion", "") or "-"}')
        self.kpi_vars["causa_top"].set(f'Causa principal: {resumen.get("causa_principal", "") or "-"}')

        self._fill_detalle(payload.get("detalle", []))
        self._fill_causa(payload.get("por_causa", []))
        self._fill_cliente(payload.get("por_cliente", []))

        por_causa_rows = payload.get("por_causa", [])
        grafica_rows = payload.get("grafica_causas", [])
        logger.info("Pantalla reclamaciones por_causa filas: %s", len(por_causa_rows))
        logger.info("Pantalla reclamaciones grafica_causas filas: %s", len(grafica_rows))
        self._draw_chart(grafica_rows if grafica_rows else por_causa_rows)

        warnings = payload.get("warnings", [])
        self.status_var.set(" | ".join(sorted(set(warnings))) if warnings else "")

    def _fill_detalle(self, rows: list[dict[str, Any]]) -> None:
        mapped = []
        for r in rows:
            mapped.append({
                "IdPedido": r.get("id_pedido", ""), "Linea": r.get("linea", ""), "FechaSalida": r.get("fecha_salida", ""), "Fecha reclamacion": r.get("fecha_reclamacion", ""),
                "Campana": r.get("campana", ""), "Cultivo": r.get("cultivo", ""), "EMPRESA": r.get("empresa", ""), "Semana": r.get("semana", ""),
                "Cliente": r.get("cliente", ""), "Pais": r.get("pais", ""), "VarCoop": r.get("var_coop", ""), "VarCliente": r.get("var_cliente", ""),
                "Calibre": r.get("calibre", ""), "Categoria": r.get("categoria", ""), "Marca": r.get("marca", ""), "Causa": r.get("causa", ""),
                "Neto reclamado": f'{float(r.get("neto_reclamado", 0) or 0):,.2f}', "Importe reclamado": f'{float(r.get("importe_reclamado", 0) or 0):,.2f}',
                "Medida": r.get("medida", ""), "Observaciones": r.get("observaciones", ""),
            })
        self.detalle_table.set_rows(mapped)

    def _fill_causa(self, rows: list[dict[str, Any]]) -> None:
        mapped = []
        for r in rows:
            mapped.append({
                "Causa": r.get("causa", ""), "N reclamaciones": int(r.get("reclamaciones_count", 0)),
                "Importe reclamado": f'{float(r.get("importe_reclamado", 0) or 0):,.2f}', "Neto reclamado": f'{float(r.get("neto_reclamado", 0) or 0):,.2f}',
                "N clientes": int(r.get("clientes_count", 0)), "N pedidos": int(r.get("pedidos_count", 0)),
            })
        self.causa_table.set_rows(mapped)

    def _fill_cliente(self, rows: list[dict[str, Any]]) -> None:
        mapped = []
        for r in rows:
            mapped.append({
                "Cliente": r.get("cliente", ""), "Pais": r.get("pais", ""), "N reclamaciones": int(r.get("reclamaciones_count", 0)),
                "Importe reclamado": f'{float(r.get("importe_reclamado", 0) or 0):,.2f}', "Neto reclamado": f'{float(r.get("neto_reclamado", 0) or 0):,.2f}',
                "N pedidos reclamados": int(r.get("pedidos_reclamados", 0)), "Causa principal": r.get("causa_principal", ""),
            })
        self.cliente_table.set_rows(mapped)

    def _draw_chart(self, rows: list[dict[str, Any]]) -> None:
        if self.ax is None or self.chart is None:
            return
        self.ax.clear()
        self.ax.set_title("Top causas de reclamacion por importe")
        if self.tooltip_controller is not None:
            self.tooltip_controller.set_targets([])

        if not rows:
            logger.info("No se pinta grafica reclamaciones por falta de datos.")
            self.ax.text(0.5, 0.5, "No hay reclamaciones para graficar con los filtros actuales.", ha="center", va="center", transform=self.ax.transAxes)
            self.chart.draw()
            return

        ordered_rows = list(rows)[:10][::-1]
        labels = [str(r.get("causa", "")) for r in ordered_rows]
        valores = [float(r.get("importe_reclamado", 0) or 0) for r in ordered_rows]
        bars = self.ax.barh(labels, valores, color="#ad1457")
        self.ax.set_xlabel("Importe reclamado EUR")
        self.ax.grid(axis="x", alpha=0.25)
        self.figure.tight_layout()

        if self.tooltip_controller is not None:
            targets = []
            for patch, row in zip(bars.patches, ordered_rows):
                payload = {
                    "causa": str(row.get("causa", "")),
                    "importe_reclamado": float(row.get("importe_reclamado", 0) or 0),
                    "neto_reclamado": float(row.get("neto_reclamado", 0) or 0),
                    "reclamaciones_count": int(row.get("reclamaciones_count", 0) or 0),
                    "pedidos_count": int(row.get("pedidos_count", 0) or 0),
                }
                targets.append((patch, "Causa", [payload]))
            self.tooltip_controller.set_targets(targets)

        self.chart.draw()

    @staticmethod
    def _format_tooltip(payload: dict[str, Any]) -> str:
        return (
            f"Causa: {payload.get('causa', '')}\n"
            f"Importe reclamado: {float(payload.get('importe_reclamado', 0) or 0):,.2f} EUR\n"
            f"Neto reclamado: {float(payload.get('neto_reclamado', 0) or 0):,.2f}\n"
            f"N reclamaciones: {int(payload.get('reclamaciones_count', 0) or 0)}\n"
            f"N pedidos: {int(payload.get('pedidos_count', 0) or 0)}"
        )

    def _build_report_payload(self) -> dict[str, Any]:
        report = default_report_dict("BOA Comercial - Reclamaciones", self.get_filters())
        report["kpis"] = [(k, str(v)) for k, v in self.latest_payload.get("kpis", self.latest_payload.get("resumen", {})).items()]
        report["tables"] = [
            {"title": "Detalle reclamaciones", "columns": self.TABLE_DETALLE_COLUMNS, "rows": self.detalle_table.rows},
            {"title": "Por causa", "columns": self.TABLE_CAUSA_COLUMNS, "rows": self.causa_table.rows},
            {"title": "Por cliente", "columns": self.TABLE_CLIENTE_COLUMNS, "rows": self.cliente_table.rows},
        ]
        if self.figure is not None:
            tmp = NamedTemporaryFile(delete=False, suffix=".png")
            tmp.close()
            self.figure.savefig(tmp.name, dpi=150, bbox_inches="tight")
            report["chart_images"] = [tmp.name]
        return report
