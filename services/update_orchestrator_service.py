from __future__ import annotations

import logging
from typing import Any

from services.legacy_sync_service import CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE, LegacySyncService
from services.runtime_cache_service import clear_runtime_caches
from services.runtime_database_service import RuntimeDatabaseLockedError, RuntimeDatabaseService

logger = logging.getLogger(__name__)

ACCESS_UPDATE_SUCCESS_MESSAGE = "Se han actualizado los datos desde Access y se ha creado una nueva foto local."


class UpdateOrchestratorService:
    """Coordina operaciones explícitas y separadas de actualización de datos."""

    def __init__(
        self,
        legacy_sync_service: LegacySyncService | None = None,
        runtime_database_service: RuntimeDatabaseService | None = None,
    ) -> None:
        self.legacy_sync_service = legacy_sync_service or LegacySyncService()
        self.runtime_database_service = runtime_database_service or RuntimeDatabaseService()

    def update_local_snapshot_only(self) -> dict[str, Any]:
        """SQLite central -> snapshot local. No lee Access ni ejecuta legacy."""
        logger.info("Actualización foto local iniciada (solo SQLite central -> snapshot local)")
        result = self._create_snapshot(force=True, cache_reason="update_local_snapshot_only")
        if result.get("ok"):
            logger.info("Actualización foto local finalizada OK")
        else:
            logger.warning("Actualización foto local finalizada con errores: %s", result.get("errors"))
        return result

    def update_runtime_snapshot(self) -> dict[str, Any]:
        return self.update_local_snapshot_only()

    def update_from_access_then_snapshot(self) -> dict[str, Any]:
        """Access -> SQLite central con staging seguro -> snapshot local."""
        logger.info("Actualización desde Access iniciada (todas las tablas activas)")
        legacy = self.update_legacy_active(snapshot_after=False)
        if legacy.get("blocked"):
            logger.warning("Actualización desde Access detenida: legacy bloqueado por seguridad")
            return {"ok": False, "partial": False, "blocked": True, "stopped": True, "legacy": legacy, "runtime": {"ok": False, "skipped": True}}
        runtime = self._create_snapshot_after_legacy(legacy, "update_from_access_then_snapshot")
        ok = bool(legacy.get("ok")) and bool(runtime.get("ok"))
        partial = bool(legacy.get("ok")) and bool(runtime.get("using_previous_snapshot"))
        logger.info("Actualización desde Access finalizada. ok=%s partial=%s legacy=%s runtime=%s", ok, partial, legacy, runtime)
        return {"ok": ok, "partial": partial, "legacy": legacy, "runtime": runtime, "message": ACCESS_UPDATE_SUCCESS_MESSAGE if ok else ""}

    def update_selected_legacy_then_snapshot(self, setting_id: int) -> dict[str, Any]:
        logger.info("Tabla legacy ejecutada. setting_id=%s", setting_id)
        ok, msg = self.legacy_sync_service.sync_setting(setting_id)
        legacy = {"ok": ok, "message": msg, "results": [(setting_id, ok, msg)], "ok_count": 1 if ok else 0, "fail_count": 0 if ok else 1, "total": 1}
        runtime = self._create_snapshot_after_legacy(legacy, f"update_selected_legacy_then_snapshot:{setting_id}") if ok else {"ok": False, "skipped": True}
        return {"ok": bool(ok and runtime.get("ok")), "legacy": legacy, "runtime": runtime, "message": msg}

    def update_legacy_active(self, snapshot_after: bool = False) -> dict[str, Any]:
        logger.info("Inicio actualización legacy activas")
        try:
            get_blocked_settings = getattr(self.legacy_sync_service, "get_central_sqlite_blocked_settings", None)
            blocked_settings = get_blocked_settings(active_only=True) if get_blocked_settings else []
            if blocked_settings:
                logger.error("Actualización legacy bloqueada por seguridad. configuraciones=%s recomendacion=%s", [row.get("Nombre", "") for row in blocked_settings], "Usar sincronización segura/staging")
                return {"ok": False, "blocked": True, "stopped": True, "results": [], "ok_count": 0, "fail_count": len(blocked_settings), "total": len(blocked_settings), "error": CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE, "blocked_settings": [row.get("Nombre", "") for row in blocked_settings]}
            results = self.legacy_sync_service.sync_active_settings()
            logger.info("Tablas legacy ejecutadas: %s", [(sid, ok) for sid, ok, _ in results])
            ok_count = sum(1 for _, ok, _ in results if ok)
            fail_count = len(results) - ok_count
            result: dict[str, Any] = {"ok": fail_count == 0, "results": results, "ok_count": ok_count, "fail_count": fail_count, "total": len(results)}
            if snapshot_after and result["ok"]:
                result["runtime"] = self._create_snapshot_after_legacy(result, "update_legacy_active")
                result["ok"] = bool(result["runtime"].get("ok"))
            logger.info("Fin actualización legacy activas. OK=%s Fallidas=%s Total=%s", ok_count, fail_count, len(results))
            return result
        except Exception as exc:
            logger.exception("Error detallado en actualización legacy activas")
            return {"ok": False, "results": [], "ok_count": 0, "fail_count": 1, "total": 0, "error": str(exc)}

    def update_all(self) -> dict[str, Any]:
        logger.info("Inicio actualización completa")
        return self.update_from_access_then_snapshot()

    def _create_snapshot_after_legacy(self, legacy: dict[str, Any], reason: str) -> dict[str, Any]:
        if not legacy.get("ok"):
            logger.warning("Snapshot después de legacy omitido por errores. reason=%s", reason)
            return {"ok": False, "skipped": True}
        logger.info("Snapshot creado después de legacy iniciado. reason=%s", reason)
        runtime = self._create_snapshot(force=True, cache_reason=reason)
        logger.info("Snapshot creado después de legacy finalizado. reason=%s ok=%s", reason, runtime.get("ok"))
        return runtime

    def _create_snapshot(self, force: bool, cache_reason: str) -> dict[str, Any]:
        try:
            ok, errors = self.runtime_database_service.prepare_runtime_databases(force=force)
            result = {"ok": ok, "errors": errors, "updated": ok, "using_previous_snapshot": (not ok and self.runtime_database_service.has_current_snapshot())}
            if ok:
                clear_runtime_caches(cache_reason)
                logger.info("Cachés limpiadas tras activar snapshot. reason=%s", cache_reason)
            return result
        except RuntimeDatabaseLockedError as exc:
            logger.warning("Actualización foto local cancelada por bloqueo: %s", exc.locked_databases)
            return {"ok": False, "errors": [str(exc)], "updated": False, "error_type": "runtime_databases_locked", "locked_databases": exc.locked_databases}
        except Exception as exc:
            logger.exception("Error detallado creando foto local")
            return {"ok": False, "errors": [str(exc)], "updated": False}
