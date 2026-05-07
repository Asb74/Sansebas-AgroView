from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class _Target:
    artist: Any
    label: str
    points: list[dict[str, Any]]


class ChartTooltipController:
    def __init__(self, ax, canvas, formatter: Callable[[dict[str, Any]], str]) -> None:
        self.ax = ax
        self.canvas = canvas
        self.figure = ax.figure
        self.formatter = formatter
        self.targets: list[_Target] = []

        self.hover_annotation = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(12, 12),
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="lightyellow", ec="#999999", alpha=0.95),
            arrowprops=dict(arrowstyle="->", color="#999999"),
            zorder=10,
        )
        self.hover_annotation.set_clip_on(False)
        self.hover_annotation.set_visible(False)

        self.fixed_annotation = None

        self.canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.canvas.mpl_connect("button_press_event", self._on_click)

    def set_targets(self, targets: list[tuple[Any, str, list[dict[str, Any]]]]) -> None:
        self.targets = [_Target(artist=t[0], label=t[1], points=t[2]) for t in targets]
        if self.fixed_annotation is not None:
            self.fixed_annotation.remove()
            self.fixed_annotation = None
        self.hover_annotation.set_visible(False)

    def _hit_test(self, event) -> tuple[_Target, int] | None:
        for target in self.targets:
            contains, info = target.artist.contains(event)
            if not contains:
                continue
            idx = 0
            if info and info.get("ind"):
                idx = int(info["ind"][0])
            if idx < len(target.points):
                return target, idx
        return None

    def _anchor_xy(self, target: _Target, idx: int) -> tuple[float, float]:
        artist = target.artist
        if hasattr(artist, "get_xdata") and hasattr(artist, "get_ydata"):
            x = artist.get_xdata()[idx]
            y = artist.get_ydata()[idx]
            return float(x), float(y)
        if hasattr(artist, "get_x") and hasattr(artist, "get_width") and hasattr(artist, "get_y") and hasattr(artist, "get_height"):
            x = artist.get_x() + artist.get_width() / 2.0
            y = artist.get_y() + artist.get_height()
            return float(x), float(y)
        return 0.0, 0.0

    def _tooltip_offset(self, event) -> tuple[int, int]:
        xoff, yoff = 15, 30
        canvas_w, canvas_h = self.figure.canvas.get_width_height()

        if event.x is not None and event.x > canvas_w * 0.75:
            xoff = -180
        elif event.x is not None and event.x < canvas_w * 0.20:
            xoff = 20

        if event.y is not None and event.y > canvas_h * 0.50:
            yoff = -60
        else:
            yoff = 30

        if event.y is not None and event.y > canvas_h * 0.85:
            yoff = -90
        elif event.y is not None and event.y < canvas_h * 0.15:
            yoff = 35

        legend = self.ax.get_legend()
        if legend is not None and event.x is not None and event.y is not None:
            try:
                bbox = legend.get_window_extent()
                if bbox.contains(event.x, event.y):
                    xoff = -160 if event.x > canvas_w * 0.5 else 24
                    yoff = -70
            except Exception:
                pass
        return xoff, yoff

    def _on_hover(self, event) -> None:
        if event.inaxes != self.ax:
            if self.hover_annotation.get_visible():
                self.hover_annotation.set_visible(False)
                self.canvas.draw_idle()
            return

        hit = self._hit_test(event)
        if hit is None:
            if self.hover_annotation.get_visible():
                self.hover_annotation.set_visible(False)
                self.canvas.draw_idle()
            return

        target, idx = hit
        payload = dict(target.points[idx])
        payload.setdefault("serie", target.label)
        ax_x, ax_y = self._anchor_xy(target, idx)
        self.hover_annotation.xy = (ax_x, ax_y)
        self.hover_annotation.xyann = self._tooltip_offset(event)
        self.hover_annotation.set_text(self.formatter(payload))
        self.hover_annotation.set_visible(True)
        self.canvas.draw_idle()

    def _on_click(self, event) -> None:
        if event.inaxes != self.ax:
            if self.fixed_annotation is not None:
                self.fixed_annotation.remove()
                self.fixed_annotation = None
            if self.hover_annotation.get_visible():
                self.hover_annotation.set_visible(False)
            self.canvas.draw_idle()
            return

        hit = self._hit_test(event)
        if hit is None:
            if self.fixed_annotation is not None:
                self.fixed_annotation.remove()
                self.fixed_annotation = None
                self.canvas.draw_idle()
            return

        target, idx = hit
        payload = dict(target.points[idx])
        payload.setdefault("serie", target.label)
        ax_x, ax_y = self._anchor_xy(target, idx)

        if self.fixed_annotation is not None:
            self.fixed_annotation.remove()
        self.fixed_annotation = self.ax.annotate(
            self.formatter(payload),
            xy=(ax_x, ax_y),
            xytext=self._tooltip_offset(event),
            textcoords="offset points",
            bbox=dict(boxstyle="round", fc="lightyellow", ec="#666666", alpha=0.95),
            arrowprops=dict(arrowstyle="->", color="#666666"),
            zorder=11,
        )
        self.fixed_annotation.set_clip_on(False)
        self.canvas.draw_idle()
