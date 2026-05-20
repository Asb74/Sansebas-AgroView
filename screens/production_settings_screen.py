from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from services.production_settings_service import ProductionSettingsService
from widgets.screen_header import ScreenHeader


class ProductionSettingsScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=10)
        self.on_back = on_back
        self.service = ProductionSettingsService()

        self._general_vars: dict[str, tk.Variable] = {}
        self._build_ui()
        self._load_general_settings()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ScreenHeader(
            self,
            title="Configuración productiva",
            subtitle="Definición operativa diaria del almacén",
            on_back=self.on_back,
        ).grid(row=0, column=0, sticky="ew")

        notebook = ttk.Notebook(self)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        general_tab = ttk.Frame(notebook, padding=12)
        notebook.add(general_tab, text="General del día")
        for title in ("Personal", "Confecciones", "Máquinas / líneas", "Rendimientos", "Penalizaciones", "Reglas / semáforo"):
            placeholder = ttk.Frame(notebook, padding=12)
            ttk.Label(placeholder, text="Pestaña preparada para una próxima integración.").pack(anchor="w")
            notebook.add(placeholder, text=title)

        self._build_general_tab(general_tab)

    def _build_general_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)

        panel = ttk.LabelFrame(parent, text="Parámetros operativos diarios", padding=12)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_columnconfigure(1, weight=1)

        def add_entry(row: int, key: str, label: str, default: str = "") -> None:
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            var = tk.StringVar(value=default)
            entry = ttk.Entry(panel, textvariable=var)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            self._general_vars[key] = var

        def add_combo(row: int, key: str, label: str, values: list[str]) -> None:
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            var = tk.StringVar(value=values[0])
            combo = ttk.Combobox(panel, textvariable=var, values=values, state="readonly")
            combo.grid(row=row, column=1, sticky="ew", pady=4)
            self._general_vars[key] = var

        def add_check(row: int, key: str, label: str, default: int = 0) -> None:
            var = tk.IntVar(value=default)
            ttk.Checkbutton(panel, text=label, variable=var).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
            self._general_vars[key] = var

        add_entry(0, "horas_turno", "Horas por turno", "8")
        add_entry(1, "numero_turnos", "Número de turnos", "1")
        add_entry(2, "horas_descanso", "Horas de descanso", "0.5")
        add_combo(3, "tipo_campana", "Tipo de campaña", ["Baja actividad", "Normal", "Alta", "Pico campaña"])
        add_combo(4, "tipo_volcado", "Tipo de volcado", ["Compacta", "Tolva", "Invierno", "Manual"])
        add_entry(5, "saturacion_maxima_pct", "Saturación máxima %", "90")

        add_check(6, "permitir_horas_extra", "Permitir horas extra", 1)
        add_check(7, "permitir_segundo_turno", "Permitir segundo turno", 0)
        add_check(8, "priorizar_pedidos_reales", "Priorizar pedidos reales", 1)
        add_check(9, "permitir_adelantar_produccion", "Permitir adelantar producción", 1)
        add_check(10, "agrupar_pedidos_compatibles", "Agrupar pedidos compatibles", 1)
        add_check(11, "minimizar_cambios_formato", "Minimizar cambios de formato", 1)

        add_entry(12, "kg_objetivo_dia", "Kg objetivo día", "0")
        add_entry(13, "palets_objetivo_dia", "Palets objetivo día", "0")
        add_entry(14, "pedidos_maximos_recomendados", "Pedidos máximos recomendados", "0")

        calc = ttk.LabelFrame(parent, text="Campos calculados", padding=12)
        calc.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        calc.grid_columnconfigure(1, weight=1)

        self._general_vars["horas_brutas_dia"] = tk.StringVar()
        self._general_vars["horas_utiles_dia"] = tk.StringVar()
        self._general_vars["saturacion_util_objetivo"] = tk.StringVar()

        self._add_readonly(calc, 0, "Horas brutas día", self._general_vars["horas_brutas_dia"])
        self._add_readonly(calc, 1, "Horas útiles día", self._general_vars["horas_utiles_dia"])
        self._add_readonly(calc, 2, "Saturación útil objetivo", self._general_vars["saturacion_util_objetivo"])

        btns = ttk.Frame(parent)
        btns.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(btns, text="Guardar configuración", command=self._save_general_settings).pack(side="left", padx=4)
        ttk.Button(btns, text="Restaurar valores por defecto", command=self._reset_defaults).pack(side="left", padx=4)
        ttk.Button(btns, text="Volver", command=self.on_back).pack(side="right", padx=4)

        for key in ("horas_turno", "numero_turnos", "horas_descanso", "saturacion_maxima_pct"):
            self._general_vars[key].trace_add("write", lambda *_: self._recalculate())

    def _add_readonly(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=variable, state="readonly").grid(row=row, column=1, sticky="ew", pady=4)

    def _load_general_settings(self) -> None:
        data = self.service.get_general_settings()
        for key, var in self._general_vars.items():
            if key in data:
                if isinstance(var, tk.IntVar):
                    var.set(int(data[key]))
                else:
                    var.set(str(data[key]))
        self._recalculate()

    def _parse_float(self, key: str, label: str) -> float:
        raw = str(self._general_vars[key].get()).strip().replace(",", ".")
        if raw == "":
            raise ValueError(f"{label}: valor obligatorio")
        return float(raw)

    def _parse_int(self, key: str, label: str) -> int:
        raw = str(self._general_vars[key].get()).strip()
        if raw == "":
            raise ValueError(f"{label}: valor obligatorio")
        return int(raw)

    def _collect_payload(self) -> dict:
        horas_turno = self._parse_float("horas_turno", "Horas por turno")
        numero_turnos = self._parse_int("numero_turnos", "Número de turnos")
        horas_descanso = self._parse_float("horas_descanso", "Horas de descanso")
        saturacion = self._parse_float("saturacion_maxima_pct", "Saturación máxima %")

        if horas_turno < 0 or numero_turnos < 0 or horas_descanso < 0:
            raise ValueError("Horas por turno, número de turnos y horas de descanso deben ser >= 0")
        if saturacion < 0 or saturacion > 100:
            raise ValueError("Saturación máxima % debe estar entre 0 y 100")

        return {
            "horas_turno": horas_turno,
            "numero_turnos": numero_turnos,
            "horas_descanso": horas_descanso,
            "tipo_campana": self._general_vars["tipo_campana"].get(),
            "tipo_volcado": self._general_vars["tipo_volcado"].get(),
            "saturacion_maxima_pct": saturacion,
            "permitir_horas_extra": int(self._general_vars["permitir_horas_extra"].get()),
            "permitir_segundo_turno": int(self._general_vars["permitir_segundo_turno"].get()),
            "priorizar_pedidos_reales": int(self._general_vars["priorizar_pedidos_reales"].get()),
            "permitir_adelantar_produccion": int(self._general_vars["permitir_adelantar_produccion"].get()),
            "agrupar_pedidos_compatibles": int(self._general_vars["agrupar_pedidos_compatibles"].get()),
            "minimizar_cambios_formato": int(self._general_vars["minimizar_cambios_formato"].get()),
            "kg_objetivo_dia": self._parse_float("kg_objetivo_dia", "Kg objetivo día"),
            "palets_objetivo_dia": self._parse_float("palets_objetivo_dia", "Palets objetivo día"),
            "pedidos_maximos_recomendados": self._parse_int("pedidos_maximos_recomendados", "Pedidos máximos recomendados"),
        }

    def _recalculate(self) -> None:
        try:
            horas_brutas = self._parse_float("horas_turno", "Horas por turno") * self._parse_int("numero_turnos", "Número de turnos")
            horas_utiles = horas_brutas - self._parse_float("horas_descanso", "Horas de descanso")
            saturacion_util = horas_utiles * self._parse_float("saturacion_maxima_pct", "Saturación máxima %") / 100.0
            self._general_vars["horas_brutas_dia"].set(f"{horas_brutas:.2f}")
            self._general_vars["horas_utiles_dia"].set(f"{horas_utiles:.2f}")
            self._general_vars["saturacion_util_objetivo"].set(f"{saturacion_util:.2f}")
        except Exception:
            self._general_vars["horas_brutas_dia"].set("-")
            self._general_vars["horas_utiles_dia"].set("-")
            self._general_vars["saturacion_util_objetivo"].set("-")

    def _save_general_settings(self) -> None:
        try:
            payload = self._collect_payload()
            self.service.save_general_settings(payload)
            self._recalculate()
            messagebox.showinfo("Configuración productiva", "Configuración guardada correctamente.", parent=self)
        except Exception as exc:
            messagebox.showerror("Datos inválidos", str(exc), parent=self)

    def _reset_defaults(self) -> None:
        self.service.reset_general_defaults()
        self._load_general_settings()
        messagebox.showinfo("Configuración productiva", "Valores por defecto restaurados.", parent=self)
