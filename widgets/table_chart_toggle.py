from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TableChartToggleFrame(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        table_builder: Callable[[ttk.Frame], Any],
        chart_builder: Callable[[ttk.Frame], Any],
        initial_view: str = "chart",
    ) -> None:
        super().__init__(parent)
        self.table_builder = table_builder
        self.chart_builder = chart_builder
        self.initial_view = initial_view if initial_view in {"chart", "table"} else "chart"
        self._current_view = ""
        self._toggle_text = tk.StringVar(value="")
        self._empty_label: ttk.Label | None = None
        self.rows_cache: list[dict[str, Any]] = []

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self.content_frame = ttk.Frame(self)
        self.content_frame.grid(row=0, column=0, sticky="nsew")
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, weight=1)

        self.table_frame = ttk.Frame(self.content_frame)
        self.table_frame.grid_rowconfigure(0, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)

        self.chart_frame = ttk.Frame(self.content_frame)
        self.chart_frame.grid_rowconfigure(0, weight=1)
        self.chart_frame.grid_columnconfigure(0, weight=1)

        self.table_view = self.table_builder(self.table_frame)
        self.chart_view = self.chart_builder(self.chart_frame)

        if hasattr(self.table_view, "grid"):
            self.table_view.grid(row=0, column=0, sticky="nsew")
        if hasattr(self.chart_view, "grid"):
            self.chart_view.grid(row=0, column=0, sticky="nsew")

        self.toggle_button = ttk.Button(self, textvariable=self._toggle_text, command=self.toggle)
        self.toggle_button.grid(row=1, column=0, sticky="w", padx=(8, 0), pady=(6, 0))

        logger.info("TableChartToggleFrame inicializado. Vista inicial=%s", self.initial_view)
        if self.initial_view == "table":
            self.show_table()
        else:
            self.show_chart()

    def show(self, view: str) -> None:
        if view == "table":
            self.show_table()
        else:
            self.show_chart()

    def _clear_content(self) -> None:
        if self._empty_label is not None:
            self._empty_label.destroy()
            self._empty_label = None
        self.table_frame.grid_remove()
        self.chart_frame.grid_remove()

    def _show_message(self, message: str) -> None:
        self._empty_label = ttk.Label(self.content_frame, text=message, foreground="#666666")
        self._empty_label.grid(row=0, column=0, sticky="w")

    def _has_significant_chart_data(self) -> bool:
        if not self.rows_cache:
            return False
        for row in self.rows_cache:
            for key in ("impacto_eur", "kg_cliente", "desviacion_eurkg"):
                try:
                    if abs(float(row.get(key, 0) or 0)) > 1e-12:
                        return True
                except (TypeError, ValueError):
                    continue
        return False

    def show_chart(self) -> None:
        self._clear_content()
        self.chart_frame.grid(row=0, column=0, sticky="nsew")
        if not self.rows_cache:
            self._show_message("Sin datos para graficar con los filtros actuales")
            logger.info("TableChartToggleFrame: grafica sin datos")
        elif not self._has_significant_chart_data():
            self._show_message("No hay desviación significativa para graficar")
            logger.info("TableChartToggleFrame: grafica sin desviacion significativa")
        else:
            logger.info("TableChartToggleFrame: grafica pintada (%s filas)", len(self.rows_cache))
        self._toggle_text.set("📋 Ver tabla")
        self._current_view = "chart"

    def show_table(self) -> None:
        self._clear_content()
        self.table_frame.grid(row=0, column=0, sticky="nsew")
        if not self.rows:
            self._show_message("Sin datos para mostrar con los filtros actuales")
            logger.info("TableChartToggleFrame: tabla sin datos")
        else:
            logger.info("TableChartToggleFrame: tabla pintada (%s filas)", len(self.rows))
        self._toggle_text.set("📊 Ver gráfica")
        self._current_view = "table"

    def toggle(self) -> None:
        if self._current_view == "chart":
            self.show_table()
        else:
            self.show_chart()

    def set_data(self, data: list[dict[str, Any]]) -> None:
        self.rows_cache = list(data)
        for target in (self.table_view, self.chart_view):
            if hasattr(target, "set_data"):
                target.set_data(data)
            elif hasattr(target, "set_rows"):
                target.set_rows(data)

        if self._current_view == "table":
            self.show_table()
        else:
            self.show_chart()

    @property
    def rows(self) -> list[dict[str, Any]]:
        if hasattr(self.table_view, "rows"):
            return list(self.table_view.rows)
        return list(self.rows_cache)
