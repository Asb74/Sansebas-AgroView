import tkinter as tk
import threading
from tkinter import messagebox, ttk

from screens.boa_comercial_screen import BOAComercialScreen
from screens.home_screen import HomeScreen
from screens.import_forfait_screen import ImportForfaitScreen
from screens.legacy_sync_settings_screen import LegacySyncSettingsScreen
from screens.map_forfait_screen import MapForfaitScreen
from screens.pedidos_screen import PedidosScreen
from screens.planificacion_diaria_screen import PlanificacionDiariaScreen
from screens.production_settings_screen import ProductionSettingsScreen
from screens.precios_orientativos_screen import PreciosOrientativosScreen
from screens.operational_quality_settings_screen import OperationalQualitySettingsScreen
from screens.ranking_cliente_settings_screen import RankingClienteSettingsScreen
from services.comercial_service import ComercialService
from services.runtime_database_service import RuntimeDatabaseService
from services.update_orchestrator_service import UpdateOrchestratorService
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
        self.comercial_service = ComercialService()
        self.runtime_db_service = RuntimeDatabaseService()
        self.update_orchestrator = UpdateOrchestratorService(runtime_database_service=self.runtime_db_service)
        ok, errors = self.runtime_db_service.prepare_runtime_databases()
        if ok:
            pass
        elif self.runtime_db_service.get_current_snapshot_dir() is not None:
            messagebox.showwarning("AgroView", self.runtime_db_service.WARNING_MESSAGE)
        else:
            messagebox.showerror("AgroView", self.runtime_db_service.ERROR_MESSAGE)
        self.show_home()

    def _setup_menu(self) -> None:
        menubar = tk.Menu(self)
        herramientas = tk.Menu(menubar, tearoff=False)
        herramientas.add_command(label="Importar forfait confección", command=self.show_import_forfait)
        herramientas.add_command(label="Mapear forfait/confecciones", command=self.show_map_forfait)
        herramientas.add_command(label="Configuración ranking clientes", command=self.show_ranking_settings)
        herramientas.add_command(label="Planificación diaria", command=self.show_planificacion_diaria)
        herramientas.add_command(label="Actualización tablas legacy", command=self.show_legacy_sync_settings)
        self.actualizaciones_menu = tk.Menu(herramientas, tearoff=False)
        self.actualizaciones_menu.add_command(label="Actualizar foto local", command=self.update_runtime_snapshot)
        self.actualizaciones_menu.add_command(label="Actualizar tablas legacy activas", command=self.update_legacy_active)
        self.actualizaciones_menu.add_command(label="Actualizar todo", command=self.update_all)
        herramientas.add_cascade(label="Actualizaciones", menu=self.actualizaciones_menu)
        herramientas.add_command(label="Configuración calidad operativa", command=self.show_operational_quality_settings)
        herramientas.add_command(label="Configuración productiva", command=self.show_production_settings)
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
                on_open_planificacion_diaria=self.show_planificacion_diaria,
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

    def show_ranking_settings(self) -> None:
        self._show_screen(RankingClienteSettingsScreen(self.container, service=self.comercial_service, on_back=self.show_home))

    def show_planificacion_diaria(self) -> None:
        self._show_screen(PlanificacionDiariaScreen(self.container, on_back=self.show_home))

    def show_legacy_sync_settings(self) -> None:
        self._show_screen(LegacySyncSettingsScreen(self.container, on_back=self.show_home))

    def show_operational_quality_settings(self) -> None:
        self._show_screen(OperationalQualitySettingsScreen(self.container, on_back=self.show_home))

    def show_production_settings(self) -> None:
        self._show_screen(ProductionSettingsScreen(self.container, on_back=self.show_home))

    def update_runtime_snapshot(self) -> None:
        self._run_update_action("Actualizar foto local", self.update_orchestrator.update_runtime_snapshot, self._format_runtime_result)

    def update_legacy_active(self) -> None:
        self._run_update_action("Actualizar tablas legacy activas", self.update_orchestrator.update_legacy_active, self._format_legacy_result)

    def update_all(self) -> None:
        self._run_update_action("Actualizar todo", self.update_orchestrator.update_all, self._format_all_result)

    def _run_update_action(self, title: str, action, formatter) -> None:
        messagebox.showinfo(title, f"Inicio de actualización: {title}.", parent=self)
        self._set_update_actions_state("disabled")

        def worker() -> None:
            result = action()
            self.after(0, lambda: self._finish_update_action(title, result, formatter))

        threading.Thread(target=worker, name=f"{title}Worker", daemon=True).start()

    def _finish_update_action(self, title: str, result: dict, formatter) -> None:
        self._set_update_actions_state("normal")
        ok, message = formatter(result)
        (messagebox.showinfo if ok else messagebox.showwarning)(title, message, parent=self)

    def _set_update_actions_state(self, state: str) -> None:
        for index in range(3):
            self.actualizaciones_menu.entryconfig(index, state=state)

    @staticmethod
    def _format_runtime_result(result: dict) -> tuple[bool, str]:
        ok = bool(result.get("ok"))
        if ok:
            return True, RuntimeDatabaseService.SUCCESS_MESSAGE
        if result.get("using_previous_snapshot"):
            return False, RuntimeDatabaseService.WARNING_MESSAGE
        return False, RuntimeDatabaseService.ERROR_MESSAGE

    @staticmethod
    def _format_legacy_result(result: dict) -> tuple[bool, str]:
        ok_count = int(result.get("ok_count", 0))
        fail_count = int(result.get("fail_count", 0))
        total = int(result.get("total", ok_count + fail_count))
        ok = fail_count == 0 and not result.get("error")
        suffix = "" if ok else "\nHay errores; revisa el log."
        return ok, f"Resultado final: tablas legacy activas procesadas.\nCorrectos: {ok_count}\nFallidos: {fail_count}\nTotal: {total}{suffix}"

    def _format_all_result(self, result: dict) -> tuple[bool, str]:
        legacy_ok, legacy_msg = self._format_legacy_result(result.get("legacy", {}))
        runtime_ok, runtime_msg = self._format_runtime_result(result.get("runtime", {}))
        ok = legacy_ok and runtime_ok
        if result.get("partial"):
            return (
                False,
                "Resultado final: actualización parcial.\n\n"
                f"{legacy_msg}\n\n"
                f"{runtime_msg}",
            )
        suffix = "" if ok else "\nHay errores; revisa el log."
        return ok, f"Resultado final: actualización completa.\n\n{legacy_msg}\n\n{runtime_msg}{suffix}"

    def _show_screen(self, screen: ttk.Frame) -> None:
        if self.current_screen is not None:
            self.current_screen.destroy()
        self.current_screen = screen
        self.current_screen.grid(row=0, column=0, sticky="nsew")
