from __future__ import annotations

import logging
from typing import Any

from services.legacy_sync_service import LegacySyncService
from services.runtime_database_service import RuntimeDatabaseLockedError, RuntimeDatabaseService

logger = logging.getLogger(__name__)


class UpdateOrchestratorService:
    """Coordina las actualizaciones legacy y la foto local runtime."""

    def __init__(
        self,
        legacy_sync_service: LegacySyncService | None = None,
        runtime_database_service: RuntimeDatabaseService | None = None,
    ) -> None:
        self.legacy_sync_service = legacy_sync_service or LegacySyncService()
        self.runtime_database_service = runtime_database_service or RuntimeDatabaseService()

    def update_runtime_snapshot(self) -> dict[str, Any]:
        logger.info("Inicio actualización foto local")
        try:
            ok, errors = self.runtime_database_service.prepare_runtime_databases(force=True)
            result = {"ok": ok, "errors": errors, "updated": ok}
            if ok:
                logger.info("Fin actualización foto local OK")
            else:
                logger.warning("Fin actualización foto local con errores: %s", errors)
            return result
        except RuntimeDatabaseLockedError as exc:
            logger.warning("Actualización foto local cancelada por bloqueo: %s", exc.locked_databases)
            return {
                "ok": False,
                "errors": [str(exc)],
                "updated": False,
                "error_type": "runtime_databases_locked",
                "locked_databases": exc.locked_databases,
            }
        except Exception as exc:
            logger.exception("Error detallado en actualización foto local")
            return {"ok": False, "errors": [str(exc)], "updated": False}

    def update_legacy_active(self) -> dict[str, Any]:
        logger.info("Inicio actualización legacy activas")
        try:
            results = self.legacy_sync_service.sync_active_settings()
            ok_count = sum(1 for _, ok, _ in results if ok)
            fail_count = len(results) - ok_count
            result = {"ok": fail_count == 0, "results": results, "ok_count": ok_count, "fail_count": fail_count, "total": len(results)}
            if fail_count:
                logger.warning("Fin actualización legacy activas con errores. OK=%s Fallidas=%s Total=%s", ok_count, fail_count, len(results))
            else:
                logger.info("Fin actualización legacy activas OK. OK=%s Total=%s", ok_count, len(results))
            return result
        except Exception as exc:
            logger.exception("Error detallado en actualización legacy activas")
            return {"ok": False, "results": [], "ok_count": 0, "fail_count": 1, "total": 0, "error": str(exc)}

    def update_all(self) -> dict[str, Any]:
        logger.info("Inicio actualización completa")
        legacy = self.update_legacy_active()
        runtime = self.update_runtime_snapshot()
        ok = bool(legacy.get("ok")) and bool(runtime.get("ok"))
        partial = bool(legacy.get("ok")) and runtime.get("error_type") == "runtime_databases_locked"
        if ok:
            logger.info("Fin actualización completa OK")
        elif partial:
            logger.warning("Actualización parcial en Actualizar todo: legacy OK, foto local cancelada por bloqueo. Runtime=%s", runtime)
        else:
            logger.warning("Fin actualización completa con errores. Legacy=%s Runtime=%s", legacy, runtime)
        return {"ok": ok, "partial": partial, "legacy": legacy, "runtime": runtime}
