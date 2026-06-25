from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)


def clear_runtime_caches(reason: str = "snapshot_activated") -> None:
    """Best-effort invalidation for caches that depend on runtime SQLite paths/snapshots."""
    cleared: list[str] = []
    try:
        module = importlib.import_module("services.simulacion_asignacion")
        invalidar = getattr(module, "invalidar_cache_utilidad_stock", None)
        if callable(invalidar):
            invalidar()
            cleared.append("services.simulacion_asignacion.invalidar_cache_utilidad_stock")
    except Exception:
        logger.exception("No se pudo limpiar caché de simulación/asignación")

    logger.info("Cachés runtime limpiadas. motivo=%s caches=%s", reason, cleared or ["snapshot_identity_dependent"])
