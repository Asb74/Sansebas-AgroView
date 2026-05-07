from __future__ import annotations

import logging
from pathlib import Path
import tkinter as tk

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "images"
_LOGO_MAP = {
    "256": "logo_256.png",
    "64": "logo_64.png",
    "32": "logo_32.png",
}


def get_logo(size: str = "64", master: tk.Misc | None = None) -> tk.PhotoImage | None:
    filename = _LOGO_MAP.get(str(size), _LOGO_MAP["64"])
    path = _ASSETS_DIR / filename
    if not path.exists():
        logger.warning("Logo no encontrado: %s", path)
        return None
    try:
        return tk.PhotoImage(master=master, file=str(path))
    except Exception as exc:
        logger.warning("No se pudo cargar logo %s: %s", path, exc)
        return None
