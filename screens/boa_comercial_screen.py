import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from screens.boa_clientes_screen import BOAClientesScreen
from screens.boa_precios_screen import BOAPreciosScreen
from screens.boa_reclamaciones_screen import BOAReclamacionesScreen
from screens.boa_resumen_screen import BOAResumenScreen
from services.comercial_service import ComercialService
from widgets.screen_header import ScreenHeader
from widgets.date_picker import DatePickerPopup
from widgets.multi_select_filter import MultiSelectFilter


class BOAComercialScreen(ttk.Frame):
    FILTERS_FILE = Path("config") / "filtros_boa.json"
    FILTER_KEYS = [
        "campana",
        "cultivo",
        "empresa",
        "semana",
        "cliente",
        "pais",
        "calibre",
        "categoria",
        "var_cliente",
        "var_coop",
        "marca",
    ]

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.service = ComercialService()

        self.fecha_desde_var = tk.StringVar()
        self.fecha_hasta_var = tk.StringVar()
        self.filters_status_var = tk.StringVar(value="Sin filtros activos")
        self.filter_widgets: dict[str, MultiSelectFilter] = {}

        self._build_ui()
        self._load_filters()
        self._build_tabs()
        self._refresh_filter_options()
        self.refresh_current()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ScreenHeader(self, title="BOA Comercial", on_back=self.on_back)
        header.grid(row=0, column=0, sticky="ew")

        filters = ttk.LabelFrame(self, text="Filtros globales", padding=12)
        filters.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        fields = [
            ("Campaña", "campana"),
            ("Cultivo", "cultivo"),
            ("Empresa", "empresa"),
            ("Semana", "semana"),
            ("Fecha desde", "fecha_desde"),
            ("Fecha hasta", "fecha_hasta"),
            ("Cliente", "cliente"),
            ("País", "pais"),
            ("Variedad Coop", "var_coop"),
            ("Variedad Cliente", "var_cliente"),
            ("Calibre", "calibre"),
            ("Categoría", "categoria"),
            ("Marca", "marca"),
        ]

        for col in range(4):
            filters.grid_columnconfigure(col, weight=1)

        for idx, (label, key) in enumerate(fields):
            r = (idx // 4) * 2
            c = idx % 4
            ttk.Label(filters, text=label).grid(row=r, column=c, sticky="w", padx=6)
            if key == "fecha_desde":
                self._build_date_field(filters, r + 1, c, self.fecha_desde_var)
            elif key == "fecha_hasta":
                self._build_date_field(filters, r + 1, c, self.fecha_hasta_var)
            else:
                widget = MultiSelectFilter(filters, title=label, on_apply=lambda k=key: self._on_filter_changed(k), width=24)
                widget.grid(row=r + 1, column=c, sticky="ew", padx=6, pady=(0, 8))
                self.filter_widgets[key] = widget

        botones_frame = ttk.Frame(filters)
        botones_frame.grid(row=8, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Button(botones_frame, text="Aplicar filtros", command=self.apply_filters).pack(side="left", padx=(0, 8))
        ttk.Button(botones_frame, text="Limpiar filtros", command=self.clear_filters).pack(side="left", padx=(0, 8))
        ttk.Button(botones_frame, text="Reaplicar filtros", command=self.reapply_filters).pack(side="left")

        ttk.Label(filters, textvariable=self.filters_status_var).grid(row=9, column=0, columnspan=4, sticky="w", padx=6, pady=(6, 0))

        self.content = ttk.Frame(self)
        self.content.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

    def _build_date_field(self, parent: ttk.Frame, row: int, col: int, var: tk.StringVar) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=col, sticky="ew", padx=6, pady=(0, 8))
        frame.grid_columnconfigure(0, weight=1)
        entry = ttk.Entry(frame, textvariable=var)
        entry.grid(row=0, column=0, sticky="ew")
        btn = ttk.Button(frame, text="...", width=3, command=lambda v=var, b=None: None)
        btn.configure(command=lambda v=var, b=btn: self._open_date_picker(v, b))
        btn.grid(row=0, column=1, padx=(4, 0))

    def _open_date_picker(self, var: tk.StringVar, anchor_widget: tk.Widget) -> None:
        DatePickerPopup(self, target_var=var, anchor_widget=anchor_widget)

    def _build_tabs(self) -> None:
        self.tabs = ttk.Notebook(self.content)
        self.tabs.grid(row=0, column=0, sticky="nsew")
        self.tabs.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.resumen_tab = BOAResumenScreen(self.tabs, service=self.service, get_filters=self.get_filters)
        self.clientes_tab = BOAClientesScreen(self.tabs, service=self.service, get_filters=self.get_filters)
        self.precios_tab = BOAPreciosScreen(self.tabs, service=self.service, get_filters=self.get_filters)
        self.reclamaciones_tab = BOAReclamacionesScreen(self.tabs, service=self.service, get_filters=self.get_filters)

        self.tabs.add(self.resumen_tab, text="Resumen")
        self.tabs.add(self.clientes_tab, text="Clientes")
        self.tabs.add(self.precios_tab, text="Precios")
        self.tabs.add(self.reclamaciones_tab, text="Reclamaciones")

    def _normalize_saved_filters(self, data: dict) -> dict:
        normalized = {}
        for key in self.FILTER_KEYS:
            raw = data.get(key, [])
            if isinstance(raw, str):
                raw = [raw] if raw.strip() else []
            elif not isinstance(raw, list):
                raw = [str(raw)] if str(raw or "").strip() else []
            normalized[key] = [str(v).strip() for v in raw if str(v or "").strip()]
        normalized["fecha_desde"] = str(data.get("fecha_desde", "") or "").strip()
        normalized["fecha_hasta"] = str(data.get("fecha_hasta", "") or "").strip()
        return normalized

    def get_filters(self) -> dict:
        return {
            **{k: self.filter_widgets[k].get_selected() for k in self.FILTER_KEYS},
            "fecha_desde": self.fecha_desde_var.get().strip(),
            "fecha_hasta": self.fecha_hasta_var.get().strip(),
        }

    def _on_filter_changed(self, changed_key: str) -> None:
        self._refresh_filter_options(changed_key)
        self._update_filters_status()

    def _refresh_filter_options(self, changed_key: str | None = None) -> None:
        current_filters = self.get_filters()
        for key in self.FILTER_KEYS:
            options = self.service.get_filter_options(current_filters, key)
            if key == "semana":
                options = sorted(options, key=self._week_sort_key)
            selected = set(self.filter_widgets[key].get_selected())
            valid_selected = [v for v in selected if v in set(options)]
            self.filter_widgets[key].set_options(options)
            self.filter_widgets[key].set_selected(valid_selected)

    @staticmethod
    def _week_sort_key(value: str) -> int:
        try:
            week = int(float(value))
        except ValueError:
            return 999
        return (week - 35) if week >= 36 else (week + 17)

    def clear_filters(self) -> None:
        for key in self.FILTER_KEYS:
            self.filter_widgets[key].clear()
        self.fecha_desde_var.set("")
        self.fecha_hasta_var.set("")
        self.service.clear_cache()
        self._refresh_filter_options()
        self._save_filters()
        self._update_filters_status()
        self.refresh_current()

    def apply_filters(self) -> None:
        self.service.clear_cache()
        self._refresh_filter_options()
        self._save_filters()
        self._update_filters_status()
        self.refresh_current()

    def reapply_filters(self) -> None:
        self.service.clear_cache()
        self.refresh_current()

    def _on_tab_changed(self, _event=None) -> None:
        tab_activa = self.tabs.tab(self.tabs.select(), "text") if hasattr(self, "tabs") else ""
        logging.getLogger(__name__).info("[TRACE NotebookTabChanged] screen=BOAComercial tab=%s", tab_activa)
        self.refresh_current()

    def refresh_current(self) -> None:
        self._update_filters_status()
        current = self.tabs.nametowidget(self.tabs.select()) if hasattr(self, "tabs") else None
        if current is not None and hasattr(current, "refresh"):
            current.refresh()

    def _update_filters_status(self) -> None:
        labels = {
            "campana": "Campaña",
            "cultivo": "Cultivo",
            "empresa": "Empresa",
            "semana": "Semana",
            "cliente": "Cliente",
            "pais": "País",
            "calibre": "Calibre",
            "categoria": "Categoría",
            "var_cliente": "Variedad Cliente",
            "var_coop": "Variedad Coop",
            "marca": "Marca",
            "fecha_desde": "Fecha desde",
            "fecha_hasta": "Fecha hasta",
        }

        filters = self.get_filters()
        parts: list[str] = []
        for key in self.FILTER_KEYS:
            selected = filters.get(key, [])
            if selected:
                parts.append(f"{labels[key]}={','.join(selected)}")
        if filters.get("fecha_desde"):
            parts.append(f"Fecha desde={filters['fecha_desde']}")
        if filters.get("fecha_hasta"):
            parts.append(f"Fecha hasta={filters['fecha_hasta']}")
        self.filters_status_var.set("Filtros activos: " + " | ".join(parts) if parts else "Sin filtros activos")

    def _save_filters(self) -> None:
        self.FILTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with self.FILTERS_FILE.open("w", encoding="utf-8") as f:
            json.dump(self.get_filters(), f, ensure_ascii=False, indent=2)

    def _load_filters(self) -> None:
        if not self.FILTERS_FILE.exists():
            self._update_filters_status()
            return
        try:
            data = json.loads(self.FILTERS_FILE.read_text(encoding="utf-8"))
            normalized = self._normalize_saved_filters(data)
            for key in self.FILTER_KEYS:
                self.filter_widgets[key].set_selected(normalized.get(key, []))
            self.fecha_desde_var.set(normalized.get("fecha_desde", ""))
            self.fecha_hasta_var.set(normalized.get("fecha_hasta", ""))
        except Exception:
            pass
        self._update_filters_status()
