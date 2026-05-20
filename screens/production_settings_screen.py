from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from services.production_settings_service import ProductionSettingsService
from utils.help_dialog import show_tab_help
from utils.production_help_texts import PRODUCTION_FIELD_HELP, PRODUCTION_PERSONAL_HELP
from widgets.screen_header import ScreenHeader


class ProductionSettingsScreen(ttk.Frame):
    VOLCADO_OPTIONS = ["Compacta", "Línea invierno", "Línea verano", "Tolva", "Manual"]
    STAFF_TYPES = ["Directo", "Indirecto", "Soporte"]

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=10)
        self.on_back = on_back
        self.service = ProductionSettingsService()

        self._general_vars: dict[str, tk.Variable] = {}
        self._tipos_volcado_vars: dict[str, tk.IntVar] = {}
        self._staff_summary_vars: dict[str, tk.Variable] = {}
        self._staff_editor_vars: dict[str, tk.Variable] = {}
        self._staff_tree: ttk.Treeview | None = None
        self._build_ui()
        self._load_general_settings()
        self._load_staff_settings()

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
        personal_tab = ttk.Frame(notebook, padding=12)
        notebook.add(personal_tab, text="Personal")
        for title in ("Confecciones", "Máquinas / líneas", "Rendimientos", "Penalizaciones", "Reglas / semáforo"):
            placeholder = ttk.Frame(notebook, padding=12)
            ttk.Label(placeholder, text="Pestaña preparada para una próxima integración.").pack(anchor="w")
            notebook.add(placeholder, text=title)

        self._build_general_tab(general_tab)
        self._build_staff_tab(personal_tab)

    # General tab (sin cambios funcionales)
    def _build_general_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        panel = ttk.LabelFrame(parent, text="Parámetros operativos diarios", padding=12)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_columnconfigure(1, weight=1)
        ttk.Button(panel, text="ⓘ Descripción de campos", command=self._show_general_day_help).grid(row=0, column=2, sticky="e", padx=(8, 0), pady=(0, 8))

        def add_entry(row: int, key: str, label: str, default: str = "") -> None:
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            var = tk.StringVar(value=default)
            ttk.Entry(panel, textvariable=var).grid(row=row, column=1, sticky="ew", pady=4)
            self._general_vars[key] = var

        def add_combo(row: int, key: str, label: str, values: list[str]) -> None:
            ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            var = tk.StringVar(value=values[0])
            ttk.Combobox(panel, textvariable=var, values=values, state="readonly").grid(row=row, column=1, sticky="ew", pady=4)
            self._general_vars[key] = var

        def add_check(row: int, key: str, label: str, default: int = 0) -> None:
            var = tk.IntVar(value=default)
            ttk.Checkbutton(panel, text=label, variable=var).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
            self._general_vars[key] = var

        def add_volcado_checks(row: int) -> None:
            ttk.Label(panel, text="Líneas de volcado activas").grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=4)
            container = ttk.Frame(panel)
            container.grid(row=row, column=1, sticky="w", pady=4)
            for idx, option in enumerate(self.VOLCADO_OPTIONS):
                var = tk.IntVar(value=1 if option == "Compacta" else 0)
                self._tipos_volcado_vars[option] = var
                ttk.Checkbutton(container, text=option, variable=var).grid(row=idx, column=0, sticky="w", pady=1)

        add_entry(1, "horas_turno", "Horas por turno", "8")
        add_entry(2, "numero_turnos", "Número de turnos", "1")
        add_entry(3, "horas_descanso", "Horas de descanso", "0.5")
        add_combo(4, "tipo_campana", "Tipo de campaña", ["Baja actividad", "Normal", "Alta", "Pico campaña"])
        add_volcado_checks(5)
        add_entry(6, "saturacion_maxima_pct", "Saturación máxima %", "90")
        add_check(7, "permitir_horas_extra", "Permitir horas extra", 1)
        add_check(8, "permitir_segundo_turno", "Permitir segundo turno", 0)
        add_check(9, "priorizar_pedidos_reales", "Priorizar pedidos reales", 1)
        add_check(10, "permitir_adelantar_produccion", "Permitir adelantar producción", 1)
        add_check(11, "agrupar_pedidos_compatibles", "Agrupar pedidos compatibles", 1)
        add_check(12, "minimizar_cambios_formato", "Minimizar cambios de formato", 1)
        add_entry(13, "kg_objetivo_dia", "Kg objetivo día", "0")
        add_entry(14, "palets_objetivo_dia", "Palets objetivo día", "0")
        add_entry(15, "pedidos_maximos_recomendados", "Pedidos máximos recomendados", "0")

        calc = ttk.LabelFrame(parent, text="Campos calculados", padding=12)
        calc.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        calc.grid_columnconfigure(1, weight=1)
        self._general_vars["horas_brutas_dia"] = tk.StringVar(); self._general_vars["horas_utiles_dia"] = tk.StringVar(); self._general_vars["saturacion_util_objetivo"] = tk.StringVar()
        self._add_readonly(calc, 0, "horas_brutas_dia", "Horas brutas día", self._general_vars["horas_brutas_dia"])
        self._add_readonly(calc, 1, "horas_utiles_dia", "Horas útiles día", self._general_vars["horas_utiles_dia"])
        self._add_readonly(calc, 2, "saturacion_util_objetivo", "Saturación útil objetivo", self._general_vars["saturacion_util_objetivo"])
        btns = ttk.Frame(parent); btns.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(btns, text="Guardar configuración", command=self._save_general_settings).pack(side="left", padx=4)
        ttk.Button(btns, text="Restaurar valores por defecto", command=self._reset_defaults).pack(side="left", padx=4)
        ttk.Button(btns, text="Volver", command=self.on_back).pack(side="right", padx=4)
        for key in ("horas_turno", "numero_turnos", "horas_descanso", "saturacion_maxima_pct"):
            self._general_vars[key].trace_add("write", lambda *_: self._recalculate())

    def _build_staff_tab(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)
        ttk.Button(parent, text="ⓘ Descripción de campos", command=self._show_personal_help).grid(row=0, column=0, sticky="e", pady=(0, 8))

        summary = ttk.LabelFrame(parent, text="Resumen de plantilla diaria", padding=12)
        summary.grid(row=1, column=0, sticky="ew")
        summary.grid_columnconfigure(1, weight=1)
        fields = [("personal_total", "Personal disponible total"), ("personal_directo", "Personal directo disponible"), ("personal_indirecto", "Personal indirecto disponible"), ("horas_por_persona", "Horas por persona"), ("ausencias_previstas", "Ausencias previstas")]
        for i, (key, label) in enumerate(fields):
            ttk.Label(summary, text=label).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=4)
            var = tk.StringVar(value="0")
            ttk.Entry(summary, textvariable=var).grid(row=i, column=1, sticky="ew", pady=4)
            self._staff_summary_vars[key] = var
        ttk.Label(summary, text="Observaciones").grid(row=5, column=0, sticky="nw", padx=(0, 8), pady=4)
        obs_var = tk.StringVar(value="")
        ttk.Entry(summary, textvariable=obs_var).grid(row=5, column=1, sticky="ew", pady=4)
        self._staff_summary_vars["observaciones"] = obs_var

        areas = ttk.LabelFrame(parent, text="Personal por área operativa", padding=12)
        areas.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        parent.grid_rowconfigure(2, weight=1)
        columns = ("id", "area", "tipo_personal", "disponible", "minimo_operativo", "optimo", "activo", "observaciones")
        tree = ttk.Treeview(areas, columns=columns, show="headings", height=10)
        self._staff_tree = tree
        headers = {"id": "ID", "area": "Área", "tipo_personal": "Tipo personal", "disponible": "Disponible", "minimo_operativo": "Mínimo operativo", "optimo": "Óptimo", "activo": "Activo", "observaciones": "Observaciones"}
        widths = {"id": 40, "area": 150, "tipo_personal": 110, "disponible": 85, "minimo_operativo": 110, "optimo": 75, "activo": 70, "observaciones": 260}
        for col in columns:
            tree.heading(col, text=headers[col]); tree.column(col, width=widths[col], anchor="w")
        yscroll = ttk.Scrollbar(areas, orient="vertical", command=tree.yview)
        xscroll = ttk.Scrollbar(areas, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew"); yscroll.grid(row=0, column=1, sticky="ns"); xscroll.grid(row=1, column=0, sticky="ew")
        areas.grid_columnconfigure(0, weight=1); areas.grid_rowconfigure(0, weight=1)
        tree.bind("<<TreeviewSelect>>", self._on_staff_row_selected)

        editor = ttk.LabelFrame(parent, text="Editar área seleccionada", padding=12)
        editor.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        editor.grid_columnconfigure(1, weight=1)
        self._staff_editor_vars = {"id": tk.StringVar(value=""), "area": tk.StringVar(value=""), "tipo_personal": tk.StringVar(value="Directo"), "disponible": tk.StringVar(value="0"), "minimo_operativo": tk.StringVar(value="0"), "optimo": tk.StringVar(value="0"), "activo": tk.IntVar(value=1), "observaciones": tk.StringVar(value="")}
        ttk.Label(editor, text="Área").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(editor, textvariable=self._staff_editor_vars["area"]).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(editor, text="Tipo personal").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(editor, textvariable=self._staff_editor_vars["tipo_personal"], values=self.STAFF_TYPES, state="readonly").grid(row=1, column=1, sticky="ew", pady=4)
        for r, key, label in ((2, "disponible", "Disponible"), (3, "minimo_operativo", "Mínimo operativo"), (4, "optimo", "Óptimo")):
            ttk.Label(editor, text=label).grid(row=r, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(editor, textvariable=self._staff_editor_vars[key]).grid(row=r, column=1, sticky="ew", pady=4)
        ttk.Checkbutton(editor, text="Activo", variable=self._staff_editor_vars["activo"]).grid(row=5, column=1, sticky="w", pady=4)
        ttk.Label(editor, text="Observaciones").grid(row=6, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(editor, textvariable=self._staff_editor_vars["observaciones"]).grid(row=6, column=1, sticky="ew", pady=4)
        ttk.Button(editor, text="Aplicar cambios a la fila", command=self._apply_staff_row_changes).grid(row=7, column=1, sticky="e", pady=(8, 0))

        btns = ttk.Frame(parent); btns.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(btns, text="Guardar personal", command=self._save_staff_settings).pack(side="left", padx=4)
        ttk.Button(btns, text="Restaurar valores por defecto", command=self._reset_staff_defaults).pack(side="left", padx=4)
        ttk.Button(btns, text="Añadir área", command=self._add_staff_area).pack(side="left", padx=4)
        ttk.Button(btns, text="Eliminar área seleccionada", command=self._delete_staff_area).pack(side="left", padx=4)

    def _add_readonly(self, parent: ttk.Frame, row: int, key: str, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=variable, state="readonly").grid(row=row, column=1, sticky="ew", pady=4)

    def _show_general_day_help(self) -> None:
        keys = ["horas_turno", "numero_turnos", "horas_descanso", "tipo_campana", "tipos_volcado_activos", "saturacion_maxima_pct", "permitir_horas_extra", "permitir_segundo_turno", "priorizar_pedidos_reales", "permitir_adelantar_produccion", "agrupar_pedidos_compatibles", "minimizar_cambios_formato", "kg_objetivo_dia", "palets_objetivo_dia", "pedidos_maximos_recomendados", "horas_brutas_dia", "horas_utiles_dia", "saturacion_util_objetivo"]
        show_tab_help(self, title="Descripción de campos - General del día", intro="Esta pestaña define los parámetros básicos de trabajo que se usarán para calcular la capacidad productiva diaria del almacén.", help_items=[PRODUCTION_FIELD_HELP[k] for k in keys if k in PRODUCTION_FIELD_HELP])

    def _show_personal_help(self) -> None:
        keys = ["personal_total", "personal_directo", "personal_indirecto", "horas_por_persona", "ausencias_previstas", "area", "tipo_personal", "disponible", "minimo_operativo", "optimo", "activo", "observaciones"]
        show_tab_help(self, title="Descripción de campos - Personal", intro="Esta pestaña define la plantilla disponible y los mínimos operativos por área de trabajo. Estos datos se usarán posteriormente para estimar si los pedidos previstos pueden producirse con el personal disponible.", help_items=[PRODUCTION_PERSONAL_HELP[k] for k in keys if k in PRODUCTION_PERSONAL_HELP])

    def _load_general_settings(self) -> None:
        data = self.service.get_general_settings()
        for key, var in self._general_vars.items():
            if key in data:
                var.set(int(data[key]) if isinstance(var, tk.IntVar) else str(data[key]))
        activos = set(data.get("tipos_volcado_activos", []))
        for option, var in self._tipos_volcado_vars.items():
            var.set(1 if option in activos else 0)
        self._recalculate()

    def _load_staff_settings(self) -> None:
        summary = self.service.get_staff_summary()
        for key, var in self._staff_summary_vars.items():
            var.set(str(summary.get(key, "")))
        self._refresh_staff_tree(self.service.get_staff_areas())

    def _refresh_staff_tree(self, rows: list[dict]) -> None:
        if not self._staff_tree:
            return
        self._staff_tree.delete(*self._staff_tree.get_children())
        for row in rows:
            self._staff_tree.insert("", "end", values=(row.get("id", ""), row.get("area", ""), row.get("tipo_personal", ""), row.get("disponible", 0), row.get("minimo_operativo", 0), row.get("optimo", 0), row.get("activo", 0), row.get("observaciones", "")))

    def _parse_float(self, key: str, label: str) -> float:
        raw = str(self._general_vars[key].get()).strip().replace(",", ".")
        if raw == "": raise ValueError(f"{label}: valor obligatorio")
        return float(raw)

    def _parse_int(self, key: str, label: str) -> int:
        raw = str(self._general_vars[key].get()).strip()
        if raw == "": raise ValueError(f"{label}: valor obligatorio")
        return int(raw)

    def _parse_non_negative_int(self, value: str, label: str) -> int:
        number = int(str(value).strip())
        if number < 0: raise ValueError(f"{label} debe ser >= 0")
        return number

    def _collect_payload(self) -> dict:
        horas_turno = self._parse_float("horas_turno", "Horas por turno"); numero_turnos = self._parse_int("numero_turnos", "Número de turnos"); horas_descanso = self._parse_float("horas_descanso", "Horas de descanso"); saturacion = self._parse_float("saturacion_maxima_pct", "Saturación máxima %")
        if horas_turno < 0 or numero_turnos < 0 or horas_descanso < 0: raise ValueError("Horas por turno, número de turnos y horas de descanso deben ser >= 0")
        if saturacion < 0 or saturacion > 100: raise ValueError("Saturación máxima % debe estar entre 0 y 100")
        tipos_volcado_activos = [option for option, var in self._tipos_volcado_vars.items() if int(var.get()) == 1]
        if not tipos_volcado_activos: raise ValueError("Debe activar al menos una línea de volcado")
        return {"horas_turno": horas_turno, "numero_turnos": numero_turnos, "horas_descanso": horas_descanso, "tipo_campana": self._general_vars["tipo_campana"].get(), "tipos_volcado_activos": tipos_volcado_activos, "saturacion_maxima_pct": saturacion, "permitir_horas_extra": int(self._general_vars["permitir_horas_extra"].get()), "permitir_segundo_turno": int(self._general_vars["permitir_segundo_turno"].get()), "priorizar_pedidos_reales": int(self._general_vars["priorizar_pedidos_reales"].get()), "permitir_adelantar_produccion": int(self._general_vars["permitir_adelantar_produccion"].get()), "agrupar_pedidos_compatibles": int(self._general_vars["agrupar_pedidos_compatibles"].get()), "minimizar_cambios_formato": int(self._general_vars["minimizar_cambios_formato"].get()), "kg_objetivo_dia": self._parse_float("kg_objetivo_dia", "Kg objetivo día"), "palets_objetivo_dia": self._parse_float("palets_objetivo_dia", "Palets objetivo día"), "pedidos_maximos_recomendados": self._parse_int("pedidos_maximos_recomendados", "Pedidos máximos recomendados")}

    def _collect_staff_summary_payload(self) -> dict:
        return {
            "personal_total": self._parse_non_negative_int(self._staff_summary_vars["personal_total"].get(), "Personal disponible total"),
            "personal_directo": self._parse_non_negative_int(self._staff_summary_vars["personal_directo"].get(), "Personal directo disponible"),
            "personal_indirecto": self._parse_non_negative_int(self._staff_summary_vars["personal_indirecto"].get(), "Personal indirecto disponible"),
            "horas_por_persona": float(str(self._staff_summary_vars["horas_por_persona"].get()).replace(",", ".")),
            "ausencias_previstas": self._parse_non_negative_int(self._staff_summary_vars["ausencias_previstas"].get(), "Ausencias previstas"),
            "observaciones": str(self._staff_summary_vars["observaciones"].get()).strip(),
        }

    def _collect_staff_rows_payload(self) -> list[dict]:
        if not self._staff_tree: return []
        rows: list[dict] = []
        areas: set[str] = set()
        for item_id in self._staff_tree.get_children():
            values = self._staff_tree.item(item_id, "values")
            area = str(values[1]).strip()
            if not area: raise ValueError("El área no puede estar vacía")
            if area.lower() in areas: raise ValueError(f"Área duplicada: {area}")
            areas.add(area.lower())
            rows.append({"area": area, "tipo_personal": str(values[2]).strip(), "disponible": self._parse_non_negative_int(values[3], f"Disponible ({area})"), "minimo_operativo": self._parse_non_negative_int(values[4], f"Mínimo operativo ({area})"), "optimo": self._parse_non_negative_int(values[5], f"Óptimo ({area})"), "activo": 1 if str(values[6]).strip() in ("1", "True", "true", "Sí", "si") else 0, "observaciones": str(values[7]).strip()})
        return rows

    def _recalculate(self) -> None:
        try:
            horas_brutas = self._parse_float("horas_turno", "Horas por turno") * self._parse_int("numero_turnos", "Número de turnos")
            horas_utiles = horas_brutas - self._parse_float("horas_descanso", "Horas de descanso")
            saturacion_util = horas_utiles * self._parse_float("saturacion_maxima_pct", "Saturación máxima %") / 100.0
            self._general_vars["horas_brutas_dia"].set(f"{horas_brutas:.2f}"); self._general_vars["horas_utiles_dia"].set(f"{horas_utiles:.2f}"); self._general_vars["saturacion_util_objetivo"].set(f"{saturacion_util:.2f}")
        except Exception:
            self._general_vars["horas_brutas_dia"].set("-"); self._general_vars["horas_utiles_dia"].set("-"); self._general_vars["saturacion_util_objetivo"].set("-")

    def _save_general_settings(self) -> None:
        try:
            self.service.save_general_settings(self._collect_payload()); self._recalculate(); messagebox.showinfo("Configuración productiva", "Configuración guardada correctamente.", parent=self)
        except Exception as exc:
            messagebox.showerror("Datos inválidos", str(exc), parent=self)

    def _reset_defaults(self) -> None:
        self.service.reset_general_defaults(); self._load_general_settings(); messagebox.showinfo("Configuración productiva", "Valores por defecto restaurados.", parent=self)

    def _on_staff_row_selected(self, _event=None) -> None:
        if not self._staff_tree: return
        selected = self._staff_tree.selection()
        if not selected: return
        values = self._staff_tree.item(selected[0], "values")
        for idx, key in enumerate(("id", "area", "tipo_personal", "disponible", "minimo_operativo", "optimo", "activo", "observaciones")):
            self._staff_editor_vars[key].set(values[idx])

    def _apply_staff_row_changes(self) -> None:
        if not self._staff_tree: return
        selected = self._staff_tree.selection()
        if not selected:
            messagebox.showerror("Personal", "Seleccione una fila para editar.", parent=self); return
        try:
            area = str(self._staff_editor_vars["area"].get()).strip()
            if not area: raise ValueError("El área es obligatoria")
            values = (self._staff_editor_vars["id"].get(), area, self._staff_editor_vars["tipo_personal"].get(), self._parse_non_negative_int(self._staff_editor_vars["disponible"].get(), "Disponible"), self._parse_non_negative_int(self._staff_editor_vars["minimo_operativo"].get(), "Mínimo operativo"), self._parse_non_negative_int(self._staff_editor_vars["optimo"].get(), "Óptimo"), 1 if int(self._staff_editor_vars["activo"].get()) else 0, str(self._staff_editor_vars["observaciones"].get()).strip())
            self._staff_tree.item(selected[0], values=values)
        except Exception as exc:
            messagebox.showerror("Datos inválidos", str(exc), parent=self)

    def _add_staff_area(self) -> None:
        if not self._staff_tree: return
        self._staff_tree.insert("", "end", values=("", "Nueva área", "Directo", 0, 0, 0, 1, ""))

    def _delete_staff_area(self) -> None:
        if not self._staff_tree: return
        selected = self._staff_tree.selection()
        if not selected:
            messagebox.showerror("Personal", "Seleccione una fila para eliminar.", parent=self); return
        if messagebox.askyesno("Confirmar eliminación", "¿Desea eliminar el área seleccionada?", parent=self):
            self._staff_tree.delete(selected[0])

    def _save_staff_settings(self) -> None:
        try:
            summary = self._collect_staff_summary_payload()
            if summary["horas_por_persona"] < 0: raise ValueError("Horas por persona debe ser >= 0")
            rows = self._collect_staff_rows_payload()
            self.service.save_staff_summary(summary)
            self.service.save_staff_areas(rows)
            self._load_staff_settings()
            messagebox.showinfo("Configuración productiva", "Personal guardado correctamente.", parent=self)
        except Exception as exc:
            messagebox.showerror("Datos inválidos", str(exc), parent=self)

    def _reset_staff_defaults(self) -> None:
        self.service.reset_staff_defaults()
        self._load_staff_settings()
        messagebox.showinfo("Configuración productiva", "Valores por defecto de personal restaurados.", parent=self)
