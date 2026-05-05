import tkinter as tk
from tkinter import ttk


class HomeScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, on_open_pedidos) -> None:
        super().__init__(master, padding=24)
        self.on_open_pedidos = on_open_pedidos

        ttk.Label(self, text="Sansebas AgroView", style="Title.TLabel").pack(pady=(20, 8))
        ttk.Label(self, text="Dashboard agrícola de campañas", style="Subtitle.TLabel").pack(pady=(0, 24))

        ttk.Button(
            self,
            text="Ver pedidos",
            style="Dashboard.TButton",
            command=self.on_open_pedidos,
        ).pack(ipadx=20, ipady=12)
