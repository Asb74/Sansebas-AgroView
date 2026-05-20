import tkinter as tk
from tkinter import messagebox


def show_help(parent: tk.Misc, title: str, description: str, example: str = "", impact: str = "") -> None:
    text_parts = [description]

    if example:
        text_parts.append("")
        text_parts.append(f"Ejemplo:\n{example}")

    if impact:
        text_parts.append("")
        text_parts.append(f"Impacto operativo:\n{impact}")

    messagebox.showinfo(title, "\n".join(text_parts), parent=parent)
