import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from services.forfait_service import ForfaitService
from widgets.data_table import DataTable


class MapForfaitScreen(ttk.Frame):
    TABLE_COLUMNS = [
        "Cultivo",
        "Campaña",
        "ConfeccionPedido",
        "NombreConfeccion",
        "GrupoConfeccion",
        "Neto",
        "Marca",
        "DescripcionCorta",
        "Forfait sugerido",
        "Forfait asignado",
        "GrupoForfait",
        "KgForfait",
        "Medidas",
        "TipoEnvase",
        "MaterialEnvase",
        "ClaveForfait",
        "Confianza",
        "MotivoSugerencia",
        "CosteConfeccionEurKg",
        "CosteTotalEurKg",
        "Estado",
    ]

    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=16)
        self.on_back = on_back
        self.service = ForfaitService()
        self.cultivo_var = tk.StringVar(value="CITRICOS")
        self.campana_var = tk.StringVar(value="2025")
        self.forfait_var = tk.StringVar()
        self.estado_var = tk.StringVar(value="PENDIENTE")
        self.obs_var = tk.StringVar()
        self.status_var = tk.StringVar(value="")
        self.rows: list[dict[str, Any]] = []
        self.forfaits: list[dict[str, Any]] = []
        self.option_to_key: dict[str, str] = {}
        self.key_to_option: dict[str, str] = {}
        self.selected_confeccion = ""
        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Mapear forfait/confecciones", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Volver", command=self.on_back).grid(row=0, column=1, sticky="e")

        controls = ttk.LabelFrame(self, text="Filtro obligatorio", padding=12)
        controls.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        controls.grid_columnconfigure(7, weight=1)
        ttk.Label(controls, text="Cultivo").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Entry(controls, textvariable=self.cultivo_var, width=18).grid(row=0, column=1, sticky="w", padx=(0, 12))
        ttk.Label(controls, text="Campaña").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(controls, textvariable=self.campana_var, width=18).grid(row=0, column=3, sticky="w", padx=(0, 12))
        ttk.Button(controls, text="Cargar confecciones", command=self.load_rows).grid(row=0, column=4, sticky="w", padx=(0, 8))
        ttk.Button(controls, text="Aplicar sugerencia a selección", command=self.apply_suggestion).grid(row=0, column=5, sticky="w", padx=(0, 8))
        ttk.Button(controls, text="Reiniciar confecciones", command=self.reset_mapping_rows).grid(row=0, column=6, sticky="w")

        edit = ttk.LabelFrame(self, text="Asignación manual de la fila seleccionada", padding=12)
        edit.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        edit.grid_columnconfigure(1, weight=1)
        ttk.Label(edit, text="Forfait asignado").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 6))
        self.forfait_combo = ttk.Combobox(edit, textvariable=self.forfait_var, values=[], state="readonly")
        self.forfait_combo.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        ttk.Label(edit, text="Estado").grid(row=0, column=2, sticky="w", padx=(12, 8), pady=(0, 6))
        ttk.Combobox(
            edit,
            textvariable=self.estado_var,
            values=["PENDIENTE", "VALIDADO", "SIN_EQUIVALENCIA"],
            state="readonly",
            width=18,
        ).grid(row=0, column=3, sticky="w", pady=(0, 6))
        ttk.Label(edit, text="Observaciones").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(edit, textvariable=self.obs_var).grid(row=1, column=1, columnspan=2, sticky="ew")
        ttk.Button(edit, text="Guardar selección", command=self.save_selected).grid(row=1, column=3, sticky="e", padx=(12, 0))

        self.table = DataTable(self, columns=self.TABLE_COLUMNS)
        self.table.grid(row=2, column=0, sticky="nsew")
        self.table.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.context_menu = tk.Menu(self, tearoff=False)
        self.context_menu.add_command(label="Asignar forfait sugerido", command=self.assign_suggested_forfait)
        self.context_menu.add_command(label="Marcar sin equivalencia", command=self.mark_without_equivalence)
        self.context_menu.add_command(label="Validar forfait asignado", command=self.validate_assigned_forfait)
        self.table.tree.bind("<Button-3>", self._show_context_menu)
        ttk.Label(self, textvariable=self.status_var).grid(row=4, column=0, sticky="w", pady=(8, 0))

    def load_rows(self) -> None:
        cultivo = self.cultivo_var.get().strip()
        campana = self.campana_var.get().strip()
        if not cultivo or not campana:
            messagebox.showwarning("Filtro obligatorio", "Indica cultivo y campaña.", parent=self)
            return
        try:
            self.forfaits = self.service.fetch_forfaits(cultivo, campana)
            self.rows = self.service.fetch_mapping_rows(cultivo, campana)
        except Exception as exc:
            messagebox.showerror("Mapear forfait", str(exc), parent=self)
            return
        self.option_to_key = {}
        self.key_to_option = {}
        values = [""]
        for row in self.forfaits:
            label = self.service.format_forfait_label(row)
            key = str(row.get("ClaveForfait") or "")
            values.append(label)
            self.option_to_key[label] = key
            self.key_to_option[key] = label
        self.forfait_combo.configure(values=values)
        self.table.set_rows(self._map_rows(self.rows))
        self._set_counter_status()

    def apply_suggestion(self) -> None:
        self.assign_suggested_forfait()

    def assign_suggested_forfait(self) -> None:
        row = self._selected_row()
        if not row:
            self.status_var.set("Selecciona una confección.")
            return
        suggestion_key = str(row.get("ClaveForfaitSugerida") or "")
        suggestion_label = self._suggestion_label(row)
        if not suggestion_key:
            messagebox.showinfo("Forfait sugerido", "Esta confección no tiene forfait sugerido.", parent=self)
            self.status_var.set("Esta confección no tiene forfait sugerido.")
            return
        if not messagebox.askyesno(
            "Asignar forfait sugerido",
            "¿Quieres asignar y guardar el forfait sugerido para esta confección?\n\n"
            f"ConfeccionPedido: {row.get('ConfeccionPedido') or ''}\n"
            f"NombreConfeccion: {row.get('NombreConfeccion') or ''}\n"
            f"Forfait sugerido: {suggestion_label}",
            parent=self,
        ):
            return
        self._save_equivalence(
            row,
            suggestion_key,
            "VALIDADO",
            self.obs_var.get().strip() or "Asignado desde forfait sugerido.",
        )

    def mark_without_equivalence(self) -> None:
        row = self._selected_row()
        if not row:
            self.status_var.set("Selecciona una confección.")
            return
        self._save_equivalence(
            row,
            "",
            "SIN_EQUIVALENCIA",
            self.obs_var.get().strip() or "Marcado sin equivalencia.",
        )

    def validate_assigned_forfait(self) -> None:
        row = self._selected_row()
        if not row:
            self.status_var.set("Selecciona una confección.")
            return
        selected_key = self.option_to_key.get(self.forfait_var.get().strip(), "") or str(row.get("ClaveForfait") or "")
        if not selected_key:
            messagebox.showinfo("Validar forfait", "No hay forfait asignado para validar.", parent=self)
            return
        self._save_equivalence(row, selected_key, "VALIDADO", self.obs_var.get().strip())

    def save_selected(self) -> None:
        row = self._selected_row()
        if not row:
            self.status_var.set("Selecciona una confección.")
            return
        selected_key = self.option_to_key.get(self.forfait_var.get().strip(), "")
        estado = self.estado_var.get().strip()
        if estado == "SIN_EQUIVALENCIA":
            selected_key = ""
        if estado == "VALIDADO" and not selected_key:
            messagebox.showerror(
                "Guardar equivalencia",
                "Para validar es obligatorio seleccionar un forfait.",
                parent=self,
            )
            return
        self._save_equivalence(row, selected_key, estado, self.obs_var.get().strip())

    def reset_mapping_rows(self) -> None:
        cultivo = self.cultivo_var.get().strip()
        campana = self.campana_var.get().strip()
        if not cultivo or not campana:
            messagebox.showwarning("Filtro obligatorio", "Indica cultivo y campaña.", parent=self)
            return
        if not messagebox.askyesno(
            "Reiniciar confecciones",
            "Se eliminarán las equivalencias de forfait para el cultivo y campaña actuales.\n\n"
            "No se borrarán los forfaits importados ni el Excel.\n\n"
            "¿Quieres continuar?",
            parent=self,
        ):
            return
        try:
            deleted = self.service.reset_mapping_rows(cultivo, campana)
        except Exception as exc:
            messagebox.showerror("Reiniciar confecciones", str(exc), parent=self)
            return
        self.load_rows()
        self._set_counter_status(f"Equivalencias eliminadas: {deleted}.")

    def _save_equivalence(self, row: dict[str, Any], clave_forfait: str, estado: str, observaciones: str = "") -> None:
        try:
            self.service.update_equivalence(
                self.cultivo_var.get().strip(),
                self.campana_var.get().strip(),
                str(row.get("ConfeccionPedido") or ""),
                clave_forfait,
                estado,
                observaciones,
            )
        except Exception as exc:
            messagebox.showerror("Guardar equivalencia", str(exc), parent=self)
            return
        confeccion = row.get("ConfeccionPedido") or ""
        self.load_rows()
        self._set_counter_status(f"Equivalencia guardada para {confeccion}.")

    def _show_context_menu(self, event: tk.Event) -> None:
        row_id = self.table.tree.identify_row(event.y)
        if not row_id:
            return
        self.table.tree.selection_set(row_id)
        self.table.tree.focus(row_id)
        self._on_select(event)
        row = self._selected_row()
        suggestion_state = "normal" if row and row.get("ClaveForfaitSugerida") else "disabled"
        self.context_menu.entryconfig("Asignar forfait sugerido", state=suggestion_state)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _set_counter_status(self, prefix: str = "") -> None:
        pendientes = sum(1 for r in self.rows if str(r.get("Estado") or "") == "PENDIENTE")
        validados = sum(1 for r in self.rows if str(r.get("Estado") or "") == "VALIDADO")
        counters = (
            f"Confecciones: {len(self.rows)} | Forfaits: {len(self.forfaits)} | "
            f"Validados: {validados} | Pendientes: {pendientes}"
        )
        self.status_var.set(f"{prefix} {counters}" if prefix else counters)

    def _suggestion_label(self, row: dict[str, Any]) -> str:
        label = str(row.get("ForfaitSugerido") or "").strip()
        if label and label != "None":
            return label
        return self._option_label_for_key(str(row.get("ClaveForfaitSugerida") or ""))

    def _option_label_for_key(self, key: str) -> str:
        return self.key_to_option.get(str(key or ""), "")

    def _on_select(self, _event: tk.Event) -> None:
        row = self._selected_row()
        if not row:
            return
        self.selected_confeccion = str(row.get("ConfeccionPedido") or "")
        self.forfait_var.set(self._option_label_for_key(str(row.get("ClaveForfait") or "")))
        self.estado_var.set(str(row.get("Estado") or "PENDIENTE"))
        self.obs_var.set(str(row.get("Observaciones") or ""))

    def _selected_row(self) -> dict[str, Any] | None:
        selection = self.table.tree.selection()
        if not selection:
            return None
        item = self.table.tree.item(selection[0])
        values = item.get("values", [])
        if len(values) < 3:
            return None
        confeccion = str(values[2])
        for row in self.rows:
            if str(row.get("ConfeccionPedido") or "") == confeccion:
                return row
        return None

    def _map_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for row in rows:
            estado = str(row.get("Estado") or "PENDIENTE")
            tag = "tag_green" if estado == "VALIDADO" else ("tag_red" if estado == "SIN_EQUIVALENCIA" else "tag_yellow")
            suggestion_label = self._suggestion_label(row)
            assigned_key = str(row.get("ClaveForfait") or "")
            assigned_label = self._option_label_for_key(assigned_key) if assigned_key else ""
            out.append(
                {
                    "Cultivo": row.get("Cultivo", ""),
                    "Campaña": row.get("Campaña", ""),
                    "ConfeccionPedido": row.get("ConfeccionPedido", ""),
                    "NombreConfeccion": row.get("NombreConfeccion", ""),
                    "GrupoConfeccion": row.get("GrupoConfeccion", ""),
                    "Neto": f'{float(row.get("Neto") or 0):,.2f}',
                    "Marca": row.get("Marca", ""),
                    "DescripcionCorta": row.get("DescripcionCorta", ""),
                    "Forfait sugerido": suggestion_label,
                    "Forfait asignado": assigned_label,
                    "GrupoForfait": row.get("GrupoForfait", "") if assigned_key else "",
                    "KgForfait": self._fmt_optional(row.get("KgForfait"), 2) if assigned_key else "",
                    "Medidas": row.get("Medidas", "") if assigned_key else "",
                    "TipoEnvase": row.get("TipoEnvase", "") if assigned_key else "",
                    "MaterialEnvase": row.get("MaterialEnvase", "") if assigned_key else "",
                    "ClaveForfait": assigned_key,
                    "Confianza": self._fmt_optional(row.get("ConfianzaSugerencia"), 0),
                    "MotivoSugerencia": row.get("MotivoSugerencia", ""),
                    "CosteConfeccionEurKg": f'{float(row.get("CosteConfeccionEurKg") or 0):,.4f}' if assigned_key else "",
                    "CosteTotalEurKg": f'{float(row.get("CosteTotalEurKg") or 0):,.4f}' if assigned_key else "",
                    "Estado": estado,
                    "__tags__": tag,
                }
            )
        return out

    @staticmethod
    def _fmt_optional(value: Any, decimals: int) -> str:
        if value is None or value == "":
            return ""
        try:
            return f"{float(value):,.{decimals}f}"
        except (TypeError, ValueError):
            return ""
