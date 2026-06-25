from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def to_float_safe(value: Any, default: float = 0.0) -> float:
    """Convert common external numeric formats to float safely.

    Accepts Python numeric values and strings using either comma or dot as
    decimal separator, including thousands separators in the opposite style.
    Returns ``default`` when conversion is not possible.
    """
    if value is None:
        return float(default)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, Decimal)):
        try:
            return float(value)
        except Exception:
            logger.debug("No se pudo convertir a float el valor recibido: %r", value)
            return float(default)

    text = str(value).strip()
    if not text:
        return float(default)

    # Tolerate spaces frequently used as thousands separators.
    text = text.replace(" ", "")

    comma_pos = text.rfind(",")
    dot_pos = text.rfind(".")
    if comma_pos >= 0 and dot_pos >= 0:
        if comma_pos > dot_pos:
            # European style: 1.234,56
            text = text.replace(".", "").replace(",", ".")
        else:
            # US style: 1,234.56
            text = text.replace(",", "")
    elif comma_pos >= 0:
        text = text.replace(",", ".")

    try:
        return float(text)
    except Exception:
        logger.debug("No se pudo convertir a float el valor recibido: %r", value)
        return float(default)
