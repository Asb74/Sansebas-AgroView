import tkinter as tk
from tkinter import ttk

from screens.boa_comercial_screen import BOAComercialScreen
from screens.home_screen import HomeScreen
from screens.import_forfait_screen import ImportForfaitScreen
from screens.map_forfait_screen import MapForfaitScreen
from screens.pedidos_screen import PedidosScreen
from screens.precios_orientativos_screen import PreciosOrientativosScreen
from utils.ui_assets import get_logo


class MainWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Sansebas AgroView")
        self.geometry("1280x720")
        self.minsize(1024, 640)
        self.configure(bg="#f3f6f2")
        self.app_icon = get_logo("32", master=self) or get_logo("64", master=self)
        if self.app_icon is not None:
            self.iconphoto(True, self.app_icon)

        self._setup_styles()
        self._setup_menu()

        self.container = ttk.Frame(self, padding=8)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.current_screen = None
        self.show_home()

    def _setup_menu(self) -> None:
        menubar = tk.Menu(self)
        herramientas = tk.Menu(menubar, tearoff=False)
        herramientas.add_command(label="Importar forfait confección", command=self.show_import_forfait)
        herramientas.add_command(label="Mapear forfait/confecciones", command=self.show_map_forfait)
        menubar.add_cascade(label="Herramientas", menu=herramientas)
        self.config(menu=menubar)

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
        self._show_screen(
            HomeScreen(
                self.container,
                on_open_pedidos=self.show_pedidos,
                on_open_boa_comercial=self.show_boa_comercial,
                on_open_precios_orientativos=self.show_precios_orientativos,
            )
        )

    def show_pedidos(self) -> None:
        self._show_screen(PedidosScreen(self.container, on_back=self.show_home))

    def show_boa_comercial(self) -> None:
        self._show_screen(BOAComercialScreen(self.container, on_back=self.show_home))

    def show_precios_orientativos(self) -> None:
        self._show_screen(PreciosOrientativosScreen(self.container, on_back=self.show_home))

    def show_import_forfait(self) -> None:
        self._show_screen(ImportForfaitScreen(self.container, on_back=self.show_home))

    def show_map_forfait(self) -> None:
        self._show_screen(MapForfaitScreen(self.container, on_back=self.show_home))

    def _show_screen(self, screen: ttk.Frame) -> None:
        if self.current_screen is not None:
            self.current_screen.destroy()
        self.current_screen = screen
        self.current_screen.grid(row=0, column=0, sticky="nsew")
