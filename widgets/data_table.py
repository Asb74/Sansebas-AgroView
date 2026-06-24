import logging
import time
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
        self.set_rows_profiled(rows)

    def set_rows_profiled(self, rows: list[dict], perf_name: str | None = None) -> None:
        logger = logging.getLogger(__name__)
        total_t0 = time.perf_counter()
        delete_t0 = time.perf_counter()
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        delete_secs = time.perf_counter() - delete_t0

        tag_t0 = time.perf_counter()
        prepared_rows = []
        for row in rows:
            values = [row.get(col, "") for col in self.columns]
            tags = row.get("__tags__", ())
            if isinstance(tags, str):
                tags = (tags,)
            elif not isinstance(tags, (tuple, list)):
                tags = ()
            prepared_rows.append((values, tuple(tags)))
        tag_secs = time.perf_counter() - tag_t0

        insert_t0 = time.perf_counter()
        for values, tags in prepared_rows:
            self.tree.insert("", "end", values=values, tags=tags)
        insert_secs = time.perf_counter() - insert_t0

        autowidth_t0 = time.perf_counter()
        # No hay autosize dinámico en esta tabla; se mide para distinguirlo del insert.
        autowidth_secs = time.perf_counter() - autowidth_t0
        total_secs = time.perf_counter() - total_t0
        if perf_name:
            logger.info("[PERF Tab.%s.Render.Delete] tiempo=%.3fs rows=%s", perf_name, delete_secs, len(rows))
            logger.info("[PERF Tab.%s.Render.Insert] tiempo=%.3fs rows=%s", perf_name, insert_secs, len(rows))
            logger.info("[PERF Tab.%s.Render.AutoWidth] tiempo=%.3fs rows=%s", perf_name, autowidth_secs, len(rows))
            logger.info("[PERF Tab.%s.Render.Tags] tiempo=%.3fs rows=%s", perf_name, tag_secs, len(rows))
            logger.info("[PERF Tab.%s.Render.Total] tiempo=%.3fs rows=%s", perf_name, total_secs, len(rows))
