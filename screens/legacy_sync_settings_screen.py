import tkinter as tk
import threading
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.legacy_sync_service import CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE, LegacySyncService
from services.runtime_database_service import RuntimeDatabaseService
from services.update_orchestrator_service import UpdateOrchestratorService
from widgets.screen_header import ScreenHeader


class LegacySyncSettingsScreen(ttk.Frame):
    columns = ("Nombre", "AccessPath", "AccessTable", "SqlitePath", "SqliteTable", "Modo", "Activa", "UltimaActualizacion", "UltimoResultado")

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=10)
        self.on_back = on_back
        self.service = LegacySyncService()
        self.update_orchestrator = UpdateOrchestratorService(legacy_sync_service=self.service)
        self.action_buttons: list[ttk.Button] = []
        self.tree: ttk.Treeview
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        ScreenHeader(self, title="Configuración", subtitle="Actualización tablas legacy", on_back=self.on_back).grid(row=0, column=0, sticky="ew")
        self.tree = ttk.Treeview(self, columns=self.columns, show="headings", height=16)
        for col in self.columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=130, anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew", pady=8)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, sticky="ew")
        actions = [
            ("Añadir", self._add), ("Editar", self._edit), ("Eliminar", self._delete), ("Probar lectura", self._test),
            ("Actualizar seleccionada", self._sync_selected), ("Actualizar activas", self._sync_active),
            ("Actualizar foto local", self._update_runtime_snapshot), ("Actualizar todo", self._update_all), ("Ver log", self._show_log),
            ("Copiar comando", self._copy_command),
            ("Crear configuración planificación por defecto", self._create_defaults),
        ]
        for i, (label, cmd) in enumerate(actions):
            button = ttk.Button(btns, text=label, command=cmd)
            button.grid(row=0, column=i, padx=4, pady=4, sticky="w")
            self.action_buttons.append(button)

    def _load(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.service.get_settings():
            self.tree.insert("", "end", iid=str(row["Id"]), values=tuple(row.get(c, "") for c in self.columns))

    def _selected_id(self) -> int | None:
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _form_dialog(self, initial: dict | None = None) -> dict | None:
        data = dict(initial or {})
        win = tk.Toplevel(self)
        win.title("Configuración legacy")
        vars = {}
        fields = ["Nombre", "AccessPath", "AccessTable", "SqlitePath", "SqliteTable", "Modo", "Observaciones"]
        filter_fields = [
            "FiltroCampanaModo", "FiltroCampanaCampo", "FiltroCampanaTipo", "FiltroCampanaValorOrigen", "FiltroCampanaValorFijo",
            "FiltroRelacionTabla", "FiltroRelacionCampoLocal", "FiltroRelacionCampoRemoto", "FiltroRelacionCampoCampana", "FiltroRelacionTipoCampana",
        ]
        for i, f in enumerate(fields):
            ttk.Label(win, text=f).grid(row=i, column=0, sticky="w", padx=6, pady=4)
            vars[f] = tk.StringVar(value=str(data.get(f, "REEMPLAZAR_TABLA" if f == "Modo" else "")))
            if f == "Modo":
                ttk.Combobox(win, textvariable=vars[f], values=["REEMPLAZAR_TABLA", "CREAR_O_REEMPLAZAR", "PLANIFICACION_HOY_EN_ADELANTE"], width=67, state="readonly").grid(row=i, column=1, sticky="ew", padx=6, pady=4)
            else:
                ttk.Entry(win, textvariable=vars[f], width=70).grid(row=i, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(
            win,
            text="Crear/Reemplazar tabla: Borra la tabla destino si existe y la crea de nuevo desde Access. Si no existe, la crea.",
            foreground="#555",
            wraplength=700,
            justify="left",
        ).grid(row=8, column=1, sticky="w", padx=6, pady=(0, 6))
        activa = tk.IntVar(value=int(data.get("Activa", 1)))
        ttk.Checkbutton(win, text="Activa", variable=activa).grid(row=len(fields), column=1, sticky="w", padx=6)

        filter_start = len(fields) + 2
        ttk.Label(win, text="Filtro campaña", font=("TkDefaultFont", 10, "bold")).grid(row=filter_start, column=0, sticky="w", padx=6, pady=(12, 4))
        filtro_activo = tk.IntVar(value=int(data.get("FiltroActivo", 0) or 0))
        ttk.Checkbutton(win, text="Filtro activo", variable=filtro_activo).grid(row=filter_start, column=1, sticky="w", padx=6, pady=(12, 4))
        for offset, f in enumerate(filter_fields, start=1):
            row_idx = filter_start + offset
            ttk.Label(win, text=f).grid(row=row_idx, column=0, sticky="w", padx=6, pady=4)
            default = ""
            if f == "FiltroCampanaModo":
                default = "NINGUNO"
            elif f in {"FiltroCampanaTipo", "FiltroRelacionTipoCampana"}:
                default = "TEXTO"
            elif f == "FiltroCampanaValorOrigen":
                default = "CAMPANA_ACTIVA"
            vars[f] = tk.StringVar(value=str(data.get(f, default) or default))
            if f == "FiltroCampanaModo":
                ttk.Combobox(win, textvariable=vars[f], values=["NINGUNO", "DIRECTO", "PREFIJO", "RELACION"], width=67, state="readonly").grid(row=row_idx, column=1, sticky="ew", padx=6, pady=4)
            elif f in {"FiltroCampanaTipo", "FiltroRelacionTipoCampana"}:
                ttk.Combobox(win, textvariable=vars[f], values=["TEXTO", "ENTERO"], width=67, state="readonly").grid(row=row_idx, column=1, sticky="ew", padx=6, pady=4)
            elif f == "FiltroCampanaValorOrigen":
                ttk.Combobox(win, textvariable=vars[f], values=["CAMPANA_ACTIVA", "FIJO"], width=67, state="readonly").grid(row=row_idx, column=1, sticky="ew", padx=6, pady=4)
            else:
                ttk.Entry(win, textvariable=vars[f], width=70).grid(row=row_idx, column=1, sticky="ew", padx=6, pady=4)
        ttk.Button(win, text="Buscar Access...", command=lambda: vars["AccessPath"].set(filedialog.askopenfilename(filetypes=[("Access MDB", "*.mdb"), ("Todos", "*.*")]))).grid(row=1, column=2)
        ttk.Button(win, text="Buscar SQLite...", command=lambda: vars["SqlitePath"].set(filedialog.askopenfilename(filetypes=[("SQLite", "*.sqlite *.db"), ("Todos", "*.*")]))).grid(row=3, column=2)
        ttk.Button(win, text="Usar SQLite por defecto", command=lambda: vars["SqlitePath"].set(self.service.default_sqlite_path())).grid(row=3, column=3)
        out = {}

        def save() -> None:
            for f in fields:
                out[f] = vars[f].get().strip()
            out["Activa"] = int(activa.get())
            out["FiltroActivo"] = int(filtro_activo.get())
            for f in filter_fields:
                out[f] = vars[f].get().strip()
            win.destroy()

        ttk.Button(win, text="Guardar", command=save).grid(row=filter_start + len(filter_fields) + 1, column=1, sticky="e", padx=6, pady=8)
        win.transient(self)
        win.grab_set()
        self.wait_window(win)
        return out or None

    def _add(self) -> None:
        data = self._form_dialog()
        if not data:
            return
        try:
            self.service.add_setting(data)
            self._load()
            if not any(str(r.get("Nombre", "")).strip() == data.get("Nombre", "") for r in self.service.get_settings()):
                messagebox.showerror("Error", "No se pudo persistir la configuración legacy.", parent=self)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _edit(self) -> None:
        sid = self._selected_id()
        if not sid:
            return
        current = next((r for r in self.service.get_settings() if int(r["Id"]) == sid), None)
        if not current:
            return
        data = self._form_dialog(current)
        if not data:
            return
        try:
            self.service.update_setting(sid, data)
            self._load()
            updated = next((r for r in self.service.get_settings() if int(r["Id"]) == sid), None)
            if not updated:
                messagebox.showerror("Error", "No se pudo guardar la edición de configuración legacy.", parent=self)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _delete(self) -> None:
        sid = self._selected_id()
        if sid and messagebox.askyesno("Confirmar", "¿Eliminar configuración?", parent=self):
            self.service.delete_setting(sid)
            self._load()

    def _test(self) -> None:
        sid = self._selected_id()
        if not sid:
            return
        ok, msg = self.service.test_access_table(sid)
        (messagebox.showinfo if ok else messagebox.showerror)("Prueba lectura", msg, parent=self)

    def _sync_selected(self) -> None:
        sid = self._selected_id()
        if not sid:
            return
        self._run_update_action("Actualizar seleccionada", lambda: self.update_orchestrator.update_selected_legacy_then_snapshot(sid), self._format_single_sync_result)

    def _sync_active(self) -> None:
        if self.service.get_central_sqlite_blocked_settings(active_only=True):
            self._show_central_sqlite_block_warning()
            return
        self._run_update_action("Actualizar activas", lambda: self.update_orchestrator.update_legacy_active(snapshot_after=True), self._format_legacy_result)

    def _update_runtime_snapshot(self) -> None:
        self._run_update_action("Actualizar foto local", self.update_orchestrator.update_runtime_snapshot, self._format_runtime_result)

    def _update_all(self) -> None:
        self._run_update_action("Actualizar todo", self.update_orchestrator.update_all, self._format_all_result)

    def _show_central_sqlite_block_warning(self) -> None:
        messagebox.showwarning(
            "Operación bloqueada",
            f"Esta operación está bloqueada por seguridad porque modificaría la SQLite central.\n\n{CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE}",
            parent=self,
        )

    def _run_update_action(self, title: str, action, formatter) -> None:
        messagebox.showinfo(title, f"Inicio de actualización: {title}.", parent=self)
        self._set_actions_state("disabled")

        def worker() -> None:
            result = action()
            self.after(0, lambda: self._finish_update_action(title, result, formatter))

        threading.Thread(target=worker, name=f"{title}Worker", daemon=True).start()

    def _finish_update_action(self, title: str, result: dict, formatter) -> None:
        self._set_actions_state("normal")
        self._load()
        ok, message = formatter(result)
        (messagebox.showinfo if ok else messagebox.showwarning)(title, message, parent=self)

    def _set_actions_state(self, state: str) -> None:
        for button in self.action_buttons:
            button.configure(state=state)

    @staticmethod
    def _format_single_sync_result(result: dict) -> tuple[bool, str]:
        ok = bool(result.get("ok"))
        legacy = result.get("legacy", {})
        message = result.get("message") or legacy.get("message", "")
        if ok:
            return True, f"Resultado final: actualización seleccionada correcta.\n{message}\nSe ha creado una nueva foto local."
        return False, f"Resultado final: actualización seleccionada fallida.\n{message}\nRevisa el log."

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
        blocked = bool(result.get("blocked"))
        ok = fail_count == 0 and not result.get("error") and not blocked
        if blocked:
            return False, (
                "Resultado final: actualización legacy detenida/bloqueada.\n"
                "Esta operación está bloqueada por seguridad porque modificaría la SQLite central.\n"
                f"{CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE}"
            )
        runtime = result.get("runtime") or {}
        if runtime:
            runtime_ok = bool(runtime.get("ok"))
            ok = ok and runtime_ok
            runtime_msg = RuntimeDatabaseService.SUCCESS_MESSAGE if runtime_ok else RuntimeDatabaseService.WARNING_MESSAGE
            suffix = "" if ok else "\nHay errores; revisa el log."
            return ok, f"Resultado final: tablas legacy activas procesadas.\nCorrectos: {ok_count}\nFallidos: {fail_count}\nTotal: {total}\n{runtime_msg}{suffix}"
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

    def _show_log(self) -> None:
        logs = self.service.get_logs(200)
        win = tk.Toplevel(self)
        win.title("Log sincronización legacy")
        txt = tk.Text(win, width=160, height=35)
        txt.pack(fill="both", expand=True)
        for log in logs:
            txt.insert("end", f"[{log['Inicio']}] {log['Nombre']} OK={log['Ok']} Export={log['FilasExportadas']} Import={log['FilasImportadas']} Msg={log['Mensaje']} Err={log['Error']}\n")

    def _copy_command(self) -> None:
        sid = self._selected_id()
        if not sid:
            return
        ok, command = self.service.build_command_preview(sid)
        if not ok:
            messagebox.showerror("Copiar comando", command, parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(command)
        messagebox.showinfo("Copiar comando", "Comando copiado al portapapeles.", parent=self)

    def _create_defaults(self) -> None:
        existing_access = self.service.resolve_default_access_path_for_planificacion()
        access = existing_access or filedialog.askopenfilename(filetypes=[("Access MDB", "*.mdb"), ("Todos", "*.*")])
        if not access:
            messagebox.showerror("Error", "No se puede crear configuración por defecto con AccessPath vacío.", parent=self)
            return
        try:
            created_or_updated = self.service.create_or_update_planificacion_defaults(access)
            self._load()
            messagebox.showinfo("Configuración", f"Configuraciones creadas/actualizadas: {created_or_updated}", parent=self)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)
