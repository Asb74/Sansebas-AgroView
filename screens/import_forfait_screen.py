import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from services.forfait_service import ForfaitService
from widgets.data_table import DataTable


class ImportForfaitScreen(ttk.Frame):
    EDITABLE_COLUMNS = {
        "GrupoForfait",
        "KgForfait",
        "UnidadesForfait",
        "KgUnidad",
        "Medidas",
        "TipoEnvase",
        "MaterialEnvase",
        "DescripcionForfait",
        "DescripcionNormalizada",
    }
    CRITICAL_COLUMNS = {"GrupoForfait", "KgForfait", "TipoEnvase", "MaterialEnvase"}

    TABLE_COLUMNS = [
        "Cultivo",
        "Campaña",
        "NombreForfait",
        "DescripcionForfait",
        "DescripcionNormalizada",
        "GrupoForfait",
        "KgForfait",
        "UnidadesForfait",
        "KgUnidad",
        "Medidas",
        "TipoEnvase",
        "MaterialEnvase",
        "ClaveForfait",
        "CosteConfeccionEurKg",
        "CosteTotalEurKg",
        "Revision",
    ]

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.service = ForfaitService()
        self.file_var = tk.StringVar()
        self.cultivo_var = tk.StringVar(value="CITRICOS")
        self.campana_var = tk.StringVar(value="2025")
        self.sheet_var = tk.StringVar(value="NARANJA")
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
        ttk.Entry(form, textvariable=self.sheet_var, width=20).grid(row=3, column=1, sticky="w")

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

    def _import(self) -> None:
        file_path = self.file_var.get().strip()
        cultivo = self.cultivo_var.get().strip()
        campana = self.campana_var.get().strip()
        sheet = self.sheet_var.get().strip() or "NARANJA"
        if not file_path or not cultivo or not campana:
            messagebox.showwarning("Faltan datos", "Selecciona Excel, cultivo y campaña.", parent=self)
            return
        try:
            inserted, updated, rows = self.service.import_forfait_excel(file_path, cultivo, campana, sheet)
        except Exception as exc:
            messagebox.showerror("Importar forfait", str(exc), parent=self)
            return
        self.rows = rows
        self.table.set_rows(self._map_rows(rows))
        self.status_var.set(f"Forfait importado. Nuevos: {inserted}. Actualizados: {updated}. Filas: {len(rows)}.")

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
            updated_rows = []
            for row in self.rows:
                updated_rows.append(self.service.update_forfait_row(int(row["Id"]), row))
        except Exception as exc:
            messagebox.showerror("Guardar cambios", str(exc), parent=self)
            return
        self.rows = updated_rows
        self.table.set_rows(self._map_rows(self.rows))
        self.status_var.set(f"Cambios guardados. Filas actualizadas: {len(updated_rows)}.")

    def _recalculate_keys(self) -> None:
        if not self.rows:
            self.status_var.set("No hay filas de forfait para recalcular.")
            return
        try:
            updated_rows = []
            for row in self.rows:
                updated_rows.append(self.service.update_forfait_row(int(row["Id"]), row))
        except Exception as exc:
            messagebox.showerror("Recalcular claves", str(exc), parent=self)
            return
        self.rows = updated_rows
        self.table.set_rows(self._map_rows(self.rows))
        self.status_var.set(f"Claves recalculadas. Filas actualizadas: {len(updated_rows)}.")

    def _normalize_groups(self) -> None:
        if not self.rows:
            self.status_var.set("No hay filas de forfait para normalizar.")
            return
        changed = 0
        updated_rows = list(self.rows)
        try:
            for index, row in enumerate(self.rows):
                original = str(row.get("GrupoForfait") or "")
                normalized = self._normalize_group_value(original)
                if normalized == original:
                    continue
                new_row = dict(row)
                new_row["GrupoForfait"] = normalized
                updated_rows[index] = self.service.update_forfait_row(int(row["Id"]), new_row)
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
            updated = self.service.update_forfait_field(int(old_row["Id"]), column, value)
        except Exception as exc:
            messagebox.showerror("Editar forfait", str(exc), parent=self)
            return
        self.rows[row_index] = updated
        self.table.set_rows(self._map_rows(self.rows))
        self.status_var.set(f"Campo {column} guardado. Clave: {updated.get('ClaveForfait') or ''}")
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
                    "Cultivo": row.get("Cultivo", ""),
                    "Campaña": row.get("Campaña", ""),
                    "NombreForfait": row.get("NombreForfait", ""),
                    "DescripcionForfait": row.get("DescripcionForfait", ""),
                    "DescripcionNormalizada": row.get("DescripcionNormalizada", ""),
                    "GrupoForfait": row.get("GrupoForfait", ""),
                    "KgForfait": self._fmt_optional(row.get("KgForfait"), 2),
                    "UnidadesForfait": row.get("UnidadesForfait", "") or "",
                    "KgUnidad": self._fmt_optional(row.get("KgUnidad"), 2),
                    "Medidas": row.get("Medidas", ""),
                    "TipoEnvase": row.get("TipoEnvase", ""),
                    "MaterialEnvase": row.get("MaterialEnvase", ""),
                    "ClaveForfait": row.get("ClaveForfait", ""),
                    "CosteConfeccionEurKg": f'{float(row.get("CosteConfeccionEurKg") or 0):,.4f}',
                    "CosteTotalEurKg": f'{float(row.get("CosteTotalEurKg") or 0):,.4f}',
                    "Revision": "REVISAR" if needs_review else "",
                    "__tags__": "tag_yellow" if needs_review else (),
                }
            )
        return out

    def _display_value(self, row: dict[str, Any], column: str) -> str:
        if column in {"KgForfait", "KgUnidad"}:
            return self._fmt_optional(row.get(column), 2)
        return str(row.get(column, "") or "")

    def _needs_review(self, row: dict[str, Any]) -> bool:
        group = str(row.get("GrupoForfait") or "").strip().upper()
        if not group or group in {"SIN_GRUPO", "PENDIENTE_REVISION"}:
            return True
        for column in ("KgForfait", "TipoEnvase", "MaterialEnvase"):
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
