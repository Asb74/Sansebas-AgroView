import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from services.forfait_service import ForfaitService
from widgets.data_table import DataTable


class ImportForfaitScreen(ttk.Frame):
    EDITABLE_COLUMNS = {
        "GrupoConfeccion",
        "NombreConfeccion",
        "Marca",
        "CosteMaterialEurKg",
        "CosteManoObraEurKg",
        "CosteTotalEurKg",
        "Estado",
        "Observaciones",
    }
    TABLE_COLUMNS = [
        "Campaña",
        "Cultivo",
        "IdConfeccion",
        "NombreConfeccion",
        "GrupoConfeccion",
        "Marca",
        "CosteMaterialEurKg",
        "CosteManoObraEurKg",
        "CosteTotalEurKg",
        "Estado",
    ]

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.service = ForfaitService()
        self.file_var = tk.StringVar()
        self.cultivo_var = tk.StringVar(value="CITRICOS")
        self.campana_var = tk.StringVar(value="2025")
        self.sheet_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")
        self.rows: list[dict[str, Any]] = []
        self._edit_entry: tk.Entry | None = None
        self._edit_context: tuple[str, str, int] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Importar forfait confección", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Volver", command=self.on_back).grid(row=0, column=1, sticky="e")

        form = ttk.LabelFrame(self, text="Origen y contexto", padding=12)
        form.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        form.grid_columnconfigure(1, weight=1)

        ttk.Label(form, text="Excel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        ttk.Entry(form, textvariable=self.file_var).grid(row=0, column=1, sticky="ew", pady=(0, 6))
        ttk.Button(form, text="Seleccionar...", command=self._select_file).grid(row=0, column=2, padx=(8, 0), pady=(0, 6))

        ttk.Label(form, text="Cultivo").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        ttk.Entry(form, textvariable=self.cultivo_var, width=20).grid(row=1, column=1, sticky="w", pady=(0, 6))

        ttk.Label(form, text="Campaña").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        ttk.Entry(form, textvariable=self.campana_var, width=20).grid(row=2, column=1, sticky="w", pady=(0, 6))

        ttk.Label(form, text="Hoja").grid(row=3, column=0, sticky="w", padx=(0, 8))
        self.sheet_combo = ttk.Combobox(form, textvariable=self.sheet_var, width=28, state="readonly")
        self.sheet_combo.grid(row=3, column=1, sticky="w")

        actions = ttk.Frame(form)
        actions.grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Button(actions, text="Importar", command=self._import).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Guardar cambios", command=self._save_changes).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Recalcular claves", command=self._recalculate_keys).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Normalizar grupos", command=self._normalize_groups).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Limpiar", command=self._clear).pack(side="left")

        self.table = DataTable(self, columns=self.TABLE_COLUMNS)
        self.table.grid(row=2, column=0, sticky="nsew")
        self.table.tree.bind("<Double-1>", self._start_cell_edit)
        ttk.Label(self, textvariable=self.status_var, foreground="#1b5e20").grid(row=3, column=0, sticky="w", pady=(8, 0))

    def _select_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Seleccionar forfait Excel",
            filetypes=[("Excel", "*.xlsx *.xlsm"), ("Todos los archivos", "*.*")],
        )
        if path:
            self.file_var.set(path)
            try:
                sheets = self.service.fetch_excel_sheet_names(path)
                self.sheet_combo["values"] = sheets
                if sheets:
                    self.sheet_var.set(sheets[0])
            except Exception as exc:
                messagebox.showerror("Excel", str(exc), parent=self)

    def _import(self) -> None:
        file_path = self.file_var.get().strip()
        cultivo = self.cultivo_var.get().strip()
        campana = self.campana_var.get().strip()
        sheet = self.sheet_var.get().strip()
        if not file_path or not sheet:
            messagebox.showwarning("Faltan datos", "Selecciona Excel y hoja.", parent=self)
            return
        try:
            result = self.service.import_related_forfait_excel(file_path, sheet)
        except Exception as exc:
            messagebox.showerror("Importar forfait", str(exc), parent=self)
            return
        self.rows = result["rows"]
        self.table.set_rows(self._map_rows(self.rows))
        self.status_var.set(
            f"Forfait importado. Nuevos: {result['nuevos']}. Actualizados: {result['actualizados']}. "
            f"Revisar: {result['revisar']}. Errores: {result['errores']}."
        )

    def _clear(self) -> None:
        self._destroy_editor()
        self.file_var.set("")
        self.rows = []
        self.table.set_rows([])
        self.status_var.set("")

    def _save_changes(self) -> None:
        if not self.rows:
            self.status_var.set("No hay filas de forfait para guardar.")
            return
        try:
            updated_rows = self.service.fetch_related_forfait(self.cultivo_var.get().strip() or None, self.campana_var.get().strip() or None)
        except Exception as exc:
            messagebox.showerror("Guardar cambios", str(exc), parent=self)
            return
        self.rows = updated_rows
        self.table.set_rows(self._map_rows(self.rows))
        self.status_var.set(f"Datos recargados. Filas: {len(updated_rows)}.")

    def _recalculate_keys(self) -> None:
        if not self.rows:
            self.status_var.set("No hay filas de forfait para recalcular.")
            return
        self.status_var.set("La recarga de claves no aplica al nuevo formato relacionado.")

    def _normalize_groups(self) -> None:
        if not self.rows:
            self.status_var.set("No hay filas de forfait para normalizar.")
            return
        changed = 0
        updated_rows = list(self.rows)
        try:
            for index, row in enumerate(self.rows):
                original = str(row.get("Grupo") or "")
                normalized = self._normalize_group_value(original)
                if normalized == original:
                    continue
                new_row = dict(row)
                updated_rows[index] = self.service.update_related_forfait_field(int(row["Id"]), "Grupo", normalized)
                changed += 1
        except Exception as exc:
            self.rows = updated_rows
            self.table.set_rows(self._map_rows(self.rows))
            messagebox.showerror("Normalizar grupos", str(exc), parent=self)
            return
        self.rows = updated_rows
        self.table.set_rows(self._map_rows(self.rows))
        self.status_var.set(f"Grupos normalizados. Filas modificadas: {changed}.")

    def _start_cell_edit(self, event: tk.Event) -> None:
        self._destroy_editor()
        if self.table.tree.identify("region", event.x, event.y) != "cell":
            return
        row_id = self.table.tree.identify_row(event.y)
        col_id = self.table.tree.identify_column(event.x)
        if not row_id or not col_id:
            return
        column_index = int(col_id.replace("#", "")) - 1
        if column_index < 0 or column_index >= len(self.TABLE_COLUMNS):
            return
        column = self.TABLE_COLUMNS[column_index]
        if column not in self.EDITABLE_COLUMNS:
            return
        row_index = self.table.tree.index(row_id)
        if row_index < 0 or row_index >= len(self.rows):
            return
        bbox = self.table.tree.bbox(row_id, col_id)
        if not bbox:
            return
        x, y, width, height = bbox
        current_value = self.table.tree.set(row_id, column)
        entry = tk.Entry(self.table.tree)
        entry.insert(0, current_value)
        entry.select_range(0, tk.END)
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()
        self._edit_entry = entry
        self._edit_context = (row_id, column, row_index)
        entry.bind("<Return>", self._commit_cell_edit)
        entry.bind("<FocusOut>", self._commit_cell_edit)
        entry.bind("<Escape>", self._cancel_cell_edit)

    def _commit_cell_edit(self, _event: tk.Event | None = None) -> None:
        if not self._edit_entry or not self._edit_context:
            return
        entry = self._edit_entry
        row_id, column, row_index = self._edit_context
        value = entry.get()
        old_row = dict(self.rows[row_index])
        old_display_value = self._display_value(old_row, column)
        self._destroy_editor()
        if value == old_display_value:
            return
        try:
            updated = self.service.update_related_forfait_field(int(old_row["Id"]), column, value)
        except Exception as exc:
            messagebox.showerror("Editar forfait", str(exc), parent=self)
            return
        self.rows[row_index] = updated
        self.table.set_rows(self._map_rows(self.rows))
        self.status_var.set(f"Campo {column} guardado.")
        if row_id in self.table.tree.get_children():
            self.table.tree.selection_set(row_id)

    def _cancel_cell_edit(self, _event: tk.Event | None = None) -> None:
        self._destroy_editor()

    def _destroy_editor(self) -> None:
        if self._edit_entry is not None:
            try:
                self._edit_entry.destroy()
            except tk.TclError:
                pass
        self._edit_entry = None
        self._edit_context = None

    def _map_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for row in rows:
            needs_review = self._needs_review(row)
            out.append(
                {
                    "Campaña": row.get("Campaña", ""),
                    "Cultivo": row.get("Cultivo", ""),
                    "IdConfeccion": row.get("IdConfeccion", ""),
                    "NombreConfeccion": row.get("NombreConfeccion", ""),
                    "GrupoConfeccion": row.get("Grupo", ""),
                    "Marca": row.get("Marca", ""),
                    "CosteMaterialEurKg": self._fmt_optional(row.get("CosteMaterialEurKg"), 4),
                    "CosteManoObraEurKg": self._fmt_optional(row.get("CosteManoObraEurKg"), 4),
                    "CosteTotalEurKg": self._fmt_optional(row.get("CosteTotalEurKg"), 4),
                    "Estado": row.get("Estado", ""),
                    "__tags__": "tag_yellow" if needs_review else (),
                }
            )
        return out

    def _display_value(self, row: dict[str, Any], column: str) -> str:
        if column.startswith("Coste"):
            return self._fmt_optional(row.get(column), 4)
        return str(row.get(column, "") or "")

    def _needs_review(self, row: dict[str, Any]) -> bool:
        group = str(row.get("Grupo") or row.get("GrupoConfeccion") or "").strip().upper()
        if not group:
            return True
        for column in ("CosteMaterialEurKg", "CosteManoObraEurKg", "CosteTotalEurKg"):
            value = row.get(column)
            if value is None or str(value).strip() == "":
                return True
        return False

    @staticmethod
    def _normalize_group_value(value: Any) -> str:
        text = str(value or "").strip().upper().replace("Á", "A")
        if text in {"MALLAS/GIRSAC", "MALLA", "MALLAS", "GIRSAC", "GIRS", "GIRSA"}:
            return "MALLAS"
        if text in {"SIN_GRUPO", ""}:
            return "PENDIENTE_REVISION"
        if text in {"ENCA", "ENCA.", "ENCAJADO"}:
            return "ENCAJADO"
        if text in {"GRAN", "GRAN.", "GRANEL"}:
            return "GRANEL"
        if text in {"ALVE", "ALVE.", "ALVEOLOS"}:
            return "ALVEOLOS"
        return text

    @staticmethod
    def _fmt_optional(value: Any, decimals: int) -> str:
        if value is None or value == "":
            return ""
        try:
            return f"{float(value):,.{decimals}f}"
        except (TypeError, ValueError):
            return ""
