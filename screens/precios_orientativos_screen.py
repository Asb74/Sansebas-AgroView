import tkinter as tk
from tkinter import messagebox, ttk

from db.connection import db_exists, get_db_path
from services.precios_orientativos_service import PreciosOrientativosService
from widgets.data_table import DataTable
from widgets.screen_header import ScreenHeader


class PreciosOrientativosScreen(ttk.Frame):
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
    ]

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.service = PreciosOrientativosService()
        self.rows: list[dict] = []

        self.filters = {
            "campana": tk.StringVar(),
            "cultivo": tk.StringVar(),
            "empresa": tk.StringVar(),
            "semana": tk.StringVar(),
            "cliente": tk.StringVar(),
            "var_coop": tk.StringVar(),
        }
        self.status_var = tk.StringVar(value="")
        self.counter_var = tk.StringVar(value="0 pedidos pendientes")
        self.coverage_var = tk.StringVar(value="Cobertura precio orientativo: 0,00%")
        self.summary_var = tk.StringVar(value="")
        self.last_summary: dict | None = None

        self._build_ui()
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
        ]
        for idx, (label, key) in enumerate(fields):
            ttk.Label(filters, text=label).grid(row=(idx // 3) * 2, column=idx % 3, padx=6, sticky="w")
            ttk.Entry(filters, textvariable=self.filters[key], width=24).grid(
                row=(idx // 3) * 2 + 1, column=idx % 3, padx=6, pady=(0, 8), sticky="ew"
            )
            filters.grid_columnconfigure(idx % 3, weight=1)

        actions = ttk.Frame(filters)
        actions.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Button(actions, text="Buscar pendientes", command=self.buscar_pendientes).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Recalcular desde cero", command=self.recalcular_desde_cero).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Calcular estimaciones", command=self.calcular_estimaciones).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Guardar estimaciones", command=self.guardar_estimaciones).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Eliminar cálculos guardados del filtro", command=self.eliminar_calculos_guardados).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Ver resumen", command=self.ver_resumen).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Limpiar", command=self.limpiar).pack(side="left")

        summary_frame = ttk.LabelFrame(self, text="Resumen de cobertura", padding=8)
        summary_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(summary_frame, textvariable=self.coverage_var, style="KPI.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(summary_frame, textvariable=self.summary_var, justify="left").grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.table = DataTable(self, columns=self.TABLE_COLUMNS)
        self.table.grid(row=3, column=0, sticky="nsew")

        ttk.Label(self, textvariable=self.counter_var, style="KPI.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Label(self, textvariable=self.status_var, foreground="#b00020").grid(row=5, column=0, sticky="w", pady=(4, 0))

    def _get_filters(self) -> dict[str, str]:
        return {k: v.get().strip() for k, v in self.filters.items()}

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
        for var in self.filters.values():
            var.set("")
        self.rows = []
        self.table.set_rows([])
        self.counter_var.set("0 pedidos pendientes")
        self.status_var.set("")
        self.last_summary = None
        self.coverage_var.set("Cobertura precio orientativo: 0,00%")
        self.summary_var.set("")

    def eliminar_calculos_guardados(self) -> None:
        filters = self._get_filters()
        has_filters = any(str(v or "").strip() for v in filters.values())
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

        pretty_names = {
            "ORIGINAL": "Original/directo",
            "MISMA_SEMANA_GCONF_CALIBREU": "Misma semana grupo+calibre",
            "SEMANA_ANTERIOR_GCONF_CALIBREU": "Semana anterior grupo+calibre",
            "SEMANA_POSTERIOR_GCONF_CALIBREU": "Semana posterior grupo+calibre",
            "MISMA_SEMANA_PROMEDIO_GRUPO_Y_CALIBRE": "Misma semana promedio grupo+calibre",
            "SEMANA_ANTERIOR_PROMEDIO_GRUPO_Y_CALIBRE": "Semana anterior promedio grupo+calibre",
            "SEMANA_POSTERIOR_PROMEDIO_GRUPO_Y_CALIBRE": "Semana posterior promedio grupo+calibre",
            "FALLBACK_FLEXIBLE_CALIBRE_Y_GRUPO": "Fallback flexible calibre+grupo",
            "FALLBACK_FLEXIBLE_SOLO_CALIBREU": "Solo calibre",
            "FALLBACK_FLEXIBLE_SOLO_GRUPO": "Solo grupo",
            "SIN_DATOS": "Sin datos",
            "ERROR_MAESTRO_CONFECCION": "Error maestro confección",
            "ERROR_MAESTRO_CALIBRE": "Error maestro calibre",
        }

        lines = [f"Total pedidos: {total:,}".replace(",", ".")]
        for item in summary.get("resumen", []):
            qty = int(item.get("cantidad", 0))
            if qty == 0:
                continue
            pct = float(item.get("porcentaje", 0))
            method = str(item.get("metodo", ""))
            label = pretty_names.get(method, method)
            lines.append(f"{label}: {qty:,} ({pct:.2f}%)".replace(",", ".").replace(".", ",", 1))
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
