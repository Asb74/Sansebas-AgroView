from __future__ import annotations

import importlib
import logging
from typing import Callable

from services.runtime_database_service import RuntimeDatabaseManager

logger = logging.getLogger(__name__)


def register_runtime_cache(name: str, clear_callback: Callable[[], None]) -> None:
    RuntimeDatabaseManager().register_cache(name, clear_callback)


def unregister_runtime_cache(name: str) -> None:
    RuntimeDatabaseManager().unregister_cache(name)


def clear_runtime_caches(reason: str = "snapshot_activated") -> int:
    """Invalidate every cache registered in the central runtime manager."""
    manager = RuntimeDatabaseManager()
    try:
        module = importlib.import_module("services.simulacion_asignacion")
        invalidar = getattr(module, "invalidar_cache_utilidad_stock", None)
        if callable(invalidar):
            manager.register_cache("services.simulacion_asignacion.invalidar_cache_utilidad_stock", invalidar)
    except Exception:
        logger.exception("No se pudo registrar caché de simulación/asignación")
    cleared = manager.invalidate_all(reason)
    logger.info("[RUNTIME] Cachés runtime limpiadas. motivo=%s total=%s", reason, cleared)
    return cleared
