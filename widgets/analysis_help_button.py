import tkinter as tk
from tkinter import ttk

from docs.analysis_notes import ANALYSIS_NOTES
from widgets.analysis_help_dialog import AnalysisHelpDialog


class AnalysisHelpButton(ttk.Button):
    def __init__(self, master: tk.Misc, analysis_key: str, text: str = "ℹ️ Cómo se calcula") -> None:
        self.analysis_key = analysis_key
        super().__init__(master, text=text, command=self._open_help)

    def _open_help(self) -> None:
        note = ANALYSIS_NOTES.get(
            self.analysis_key,
            {
                "title": "Nota no disponible",
                "que_mide": f"No se encontro una nota para la clave: {self.analysis_key}",
                "como_se_calcula": "",
                "datos_usados": "",
                "limitaciones": "",
                "interpretacion": "",
                "uso_practico": "",
            },
        )
        AnalysisHelpDialog(self, note)
