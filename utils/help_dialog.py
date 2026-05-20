import tkinter as tk
from tkinter import messagebox, ttk


def show_help(parent: tk.Misc, title: str, description: str, example: str = "", impact: str = "") -> None:
    text_parts = [description]

    if example:
        text_parts.append("")
        text_parts.append(f"Ejemplo:\n{example}")

    if impact:
        text_parts.append("")
        text_parts.append(f"Impacto operativo:\n{impact}")

    messagebox.showinfo(title, "\n".join(text_parts), parent=parent)


def show_tab_help(parent: tk.Misc, title: str, intro: str, help_items: list[dict]) -> None:
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry("720x520")
    dialog.transient(parent)
    dialog.grab_set()

    root = ttk.Frame(dialog, padding=12)
    root.pack(fill="both", expand=True)
    root.grid_rowconfigure(1, weight=1)
    root.grid_columnconfigure(0, weight=1)

    ttk.Label(root, text="General del día", font=("TkDefaultFont", 14, "bold")).grid(
        row=0, column=0, sticky="w", pady=(0, 8)
    )

    body = ttk.Frame(root)
    body.grid(row=1, column=0, sticky="nsew")
    body.grid_rowconfigure(0, weight=1)
    body.grid_columnconfigure(0, weight=1)

    canvas = tk.Canvas(body, highlightthickness=0)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=scrollbar.set)

    content = ttk.Frame(canvas, padding=(0, 0, 8, 0))
    content_window = canvas.create_window((0, 0), window=content, anchor="nw")

    def _update_scroll_region(_: tk.Event | None = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _fit_content_width(event: tk.Event) -> None:
        canvas.itemconfigure(content_window, width=event.width)

    content.bind("<Configure>", _update_scroll_region)
    canvas.bind("<Configure>", _fit_content_width)

    ttk.Label(content, text=intro, wraplength=660, justify="left").grid(row=0, column=0, sticky="w", pady=(0, 12))

    for idx, item in enumerate(help_items, start=1):
        ttk.Label(content, text=item.get("title", ""), font=("TkDefaultFont", 10, "bold")).grid(
            row=(idx * 2) - 1, column=0, sticky="w"
        )

        text_lines = [
            item.get("description", ""),
            f"Ejemplo: {item.get('example', '')}",
            f"Impacto operativo: {item.get('impact', '')}",
        ]
        ttk.Label(content, text="\n".join(text_lines), wraplength=660, justify="left").grid(
            row=idx * 2, column=0, sticky="w", pady=(0, 10)
        )

    ttk.Button(root, text="Cerrar", command=dialog.destroy).grid(row=2, column=0, sticky="e", pady=(12, 0))
    dialog.wait_window()
