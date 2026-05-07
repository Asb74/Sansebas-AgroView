import tkinter as tk
from tkinter import ttk


class MultiSelectFilter(ttk.Frame):
    def __init__(self, master: tk.Misc, title: str, on_apply=None, width: int = 28) -> None:
        super().__init__(master)
        self.title = title
        self.on_apply = on_apply
        self.available_options: list[str] = []
        self._selected: set[str] = set()
        self._summary_var = tk.StringVar(value="Todos")
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None
        self._search_var = tk.StringVar(value="")
        self.filtered_options: list[str] = []

        self.button = ttk.Button(self, textvariable=self._summary_var, width=width, command=self._open_popup)
        self.button.pack(fill="x")

    def set_options(self, options: list[str]) -> None:
        normalized = [str(v).strip() for v in options if str(v or "").strip()]
        self.available_options = normalized
        self._selected = {v for v in self._selected if v in set(self.available_options)}
        self._update_summary()

    def set_selected(self, values: list[str]) -> None:
        self._selected = {str(v).strip() for v in values if str(v or "").strip()}
        if self.available_options:
            self._selected = {v for v in self._selected if v in set(self.available_options)}
        self._update_summary()

    def get_selected(self) -> list[str]:
        return list(self._selected)

    def clear(self) -> None:
        self._selected.clear()
        self._update_summary()

    def _update_summary(self) -> None:
        count = len(self._selected)
        if count == 0:
            self._summary_var.set("Todos")
            return
        if count <= 2:
            self._summary_var.set(", ".join(sorted(self._selected)))
            return
        self._summary_var.set(f"{count} seleccionados")

    def _open_popup(self) -> None:
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.lift()
            return

        self._popup = tk.Toplevel(self)
        self._popup.title(self.title)
        self._popup.transient(self.winfo_toplevel())
        self._popup.grab_set()
        popup_w = max(360, self.winfo_width())
        popup_h = 420
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        if x + popup_w > screen_w:
            x = max(0, screen_w - popup_w - 8)
        if y + popup_h > screen_h:
            y = max(0, self.winfo_rooty() - popup_h)

        self._popup.geometry(f"{popup_w}x{popup_h}+{x}+{y}")
        self._popup.grid_rowconfigure(1, weight=1)
        self._popup.grid_columnconfigure(0, weight=1)

        search_entry = ttk.Entry(self._popup, textvariable=self._search_var)
        search_entry.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        self._search_var.trace_add("write", lambda *_: self._refresh_listbox())

        list_frame = ttk.Frame(self._popup)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=8)
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self._listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, exportselection=False)
        self._listbox.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(list_frame, orient="vertical", command=self._listbox.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=yscroll.set)

        self._refresh_listbox()

        actions = ttk.Frame(self._popup)
        actions.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        ttk.Button(actions, text="Seleccionar todo", command=self._select_all).pack(side="left")
        ttk.Button(actions, text="Limpiar", command=self._clear_selection).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Aplicar", command=self._apply_selection).pack(side="right")

    def _refresh_listbox(self) -> None:
        if self._listbox is None:
            return
        term = self._search_var.get().strip().lower()
        if term:
            self.filtered_options = [v for v in self.available_options if term in v.lower()]
        else:
            self.filtered_options = list(self.available_options)

        self._listbox.delete(0, tk.END)
        for value in self.filtered_options:
            self._listbox.insert(tk.END, value)
        for idx, value in enumerate(self.filtered_options):
            if value in self._selected:
                self._listbox.selection_set(idx)

    def _select_all(self) -> None:
        if self._listbox is None:
            return
        self._listbox.selection_set(0, tk.END)

    def _clear_selection(self) -> None:
        if self._listbox is None:
            return
        self._listbox.selection_clear(0, tk.END)

    def _apply_selection(self) -> None:
        if self._listbox is None:
            return
        selected_indices = self._listbox.curselection()
        self._selected = {self.filtered_options[i] for i in selected_indices if i < len(self.filtered_options)}
        self._update_summary()
        if self.on_apply is not None:
            self.on_apply()
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
