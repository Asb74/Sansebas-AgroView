from __future__ import annotations

import logging
from typing import Any

from services.legacy_sync_service import CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE, LegacySyncService
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
            result = {"ok": ok, "errors": errors, "updated": ok, "using_previous_snapshot": (not ok and self.runtime_database_service.has_current_snapshot())}
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
            get_blocked_settings = getattr(self.legacy_sync_service, "get_central_sqlite_blocked_settings", None)
            blocked_settings = get_blocked_settings(active_only=True) if get_blocked_settings else []
            if blocked_settings:
                logger.error(
                    "Actualización legacy bloqueada por seguridad. configuraciones=%s recomendacion=%s",
                    [row.get("Nombre", "") for row in blocked_settings],
                    "Usar sincronización segura/staging",
                )
                return {
                    "ok": False,
                    "blocked": True,
                    "stopped": True,
                    "results": [],
                    "ok_count": 0,
                    "fail_count": len(blocked_settings),
                    "total": len(blocked_settings),
                    "error": CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE,
                    "blocked_settings": [row.get("Nombre", "") for row in blocked_settings],
                }
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
        if legacy.get("blocked"):
            logger.warning("Actualizar todo detenido: legacy activas bloqueadas por seguridad. No se continúa con runtime.")
            return {"ok": False, "partial": False, "blocked": True, "stopped": True, "legacy": legacy, "runtime": {"ok": False, "skipped": True}}
        runtime = self.update_runtime_snapshot()
        ok = bool(legacy.get("ok")) and bool(runtime.get("ok"))
        partial = bool(legacy.get("ok")) and bool(runtime.get("using_previous_snapshot"))
        if ok:
            logger.info("Fin actualización completa OK")
        elif partial:
            logger.warning("Actualización parcial en Actualizar todo: legacy OK, usando última foto local disponible. Runtime=%s", runtime)
        else:
            logger.warning("Fin actualización completa con errores. Legacy=%s Runtime=%s", legacy, runtime)
        return {"ok": ok, "partial": partial, "legacy": legacy, "runtime": runtime}
