import tkinter as tk
from tkinter import ttk

from db.connection import db_exists, get_db_path
from db.pedidos_repository import PedidosRepository
from widgets.data_table import DataTable


class PedidosScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.repo = PedidosRepository()

        self.campana = tk.StringVar()
        self.fecha_desde = tk.StringVar()
        self.fecha_hasta = tk.StringVar()
        self.cliente = tk.StringVar()
        self.var_coop = tk.StringVar()
        self.pais = tk.StringVar()

        self.status_var = tk.StringVar(value="")
        self.kpi_var = {
            "registros": tk.StringVar(value="Registros: 0"),
            "cajas": tk.StringVar(value="Cajas: 0"),
            "neto_cliente": tk.StringVar(value="NetoCliente: 0"),
            "neto_coop": tk.StringVar(value="NetoCoop: 0"),
        }

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ttk.Label(header, text="Ver pedidos", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Volver", command=self.on_back).grid(row=0, column=1, sticky="e")

        filters = ttk.LabelFrame(self, text="Filtros", padding=12)
        filters.grid(row=1, column=0, sticky="ew", pady=(10, 8))

        fields = [
            ("Campaña", self.campana),
            ("Fecha desde (YYYY-MM-DD)", self.fecha_desde),
            ("Fecha hasta (YYYY-MM-DD)", self.fecha_hasta),
            ("Cliente", self.cliente),
            ("Variedad Coop", self.var_coop),
            ("País", self.pais),
        ]

        for idx, (label, var) in enumerate(fields):
            ttk.Label(filters, text=label).grid(row=idx // 3 * 2, column=idx % 3, sticky="w", padx=6)
            ttk.Entry(filters, textvariable=var, width=24).grid(row=idx // 3 * 2 + 1, column=idx % 3, padx=6, pady=(0, 8), sticky="ew")
            filters.grid_columnconfigure(idx % 3, weight=1)

        btns = ttk.Frame(filters)
        btns.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Buscar", command=self.buscar).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Limpiar", command=self.limpiar).pack(side="left")

        kpi_frame = ttk.Frame(self)
        kpi_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        for i, key in enumerate(["registros", "cajas", "neto_cliente", "neto_coop"]):
            ttk.Label(kpi_frame, textvariable=self.kpi_var[key], style="KPI.TLabel").grid(row=0, column=i, padx=(0, 16), sticky="w")

        columns = PedidosRepository.COLUMNS
        self.table = DataTable(self, columns=columns)
        self.table.grid(row=3, column=0, sticky="nsew")

        ttk.Label(self, textvariable=self.status_var, foreground="#b00020").grid(row=4, column=0, sticky="w", pady=(8, 0))

    def buscar(self) -> None:
        if not db_exists():
            self.status_var.set(f"No se encontró la base de datos: {get_db_path()}")
            return

        filters = {
            "campana": self.campana.get().strip(),
            "fecha_desde": self.fecha_desde.get().strip(),
            "fecha_hasta": self.fecha_hasta.get().strip(),
            "cliente": self.cliente.get().strip(),
            "var_coop": self.var_coop.get().strip(),
            "pais": self.pais.get().strip(),
        }
        try:
            rows = self.repo.fetch_pedidos(filters=filters, limit=500)
            self.status_var.set("")
            self.table.set_rows(rows)
            self._update_kpis(rows)
        except ValueError:
            self.status_var.set("Formato de fecha inválido. Usa YYYY-MM-DD.")
        except Exception as exc:
            self.status_var.set(f"Error consultando pedidos: {exc}")

    def limpiar(self) -> None:
        for var in [self.campana, self.fecha_desde, self.fecha_hasta, self.cliente, self.var_coop, self.pais]:
            var.set("")
        self.table.set_rows([])
        self._update_kpis([])
        self.status_var.set("")

    def _update_kpis(self, rows: list[dict]) -> None:
        cajas = sum(self._to_float(r.get("Cajas")) for r in rows)
        neto_cliente = sum(self._to_float(r.get("NetoCliente")) for r in rows)
        neto_coop = sum(self._to_float(r.get("NetoCoop")) for r in rows)

        self.kpi_var["registros"].set(f"Registros: {len(rows)}")
        self.kpi_var["cajas"].set(f"Cajas: {cajas:,.2f}")
        self.kpi_var["neto_cliente"].set(f"NetoCliente: {neto_cliente:,.2f}")
        self.kpi_var["neto_coop"].set(f"NetoCoop: {neto_coop:,.2f}")

    @staticmethod
    def _to_float(value) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
