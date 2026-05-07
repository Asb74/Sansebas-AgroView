import tkinter as tk
from tkinter import ttk
from typing import Any


class AnalysisHelpDialog(tk.Toplevel):
    SECTION_LABELS = [
        ("que_mide", "Qué mide"),
        ("como_se_calcula", "Cómo se calcula"),
        ("datos_usados", "Datos usados"),
        ("limitaciones", "Limitaciones"),
        ("interpretacion", "Interpretación"),
        ("uso_practico", "Uso práctico"),
    ]

    def __init__(self, master: tk.Misc, note: dict[str, Any]) -> None:
        super().__init__(master)
        title = str(note.get("title") or "Nota de análisis")
        self.title(title)
        self.geometry("760x560")
        self.minsize(520, 360)
        self.transient(master.winfo_toplevel())

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        ttk.Label(self, text=title, style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 8)
        )

        body = ttk.Frame(self)
        body.grid(row=1, column=0, sticky="nsew", padx=16)
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        text = tk.Text(body, wrap="word", height=20, borderwidth=0, padx=10, pady=10)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        text.tag_configure("section", font=("TkDefaultFont", 10, "bold"), spacing1=10, spacing3=4)
        text.tag_configure("body", spacing3=6)
        text.tag_configure("bullet", lmargin1=18, lmargin2=34, spacing3=4)

        for field, label in self.SECTION_LABELS:
            value = note.get(field, "")
            if not value:
                continue
            text.insert("end", f"{label}\n", "section")
            self._insert_value(text, value)
            text.insert("end", "\n")

        text.configure(state="disabled")

        footer = ttk.Frame(self)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
        footer.grid_columnconfigure(0, weight=1)
        ttk.Button(footer, text="Cerrar", command=self.destroy).grid(row=0, column=1, sticky="e")

        self.bind("<Escape>", lambda _event: self.destroy())
        self.focus_set()

    @staticmethod
    def _insert_value(text: tk.Text, value: Any) -> None:
        if isinstance(value, (list, tuple)):
            for item in value:
                text.insert("end", f"- {item}\n", "bullet")
            return
        text.insert("end", f"{value}\n", "body")
