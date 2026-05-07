from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from reports.pdf_report_service import PdfReportService


class ReportButton(ttk.Frame):
    def __init__(self, master: tk.Misc, title_provider: Callable[[], str], data_provider: Callable[[], dict]) -> None:
        super().__init__(master)
        self.title_provider = title_provider
        self.data_provider = data_provider
        self.pdf_service = PdfReportService()
        ttk.Button(self, text="Generar informe PDF", command=self._on_generate).pack(anchor="e")

    def _on_generate(self) -> None:
        default_name = f"{self.title_provider().replace(' ', '_').lower()}.pdf"
        out = filedialog.asksaveasfilename(
            title="Guardar informe PDF",
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF", "*.pdf")],
        )
        if not out:
            return
        data = self.data_provider()
        ok, msg = self.pdf_service.generate(out, data)
        if ok:
            messagebox.showinfo("Informe PDF", msg)
        else:
            messagebox.showerror("Informe PDF", msg)
