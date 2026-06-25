from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import shutil
from typing import Any

from config import CENTRAL_SQLITE_DIR, CURRENT_SNAPSHOT_FILE, RUNTIME_SQLITE_DIR, RUNTIME_SNAPSHOTS_DIR, SQLITE_DATABASES

logger = logging.getLogger(__name__)


class RuntimeDatabaseLockedError(RuntimeError):
    """Compatibilidad: ya no se usa para reemplazos de SQLite abiertos."""

    def __init__(self, locked_databases: list[str]) -> None:
        self.locked_databases = locked_databases
        super().__init__(f"Bases runtime bloqueadas/en uso: {', '.join(locked_databases)}")


class RuntimeDatabaseService:
    SUCCESS_MESSAGE = "Foto local actualizada correctamente."
    WARNING_MESSAGE = "No se pudo actualizar la foto local. Se usará la última foto disponible."
    ERROR_MESSAGE = "No se pudo preparar ninguna foto local de datos."
    INFO_FILE = "snapshot_info.txt"

    def __init__(self) -> None:
        self.central_dir = Path(CENTRAL_SQLITE_DIR)
        self.runtime_dir = Path(RUNTIME_SQLITE_DIR)
        self.snapshots_dir = Path(RUNTIME_SNAPSHOTS_DIR)
        self.current_snapshot_file = Path(CURRENT_SNAPSHOT_FILE)
        self.snapshot_file = self.current_snapshot_file

    def get_current_snapshot_dir(self) -> Path:
        snapshot_dir = self._resolve_current_snapshot_dir()
        if snapshot_dir is not None:
            return snapshot_dir
        ok, _errors = self.prepare_runtime_databases()
        if ok:
            snapshot_dir = self._resolve_current_snapshot_dir()
        if snapshot_dir is None:
            logger.error("No hay snapshot local activo disponible")
            raise RuntimeError("No hay snapshot local activo disponible")
        return snapshot_dir

    def get_runtime_path(self, db_name: str) -> Path:
        snapshot_dir = self.get_current_snapshot_dir()
        path = snapshot_dir / db_name
        logger.info("Ruta SQLite runtime resuelta: %s", path)
        return path

    def has_current_snapshot(self) -> bool:
        return self._resolve_current_snapshot_dir() is not None

    def prepare_runtime_databases(self, force: bool = False) -> tuple[bool, list[str]]:
        del force  # Se conserva por compatibilidad de llamadas existentes.
        try:
            snapshot_dir = self.create_new_snapshot()
            self.activate_snapshot(snapshot_dir)
            self.cleanup_old_snapshots(keep=3)
            return True, []
        except Exception as exc:
            logger.exception("No se pudo crear nueva foto local: %s", exc)
            latest = self._get_latest_valid_snapshot()
            if latest is not None:
                logger.warning("Usando último snapshot válido: %s", latest)
                if self._resolve_current_snapshot_dir() is None:
                    try:
                        self.activate_snapshot(latest)
                    except Exception:
                        logger.exception("No se pudo activar el último snapshot válido: %s", latest)
                return False, [str(exc)]
            return False, [str(exc) or self.ERROR_MESSAGE]

    def create_new_snapshot(self) -> Path:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = self.snapshots_dir / timestamp
        counter = 1
        while snapshot_dir.exists():
            snapshot_dir = self.snapshots_dir / f"{timestamp}_{counter:02d}"
            counter += 1
        logger.info("Creando snapshot local: %s", snapshot_dir)
        snapshot_dir.mkdir(parents=True)
        try:
            for db_name in SQLITE_DATABASES:
                source = self.central_dir / db_name
                destination = snapshot_dir / db_name
                logger.info("Copiando base SQLite a snapshot: %s -> %s", source, destination)
                if not source.exists():
                    raise FileNotFoundError(f"No se encontró la base central: {source}")
                shutil.copy2(source, destination)
            self._write_snapshot_info(snapshot_dir)
            return snapshot_dir
        except Exception:
            if snapshot_dir.exists():
                shutil.rmtree(snapshot_dir, ignore_errors=True)
                logger.warning("Snapshot incompleto eliminado: %s", snapshot_dir)
            raise

    def activate_snapshot(self, snapshot_dir: Path) -> None:
        snapshot_dir = Path(snapshot_dir)
        if not self._is_valid_snapshot(snapshot_dir):
            raise RuntimeError(f"Snapshot inválido o incompleto: {snapshot_dir}")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.current_snapshot_file.write_text(snapshot_dir.name, encoding="utf-8")
        logger.info("Snapshot activado: %s", snapshot_dir)

    def get_snapshot_info(self) -> dict[str, Any]:
        snapshot_dir = self.get_current_snapshot_dir()
        if snapshot_dir is None:
            return {"timestamp": None, "label": "Foto de datos: No disponible", "path": None}
        info_file = snapshot_dir / self.INFO_FILE
        timestamp = snapshot_dir.name.split("_")
        raw_timestamp = "_".join(timestamp[:2]) if len(timestamp) >= 2 else snapshot_dir.name
        if info_file.exists():
            for line in info_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("created_at="):
                    raw_timestamp = line.split("=", 1)[1].strip()
                    break
        label = "Foto de datos: No disponible"
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y%m%d_%H%M%S"):
            try:
                dt = datetime.strptime(raw_timestamp, fmt)
                label = f"Foto de datos: {dt.strftime('%d/%m/%Y %H:%M')}"
                break
            except ValueError:
                continue
        return {"timestamp": raw_timestamp, "label": label, "path": str(snapshot_dir)}

    def cleanup_old_snapshots(self, keep: int = 3) -> None:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        valid = [p for p in self.snapshots_dir.iterdir() if p.is_dir() and self._is_valid_snapshot(p)]
        valid.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in valid[max(keep, 1):]:
            shutil.rmtree(old, ignore_errors=True)
            logger.info("Snapshot antiguo eliminado: %s", old)

    def _resolve_current_snapshot_dir(self) -> Path | None:
        if self.current_snapshot_file.exists():
            snapshot_name = self.current_snapshot_file.read_text(encoding="utf-8").strip()
            if snapshot_name:
                snapshot_dir = Path(snapshot_name)
                if not snapshot_dir.is_absolute():
                    snapshot_dir = self.snapshots_dir / snapshot_name
                if self._is_valid_snapshot(snapshot_dir):
                    return snapshot_dir
                logger.warning("Snapshot activo inválido o incompleto: %s", snapshot_dir)
        latest = self._get_latest_valid_snapshot()
        if latest is not None:
            logger.warning("Usando último snapshot válido: %s", latest)
        return latest

    def _write_snapshot_info(self, snapshot_dir: Path) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        lines = [f"created_at={now}", f"source_dir={self.central_dir}", "databases=" + ",".join(SQLITE_DATABASES)]
        (snapshot_dir / self.INFO_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _is_valid_snapshot(self, snapshot_dir: Path) -> bool:
        return snapshot_dir.is_dir() and all((snapshot_dir / db_name).exists() for db_name in SQLITE_DATABASES)

    def _get_latest_valid_snapshot(self) -> Path | None:
        if not self.snapshots_dir.exists():
            return None
        valid = [p for p in self.snapshots_dir.iterdir() if p.is_dir() and self._is_valid_snapshot(p)]
        if not valid:
            return None
        return max(valid, key=lambda p: p.stat().st_mtime)
