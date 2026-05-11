import tkinter as tk
from tkinter import ttk

from utils.ui_assets import get_logo


class ScreenHeader(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        subtitle: str | None = None,
        on_back=None,
        logo_size: str = "64",
    ) -> None:
        super().__init__(parent)
        self.grid_columnconfigure(0, weight=1)

        left = ttk.Frame(self)
        left.grid(row=0, column=0, sticky="w")

        self.logo_img = get_logo(logo_size, master=self)
        if self.logo_img is not None:
            tk.Label(left, image=self.logo_img, bg="#f3f6f2").pack(side="left", padx=(0, 10))

        text_frame = ttk.Frame(left)
        text_frame.pack(side="left")

        ttk.Label(text_frame, text=title, style="Section.TLabel").pack(anchor="w")
        if subtitle:
            ttk.Label(text_frame, text=subtitle, style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        if on_back is not None:
            ttk.Button(self, text="Volver", command=on_back).grid(row=0, column=1, sticky="e")
