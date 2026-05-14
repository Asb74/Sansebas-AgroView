import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from services.legacy_sync_service import LegacySyncService
from widgets.screen_header import ScreenHeader


class LegacySyncSettingsScreen(ttk.Frame):
    columns = ("Nombre", "AccessPath", "AccessTable", "SqlitePath", "SqliteTable", "Modo", "Activa", "UltimaActualizacion", "UltimoResultado")

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=10)
        self.on_back = on_back
        self.service = LegacySyncService()
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
            ("Actualizar seleccionada", self._sync_selected), ("Actualizar activas", self._sync_active), ("Ver log", self._show_log),
            ("Copiar comando", self._copy_command),
            ("Crear configuración planificación por defecto", self._create_defaults),
        ]
        for i, (label, cmd) in enumerate(actions):
            ttk.Button(btns, text=label, command=cmd).grid(row=0, column=i, padx=4, pady=4, sticky="w")

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
        ttk.Button(win, text="Buscar Access...", command=lambda: vars["AccessPath"].set(filedialog.askopenfilename(filetypes=[("Access MDB", "*.mdb"), ("Todos", "*.*")]))).grid(row=1, column=2)
        ttk.Button(win, text="Buscar SQLite...", command=lambda: vars["SqlitePath"].set(filedialog.askopenfilename(filetypes=[("SQLite", "*.sqlite *.db"), ("Todos", "*.*")]))).grid(row=3, column=2)
        ttk.Button(win, text="Usar SQLite por defecto", command=lambda: vars["SqlitePath"].set(self.service.default_sqlite_path())).grid(row=3, column=3)
        out = {}

        def save() -> None:
            for f in fields:
                out[f] = vars[f].get().strip()
            out["Activa"] = int(activa.get())
            win.destroy()

        ttk.Button(win, text="Guardar", command=save).grid(row=len(fields)+1, column=1, sticky="e", padx=6, pady=8)
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
        ok, msg = self.service.sync_setting(sid)
        self._load()
        (messagebox.showinfo if ok else messagebox.showerror)("Sincronización", msg, parent=self)

    def _sync_active(self) -> None:
        results = self.service.sync_active_settings()
        self._load()
        total = len(results)
        oks = sum(1 for _, ok, _ in results if ok)
        messagebox.showinfo("Sincronización", f"Actualizadas activas: {oks}/{total}", parent=self)

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
