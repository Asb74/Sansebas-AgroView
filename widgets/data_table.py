import tkinter as tk
from tkinter import ttk


class DataTable(ttk.Frame):
    def __init__(self, master: tk.Misc, columns: list[str]) -> None:
        super().__init__(master)
        self.columns = columns

        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        self.tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")

        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")

        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, stretch=True)

        # Tags semaforo reutilizables para tablas analiticas.
        self.tree.tag_configure("tag_green", foreground="#1b5e20")
        self.tree.tag_configure("tag_yellow", foreground="#8d6e00")
        self.tree.tag_configure("tag_red", foreground="#b71c1c")
        self.tree.tag_configure("tag_orange", foreground="#e65100")

    def set_rows(self, rows: list[dict]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in rows:
            values = [row.get(col, "") for col in self.columns]
            tags = row.get("__tags__", ())
            if isinstance(tags, str):
                tags = (tags,)
            elif not isinstance(tags, (tuple, list)):
                tags = ()
            self.tree.insert("", "end", values=values, tags=tuple(tags))
