import re
import tkinter as tk
from tkinter import ttk
from typing import Any

from widgets.chart_tooltips import ChartTooltipController
from widgets.data_table import DataTable

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
except Exception:
    FigureCanvasTkAgg = None
    Figure = None


class TableChartView(ttk.Frame):
    def __init__(self, master: tk.Misc, columns: list[str]) -> None:
        super().__init__(master)
        self.columns = columns
        self.rows: list[dict[str, Any]] = []
        self.chart_visible = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.table_container = ttk.Frame(self)
        self.table_container.grid(row=0, column=0, sticky="nsew")
        self.table_container.grid_rowconfigure(0, weight=1)
        self.table_container.grid_columnconfigure(0, weight=1)

        self.table = DataTable(self.table_container, columns=columns)
        self.table.grid(row=0, column=0, sticky="nsew")

        self.chart_container = ttk.Frame(self)
        self.chart_container.grid(row=0, column=0, sticky="nsew")
        self.chart_container.grid_rowconfigure(0, weight=1)
        self.chart_container.grid_columnconfigure(0, weight=1)

        self.chart_msg = ttk.Label(self.chart_container, text="")
        self.figure = None
        self.ax = None
        self.chart = None
        self.tooltip_controller = None

        if Figure is None or FigureCanvasTkAgg is None:
            self.chart_msg.configure(text="Matplotlib no disponible. Instalar con: c:/python313/python.exe -m pip install matplotlib")
            self.chart_msg.grid(row=0, column=0, sticky="w")
        else:
            self.figure = Figure(figsize=(8, 4), dpi=100)
            self.ax = self.figure.add_subplot(111)
            self.chart = FigureCanvasTkAgg(self.figure, master=self.chart_container)
            self.chart.get_tk_widget().grid(row=0, column=0, sticky="nsew")
            self.tooltip_controller = ChartTooltipController(self.ax, self.chart, self._format_tooltip)

        self.chart_container.grid_remove()

        self.toggle_btn_text = tk.StringVar(value="📊 Ver gráfica")
        self.toggle_btn = ttk.Button(self, textvariable=self.toggle_btn_text, command=self._toggle)
        self.toggle_btn.place(relx=0.0, rely=1.0, x=8, y=-8, anchor="sw")

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self.rows = list(rows)
        self.table.set_rows(self.rows)
        if self.chart_visible:
            self._render_chart()

    def _toggle(self) -> None:
        self.chart_visible = not self.chart_visible
        if self.chart_visible:
            self.table_container.grid_remove()
            self.chart_container.grid()
            self.toggle_btn_text.set("📋 Ver tabla")
            self._render_chart()
        else:
            self.chart_container.grid_remove()
            self.table_container.grid()
            self.toggle_btn_text.set("📊 Ver gráfica")

    def _render_chart(self) -> None:
        if self.ax is None or self.chart is None:
            return
        self.ax.clear()
        if self.tooltip_controller is not None:
            self.tooltip_controller.set_targets([])

        if not self.rows:
            self.ax.text(0.5, 0.5, "Sin datos para graficar", ha="center", va="center", transform=self.ax.transAxes)
            self.chart.draw()
            return

        cat_col = self._detect_category_column()
        metric_col = self._detect_metric_column()
        has_week = cat_col.lower().startswith("semana")

        if has_week and "Precio medio real" in self.columns and "Precio medio orientativo" in self.columns:
            data = []
            for row in self.rows:
                week = self._to_float(row.get(cat_col))
                if week is None:
                    continue
                real = self._to_float(row.get("Precio medio real")) or 0.0
                orient = self._to_float(row.get("Precio medio orientativo")) or 0.0
                data.append((int(week), real, orient, dict(row)))
            data.sort(key=lambda t: (t[0] - 35) if t[0] >= 36 else (t[0] + 17))
            if not data:
                self.ax.text(0.5, 0.5, "Sin datos para graficar", ha="center", va="center", transform=self.ax.transAxes)
                self.chart.draw()
                return
            xs = list(range(len(data)))
            labels = [str(d[0]) for d in data]
            l1, = self.ax.plot(xs, [d[1] for d in data], marker="o", color="#1f77b4", label="Precio medio real")
            l2, = self.ax.plot(xs, [d[2] for d in data], marker="o", color="#2ca02c", label="Precio medio orientativo")
            self.ax.set_xticks(xs)
            self.ax.set_xticklabels(labels, fontsize=8)
            self.ax.set_xlabel(cat_col)
            self.ax.grid(alpha=0.25)
            self.ax.legend(loc="upper left", bbox_to_anchor=(0, 1.12), ncol=2, frameon=False)
            self.figure.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.18)
            if self.tooltip_controller is not None:
                p1 = [{"serie": "Precio medio real", "x_label": str(d[0]), "y_value": d[1], **d[3]} for d in data]
                p2 = [{"serie": "Precio medio orientativo", "x_label": str(d[0]), "y_value": d[2], **d[3]} for d in data]
                self.tooltip_controller.set_targets([(l1, "Precio medio real", p1), (l2, "Precio medio orientativo", p2)])
            self.chart.draw()
            return

        pairs = []
        for row in self.rows:
            label = str(row.get(cat_col, "")).strip()
            val = self._to_float(row.get(metric_col))
            if label and val is not None:
                pairs.append((label, float(val), dict(row)))
        pairs.sort(key=lambda t: t[1], reverse=True)
        pairs = pairs[:15]
        if not pairs:
            self.ax.text(0.5, 0.5, "Sin datos para graficar", ha="center", va="center", transform=self.ax.transAxes)
            self.chart.draw()
            return
        pairs = list(reversed(pairs))
        labels = [p[0] for p in pairs]
        vals = [p[1] for p in pairs]
        bars = self.ax.barh(labels, vals, color="#2e7d32")
        self.ax.set_xlabel(metric_col)
        self.ax.grid(axis="x", alpha=0.25)
        self.figure.tight_layout()
        if self.tooltip_controller is not None:
            targets = []
            for patch, (_lab, val, row) in zip(bars.patches, pairs):
                payload = {"serie": metric_col, "x_label": _lab, "y_value": val, **row}
                targets.append((patch, metric_col, [payload]))
            self.tooltip_controller.set_targets(targets)
        self.chart.draw()

    def _detect_category_column(self) -> str:
        for c in self.columns:
            if c in {"Semana", "Cliente", "VarCoop", "Pais", "Empresa", "Causa", "Agrupación", "Agrupacion", "Variedad"}:
                return c
        return self.columns[0]

    def _detect_metric_column(self) -> str:
        priority = [
            "Importe reclamado",
            "Importe real",
            "Importe orientativo",
            "Kg cliente",
            "Neto reclamado",
            "Cajas",
        ]
        for p in priority:
            if p in self.columns:
                return p
        return self.columns[1] if len(self.columns) > 1 else self.columns[0]

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("EUR", "").replace("€", "").replace("%", "").replace(" ", "")
        text = text.replace(".", "").replace(",", ".") if text.count(",") == 1 and text.count(".") > 1 else text.replace(",", "")
        text = re.sub(r"[^0-9\.-]", "", text)
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _format_tooltip(payload: dict[str, Any]) -> str:
        lines = []
        if payload.get("serie"):
            lines.append(f"Serie: {payload.get('serie')}")
        if payload.get("x_label"):
            lines.append(f"Eje X: {payload.get('x_label')}")
        if payload.get("y_value") is not None:
            try:
                lines.append(f"Valor: {float(payload.get('y_value')):,.3f}")
            except Exception:
                lines.append(f"Valor: {payload.get('y_value')}")
        for key in ["Semana", "Cliente", "VarCoop", "Pais", "Causa", "Kg cliente", "N pedidos", "Importe reclamado", "Diferencia EUR/kg"]:
            if key in payload and payload[key] not in (None, ""):
                lines.append(f"{key}: {payload[key]}")
        return "\n".join(lines[:8])
