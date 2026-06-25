import tkinter as tk
import threading
from tkinter import filedialog, messagebox, ttk

from services.legacy_sync_service import CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE, LegacySyncService
from services.runtime_database_service import RuntimeDatabaseService
from services.update_orchestrator_service import UpdateOrchestratorService
from widgets.screen_header import ScreenHeader


class LegacySyncSettingsScreen(ttk.Frame):
    columns = ("Estado", "Nombre", "Grupo", "OrigenTipo", "AccessPath", "AccessTable", "DestinoTipo", "SqlitePath", "SqliteTable", "FiltroModo", "FiltroCampo", "FiltroTipo", "ReemplazoModo", "Activa", "UltimaActualizacion", "UltimoResultado")

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=10)
        self.on_back = on_back
        self.service = LegacySyncService()
        self.update_orchestrator = UpdateOrchestratorService(legacy_sync_service=self.service)
        self.action_buttons: list[ttk.Button] = []
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        ScreenHeader(self, title="Configuración", subtitle="Gestor de sincronizaciones", on_back=self.on_back).grid(row=0, column=0, sticky="ew")
        xscroll = ttk.Scrollbar(self, orient="horizontal")
        yscroll = ttk.Scrollbar(self, orient="vertical")
        self.tree = ttk.Treeview(self, columns=self.columns, show="headings", height=16, xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        xscroll.configure(command=self.tree.xview); yscroll.configure(command=self.tree.yview)
        for col in self.columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150 if col.endswith("Path") else 120, anchor="w")
        self.tree.grid(row=1, column=0, sticky="nsew", pady=8)
        yscroll.grid(row=1, column=1, sticky="ns"); xscroll.grid(row=2, column=0, sticky="ew")
        self.grid_rowconfigure(1, weight=1); self.grid_columnconfigure(0, weight=1)
        btns = ttk.Frame(self); btns.grid(row=3, column=0, sticky="ew")
        actions = [("Añadir", self._add), ("Editar", self._edit), ("Eliminar", self._delete), ("Probar lectura", self._test), ("Probar configuración", self._test_configuration), ("Analizar origen", self._analyze_origin), ("Analizar destino", self._analyze_destination), ("Actualizar seleccionada", self._sync_selected), ("Actualizar activas", self._sync_active), ("Actualizar foto local", self._update_runtime_snapshot), ("Actualizar todo", self._update_all), ("Ver log", self._show_log), ("Copiar comando", self._copy_command), ("Crear configuración planificación por defecto", self._create_defaults)]
        for i, (label, cmd) in enumerate(actions):
            b = ttk.Button(btns, text=label, command=cmd); b.grid(row=i//7, column=i%7, padx=4, pady=4, sticky="w"); self.action_buttons.append(b)

    def _load(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.service.get_settings():
            vals = []
            for c in self.columns:
                vals.append("✅" if c == "Estado" and int(row.get("Activa", 0) or 0) else ("⏸" if c == "Estado" else row.get(c, "")))
            self.tree.insert("", "end", iid=str(row["Id"]), values=tuple(vals))

    def _selected_id(self) -> int | None:
        sel = self.tree.selection(); return int(sel[0]) if sel else None

    def _form_dialog(self, initial: dict | None = None) -> dict | None:
        data = dict(initial or {})
        win = tk.Toplevel(self); win.title("Gestor de sincronizaciones")
        canvas = tk.Canvas(win, width=980, height=720); scroll = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas, padding=10); frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw"); canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True); scroll.pack(side="right", fill="y")
        vars: dict[str, tk.StringVar] = {}
        checks: dict[str, tk.IntVar] = {}
        combos: dict[str, ttk.Combobox] = {}
        fields = ["Nombre", "Grupo", "Descripcion", "OrigenTipo", "AccessPath", "AccessTable", "DestinoTipo", "SqlitePath", "SqliteTable", "Modo", "FiltroModo", "FiltroCampo", "FiltroTipo", "FiltroValorOrigen", "FiltroValorFijo", "ReemplazoModo", "OrdenEjecucion"]
        defaults = {"OrigenTipo":"ACCESS", "DestinoTipo":"SQLITE", "Modo":"REEMPLAZAR_TABLA", "FiltroModo":"NINGUNO", "FiltroTipo":"TEXTO", "FiltroValorOrigen":"CAMPANA_ACTIVA", "ReemplazoModo":"TABLA_COMPLETA", "OrdenEjecucion":"100"}
        def section(title, row): ttk.Label(frame, text=title, font=("TkDefaultFont", 10, "bold")).grid(row=row, column=0, sticky="w", pady=(12, 4)); return row+1
        row=0
        for title, group in [("A) General", ["Nombre","Grupo","Descripcion","OrdenEjecucion"]), ("B) Origen", ["OrigenTipo","AccessPath","AccessTable"]), ("C) Destino", ["DestinoTipo","SqlitePath","SqliteTable"]), ("D) Filtro campaña", ["FiltroModo","FiltroCampo","FiltroTipo","FiltroValorOrigen","FiltroValorFijo"]), ("E) Reemplazo", ["Modo","ReemplazoModo"])]:
            row=section(title,row)
            for f in group:
                ttk.Label(frame, text=f).grid(row=row, column=0, sticky="w", padx=6, pady=3)
                vars[f]=tk.StringVar(value=str(data.get(f, data.get({"FiltroModo":"FiltroCampanaModo","FiltroCampo":"FiltroCampanaCampo","FiltroTipo":"FiltroCampanaTipo","FiltroValorOrigen":"FiltroCampanaValorOrigen","FiltroValorFijo":"FiltroCampanaValorFijo"}.get(f,""), defaults.get(f,""))) or defaults.get(f,"")))
                values = []
                if f=="OrigenTipo": values=["ACCESS"]
                elif f=="DestinoTipo": values=["SQLITE"]
                elif f=="Modo": values=["REEMPLAZAR_TABLA","CREAR_O_REEMPLAZAR","PLANIFICACION_HOY_EN_ADELANTE"]
                elif f=="FiltroModo": values=["NINGUNO","DIRECTO","PREFIJO_TEXTO","PREFIJO_NUMERICO","RELACION"]
                elif f=="FiltroTipo": values=["TEXTO","ENTERO"]
                elif f=="FiltroValorOrigen": values=["CAMPANA_ACTIVA","FIJO"]
                elif f=="ReemplazoModo": values=["TABLA_COMPLETA","PARTICION","SOLO_INSERTAR","MERGE"]
                if f in {"AccessTable","SqliteTable","FiltroCampo"} or values:
                    combos[f]=ttk.Combobox(frame, textvariable=vars[f], values=values, width=80, state="normal" if f in {"AccessTable","SqliteTable","FiltroCampo"} else "readonly")
                    combos[f].grid(row=row, column=1, sticky="ew", padx=6, pady=3)
                else:
                    ttk.Entry(frame, textvariable=vars[f], width=83).grid(row=row, column=1, sticky="ew", padx=6, pady=3)
                if f=="AccessPath": ttk.Button(frame, text="Buscar", command=lambda: vars["AccessPath"].set(filedialog.askopenfilename(filetypes=[("Access MDB", "*.mdb *.accdb"), ("Todos", "*.*")]))).grid(row=row,column=2)
                if f=="SqlitePath": ttk.Button(frame, text="Buscar", command=lambda: vars["SqlitePath"].set(filedialog.askopenfilename(filetypes=[("SQLite", "*.sqlite *.db"), ("Todos", "*.*")]))).grid(row=row,column=2)
                row+=1
        for name, label in [("Activa","Activa"),("FiltroActivo","Filtro activo"),("CrearSnapshotDespues","Crear snapshot después"),("LimpiarCacheDespues","Limpiar caché después"),("RequiereConfirmacion","Requiere confirmación")]:
            checks[name]=tk.IntVar(value=int(data.get(name, 1 if name in {"Activa","CrearSnapshotDespues","LimpiarCacheDespues"} else 0) or 0)); ttk.Checkbutton(frame,text=label,variable=checks[name]).grid(row=row,column=1,sticky="w",padx=6,pady=3); row+=1
        access_columns: list[dict] = []
        def load_access_tables():
            try: combos["AccessTable"]["values"] = self.service.list_access_tables(vars["AccessPath"].get()); messagebox.showinfo("Analizar origen", "Tablas Access cargadas.", parent=win)
            except Exception as exc: messagebox.showerror("Analizar origen", str(exc), parent=win)
        def load_access_columns():
            nonlocal access_columns
            try: access_columns=self.service.list_access_columns(vars["AccessPath"].get(), vars["AccessTable"].get()); combos["FiltroCampo"]["values"]=[c["name"] for c in access_columns]; messagebox.showinfo("Analizar origen", "Campos Access cargados.", parent=win)
            except Exception as exc: messagebox.showerror("Analizar origen", str(exc), parent=win)
        def load_sqlite_tables():
            try: combos["SqliteTable"]["values"] = self.service.list_sqlite_tables(vars["SqlitePath"].get()); messagebox.showinfo("Analizar destino", "Tablas SQLite cargadas.", parent=win)
            except Exception as exc: messagebox.showerror("Analizar destino", str(exc), parent=win)
        def load_sqlite_columns():
            try: cols=self.service.list_sqlite_columns(vars["SqlitePath"].get(), vars["SqliteTable"].get()); messagebox.showinfo("Analizar destino", "Campos SQLite:\n"+"\n".join(c["name"] for c in cols), parent=win)
            except Exception as exc: messagebox.showerror("Analizar destino", str(exc), parent=win)
        def suggest():
            nonlocal access_columns
            if not access_columns: load_access_columns()
            sug=self.service.suggest_filter(access_columns); checks["FiltroActivo"].set(int(sug["FiltroActivo"])); vars["FiltroModo"].set(sug["FiltroModo"]); vars["FiltroCampo"].set(sug["FiltroCampo"]); vars["FiltroTipo"].set(sug["FiltroTipo"]); messagebox.showinfo("Sugerir filtro", f"Sugerencia aplicada: {sug}", parent=win)
        def preview():
            info=self.service.preview_configuration(collect()); messagebox.showinfo("Probar configuración", "\n".join([f"SQL Access: {info['access_sql']}", f"Campaña usada: {info['campana'] or 'N/D'}", f"Filas estimadas: {info['estimated_rows'] or 'No calculado'}", f"Destino SQLite: {info['sqlite_destino']}", f"Modo reemplazo: {info['reemplazo_modo']}", f"Crear snapshot: {info['crear_snapshot']}", f"Limpiar caché: {info['limpiar_cache']}"]), parent=win)
        tools=ttk.Frame(frame); tools.grid(row=row,column=1,sticky="w",pady=8)
        for i,(txt,cmd) in enumerate([("Cargar tablas",load_access_tables),("Analizar campos",load_access_columns),("Cargar tablas destino",load_sqlite_tables),("Analizar destino",load_sqlite_columns),("Sugerir filtro",suggest),("Probar configuración",preview)]): ttk.Button(tools,text=txt,command=cmd).grid(row=0,column=i,padx=3)
        row+=1; out={}
        def collect():
            payload={f:v.get().strip() for f,v in vars.items()}; payload.update({k:int(v.get()) for k,v in checks.items()})
            payload["Observaciones"]=payload.get("Descripcion",""); return payload
        def save(): out.update(collect()); win.destroy()
        ttk.Button(frame,text="Guardar",command=save).grid(row=row,column=1,sticky="e",pady=10)
        win.transient(self); win.grab_set(); self.wait_window(win); return out or None

    def _selected_setting(self):
        sid=self._selected_id(); return next((r for r in self.service.get_settings() if int(r["Id"])==sid), None) if sid else None
    def _add(self):
        data=self._form_dialog();
        if data:
            try: self.service.add_setting(data); self._load()
            except Exception as exc: messagebox.showerror("Error", str(exc), parent=self)
    def _edit(self):
        sid=self._selected_id(); current=self._selected_setting()
        if sid and current:
            data=self._form_dialog(current)
            if data:
                try: self.service.update_setting(sid,data); self._load()
                except Exception as exc: messagebox.showerror("Error", str(exc), parent=self)
    def _delete(self):
        sid=self._selected_id()
        if sid and messagebox.askyesno("Confirmar","¿Eliminar configuración?",parent=self): self.service.delete_setting(sid); self._load()
    def _test(self):
        sid=self._selected_id();
        if sid: ok,msg=self.service.test_access_table(sid); (messagebox.showinfo if ok else messagebox.showerror)("Prueba lectura",msg,parent=self)
    def _test_configuration(self):
        setting=self._selected_setting()
        if setting:
            info=self.service.preview_configuration(setting); messagebox.showinfo("Probar configuración", "\n".join([f"SQL Access: {info['access_sql']}", f"Campaña usada: {info['campana'] or 'N/D'}", f"Filas estimadas: {info['estimated_rows'] or 'No calculado'}", f"Destino SQLite: {info['sqlite_destino']}", f"Modo reemplazo: {info['reemplazo_modo']}", f"Crear snapshot: {info['crear_snapshot']}", f"Limpiar caché: {info['limpiar_cache']}"]), parent=self)
    def _analyze_origin(self):
        s=self._selected_setting()
        if s:
            try: messagebox.showinfo("Analizar origen", "\n".join(self.service.list_access_tables(s.get("AccessPath",""))), parent=self)
            except Exception as exc: messagebox.showerror("Analizar origen", str(exc), parent=self)
    def _analyze_destination(self):
        s=self._selected_setting()
        if s:
            try: messagebox.showinfo("Analizar destino", "\n".join(self.service.list_sqlite_tables(s.get("SqlitePath",""))), parent=self)
            except Exception as exc: messagebox.showerror("Analizar destino", str(exc), parent=self)
    def _sync_selected(self):
        sid=self._selected_id();
        if sid: self._run_update_action("Actualizar seleccionada", lambda: self.update_orchestrator.update_selected_legacy_then_snapshot(sid), self._format_single_sync_result)
    def _sync_active(self):
        if self.service.get_central_sqlite_blocked_settings(active_only=True): return self._show_central_sqlite_block_warning()
        self._run_update_action("Actualizar activas", lambda: self.update_orchestrator.update_legacy_active(snapshot_after=True), self._format_legacy_result)
    def _update_runtime_snapshot(self): self._run_update_action("Actualizar foto local", self.update_orchestrator.update_runtime_snapshot, self._format_runtime_result)
    def _update_all(self): self._run_update_action("Actualizar todo", self.update_orchestrator.update_all, self._format_all_result)
    def _show_central_sqlite_block_warning(self): messagebox.showwarning("Operación bloqueada", f"Esta operación está bloqueada por seguridad porque modificaría la SQLite central.\n\n{CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE}", parent=self)
    def _run_update_action(self,title,action,formatter):
        messagebox.showinfo(title, f"Inicio de actualización: {title}.", parent=self); self._set_actions_state("disabled")
        threading.Thread(target=lambda: self.after(0, lambda r=action(): self._finish_update_action(title,r,formatter)), daemon=True).start()
    def _finish_update_action(self,title,result,formatter): self._set_actions_state("normal"); self._load(); ok,msg=formatter(result); (messagebox.showinfo if ok else messagebox.showwarning)(title,msg,parent=self)
    def _set_actions_state(self,state):
        for b in self.action_buttons: b.configure(state=state)
    @staticmethod
    def _format_single_sync_result(result):
        ok=bool(result.get("ok")); msg=result.get("message") or result.get("legacy",{}).get("message",""); return ok, (f"Resultado final: actualización seleccionada correcta.\n{msg}\nSe ha creado una nueva foto local." if ok else f"Resultado final: actualización seleccionada fallida.\n{msg}\nRevisa el log.")
    @staticmethod
    def _format_runtime_result(result):
        ok=bool(result.get("ok")); return ok, RuntimeDatabaseService.SUCCESS_MESSAGE if ok else (RuntimeDatabaseService.WARNING_MESSAGE if result.get("using_previous_snapshot") else RuntimeDatabaseService.ERROR_MESSAGE)
    @staticmethod
    def _format_legacy_result(result):
        fail=int(result.get("fail_count",0)); blocked=bool(result.get("blocked")); ok=fail==0 and not result.get("error") and not blocked; return ok, f"Resultado final: tablas legacy activas procesadas.\nCorrectos: {result.get('ok_count',0)}\nFallidos: {fail}\nTotal: {result.get('total',0)}" + (f"\n{CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE}" if blocked else "")
    def _format_all_result(self,result):
        a,am=self._format_legacy_result(result.get("legacy",{})); b,bm=self._format_runtime_result(result.get("runtime",{})); return a and b, f"Resultado final: actualización completa.\n\n{am}\n\n{bm}"
    def _show_log(self):
        win=tk.Toplevel(self); win.title("Log sincronización legacy"); txt=tk.Text(win,width=160,height=35); txt.pack(fill="both",expand=True)
        for log in self.service.get_logs(200): txt.insert("end", f"[{log['Inicio']}] {log['Nombre']} OK={log['Ok']} Export={log['FilasExportadas']} Import={log['FilasImportadas']} Msg={log['Mensaje']} Err={log['Error']}\n")
    def _copy_command(self):
        sid=self._selected_id();
        if sid:
            ok,cmd=self.service.build_command_preview(sid)
            if not ok: return messagebox.showerror("Copiar comando",cmd,parent=self)
            self.clipboard_clear(); self.clipboard_append(cmd); messagebox.showinfo("Copiar comando","Comando copiado al portapapeles.",parent=self)
    def _create_defaults(self):
        access=self.service.resolve_default_access_path_for_planificacion() or filedialog.askopenfilename(filetypes=[("Access MDB", "*.mdb *.accdb"), ("Todos", "*.*")])
        if not access: return messagebox.showerror("Error","No se puede crear configuración por defecto con AccessPath vacío.",parent=self)
        try: n=self.service.create_or_update_planificacion_defaults(access); self._load(); messagebox.showinfo("Configuración", f"Configuraciones creadas/actualizadas: {n}", parent=self)
        except Exception as exc: messagebox.showerror("Error",str(exc),parent=self)
