import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from db.connection import db_exists, get_db_path
from services.precios_orientativos_service import PreciosOrientativosService
from widgets.data_table import DataTable
from widgets.multi_select_filter import MultiSelectFilter
from widgets.screen_header import ScreenHeader


class PreciosOrientativosScreen(ttk.Frame):
    FILTERS_FILE = Path("config") / "filtros_precios.json"
    FILTER_KEYS = ["campana", "cultivo", "empresa", "semana", "cliente", "var_coop", "grupo_varietal", "estado_precio"]
    TABLE_COLUMNS = [
        "IdPedidoLora",
        "Linea",
        "Campaña",
        "Semana",
        "FechaSalida",
        "Cultivo",
        "Empresa",
        "EmpresaNombre",
        "Cliente",
        "Confeccion",
        "GrupoConfeccion",
        "Calibre",
        "CalibreU",
        "VarCoop",
        "NetoCliente",
        "EurosKG",
        "EurosOrientativos",
        "EurosOrientativosCalcAnterior",
        "EurosOrientativosCalc",
        "PrecioOrientativoFinal",
        "OrigenPrecioOrientativo",
        "Metodo",
        "MuestrasUsadas",
        "MediaGrupo",
        "MediaCalibre",
        "CalibreUUsado",
        "SemanaPrecioUsada",
        "CampanaUsada",
        "CultivoUsado",
        "EmpresaUsada",
        "IdsUsados",
        "Observaciones",
        "GrupoVarietal",
        "EstadoPrecio",
    ]

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.service = PreciosOrientativosService()
        self.rows: list[dict] = []
        self.propuesta_rows: list[dict] = []
        self.propuesta_table: DataTable | None = None
        self._proposal_editor: tk.Entry | None = None

        self.filter_widgets: dict[str, MultiSelectFilter] = {}
        self.status_var = tk.StringVar(value="")
        self.counter_var = tk.StringVar(value="0 pedidos pendientes")
        self.coverage_var = tk.StringVar(value="Cobertura precio orientativo: 0,00%")
        self.summary_var = tk.StringVar(value="")
        self.last_summary: dict | None = None

        self._build_ui()
        self._load_filters()
        self._refresh_filter_options()
        schema_warnings = self.service.init_schema()
        if schema_warnings:
            self.status_var.set(" | ".join(schema_warnings))

    def _build_ui(self) -> None:
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ScreenHeader(self, title="Análisis de precios", subtitle="Revisar precios orientativos", on_back=self.on_back)
        header.grid(row=0, column=0, sticky="ew")

        filters = ttk.LabelFrame(self, text="Filtros", padding=12)
        filters.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        fields = [
            ("Campaña", "campana"),
            ("Cultivo", "cultivo"),
            ("Empresa", "empresa"),
            ("Semana", "semana"),
            ("Cliente", "cliente"),
            ("Variedad Coop", "var_coop"),
            ("Grupo varietal", "grupo_varietal"),
        ]
        for idx, (label, key) in enumerate(fields):
            ttk.Label(filters, text=label).grid(row=(idx // 3) * 2, column=idx % 3, padx=6, sticky="w")
            w = MultiSelectFilter(filters, title=label, on_apply=lambda k=key: self._on_filter_changed(k), width=24)
            w.grid(row=(idx // 3) * 2 + 1, column=idx % 3, padx=6, pady=(0, 8), sticky="ew")
            self.filter_widgets[key] = w
            filters.grid_columnconfigure(idx % 3, weight=1)

        row_base = ((len(fields) - 1) // 3) * 2 + 2
        ttk.Label(filters, text="Estado precio").grid(row=row_base, column=0, padx=6, sticky="w")
        w_estado = MultiSelectFilter(filters, title="Estado precio", on_apply=lambda: self._on_filter_changed("estado_precio"), width=24)
        w_estado.grid(row=row_base + 1, column=0, padx=6, pady=(0, 8), sticky="ew")
        w_estado.set_options(["TODOS", "SIN_PRECIO", "CON_PRECIO", "ESTIMADO", "ORIGINAL"])
        self.filter_widgets["estado_precio"] = w_estado

        actions = ttk.Frame(filters)
        actions.grid(row=row_base + 2, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(actions, text="Buscar pendientes", command=self.buscar_pendientes).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Recalcular desde cero", command=self.recalcular_desde_cero).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Calcular estimaciones", command=self.calcular_estimaciones).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Guardar estimaciones", command=self.guardar_estimaciones).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Preparar propuesta", command=self.preparar_propuesta).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Generar PDF propuesta", command=self.generar_pdf_propuesta).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Eliminar cálculos guardados del filtro", command=self.eliminar_calculos_guardados).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Ver resumen", command=self.ver_resumen).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Ver resumen semanal", command=self.ver_resumen_semanal).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Limpiar", command=self.limpiar).pack(side="left")

        summary_frame = ttk.LabelFrame(self, text="Resumen de cobertura", padding=8)
        summary_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(summary_frame, textvariable=self.coverage_var, style="KPI.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(summary_frame, textvariable=self.summary_var, justify="left").grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.table = DataTable(self, columns=self.TABLE_COLUMNS)
        self.table.grid(row=3, column=0, sticky="nsew")

        proposal_frame = ttk.LabelFrame(self, text="Propuesta de precios", padding=8)
        proposal_frame.grid(row=4, column=0, sticky="nsew", pady=(8, 0))
        proposal_frame.grid_rowconfigure(0, weight=1)
        proposal_frame.grid_columnconfigure(0, weight=1)
        proposal_columns = ["IdPedidoLora", "Línea", "Semana", "FechaSalida", "Cliente", "Variedad Coop", "Calibre", "Confección", "GrupoConfección", "NetoCliente", "EurosOrientativos actual", "EurosOrientativosCalc", "€/kg propuesto", "Método", "Observaciones"]
        self.propuesta_table = DataTable(proposal_frame, columns=proposal_columns)
        self.propuesta_table.grid(row=0, column=0, sticky="nsew")
        self.propuesta_table.tree.bind("<Double-1>", self._on_propuesta_double_click)

        ttk.Label(self, textvariable=self.counter_var, style="KPI.TLabel").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Label(self, textvariable=self.status_var, foreground="#b00020").grid(row=6, column=0, sticky="w", pady=(4, 0))

    def _get_filters(self) -> dict[str, list[str]]:
        return {k: self.filter_widgets[k].get_selected() for k in self.FILTER_KEYS}

    def _on_filter_changed(self, _changed_key: str) -> None:
        self._refresh_filter_options()
        self._save_filters()

    def _refresh_filter_options(self) -> None:
        current = self._get_filters()
        for key in [k for k in self.FILTER_KEYS if k != "estado_precio"]:
            options = self.service.get_filter_options(current, key)
            selected = self.filter_widgets[key].get_selected()
            self.filter_widgets[key].set_options(options)
            self.filter_widgets[key].set_selected([v for v in selected if v in set(options)])

    def buscar_pendientes(self) -> None:
        if not db_exists():
            self.status_var.set(f"No se encontró la base de datos: {get_db_path()}")
            return
        rows, warnings = self.service.buscar_pendientes(self._get_filters())
        self.rows = rows
        self.table.set_rows(self.rows)
        self.counter_var.set(f"{len(self.rows)} pedidos pendientes")
        self.status_var.set(" | ".join(sorted(set(warnings))) if warnings else "")
        self.last_summary = None
        self.coverage_var.set("Cobertura precio orientativo: 0,00%")
        self.summary_var.set("")
        self.propuesta_rows = []
        if self.propuesta_table:
            self.propuesta_table.set_rows([])

    def calcular_estimaciones(self) -> None:
        if not self.rows:
            self.status_var.set("Primero ejecuta 'Buscar pendientes'.")
            return
        estimated, warnings = self.service.calcular_estimaciones(self.rows)
        self.rows = estimated
        self.table.set_rows(self.rows)
        self.counter_var.set(f"{len(self.rows)} pedidos pendientes")
        summary = self.service.generar_resumen_estimaciones(self.rows)
        self.last_summary = summary
        self._render_summary(summary)
        base_msg = f"Estimaciones calculadas. Cobertura: {summary.get('cobertura', 0):.2f}%".replace(".", ",")
        self.status_var.set((base_msg + (" | " + " | ".join(sorted(set(warnings))) if warnings else "")))

    def recalcular_desde_cero(self) -> None:
        if not db_exists():
            self.status_var.set(f"No se encontró la base de datos: {get_db_path()}")
            return
        rows, warnings = self.service.buscar_para_recalculo(self._get_filters())
        self.rows = rows
        self.table.set_rows(self.rows)
        self.counter_var.set(f"{len(self.rows)} pedidos cargados para recálculo")
        self.status_var.set(" | ".join(sorted(set(warnings))) if warnings else "Modo recálculo total cargado.")
        self.last_summary = None
        self.coverage_var.set("Cobertura precio orientativo: 0,00%")
        self.summary_var.set("")
        self.propuesta_rows = []
        if self.propuesta_table:
            self.propuesta_table.set_rows([])

    def preparar_propuesta(self) -> None:
        if not self.rows:
            self.status_var.set("Primero ejecuta 'Buscar pendientes'.")
            return
        if not any((self.service._to_float(r.get("EurosOrientativosCalc")) or 0) > 0 or str(r.get("Metodo") or "") for r in self.rows):
            self.status_var.set("Primero ejecuta 'Calcular estimaciones'.")
            return
        self.propuesta_rows = self.service.preparar_propuesta_rows(self.rows)
        if self.propuesta_table:
            self.propuesta_table.set_rows(self.propuesta_rows)
        self.status_var.set(f"Propuesta preparada con {len(self.propuesta_rows)} líneas sin precio orientativo original.")

    def _on_propuesta_double_click(self, event: tk.Event) -> None:
        if not self.propuesta_table:
            return
        tree = self.propuesta_table.tree
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = tree.identify_column(event.x)
        col_idx = int(col.replace("#", "")) - 1
        if self.propuesta_table.columns[col_idx] != "€/kg propuesto":
            return
        item_id = tree.identify_row(event.y)
        if not item_id:
            return
        x, y, width, height = tree.bbox(item_id, col)
        values = list(tree.item(item_id, "values"))
        self._proposal_editor = tk.Entry(tree)
        self._proposal_editor.place(x=x, y=y, width=width, height=height)
        self._proposal_editor.insert(0, values[col_idx])
        self._proposal_editor.focus_set()
        self._proposal_editor.bind("<Return>", lambda _e: self._save_proposed_value(item_id, col_idx))
        self._proposal_editor.bind("<FocusOut>", lambda _e: self._save_proposed_value(item_id, col_idx))

    def _save_proposed_value(self, item_id: str, col_idx: int) -> None:
        if not self.propuesta_table or not self._proposal_editor:
            return
        raw = self._proposal_editor.get().strip()
        normalized = raw.replace(",", ".")
        if raw:
            try:
                value = float(normalized)
                if value < 0:
                    raise ValueError
                final_value = f"{value:.4f}"
            except Exception:
                messagebox.showwarning("Valor inválido", "Introduce un número decimal válido mayor o igual a 0.", parent=self.winfo_toplevel())
                self._proposal_editor.focus_set()
                return
        else:
            final_value = ""
        tree = self.propuesta_table.tree
        values = list(tree.item(item_id, "values"))
        values[col_idx] = final_value
        tree.item(item_id, values=values)
        row_idx = tree.index(item_id)
        if 0 <= row_idx < len(self.propuesta_rows):
            self.propuesta_rows[row_idx]["€/kg propuesto"] = final_value
        self._proposal_editor.destroy()
        self._proposal_editor = None

    def generar_pdf_propuesta(self) -> None:
        if not self.propuesta_rows:
            self.status_var.set("Primero pulsa 'Preparar propuesta'.")
            return
        out_path, error = self.service.generar_pdf_propuesta(self.propuesta_rows, self._get_filters())
        if error:
            messagebox.showwarning("No se pudo generar el PDF", error, parent=self.winfo_toplevel())
            self.status_var.set(error)
            return
        messagebox.showinfo("PDF generado", f"PDF generado correctamente: {out_path}", parent=self.winfo_toplevel())
        self.status_var.set(f"PDF generado correctamente: {out_path}")

    def guardar_estimaciones(self) -> None:
        if not self.rows:
            self.status_var.set("No hay filas para guardar.")
            return
        saved, warnings = self.service.guardar_estimaciones(self.rows)
        msg = f"Estimaciones guardadas: {saved} pedidos."
        if warnings:
            msg += " " + " | ".join(sorted(set(warnings)))
        self.status_var.set(msg)

    def limpiar(self) -> None:
        for key in self.FILTER_KEYS:
            self.filter_widgets[key].clear()
        self._refresh_filter_options()
        self._save_filters()
        self.rows = []
        self.table.set_rows([])
        self.counter_var.set("0 pedidos pendientes")
        self.status_var.set("")
        self.last_summary = None
        self.coverage_var.set("Cobertura precio orientativo: 0,00%")
        self.summary_var.set("")

    def eliminar_calculos_guardados(self) -> None:
        filters = self._get_filters()
        has_filters = any(bool(v) for v in filters.values())
        if has_filters:
            msg = (
                "Se van a eliminar los precios orientativos calculados guardados para el filtro actual. "
                "Esta acción no modifica DBPedidos.sqlite. ¿Deseas continuar?"
            )
        else:
            msg = "No hay filtros aplicados. Esto eliminará TODOS los cálculos guardados. ¿Deseas continuar?"

        confirmed = messagebox.askyesno("Confirmar eliminación", msg, parent=self.winfo_toplevel())
        if not confirmed:
            return

        deleted = self.service.eliminar_calculos_guardados(filters)
        self.rows = []
        self.table.set_rows([])
        self.counter_var.set("0 pedidos pendientes")
        self.last_summary = None
        self.coverage_var.set("Cobertura precio orientativo: 0,00%")
        self.summary_var.set("")
        self.status_var.set(f"Cálculos eliminados: {deleted}")

    def _render_summary(self, summary: dict) -> None:
        total = int(summary.get("total", 0))
        cobertura = float(summary.get("cobertura", 0))
        self.coverage_var.set(f"Cobertura precio orientativo: {cobertura:.2f}%".replace(".", ","))
        lines = [
            f"Líneas analizadas: {total:,}".replace(",", "."),
            f"Con precio original: {int(summary.get('con_original', 0)):,}".replace(",", "."),
            f"Estimadas guardadas: {int(summary.get('estimadas_guardadas', 0)):,}".replace(",", "."),
            f"Sin precio: {int(summary.get('sin_precio', 0)):,}".replace(",", "."),
            f"Errores maestro: {int(summary.get('errores_maestro', 0)):,}".replace(",", "."),
            f"Cobertura total: {cobertura:.2f}%".replace(".", ","),
        ]
        self.summary_var.set("\n".join(lines))

    def ver_resumen(self) -> None:
        if not self.last_summary:
            self.status_var.set("Primero calcula estimaciones para ver el resumen.")
            return

        win = tk.Toplevel(self)
        win.title("Resumen de estimaciones")
        win.geometry("640x420")
        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        table = DataTable(frame, columns=["Método", "Cantidad", "Porcentaje"])
        table.grid(row=0, column=0, sticky="nsew")
        rows = []
        for item in self.last_summary.get("resumen", []):
            rows.append(
                {
                    "Método": item.get("metodo", ""),
                    "Cantidad": int(item.get("cantidad", 0)),
                    "Porcentaje": f'{float(item.get("porcentaje", 0)):.2f}%',
                }
            )
        table.set_rows(rows)

    def ver_resumen_semanal(self) -> None:
        if not self.rows:
            self.status_var.set("No hay datos para generar resumen semanal.")
            return
        semanal = self.service.generar_resumen_semanal(self.rows)
        if not semanal:
            self.summary_var.set("Sin datos semanales")
            return
        lines = []
        for row in semanal[:12]:
            cov = float(row.get("Cobertura %", 0))
            color = "🟢" if cov >= 80 else ("🟡" if cov >= 50 else "🔴")
            lines.append(
                f"{color} Sem {row.get('Semana','')}: pedidos={row.get('Total líneas',0)} | kg={float(row.get('Kg',0)):,.0f} | cobertura={cov:.2f}% | sin precio={row.get('Sin precio',0)} | importe={float(row.get('Importe afectado',0)):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            )
        self.summary_var.set("\n".join(lines))

    def _save_filters(self) -> None:
        self.FILTERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with self.FILTERS_FILE.open("w", encoding="utf-8") as f:
            json.dump(self._get_filters(), f, ensure_ascii=False, indent=2)

    def _load_filters(self) -> None:
        if not self.FILTERS_FILE.exists():
            self.filter_widgets["estado_precio"].set_selected(["TODOS"])
            return
        try:
            data = json.loads(self.FILTERS_FILE.read_text(encoding="utf-8"))
            for key in self.FILTER_KEYS:
                raw = data.get(key, [])
                if isinstance(raw, str):
                    raw = [raw] if raw.strip() else []
                self.filter_widgets[key].set_selected(raw)
        except Exception:
            self.filter_widgets["estado_precio"].set_selected(["TODOS"])
