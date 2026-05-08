import tkinter as tk
from tkinter import ttk
from typing import Any
import logging

from reports.report_data_builder import default_report_dict
from services.comercial_service import ComercialService
from widgets.analysis_help_button import AnalysisHelpButton
from widgets.chart_tooltips import ChartTooltipController
from widgets.report_button import ReportButton
from widgets.table_chart_toggle import TableChartToggleFrame
from widgets.table_chart_view import TableChartView

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except Exception:
    FigureCanvasTkAgg = None
    Figure = None


class BOAPreciosScreen(ttk.Frame):
    logger = logging.getLogger(__name__)
    TABLE_WEEK_COLUMNS = [
        "Semana", "Kg cliente", "Precio medio real", "Precio medio orientativo", "Diferencia EUR/kg",
        "Importe real", "Importe orientativo", "Desviacion total EUR",
        "Kg total (debug)", "Kg con EurosKG válido (debug)", "Suma ponderada EurosKG (debug)", "Precio real calculado (debug)",
        "Originales", "Estimados", "Sin datos", "N pedidos",
    ]
    TABLE_VAR_CAL_COLUMNS = [
        "VarCoop", "Calibre", "Kg cliente", "Precio medio real", "Precio medio orientativo",
        "Diferencia EUR/kg", "Desviacion total EUR",
        "Kg total (debug)", "Kg con EurosKG válido (debug)", "Suma ponderada EurosKG (debug)", "Precio real calculado (debug)",
        "N pedidos",
    ]
    TABLE_DESV_CLIENTE_COLUMNS = [
        "Ranking", "Cliente", "Pais", "Kg", "Precio real €/kg", "Precio orientativo €/kg",
        "Dif. precio €/kg", "Coste forfait €/kg", "Margen €/kg", "Margen total €",
        "N reclam.", "Reclam. €/kg", "% reclamado", "Margen ajustado €/kg", "Margen ajustado total €",
        "Cumplimiento %", "Cobertura forfait %", "Estado cobertura", "Pts rentabilidad", "Pts precio", "Pts volumen", "Penalización reclam.", "Prioridad", "Estado", "PrioridadScore",
    ]

    class _SimpleTableView(ttk.Frame):
        def __init__(self, master: tk.Misc, columns: list[str]) -> None:
            super().__init__(master)
            from widgets.data_table import DataTable

            self.rows: list[dict[str, Any]] = []
            self.grid_rowconfigure(0, weight=1)
            self.grid_columnconfigure(0, weight=1)
            self.table = DataTable(self, columns=columns)
            self.table.grid(row=0, column=0, sticky="nsew")

        def set_rows(self, rows: list[dict[str, Any]]) -> None:
            self.rows = list(rows)
            self.table.set_rows(self.rows)

    class _DesvChartView(ttk.Frame):
        def __init__(self, master: tk.Misc, tooltip_formatter) -> None:
            super().__init__(master)
            self.rows: list[dict[str, Any]] = []
            self.tooltip_formatter = tooltip_formatter
            self.figure = None
            self.ax = None
            self.chart = None
            self.tooltip_controller = None
            self.grid_rowconfigure(0, weight=1)
            self.grid_columnconfigure(0, weight=1)
            if Figure is None or FigureCanvasTkAgg is None:
                ttk.Label(self, text="Matplotlib no disponible para la gráfica de desviación.").grid(row=0, column=0, sticky="w")
            else:
                self.figure = Figure(figsize=(9, 3.5), dpi=100)
                self.ax = self.figure.add_subplot(111)
                self.chart = FigureCanvasTkAgg(self.figure, master=self)
                self.chart.get_tk_widget().grid(row=0, column=0, sticky="nsew")
                self.tooltip_controller = ChartTooltipController(self.ax, self.chart, self.tooltip_formatter)

        def set_rows(self, rows: list[dict[str, Any]]) -> None:
            self.rows = list(rows)
            if self.ax is None or self.chart is None:
                return
            self.ax.clear()
            if self.tooltip_controller is not None:
                self.tooltip_controller.set_targets([])
            if not self.rows:
                self.ax.text(0.5, 0.5, "Sin datos para mostrar", ha="center", va="center", transform=self.ax.transAxes)
                self.chart.draw()
                return
            top = self.rows[:15][::-1]
            labels = [str(r.get("cliente", "")) for r in top]
            vals = [float(r.get("impacto_eur", 0) or 0) for r in top]
            colors = ["#2e7d32" if v >= 0 else "#c62828" for v in vals]
            bars = self.ax.barh(labels, vals, color=colors)
            self.ax.set_title("Top 15 clientes por Impacto €")
            self.ax.set_xlabel("Impacto €")
            self.ax.grid(axis="x", alpha=0.25)
            if self.figure is not None:
                self.figure.tight_layout()
            if self.tooltip_controller is not None:
                targets = []
                for patch, row in zip(bars.patches, top):
                    payload = {
                        "cliente": row.get("cliente", ""),
                        "impacto": float(row.get("impacto_eur", 0) or 0),
                        "desviacion": float(row.get("desviacion_eurkg", 0) or 0),
                        "kg": float(row.get("kg_cliente", 0) or 0),
                        "pedidos": int(row.get("pedidos_count", 0) or 0),
                    }
                    targets.append((patch, "Impacto", [payload]))
                self.tooltip_controller.set_targets(targets)
            self.chart.draw()

    def __init__(self, master: tk.Misc, service: ComercialService, get_filters) -> None:
        super().__init__(master)
        self.service = service
        self.get_filters = get_filters
        self.status_var = tk.StringVar(value="")
        self.latest_data: dict[str, Any] = {}
        self.kpi_vars = {
            "precio_real": tk.StringVar(value="Precio medio real ponderado: 0.000 EUR/kg"),
            "precio_ori": tk.StringVar(value="Precio medio orientativo ponderado: 0.000 EUR/kg"),
            "dif_media": tk.StringVar(value="Diferencia media EUR/kg: 0.000"),
            "imp_real": tk.StringVar(value="Importe real: 0.00 EUR"),
            "imp_ori": tk.StringVar(value="Importe orientativo: 0.00 EUR"),
            "desv_total": tk.StringVar(value="Desviacion total EUR: 0.00"),
            "kg_con": tk.StringVar(value="Kg con precio orientativo: 0.00"),
            "kg_sin": tk.StringVar(value="Kg sin precio orientativo: 0.00"),
            "cov": tk.StringVar(value="% cobertura precio orientativo: 0.00%"),
        }
        self.desv_kpi_vars = {
            "kg_analizados": tk.StringVar(value="Kg analizados: 0.00"),
            "kg_con_forfait": tk.StringVar(value="Kg con forfait: 0.00"),
            "kg_sin_forfait": tk.StringVar(value="Kg sin forfait: 0.00"),
            "cov_forfait": tk.StringVar(value="Cobertura forfait %: 0.00%"),
            "margen_total": tk.StringVar(value="Margen total €: 0.00"),
            "margen_medio": tk.StringVar(value="Margen medio €/kg: 0.0000"),
            "precio_real": tk.StringVar(value="Precio real medio €/kg: 0.0000"),
            "precio_ori": tk.StringVar(value="Precio orientativo medio €/kg: 0.0000"),
            "dif_media": tk.StringVar(value="Diferencia media €/kg: 0.0000"),
            "coste_forfait": tk.StringVar(value="Coste forfait medio €/kg: 0.0000"),
        }
        self.desv_sort_var = tk.StringVar(value="prioridad_score")
        self.figure = None
        self.ax = None
        self.chart = None
        self.tooltip_controller = None
        self.real_line = None
        self.orient_line = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Analisis de precios", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        AnalysisHelpButton(header, "precios").grid(row=0, column=1, sticky="e", padx=(0, 8))
        ReportButton(header, title_provider=lambda: "Informe BOA Precios", data_provider=self._build_report_payload).grid(row=0, column=2, sticky="e")

        self.tabs = ttk.Notebook(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        resumen_tab = ttk.Frame(self.tabs, padding=8)
        resumen_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(resumen_tab, "precios").grid(row=0, column=0, sticky="e", pady=(0, 6))
        kpi_frame = ttk.Frame(resumen_tab)
        kpi_frame.grid(row=1, column=0, sticky="ew")
        for i, key in enumerate(self.kpi_vars):
            ttk.Label(kpi_frame, textvariable=self.kpi_vars[key], style="KPI.TLabel").grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 24), pady=(0, 6))
        self.tabs.add(resumen_tab, text="Resumen precios")

        evo_tab = ttk.Frame(self.tabs, padding=8)
        evo_tab.grid_rowconfigure(1, weight=1)
        evo_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(evo_tab, "precios_evolucion_semanal").grid(row=0, column=0, sticky="e", pady=(0, 6))
        chart_frame = ttk.LabelFrame(evo_tab, text="Evolucion semanal precio medio (EUR/kg)", padding=8)
        chart_frame.grid(row=1, column=0, sticky="nsew")
        chart_frame.grid_columnconfigure(0, weight=1)
        if Figure is None or FigureCanvasTkAgg is None:
            self.chart_error = ttk.Label(chart_frame, text="Matplotlib no disponible para la grafica semanal.")
            self.chart_error.grid(row=0, column=0, sticky="w")
        else:
            self.figure = Figure(figsize=(9, 4), dpi=100)
            self.ax = self.figure.add_subplot(111)
            self.chart = FigureCanvasTkAgg(self.figure, master=chart_frame)
            self.chart.get_tk_widget().grid(row=0, column=0, sticky="nsew")
            self.tooltip_controller = ChartTooltipController(self.ax, self.chart, self._format_tooltip)
        self.tabs.add(evo_tab, text="Evolucion semanal")

        week_tab = ttk.Frame(self.tabs, padding=8)
        week_tab.grid_rowconfigure(1, weight=1)
        week_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(week_tab, "precios_analisis_semana").grid(row=0, column=0, sticky="e", pady=(0, 6))
        self.week_table = TableChartView(week_tab, columns=self.TABLE_WEEK_COLUMNS)
        self.week_table.grid(row=1, column=0, sticky="nsew")
        self.tabs.add(week_tab, text="Analisis por semana")

        var_cal_tab = ttk.Frame(self.tabs, padding=8)
        var_cal_tab.grid_rowconfigure(1, weight=1)
        var_cal_tab.grid_columnconfigure(0, weight=1)
        AnalysisHelpButton(var_cal_tab, "precios_variedad_calibre").grid(row=0, column=0, sticky="e", pady=(0, 6))
        self.var_cal_table = TableChartView(var_cal_tab, columns=self.TABLE_VAR_CAL_COLUMNS)
        self.var_cal_table.grid(row=1, column=0, sticky="nsew")
        self.tabs.add(var_cal_tab, text="Variedad / calibre")

        desv_tab = ttk.Frame(self.tabs, padding=8)
        desv_tab.grid_rowconfigure(1, weight=1)
        desv_tab.grid_columnconfigure(0, weight=1)
        desv_top = ttk.Frame(desv_tab)
        desv_top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        desv_top.grid_columnconfigure(0, weight=1)
        kpi_frame = ttk.Frame(desv_top)
        kpi_frame.grid(row=0, column=0, sticky="w")
        for i, key in enumerate(self.desv_kpi_vars):
            ttk.Label(kpi_frame, textvariable=self.desv_kpi_vars[key], style="KPI.TLabel").grid(
                row=i // 3,
                column=i % 3,
                sticky="w",
                padx=(0, 18),
                pady=(0, 4),
            )
        sort_frame = ttk.Frame(desv_top)
        sort_frame.grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Label(sort_frame, text="Ordenar por:").grid(row=0, column=0, padx=(0, 4))
        sort_combo = ttk.Combobox(
            sort_frame,
            state="readonly",
            width=20,
            textvariable=self.desv_sort_var,
            values=["prioridad_score", "margen_ajustado_total", "margen_ajustado_eurkg", "margen_total_eur", "margen_eurkg", "cumplimiento_pct", "kg", "reclamado_eurkg", "n_reclamaciones", "dif_precio_eurkg"],
        )
        sort_combo.grid(row=0, column=1)
        sort_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        AnalysisHelpButton(desv_top, "precios_desviacion_cliente").grid(row=0, column=2, sticky="e")
        self.desv_toggle = TableChartToggleFrame(
            desv_tab,
            table_builder=lambda parent: self._SimpleTableView(parent, self.TABLE_DESV_CLIENTE_COLUMNS),
            chart_builder=lambda parent: self._DesvChartView(parent, self._format_desv_tooltip),
            initial_view="chart",
        )
        self.desv_toggle.grid(row=1, column=0, sticky="nsew")
        self.tabs.add(desv_tab, text="Desviación por cliente")

        ttk.Label(self, textvariable=self.status_var, foreground="#b00020").grid(row=2, column=0, sticky="w", pady=(8, 0))

    def refresh(self) -> None:
        filters = self.get_filters()
        filters["desv_sort_by"] = self.desv_sort_var.get()
        data = self.service.get_analisis_precios(filters)
        self.latest_data = data

        kpis = data.get("kpis_precios", {})
        self.kpi_vars["precio_real"].set(f'Precio medio real ponderado: {kpis.get("precio_medio_real", 0):,.3f} EUR/kg')
        self.kpi_vars["precio_ori"].set(f'Precio medio orientativo ponderado: {kpis.get("precio_medio_orientativo", 0):,.3f} EUR/kg')
        self.kpi_vars["dif_media"].set(f'Diferencia media EUR/kg: {kpis.get("diferencia_media_eurkg", 0):,.3f}')
        self.kpi_vars["imp_real"].set(f'Importe real: {kpis.get("importe_real", 0):,.2f} EUR')
        self.kpi_vars["imp_ori"].set(f'Importe orientativo: {kpis.get("importe_orientativo", 0):,.2f} EUR')
        self.kpi_vars["desv_total"].set(f'Desviacion total EUR: {kpis.get("desviacion_total_eur", 0):,.2f}')
        self.kpi_vars["kg_con"].set(f'Kg con precio orientativo: {kpis.get("kg_con_precio_orientativo", 0):,.2f}')
        self.kpi_vars["kg_sin"].set(f'Kg sin precio orientativo: {kpis.get("kg_sin_precio_orientativo", 0):,.2f}')
        total_kg = float(kpis.get("kg_cliente", 0) or 0)
        kg_con = float(kpis.get("kg_con_precio_orientativo", 0) or 0)
        cov = (kg_con / total_kg * 100.0) if total_kg else 0.0
        self.kpi_vars["cov"].set(f'% cobertura precio orientativo: {cov:,.2f}%')

        semana_rows = data.get("evolucion_semanal", [])
        self._draw_weekly_chart(semana_rows)
        self._fill_week_table(semana_rows)
        self._fill_var_cal_table(data.get("precios_por_variedad_calibre", []))
        # Compatibilidad: si viene embebido en el payload principal, lo usamos;
        # si no, caemos al flujo actual.
        desv_payload = data.get("desviacion_clientes")
        if isinstance(desv_payload, dict):
            desv = desv_payload
        else:
            desv = self.service.get_desviacion_clientes(filters)
        self.logger.info(
            "Desviacion por cliente: filas recibidas=%s, vista inicial=%s",
            len(desv.get("rows", [])),
            getattr(self.desv_toggle, "initial_view", "chart"),
        )
        self._fill_desv_cliente_table(desv.get("rows", []))
        self._fill_desv_kpis(desv.get("kpis_forfait", {}))
        self._draw_desv_cliente_chart(desv.get("grafica", []))

        warnings = list(data.get("warnings", [])) + list(desv.get("warnings", []))
        if not desv.get("rows", []):
            warnings.append("Desviación por cliente: sin datos para los filtros actuales.")
        self.status_var.set(" | ".join(sorted(set(warnings))) if warnings else "")

    def _fill_week_table(self, rows: list[dict[str, Any]]) -> None:
        mapped = []
        for row in rows:
            mapped.append({
                "Semana": row.get("grupo", ""), "Kg cliente": f'{row.get("kg_cliente", 0):,.2f}',
                "Precio medio real": f'{row.get("precio_medio_real", 0):,.3f}', "Precio medio orientativo": f'{row.get("precio_medio_orientativo", 0):,.3f}',
                "Diferencia EUR/kg": f'{row.get("diferencia_media_eurkg", 0):,.3f}', "Importe real": f'{row.get("importe_real", 0):,.2f}',
                "Importe orientativo": f'{row.get("importe_orientativo", 0):,.2f}', "Desviacion total EUR": f'{row.get("desviacion_total_eur", 0):,.2f}',
                "Kg total (debug)": f'{row.get("debug_kg_total", 0):,.2f}',
                "Kg con EurosKG válido (debug)": f'{row.get("debug_kg_euroskg_valido", 0):,.2f}',
                "Suma ponderada EurosKG (debug)": f'{row.get("debug_suma_ponderada_euroskg", 0):,.2f}',
                "Precio real calculado (debug)": f'{row.get("debug_precio_real_calculado", 0):,.4f}',
                "Originales": int(row.get("originales", 0)), "Estimados": int(row.get("estimados", 0)), "Sin datos": int(row.get("sin_datos", 0)), "N pedidos": int(row.get("pedidos_count", 0)),
            })
        self.week_table.set_rows(mapped)

    def _fill_var_cal_table(self, rows: list[dict[str, Any]]) -> None:
        mapped = []
        for row in rows:
            mapped.append({
                "VarCoop": row.get("var_coop", ""), "Calibre": row.get("calibre", ""), "Kg cliente": f'{row.get("kg_cliente", 0):,.2f}',
                "Precio medio real": f'{row.get("precio_medio_real", 0):,.3f}', "Precio medio orientativo": f'{row.get("precio_medio_orientativo", 0):,.3f}',
                "Diferencia EUR/kg": f'{row.get("diferencia_media_eurkg", 0):,.3f}', "Desviacion total EUR": f'{row.get("desviacion_total_eur", 0):,.2f}',
                "Kg total (debug)": f'{row.get("debug_kg_total", 0):,.2f}',
                "Kg con EurosKG válido (debug)": f'{row.get("debug_kg_euroskg_valido", 0):,.2f}',
                "Suma ponderada EurosKG (debug)": f'{row.get("debug_suma_ponderada_euroskg", 0):,.2f}',
                "Precio real calculado (debug)": f'{row.get("debug_precio_real_calculado", 0):,.4f}',
                "N pedidos": int(row.get("pedidos_count", 0)),
            })
        self.var_cal_table.set_rows(mapped)

    def _draw_weekly_chart(self, rows: list[dict[str, Any]]) -> None:
        if self.ax is None or self.chart is None:
            return
        self.ax.clear()
        self.real_line = None
        self.orient_line = None
        if not rows:
            self.ax.set_title("Evolucion semanal precio medio (EUR/kg)")
            self.ax.text(0.5, 0.5, "Sin datos para mostrar", ha="center", va="center", transform=self.ax.transAxes)
            self.chart.draw()
            return

        points: list[dict[str, Any]] = []
        for row in rows:
            try:
                semana = int(float(str(row.get("grupo", "")).strip()))
            except ValueError:
                continue
            points.append({"semana": semana, "real": float(row.get("precio_medio_real") or 0), "orient": float(row.get("precio_medio_orientativo") or 0), "dif": float(row.get("diferencia_media_eurkg") or 0), "kg": float(row.get("kg_cliente") or 0), "pedidos": int(row.get("pedidos_count") or 0)})
        if not points:
            self.ax.text(0.5, 0.5, "Sin semanas numericas para mostrar", ha="center", va="center", transform=self.ax.transAxes)
            self.chart.draw()
            return

        points.sort(key=lambda p: (p["semana"] - 35) if p["semana"] >= 36 else (p["semana"] + 17))
        x_vals = list(range(len(points)))
        x_labels = [str(p["semana"]) for p in points]
        self.real_line, = self.ax.plot(x_vals, [p["real"] for p in points], color="#1f77b4", marker="o", linewidth=2, markersize=5, picker=6, label="Real")
        self.orient_line, = self.ax.plot(x_vals, [p["orient"] for p in points], color="#2ca02c", marker="o", linewidth=2, markersize=5, picker=6, label="Orientativo")
        if self.tooltip_controller is not None:
            self.tooltip_controller.set_targets([(self.real_line, "Real", points), (self.orient_line, "Orientativo", points)])

        self.ax.set_title("Evolucion semanal precio medio (EUR/kg)")
        self.ax.set_xlabel("Semana agricola")
        self.ax.set_ylabel("EUR/kg")
        self.ax.set_xticks(x_vals)
        self.ax.set_xticklabels(x_labels, fontsize=8)
        self.ax.grid(alpha=0.25)
        self.ax.legend(loc="upper left", bbox_to_anchor=(0, 1.15), ncol=2, frameon=False)
        self.figure.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.16)
        self.chart.draw()

    def _format_tooltip(self, point: dict[str, Any]) -> str:
        label = point.get("serie", "")
        precio = point["real"] if label == "Real" else point["orient"]
        return f"Semana: {point['semana']}\nSerie: {label}\nPrecio: {precio:.3f} EUR/kg\nDiferencia: {point['dif']:.3f} EUR/kg\nKg: {point['kg']:,.0f}\nPedidos: {point['pedidos']}"

    def _build_report_payload(self) -> dict[str, Any]:
        report = default_report_dict("BOA Comercial - Precios", self.get_filters())
        report["title"] = "RANKING DE CLIENTES"
        report["subtitle"] = "Análisis comercial y rentabilidad"
        report["report_variant"] = "desviacion_cliente_executive"
        report["kpis"] = [
            ("Kg analizados", self._kpi_value("kg_analizados", prefix="Kg analizados: ")),
            ("Margen total €", self._kpi_value("margen_total", prefix="Margen total €: ")),
            ("Margen ajustado total €", self._kpi_value("kg_con_forfait", prefix="Margen ajustado total €: ")),
            ("Margen medio €/kg", self._kpi_value("margen_medio", prefix="Margen medio €/kg: ")),
            ("Cobertura forfait %", self._kpi_value("cov_forfait", prefix="Cobertura forfait %: ")),
            ("N reclamaciones", self._kpi_value("precio_real", prefix="N reclamaciones: ")),
            ("Importe reclamado total €", self._kpi_value("precio_ori", prefix="Importe reclamado total €: ")),
            ("Reclamado €/kg medio", self._kpi_value("coste_forfait", prefix="Reclamado €/kg medio: ")),
        ]
        executive_rows: list[dict[str, Any]] = []
        for row in self.desv_toggle.rows:
            executive_rows.append(
                {
                    "Ranking": row.get("Ranking", ""),
                    "Cliente": row.get("Cliente", row.get("cliente", "")),
                    "Pais": row.get("Pais", row.get("pais", "")),
                    "Prioridad": row.get("Prioridad", row.get("prioridad", "")),
                    "Estado": row.get("Estado", row.get("estado", "")),
                    "Margen total €": row.get("Margen total €", row.get("margen_total_eur", "")),
                    "Margen ajustado total €": row.get(
                        "Margen ajustado total €",
                        row.get("margen_ajustado_total_eur", ""),
                    ),
                }
            )
        report["tables"] = [
            {
                "title": "Ranking comercial",
                "columns": [
                    "Ranking",
                    "Cliente",
                    "Pais",
                    "Prioridad",
                    "Estado",
                    "Margen total €",
                    "Margen ajustado total €",
                ],
                "rows": executive_rows,
            },
        ]
        return report

    def _kpi_value(self, key: str, prefix: str = "") -> str:
        var = self.desv_kpi_vars.get(key) or self.kpi_vars.get(key)
        if not var:
            return ""
        value = var.get()
        if prefix and isinstance(value, str):
            return value.replace(prefix, "")
        return value

    def _fill_desv_cliente_table(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            self.logger.info("Desviacion por cliente: sin datos para tabla")
        mapped: list[dict[str, Any]] = []
        for r in rows:
            mapped.append(
                {
                    "Ranking": int(r.get("ranking_posicion", 0) or 0),
                    "Cliente": r.get("cliente", ""),
                    "Pais": r.get("pais", ""),
                    "Kg": f'{float(r.get("kg_cliente", 0) or 0):,.2f}',
                    "Precio real €/kg": f'{float(r.get("precio_medio_real", 0) or 0):,.4f}',
                    "Precio orientativo €/kg": f'{float(r.get("precio_referencia_ajustado", 0) or 0):,.4f}',
                    "Dif. precio €/kg": f'{float(r.get("dif_precio_eurkg", 0) or 0):,.4f}',
                    "Coste forfait €/kg": self._fmt_optional(r.get("coste_forfait_eurkg"), 4),
                    "Margen €/kg": self._fmt_optional(r.get("margen_eurkg"), 4),
                    "Margen total €": f'{float(r.get("margen_total_eur", 0) or 0):,.2f}',
                    "N reclam.": int(r.get("n_reclamaciones", 0) or 0),
                    "Reclam. €/kg": f'{float(r.get("reclamado_eurkg", 0) or 0):,.4f}',
                    "% reclamado": f'{float(r.get("pct_reclamado_ventas", 0) or 0):,.2f}%',
                    "Margen ajustado €/kg": f'{float(r.get("margen_ajustado_eurkg", 0) or 0):,.4f}',
                    "Margen ajustado total €": f'{float(r.get("margen_ajustado_total_eur", 0) or 0):,.2f}',
                    "Cumplimiento %": f'{float(r.get("cumplimiento_pct", 0) or 0):,.2f}%',
                    "Cobertura forfait %": f'{float(r.get("cobertura_forfait_pct", 0) or 0):,.2f}%',
                    "Estado cobertura": r.get("estado_cobertura", "COMPLETA"),
                    "Pts rentabilidad": f'{float(r.get("pts_rentabilidad", 0) or 0):,.2f}',
                    "Pts precio": f'{float(r.get("pts_precio", 0) or 0):,.2f}',
                    "Pts volumen": f'{float(r.get("pts_volumen", 0) or 0):,.2f}',
                    "Penalización reclam.": f'{float(r.get("penalizacion_reclam", 0) or 0):,.2f}',
                    "Prioridad": r.get("prioridad", "MEDIA"),
                    "Estado": r.get("estado", "REVISAR"),
                    "PrioridadScore": f'{float(r.get("score_prioridad", 0) or 0):,.2f}',
                    "cliente": r.get("cliente", ""),
                    "impacto_eur": float(r.get("impacto_eur", 0) or 0),
                    "desviacion_eurkg": float(r.get("desviacion_eurkg", 0) or 0),
                    "kg_cliente": float(r.get("kg_cliente", 0) or 0),
                    "pedidos_count": int(r.get("pedidos_count", 0) or 0),
                    "__tags__": self._estado_tag(str(r.get("estado", "REVISAR"))),
                }
            )
        self.desv_toggle.set_data(mapped)
        self.logger.info("Desviacion por cliente: tabla actualizada (%s filas)", len(mapped))

    def _fill_desv_kpis(self, kpis: dict[str, Any]) -> None:
        self.desv_kpi_vars["kg_analizados"].set(
            f'Kg analizados: {float(kpis.get("kg_analizados", 0) or 0):,.2f}'
        )
        self.desv_kpi_vars["kg_con_forfait"].set(
            f'Margen ajustado total €: {float(kpis.get("margen_ajustado_total_eur", 0) or 0):,.2f}'
        )
        self.desv_kpi_vars["kg_sin_forfait"].set(
            f'Kg sin forfait: {float(kpis.get("kg_sin_forfait", 0) or 0):,.2f}'
        )
        self.desv_kpi_vars["cov_forfait"].set(
            f'Cobertura forfait %: {float(kpis.get("cobertura_forfait_pct", 0) or 0):,.2f}%'
        )
        self.desv_kpi_vars["margen_total"].set(
            f'Margen total €: {float(kpis.get("margen_total_eur", 0) or 0):,.2f}'
        )
        self.desv_kpi_vars["margen_medio"].set(f'Margen medio €/kg: {float(kpis.get("margen_medio_eurkg", 0) or 0):,.4f}')
        self.desv_kpi_vars["precio_real"].set(f'N reclamaciones: {int(kpis.get("n_reclamaciones", 0) or 0)}')
        self.desv_kpi_vars["precio_ori"].set(f'Importe reclamado total €: {float(kpis.get("importe_reclamado_total_eur", 0) or 0):,.2f}')
        self.desv_kpi_vars["dif_media"].set(f'Reclamaciones / 100.000 kg: {float(kpis.get("reclamaciones_por_100k_kg", 0) or 0):,.2f}')
        self.desv_kpi_vars["coste_forfait"].set(f'Reclamado €/kg medio: {float(kpis.get("reclamado_medio_eurkg", 0) or 0):,.4f}')

    @staticmethod
    def _fmt_optional(value: Any, decimals: int) -> str:
        if value is None or value == "":
            return ""
        try:
            return f"{float(value):,.{decimals}f}"
        except (TypeError, ValueError):
            return ""

    def _draw_desv_cliente_chart(self, rows: list[dict[str, Any]]) -> None:
        # Chart is rendered from the same mapped rows through the toggle frame.
        return

    @staticmethod
    def _estado_tag(estado: str) -> str:
        if estado == "BUENO":
            return "tag_green"
        if estado == "ACEPTABLE":
            return "tag_green_soft"
        if estado in {"REVISAR", "COBERTURA PARCIAL"}:
            return "tag_yellow"
        if estado in {"MALO", "SIN_FORFAIT", "SIN_DATOS"}:
            return "tag_red"
        return "tag_yellow"

    @staticmethod
    def _format_desv_tooltip(payload: dict[str, Any]) -> str:
        return (
            f"Cliente: {payload.get('cliente', '')}\n"
            f"Impacto €: {float(payload.get('impacto', 0) or 0):,.2f}\n"
            f"Desviación €/kg: {float(payload.get('desviacion', 0) or 0):,.4f}\n"
            f"Kg cliente: {float(payload.get('kg', 0) or 0):,.2f}\n"
            f"N pedidos: {int(payload.get('pedidos', 0) or 0)}"
        )
