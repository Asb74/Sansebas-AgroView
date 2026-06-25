from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from config import CENTRAL_SQLITE_DIR, RUNTIME_SQLITE_DIR, RUNTIME_SNAPSHOT_FILE, SQLITE_DATABASES

logger = logging.getLogger(__name__)


class RuntimeDatabaseLockedError(RuntimeError):
    """Error controlado cuando una o varias bases runtime están en uso."""

    def __init__(self, locked_databases: list[str]) -> None:
        self.locked_databases = locked_databases
        super().__init__(f"Bases runtime bloqueadas/en uso: {', '.join(locked_databases)}")


class RuntimeDatabaseService:
    WARNING_MESSAGE = "No se pudo actualizar la foto local. Se usará la última copia disponible."

    def __init__(self) -> None:
        self.central_dir = Path(CENTRAL_SQLITE_DIR)
        self.runtime_dir = Path(RUNTIME_SQLITE_DIR)
        self.snapshot_file = Path(RUNTIME_SNAPSHOT_FILE)

    def prepare_runtime_databases(self, force: bool = False) -> tuple[bool, list[str]]:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        locked_databases = self.validate_runtime_databases_available()
        if locked_databases:
            logger.warning("Actualización foto local cancelada por bloqueo. Bases bloqueadas: %s", locked_databases)
            raise RuntimeDatabaseLockedError(locked_databases)

        errors: list[str] = []
        updated_any = False
        for db_name in SQLITE_DATABASES:
            ok = self.copy_database_to_runtime(db_name)
            updated_any = updated_any or ok
            if not ok:
                errors.append(db_name)
        if (updated_any and not errors) or force:
            self._write_snapshot_info()
        return len(errors) == 0, errors

    def validate_runtime_databases_available(self) -> list[str]:
        locked_databases = [db_name for db_name in SQLITE_DATABASES if self.is_runtime_database_locked(db_name)]
        if locked_databases:
            logger.warning("Bases runtime bloqueadas detectadas: %s", locked_databases)
        return locked_databases

    def is_runtime_database_locked(self, db_name: str) -> bool:
        runtime_path = self.get_runtime_path(db_name)
        if not runtime_path.exists():
            return False

        try:
            runtime_path.rename(runtime_path)
        except OSError as exc:
            logger.warning("Base runtime en uso detectada por comprobación de renombrado: %s (%s)", db_name, exc)
            return True

        uri = f"file:{runtime_path.as_posix()}?mode=rw"
        try:
            with sqlite3.connect(uri, uri=True, timeout=0) as conn:
                conn.execute("PRAGMA query_only = 1")
                conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                logger.warning("Base runtime en uso detectada por SQLite: %s (%s)", db_name, exc)
                return True
            logger.warning("No se pudo validar disponibilidad SQLite de %s: %s", db_name, exc)
            return True
        except OSError as exc:
            logger.warning("No se pudo validar disponibilidad del archivo runtime %s: %s", db_name, exc)
            return True
        return False

    def copy_database_to_runtime(self, db_name: str) -> bool:
        source = self.central_dir / db_name
        runtime_path = self.get_runtime_path(db_name)
        tmp_path = runtime_path.with_suffix(runtime_path.suffix + ".tmp")
        try:
            shutil.copy2(source, tmp_path)
            tmp_path.replace(runtime_path)
            logger.info("Runtime DB actualizada: %s", runtime_path)
            return True
        except PermissionError as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            logger.error("Permiso denegado al reemplazar runtime DB %s. Es probable que esté en uso: %s", db_name, exc)
            if runtime_path.exists():
                return False
            raise
        except Exception as exc:
            logger.exception("No se pudo copiar %s a runtime: %s", db_name, exc)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            if runtime_path.exists():
                return False
            raise

    def get_runtime_path(self, db_name: str) -> Path:
        return self.runtime_dir / db_name

    def get_snapshot_info(self) -> dict[str, Any]:
        if not self.snapshot_file.exists():
            return {"timestamp": None, "label": "Foto de datos: No disponible"}
        timestamp = self.snapshot_file.read_text(encoding="utf-8").strip()
        if not timestamp:
            return {"timestamp": None, "label": "Foto de datos: No disponible"}
        try:
            dt = datetime.fromisoformat(timestamp)
            return {"timestamp": timestamp, "label": f"Foto de datos: {dt.strftime('%d/%m/%Y %H:%M')}"}
        except ValueError:
            return {"timestamp": timestamp, "label": "Foto de datos: No disponible"}

    def _write_snapshot_info(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.snapshot_file.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
