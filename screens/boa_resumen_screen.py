import tkinter as tk
from tkinter import ttk
from typing import Any

from reports.report_data_builder import default_report_dict
from services.comercial_service import ComercialService
from widgets.analysis_help_button import AnalysisHelpButton
from widgets.report_button import ReportButton
from widgets.table_chart_view import TableChartView


class BOAResumenScreen(ttk.Frame):
    TABLE_COLUMNS = [
        "Agrupacion",
        "Kg cliente",
        "Kg cooperativa",
        "Merma kg",
        "% merma",
        "Cajas",
        "Precio medio real",
        "Precio medio orientativo",
        "Desviacion EUR/kg",
        "Importe real",
        "Importe orientativo",
        "Desviacion total EUR",
        "Kg total (debug)",
        "Kg con EurosKG válido (debug)",
        "Suma ponderada EurosKG (debug)",
        "Precio real calculado (debug)",
        "N pedidos",
        "Originales",
        "Estimados",
        "Sin datos",
    ]

    GROUP_TABS = [
        ("Ventas por cliente", "clientes"),
        ("Ventas por variedad coop", "variedad_coop"),
        ("Ventas por pais", "pais"),
        ("Ventas por semana", "semana"),
        ("Ventas por empresa", "empresa"),
    ]

    def __init__(self, master: tk.Misc, service: ComercialService, get_filters) -> None:
        super().__init__(master)
        self.service = service
        self.get_filters = get_filters

        self.status_var = tk.StringVar(value="")
        self.kpi_vars = {
            "kg_cliente": tk.StringVar(value="Kg cliente: 0"),
            "kg_coop": tk.StringVar(value="Kg cooperativa: 0"),
            "merma": tk.StringVar(value="Merma kg: 0"),
            "pct_merma": tk.StringVar(value="% merma: 0.00%"),
            "cajas": tk.StringVar(value="Cajas: 0"),
            "precio_real": tk.StringVar(value="Precio medio real: 0.000 EUR/kg"),
            "precio_ori": tk.StringVar(value="Precio medio orientativo: 0.000 EUR/kg"),
            "dif_media": tk.StringVar(value="Diferencia media EUR/kg: 0.000"),
            "imp_real": tk.StringVar(value="Importe real estimado: 0.00 EUR"),
            "imp_ori": tk.StringVar(value="Importe orientativo: 0.00 EUR"),
            "desv_total": tk.StringVar(value="Desviacion total EUR: 0.00"),
            "pedidos": tk.StringVar(value="N pedidos: 0"),
            "pedidos_reclamados": tk.StringVar(value="Pedidos reclamados: 0"),
            "importe_reclamado": tk.StringVar(value="Importe reclamado: 0.00 EUR"),
            "ori_count": tk.StringVar(value="Orientativo original: 0"),
            "est_count": tk.StringVar(value="Orientativo estimado: 0"),
            "sin_count": tk.StringVar(value="Orientativo sin datos: 0"),
            "cov": tk.StringVar(value="Cobertura precio orientativo: 0.00%"),
        }
        self.tables: dict[str, TableChartView] = {}
        self.latest_data: dict[str, Any] = {}

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Resumen comercial", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        AnalysisHelpButton(header, "resumen_comercial").grid(row=0, column=1, sticky="e", padx=(0, 8))
        ReportButton(header, title_provider=lambda: "Informe BOA Resumen", data_provider=self._build_report_payload).grid(
            row=0, column=2, sticky="e"
        )

        kpi_frame = ttk.Frame(self)
        kpi_frame.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        for i, key in enumerate(self.kpi_vars):
            ttk.Label(kpi_frame, textvariable=self.kpi_vars[key], style="KPI.TLabel").grid(
                row=i // 3,
                column=i % 3,
                sticky="w",
                padx=(0, 24),
                pady=(0, 6),
            )

        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        notebook = ttk.Notebook(body)
        notebook.grid(row=0, column=0, sticky="nsew")

        for title, key in self.GROUP_TABS:
            tab = ttk.Frame(notebook, padding=6)
            tab.grid_rowconfigure(1, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            AnalysisHelpButton(tab, "resumen_comercial").grid(row=0, column=0, sticky="e", pady=(0, 6))
            table = TableChartView(tab, columns=self.TABLE_COLUMNS)
            table.grid(row=1, column=0, sticky="nsew")
            notebook.add(tab, text=title)
            self.tables[key] = table

        ttk.Label(self, textvariable=self.status_var, foreground="#b00020").grid(row=3, column=0, sticky="w", pady=(8, 0))

    def refresh(self) -> None:
        filters = self.get_filters()
        data = self.service.get_resumen_comercial(filters)
        self.latest_data = data

        kpis = data.get("kpis", {})
        self.kpi_vars["kg_cliente"].set(f'Kg cliente: {kpis.get("kg_cliente", 0):,.2f}')
        self.kpi_vars["kg_coop"].set(f'Kg cooperativa: {kpis.get("kg_cooperativa", 0):,.2f}')
        self.kpi_vars["merma"].set(f'Merma kg: {kpis.get("merma_kg", 0):,.2f}')
        self.kpi_vars["pct_merma"].set(f'% merma: {kpis.get("pct_merma", 0) * 100:,.2f}%')
        self.kpi_vars["cajas"].set(f'Cajas: {kpis.get("cajas", 0):,.2f}')
        self.kpi_vars["precio_real"].set(f'Precio medio real: {kpis.get("precio_medio_real", 0):,.3f} EUR/kg')
        self.kpi_vars["precio_ori"].set(f'Precio medio orientativo: {kpis.get("precio_medio_orientativo", 0):,.3f} EUR/kg')
        self.kpi_vars["dif_media"].set(f'Diferencia media EUR/kg: {kpis.get("diferencia_media_eurkg", 0):,.3f}')
        self.kpi_vars["imp_real"].set(f'Importe real estimado: {kpis.get("importe_real", 0):,.2f} EUR')
        self.kpi_vars["imp_ori"].set(f'Importe orientativo: {kpis.get("importe_orientativo", 0):,.2f} EUR')
        self.kpi_vars["desv_total"].set(f'Desviacion total EUR: {kpis.get("desviacion_total_eur", 0):,.2f}')
        self.kpi_vars["pedidos"].set(f'N pedidos: {kpis.get("pedidos_count", 0):,}')
        self.kpi_vars["pedidos_reclamados"].set(f'Pedidos reclamados: {kpis.get("pedidos_reclamados", 0):,}')
        self.kpi_vars["importe_reclamado"].set(f'Importe reclamado: {kpis.get("importe_reclamado", 0):,.2f} EUR')
        self.kpi_vars["ori_count"].set(f'Orientativo original: {kpis.get("pedidos_orientativo_original", 0):,}')
        self.kpi_vars["est_count"].set(f'Orientativo estimado: {kpis.get("pedidos_orientativo_estimado", 0):,}')
        self.kpi_vars["sin_count"].set(f'Orientativo sin datos: {kpis.get("pedidos_orientativo_sin_datos", 0):,}')
        self.kpi_vars["cov"].set(f'Cobertura precio orientativo: {kpis.get("pct_cobertura_orientativo", 0):,.2f}%')

        grouped_data = data.get("grouped", {})
        for _, key in self.GROUP_TABS:
            self._fill_group_table(key, grouped_data.get(key, []))

        warnings = data.get("warnings", [])
        self.status_var.set(" | ".join(sorted(set(warnings))) if warnings else "")

    def _fill_group_table(self, key: str, rows: list[dict[str, Any]]) -> None:
        mapped: list[dict[str, Any]] = []
        for row in rows:
            mapped.append(
                {
                    "Agrupacion": row.get("grupo", ""),
                    "Kg cliente": f'{row.get("kg_cliente", 0):,.2f}',
                    "Kg cooperativa": f'{row.get("kg_cooperativa", 0):,.2f}',
                    "Merma kg": f'{row.get("merma_kg", 0):,.2f}',
                    "% merma": f'{row.get("pct_merma", 0) * 100:,.2f}%',
                    "Cajas": f'{row.get("cajas", 0):,.2f}',
                    "Precio medio real": f'{row.get("precio_medio_real", 0):,.3f}',
                    "Precio medio orientativo": f'{row.get("precio_medio_orientativo", 0):,.3f}',
                    "Desviacion EUR/kg": f'{row.get("diferencia_media_eurkg", 0):,.3f}',
                    "Importe real": f'{row.get("importe_real", 0):,.2f}',
                    "Importe orientativo": f'{row.get("importe_orientativo", 0):,.2f}',
                    "Desviacion total EUR": f'{row.get("desviacion_total_eur", 0):,.2f}',
                    "Kg total (debug)": f'{row.get("debug_kg_total", 0):,.2f}',
                    "Kg con EurosKG válido (debug)": f'{row.get("debug_kg_euroskg_valido", 0):,.2f}',
                    "Suma ponderada EurosKG (debug)": f'{row.get("debug_suma_ponderada_euroskg", 0):,.2f}',
                    "Precio real calculado (debug)": f'{row.get("debug_precio_real_calculado", 0):,.4f}',
                    "N pedidos": int(row.get("pedidos_count", 0)),
                    "Originales": int(row.get("originales", 0)),
                    "Estimados": int(row.get("estimados", 0)),
                    "Sin datos": int(row.get("sin_datos", 0)),
                }
            )
        self.tables[key].set_rows(mapped)

    def _build_report_payload(self) -> dict[str, Any]:
        report = default_report_dict("BOA Comercial - Resumen", self.get_filters())
        kpis = self.latest_data.get("kpis", {})
        report["kpis"] = [(k, str(v)) for k, v in kpis.items()]
        report["tables"] = []
        for title, key in self.GROUP_TABS:
            table = self.tables.get(key)
            if table is None:
                continue
            report["tables"].append({"title": title, "columns": self.TABLE_COLUMNS, "rows": table.rows})
        return report
