import tkinter as tk
from tkinter import ttk


class HomeScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, on_open_pedidos, on_open_boa_comercial, on_open_precios_orientativos, on_open_planificacion_diaria) -> None:
        super().__init__(master, padding=24)
        self.on_open_pedidos = on_open_pedidos
        self.on_open_boa_comercial = on_open_boa_comercial
        self.on_open_precios_orientativos = on_open_precios_orientativos
        self.on_open_planificacion_diaria = on_open_planificacion_diaria

        ttk.Label(self, text="Sansebas AgroView", style="Title.TLabel").pack(pady=(20, 8))
        ttk.Label(self, text="Dashboard agrícola de campañas", style="Subtitle.TLabel").pack(pady=(0, 24))

        ttk.Button(
            self,
            text="Ver pedidos",
            style="Dashboard.TButton",
            command=self.on_open_pedidos,
        ).pack(ipadx=20, ipady=12, pady=(0, 14))

        ttk.Button(
            self,
            text="BOA Comercial",
            style="Dashboard.TButton",
            command=self.on_open_boa_comercial,
        ).pack(ipadx=20, ipady=12, pady=(0, 14))

        ttk.Button(
            self,
            text="Revisar precios orientativos",
            style="Dashboard.TButton",
            command=self.on_open_precios_orientativos,
        ).pack(ipadx=20, ipady=12)

        ttk.Button(
            self,
            text="Planificación diaria",
            style="Dashboard.TButton",
            command=self.on_open_planificacion_diaria,
        ).pack(ipadx=20, ipady=12, pady=(14, 0))


