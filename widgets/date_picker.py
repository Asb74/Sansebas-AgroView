import calendar
from datetime import date
import tkinter as tk
from tkinter import ttk


class DatePickerPopup(tk.Toplevel):
    def __init__(self, parent: tk.Misc, target_var: tk.StringVar, anchor_widget: tk.Widget) -> None:
        super().__init__(parent)
        self.target_var = target_var
        self.anchor_widget = anchor_widget

        self.title("Seleccionar fecha")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.resizable(False, False)

        today = date.today()
        initial = self._parse_date(target_var.get().strip()) or today
        self.current_year = initial.year
        self.current_month = initial.month

        self.header_var = tk.StringVar(value="")
        self._build_ui()
        self._render_calendar()
        self._position_popup()

    @staticmethod
    def _parse_date(value: str) -> date | None:
        if len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
            try:
                return date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
            except ValueError:
                return None
        return None

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        nav = ttk.Frame(self, padding=(8, 8, 8, 4))
        nav.grid(row=0, column=0, sticky="ew")
        nav.grid_columnconfigure(4, weight=1)

        ttk.Button(nav, text="<<", width=3, command=self._prev_year).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(nav, text="<", width=3, command=self._prev_month).grid(row=0, column=1, padx=(0, 8))
        ttk.Label(nav, textvariable=self.header_var, anchor="center").grid(row=0, column=2, columnspan=3, sticky="ew")
        ttk.Button(nav, text=">", width=3, command=self._next_month).grid(row=0, column=5, padx=(8, 4))
        ttk.Button(nav, text=">>", width=3, command=self._next_year).grid(row=0, column=6)

        week_days = ttk.Frame(self, padding=(8, 0, 8, 0))
        week_days.grid(row=1, column=0, sticky="ew")
        week_days.grid_remove()

        self.calendar_frame = ttk.Frame(self, padding=(8, 4, 8, 4))
        self.calendar_frame.grid(row=2, column=0, sticky="nsew")
        for col in range(7):
            self.calendar_frame.grid_columnconfigure(col, weight=1, minsize=40)

        actions = ttk.Frame(self, padding=(8, 4, 8, 8))
        actions.grid(row=3, column=0, sticky="ew")
        ttk.Button(actions, text="Hoy", command=self._set_today).pack(side="left")
        ttk.Button(actions, text="Limpiar", command=self._clear).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Cancelar", command=self.destroy).pack(side="right")

    def _render_calendar(self) -> None:
        month_name = [
            "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
        ][self.current_month]
        self.header_var.set(f"{month_name} {self.current_year}")

        for child in self.calendar_frame.winfo_children():
            child.destroy()

        labels = ["L", "M", "X", "J", "V", "S", "D"]
        for col, lbl in enumerate(labels):
            ttk.Label(self.calendar_frame, text=lbl, anchor="center").grid(
                row=0, column=col, sticky="nsew", padx=2, pady=2
            )

        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdayscalendar(self.current_year, self.current_month)

        for r, week in enumerate(weeks):
            for c, day_num in enumerate(week):
                if day_num == 0:
                    ttk.Label(self.calendar_frame, text="", width=4).grid(
                        row=r + 1, column=c, sticky="nsew", padx=2, pady=2
                    )
                    continue
                ttk.Button(
                    self.calendar_frame,
                    text=str(day_num),
                    width=4,
                    command=lambda d=day_num: self._select_day(d),
                ).grid(row=r + 1, column=c, sticky="nsew", padx=2, pady=2)

    def _position_popup(self) -> None:
        self.update_idletasks()
        popup_w = self.winfo_reqwidth()
        popup_h = self.winfo_reqheight()
        x = self.anchor_widget.winfo_rootx()
        y = self.anchor_widget.winfo_rooty() + self.anchor_widget.winfo_height()

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        if x + popup_w > screen_w:
            x = max(0, screen_w - popup_w - 8)
        if y + popup_h > screen_h:
            y = max(0, self.anchor_widget.winfo_rooty() - popup_h)

        self.geometry(f"{popup_w}x{popup_h}+{x}+{y}")

    def _prev_month(self) -> None:
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        self._render_calendar()

    def _next_month(self) -> None:
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        self._render_calendar()

    def _prev_year(self) -> None:
        self.current_year -= 1
        self._render_calendar()

    def _next_year(self) -> None:
        self.current_year += 1
        self._render_calendar()

    def _select_day(self, day_num: int) -> None:
        self.target_var.set(f"{self.current_year:04d}-{self.current_month:02d}-{day_num:02d}")
        self.destroy()

    def _set_today(self) -> None:
        today = date.today()
        self.target_var.set(f"{today.year:04d}-{today.month:02d}-{today.day:02d}")
        self.destroy()

    def _clear(self) -> None:
        self.target_var.set("")
        self.destroy()
