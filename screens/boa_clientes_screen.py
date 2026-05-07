import tkinter as tk
from tkinter import ttk
from tempfile import NamedTemporaryFile
from typing import Any

from reports.report_data_builder import default_report_dict
from services.comercial_service import ComercialService
from widgets.analysis_help_button import AnalysisHelpButton
from widgets.chart_tooltips import ChartTooltipController
from widgets.report_button import ReportButton
from widgets.table_chart_view import TableChartView

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except Exception:
    FigureCanvasTkAgg = None
    Figure = None


class BOAClientesScreen(ttk.Frame):
    TABLE_RANKING_COLUMNS = [
        "Cliente", "Pais principal", "Kg cliente", "Kg cooperativa", "Merma kg", "% merma", "Cajas",
        "Precio medio real", "Precio medio orientativo", "Diferencia EUR/kg", "Importe real", "Importe orientativo",
        "Desviacion total EUR", "Kg total (debug)", "Kg con EurosKG válido (debug)",
        "Suma ponderada EurosKG (debug)", "Precio real calculado (debug)",
        "N pedidos", "Reclamaciones", "Importe reclamado", "Originales", "Estimados", "Sin datos",
    ]

    TABLE_EVOL_COLUMNS = [
        "Cliente", "Semana", "Kg cliente", "Precio medio real", "Precio medio orientativo",
        "Diferencia EUR/kg", "Importe real", "Kg total (debug)", "Kg con EurosKG válido (debug)",
        "Suma ponderada EurosKG (debug)", "Precio real calculado (debug)", "N pedidos",
    ]

    def __init__(self, master: tk.Misc, service: ComercialService, get_filters) -> None:
        super().__init__(master)
        self.service = service
        self.get_filters = get_filters
        self.status_var = tk.StringVar(value="")
        self.latest_payload: dict[str, Any] = {}
        self.kpi_vars = {
            "clientes": tk.StringVar(value="N clientes: 0"),
            "kg": tk.StringVar(value="Kg cliente: 0.00"),
            "cajas": tk.StringVar(value="Cajas: 0.00"),
            "imp_real": tk.StringVar(value="Importe real: 0.00 EUR"),
            "precio_real": tk.StringVar(value="Precio medio real: 0.000 EUR/kg"),
            "precio_ori": tk.StringVar(value="Precio medio orientativo: 0.000 EUR/kg"),
            "desv": tk.StringVar(value="Desviacion total EUR: 0.00"),
            "pedidos": tk.StringVar(value="N pedidos: 0"),
            "reclamados": tk.StringVar(value="Pedidos reclamados: 0"),
            "imp_reclamado": tk.StringVar(value="Importe reclamado: 0.00 EUR"),
        }
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Analisis de clientes", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        AnalysisHelpButton(header, "clientes").grid(row=0, column=1, sticky="e", padx=(0, 8))
        ReportButton(header, title_provider=lambda: "Informe BOA Clientes", data_provider=self._build_report_payload).grid(row=0, column=2, sticky="e")

        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        resumen_tab = ttk.Frame(self.tabs, padding=8)
        AnalysisHelpButton(resumen_tab, "clientes").pack(anchor="e", pady=(0, 6))
        kpi_frame = ttk.Frame(resumen_tab)
        kpi_frame.pack(fill="x", anchor="w")
        for i, key in enumerate(self.kpi_vars):
            ttk.Label(kpi_frame, textvariable=self.kpi_vars[key], style="KPI.TLabel").grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 24), pady=(0, 6))
        self.tabs.add(resumen_tab, text="Resumen clientes")

        ranking_tab = ttk.Frame(self.tabs, padding=8)
        ranking_tab.grid_rowconfigure(1, weight=1)
        ranking_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(ranking_tab, "clientes_ranking").grid(row=0, column=0, sticky="e", pady=(0, 6))
        self.ranking_table = TableChartView(ranking_tab, columns=self.TABLE_RANKING_COLUMNS)
        self.ranking_table.grid(row=1, column=0, sticky="nsew")
        self.tabs.add(ranking_tab, text="Ranking clientes")

        evol_tab = ttk.Frame(self.tabs, padding=8)
        evol_tab.grid_rowconfigure(1, weight=1)
        evol_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(evol_tab, "clientes_evolucion").grid(row=0, column=0, sticky="e", pady=(0, 6))
        self.evol_table = TableChartView(evol_tab, columns=self.TABLE_EVOL_COLUMNS)
        self.evol_table.grid(row=1, column=0, sticky="nsew")
        self.tabs.add(evol_tab, text="Evolucion por cliente")

        graph_tab = ttk.Frame(self.tabs, padding=8)
        graph_tab.grid_rowconfigure(1, weight=1)
        graph_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(graph_tab, "clientes_ranking").grid(row=0, column=0, sticky="e", pady=(0, 6))
        if Figure is None or FigureCanvasTkAgg is None:
            self.graph_error = ttk.Label(graph_tab, text="Matplotlib no disponible para grafica de clientes.")
            self.graph_error.grid(row=1, column=0, sticky="w")
            self.figure = None
            self.ax = None
            self.chart = None
        else:
            self.figure = Figure(figsize=(8, 5), dpi=100)
            self.ax = self.figure.add_subplot(111)
            self.chart = FigureCanvasTkAgg(self.figure, master=graph_tab)
            self.chart.get_tk_widget().grid(row=1, column=0, sticky="nsew")
            self.tooltip_controller = ChartTooltipController(self.ax, self.chart, self._format_tooltip)
        self.tabs.add(graph_tab, text="Grafica clientes")

        ttk.Label(self, textvariable=self.status_var, foreground="#b00020").grid(row=2, column=0, sticky="w", pady=(8, 0))

    def refresh(self) -> None:
        payload = self.service.get_analisis_clientes(self.get_filters())
        self.latest_payload = payload
        kpis = payload.get("kpis", {})
        self.kpi_vars["clientes"].set(f'N clientes: {int(kpis.get("clientes_count", 0)):,}')
        self.kpi_vars["kg"].set(f'Kg cliente: {kpis.get("kg_cliente", 0):,.2f}')
        self.kpi_vars["cajas"].set(f'Cajas: {kpis.get("cajas", 0):,.2f}')
        self.kpi_vars["imp_real"].set(f'Importe real: {kpis.get("importe_real", 0):,.2f} EUR')
        self.kpi_vars["precio_real"].set(f'Precio medio real: {kpis.get("precio_medio_real", 0):,.3f} EUR/kg')
        self.kpi_vars["precio_ori"].set(f'Precio medio orientativo: {kpis.get("precio_medio_orientativo", 0):,.3f} EUR/kg')
        self.kpi_vars["desv"].set(f'Desviacion total EUR: {kpis.get("desviacion_total_eur", 0):,.2f}')
        self.kpi_vars["pedidos"].set(f'N pedidos: {int(kpis.get("pedidos_count", 0)):,}')
        self.kpi_vars["reclamados"].set(f'Pedidos reclamados: {int(kpis.get("pedidos_reclamados", 0)):,}')
        self.kpi_vars["imp_reclamado"].set(f'Importe reclamado: {kpis.get("importe_reclamado", 0):,.2f} EUR')

        self._fill_ranking(payload.get("ranking", []))
        self._fill_evolucion(payload.get("evolucion", []))
        self._draw_top_clients(payload.get("grafica_clientes", []))

        warnings = payload.get("warnings", [])
        self.status_var.set(" | ".join(sorted(set(warnings))) if warnings else "")

    def _fill_ranking(self, rows: list[dict[str, Any]]) -> None:
        mapped = []
        for row in rows:
            mapped.append({
                "Cliente": row.get("grupo", ""), "Pais principal": row.get("pais_principal", ""),
                "Kg cliente": f'{row.get("kg_cliente", 0):,.2f}', "Kg cooperativa": f'{row.get("kg_cooperativa", 0):,.2f}',
                "Merma kg": f'{row.get("merma_kg", 0):,.2f}', "% merma": f'{row.get("pct_merma", 0) * 100:,.2f}%',
                "Cajas": f'{row.get("cajas", 0):,.2f}', "Precio medio real": f'{row.get("precio_medio_real", 0):,.3f}',
                "Precio medio orientativo": f'{row.get("precio_medio_orientativo", 0):,.3f}',
                "Diferencia EUR/kg": f'{row.get("diferencia_media_eurkg", 0):,.3f}',
                "Importe real": f'{row.get("importe_real", 0):,.2f}', "Importe orientativo": f'{row.get("importe_orientativo", 0):,.2f}',
                "Desviacion total EUR": f'{row.get("desviacion_total_eur", 0):,.2f}',
                "Kg total (debug)": f'{row.get("debug_kg_total", 0):,.2f}',
                "Kg con EurosKG válido (debug)": f'{row.get("debug_kg_euroskg_valido", 0):,.2f}',
                "Suma ponderada EurosKG (debug)": f'{row.get("debug_suma_ponderada_euroskg", 0):,.2f}',
                "Precio real calculado (debug)": f'{row.get("debug_precio_real_calculado", 0):,.4f}',
                "N pedidos": int(row.get("pedidos_count", 0)),
                "Reclamaciones": int(row.get("reclamaciones", 0)), "Importe reclamado": f'{row.get("importe_reclamado", 0):,.2f}',
                "Originales": int(row.get("originales", 0)), "Estimados": int(row.get("estimados", 0)), "Sin datos": int(row.get("sin_datos", 0)),
            })
        self.ranking_table.set_rows(mapped)

    def _fill_evolucion(self, rows: list[dict[str, Any]]) -> None:
        mapped = []
        for row in rows:
            mapped.append({
                "Cliente": row.get("cliente", ""), "Semana": row.get("semana", ""), "Kg cliente": f'{row.get("kg_cliente", 0):,.2f}',
                "Precio medio real": f'{row.get("precio_medio_real", 0):,.3f}', "Precio medio orientativo": f'{row.get("precio_medio_orientativo", 0):,.3f}',
                "Diferencia EUR/kg": f'{row.get("diferencia_media_eurkg", 0):,.3f}', "Importe real": f'{row.get("importe_real", 0):,.2f}',
                "Kg total (debug)": f'{row.get("debug_kg_total", 0):,.2f}',
                "Kg con EurosKG válido (debug)": f'{row.get("debug_kg_euroskg_valido", 0):,.2f}',
                "Suma ponderada EurosKG (debug)": f'{row.get("debug_suma_ponderada_euroskg", 0):,.2f}',
                "Precio real calculado (debug)": f'{row.get("debug_precio_real_calculado", 0):,.4f}',
                "N pedidos": int(row.get("pedidos_count", 0)),
            })
        self.evol_table.set_rows(mapped)

    def _draw_top_clients(self, rows: list[dict[str, Any]]) -> None:
        if self.ax is None or self.chart is None:
            return
        self.ax.clear()
        if hasattr(self, "tooltip_controller"):
            self.tooltip_controller.set_targets([])
        if not rows:
            self.ax.set_title("Top clientes por Importe real")
            self.ax.text(0.5, 0.5, "Sin datos", ha="center", va="center")
            self.chart.draw()
            return
        ordered_rows = list(rows)[::-1]
        labels = [str(r.get("cliente", "")) for r in ordered_rows]
        importes = [float(r.get("importe_real", 0) or 0) for r in ordered_rows]
        bars = self.ax.barh(labels, importes, color="#2e7d32")
        self.ax.set_title("Top 15 clientes por Importe real")
        self.ax.set_xlabel("Importe real (EUR)")
        self.ax.grid(axis="x", alpha=0.25)
        self.figure.tight_layout()
        if hasattr(self, "tooltip_controller"):
            targets = []
            for patch, row in zip(bars.patches, ordered_rows):
                payload = {"serie": "Importe real", "x_label": str(row.get("cliente", "")), "y_value": float(row.get("importe_real", 0) or 0), "kg": float(row.get("kg_cliente", 0) or 0)}
                targets.append((patch, "Importe real", [payload]))
            self.tooltip_controller.set_targets(targets)
        self.chart.draw()

    def _format_tooltip(self, payload: dict[str, Any]) -> str:
        return (
            f"Serie: {payload.get('serie', '')}\n"
            f"Cliente: {payload.get('x_label', '')}\n"
            f"Importe: {float(payload.get('y_value', 0) or 0):,.2f} EUR\n"
            f"Kg: {float(payload.get('kg', 0) or 0):,.0f}"
        )

    def _build_report_payload(self) -> dict[str, Any]:
        report = default_report_dict("BOA Comercial - Clientes", self.get_filters())
        report["kpis"] = [(k, str(v)) for k, v in self.latest_payload.get("kpis", {}).items()]
        report["tables"] = [
            {"title": "Ranking clientes", "columns": self.TABLE_RANKING_COLUMNS, "rows": self.ranking_table.rows},
            {"title": "Evolucion por cliente", "columns": self.TABLE_EVOL_COLUMNS, "rows": self.evol_table.rows},
        ]
        if self.figure is not None:
            tmp = NamedTemporaryFile(delete=False, suffix=".png")
            tmp.close()
            self.figure.savefig(tmp.name, dpi=150, bbox_inches="tight")
            report["chart_images"] = [tmp.name]
        return report
