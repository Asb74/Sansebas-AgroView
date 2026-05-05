import tkinter as tk
from tkinter import ttk

from screens.home_screen import HomeScreen
from screens.pedidos_screen import PedidosScreen


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Sansebas AgroView")
        self.geometry("1280x720")
        self.minsize(1024, 640)
        self.configure(bg="#f3f6f2")

        self._setup_styles()

        self.container = ttk.Frame(self, padding=8)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.current_screen = None
        self.show_home()

    def _setup_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background="#f3f6f2")
        style.configure("TLabel", background="#f3f6f2", foreground="#1f3a2b")
        style.configure("Title.TLabel", font=("Segoe UI", 30, "bold"), foreground="#1b5e20")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 14), foreground="#4e6b53")
        style.configure("Section.TLabel", font=("Segoe UI", 18, "bold"), foreground="#1b5e20")
        style.configure("KPI.TLabel", font=("Segoe UI", 11, "bold"), foreground="#2d4f39")

        style.configure(
            "Dashboard.TButton",
            font=("Segoe UI", 14, "bold"),
            background="#2e7d32",
            foreground="white",
            padding=10,
        )
        style.map("Dashboard.TButton", background=[("active", "#1b5e20")])

    def show_home(self) -> None:
        self._show_screen(HomeScreen(self.container, on_open_pedidos=self.show_pedidos))

    def show_pedidos(self) -> None:
        self._show_screen(PedidosScreen(self.container, on_back=self.show_home))

    def _show_screen(self, screen: ttk.Frame) -> None:
        if self.current_screen is not None:
            self.current_screen.destroy()
        self.current_screen = screen
        self.current_screen.grid(row=0, column=0, sticky="nsew")
