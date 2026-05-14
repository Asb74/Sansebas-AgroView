from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from db.operational_quality_repository import VISIBLE_ORIGINS
from services.operational_quality_service import OperationalQualityService
from widgets.screen_header import ScreenHeader

COLUMNS = ("Origen", "% Primera", "% Segunda", "% Destrío", "Usar histórico", "% destrío recuperable industria")


class OperationalQualitySettingsScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, on_back) -> None:
        super().__init__(master, padding=10)
        self.on_back = on_back
        self.service = OperationalQualityService()
        self.tree: ttk.Treeview
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        ScreenHeader(self, title="Configuración", subtitle="Configuración calidad operativa", on_back=self.on_back).grid(row=0, column=0, sticky="ew")
        self.tree = ttk.Treeview(self, columns=COLUMNS, show="headings", height=12)
        for c in COLUMNS:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=180 if c == "Origen" else 130, anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew", pady=8)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._edit_selected)

        help_text = (
            "% destrío recuperable industria indica qué parte del destrío puede aprovecharse como industria. "
            "No reduce la cobertura comercial; se usará más adelante para balance industrial/económico."
        )
        ttk.Label(self, text=help_text, wraplength=980, justify="left").grid(row=2, column=0, sticky="w", pady=(0, 8))

        btns = ttk.Frame(self)
        btns.grid(row=3, column=0, sticky="ew")
        ttk.Button(btns, text="Editar fila", command=self._edit_selected).pack(side="left", padx=4)
        ttk.Button(btns, text="Guardar", command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="Restablecer valores predeterminados", command=self._reset_defaults).pack(side="left", padx=4)
        ttk.Button(btns, text="Volver", command=self.on_back).pack(side="right", padx=4)

    def _fmt_pct(self, dec: float) -> str:
        return f"{dec * 100:.2f}".rstrip("0").rstrip(".")

    def _load(self) -> None:
        self.tree.delete(*self.tree.get_children())
        rows = {r["Origen"]: r for r in self.service.get_settings()}
        for origen in VISIBLE_ORIGINS:
            r = rows.get(origen)
            if not r:
                continue
            self.tree.insert("", "end", iid=r["Origen"], values=(
                r["Origen"], self._fmt_pct(float(r["PrimeraPct"])), self._fmt_pct(float(r["SegundaPct"])),
                self._fmt_pct(float(r["DestrioFallbackPct"])), "Sí" if int(r["UsarDestrioHistorico"]) else "No",
                self._fmt_pct(float(r["IndustriaRecuperablePct"])),
            ))

    def _parse_pct(self, txt: str) -> float:
        raw = (txt or "").strip().replace(",", ".")
        if raw == "":
            raise ValueError("No se permiten valores vacíos")
        val = float(raw)
        if val < 0 or val > 100:
            raise ValueError("Los porcentajes deben estar entre 0 y 100")
        return val / 100.0

    def _edit_selected(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = list(self.tree.item(iid, "values"))
        win = tk.Toplevel(self)
        win.title(f"Editar {vals[0]}")
        labels = COLUMNS[1:]
        vars_: list[tk.StringVar] = []
        for i, label in enumerate(labels, start=1):
            ttk.Label(win, text=label).grid(row=i, column=0, sticky="w", padx=6, pady=4)
            v = tk.StringVar(value=str(vals[i]))
            vars_.append(v)
            if label == "Usar histórico":
                ttk.Combobox(win, textvariable=v, values=["Sí", "No"], state="readonly", width=20).grid(row=i, column=1, padx=6, pady=4)
            else:
                ttk.Entry(win, textvariable=v, width=24).grid(row=i, column=1, padx=6, pady=4)

        def _ok() -> None:
            self.tree.item(iid, values=(vals[0], *[v.get().strip() for v in vars_]))
            win.destroy()

        ttk.Button(win, text="Aceptar", command=_ok).grid(row=len(labels)+2, column=1, sticky="e", padx=6, pady=8)
        win.transient(self)
        win.grab_set()
        self.wait_window(win)

    def _rows_for_save(self) -> list[dict]:
        rows = []
        for iid in self.tree.get_children():
            o, p1, p2, d, h, ir = self.tree.item(iid, "values")
            p1d = self._parse_pct(p1)
            p2d = self._parse_pct(p2)
            if abs((p1d + p2d) - 1.0) > 0.0001 and not messagebox.askyesno("Advertencia", f"{o}: % primera + % segunda no suma 100. ¿Guardar igualmente?", parent=self):
                raise ValueError("Guardar cancelado por validación")
            rows.append({
                "Origen": o,
                "PrimeraPct": p1d,
                "SegundaPct": p2d,
                "DestrioFallbackPct": self._parse_pct(d),
                "UsarDestrioHistorico": 1 if str(h).strip().upper().startswith("S") else 0,
                "IndustriaRecuperablePct": self._parse_pct(ir),
            })
        return rows

    def _save(self) -> None:
        try:
            self.service.save_settings(self._rows_for_save())
            messagebox.showinfo("Configuración", "Configuración de calidad operativa guardada correctamente.", parent=self)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _reset_defaults(self) -> None:
        if not messagebox.askyesno("Confirmar", "¿Restablecer valores predeterminados?", parent=self):
            return
        self.service.reset_defaults()
        self._load()
        messagebox.showinfo("Configuración", "Valores predeterminados restaurados.", parent=self)
