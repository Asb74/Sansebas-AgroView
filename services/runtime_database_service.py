from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import contextvars
import hashlib
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import threading
from time import perf_counter, sleep
from typing import Any, Callable

from config import CENTRAL_SQLITE_DIR, CURRENT_SNAPSHOT_FILE, RUNTIME_SQLITE_DIR, RUNTIME_SNAPSHOTS_DIR, SQLITE_DATABASES

logger = logging.getLogger(__name__)

DIAG_SNAPSHOT_PEDIDOS = True
DEBUG_KEEP_FAILED_BUILDING = True
DEBUG_PEDIDOS_COMPARE = True
_RUNTIME_OPERATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("runtime_operation_id", default=None)
SNAPSHOT_CHECKSUM_MAX_BYTES = 200 * 1024 * 1024


def make_operation_id(operation_name: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in operation_name)
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{safe}"

def set_runtime_operation_id(operation_id: str | None):
    return _RUNTIME_OPERATION_ID.set(operation_id)

def reset_runtime_operation_id(token) -> None:
    _RUNTIME_OPERATION_ID.reset(token)

def get_runtime_operation_id() -> str | None:
    return _RUNTIME_OPERATION_ID.get()

def _path_meta(path: Path) -> dict[str, Any]:
    try:
        exists = path.exists()
        st = path.stat() if exists else None
        return {"path": str(path), "exists": exists, "size": st.st_size if st else 0, "mtime": st.st_mtime if st else 0.0}
    except Exception as exc:
        return {"path": str(path), "error": str(exc)}


class RuntimeDatabaseLockedError(RuntimeError):
    def __init__(self, locked_databases: list[str]) -> None:
        self.locked_databases = locked_databases
        super().__init__(f"Bases runtime bloqueadas/en uso: {', '.join(locked_databases)}")


class RuntimeState(str, Enum):
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    UPDATING = "UPDATING"
    SWITCHING_SNAPSHOT = "SWITCHING_SNAPSHOT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RuntimeChangedEvent:
    previous_snapshot: Path | None
    current_snapshot: Path
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    caches_cleared: int
    connections_closed: int
    connections_opened: int
    reason: str


class RuntimeDatabaseManager:
    """Central runtime coordinator for active snapshots, SQLite connections and caches."""

    _instance: "RuntimeDatabaseManager | None" = None
    _instance_lock = threading.RLock()
    INFO_FILE = "snapshot_info.txt"

    def __new__(cls) -> "RuntimeDatabaseManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self.central_dir = Path(CENTRAL_SQLITE_DIR)
        self.runtime_dir = Path(RUNTIME_SQLITE_DIR)
        self.snapshots_dir = Path(RUNTIME_SNAPSHOTS_DIR)
        self.current_snapshot_file = Path(CURRENT_SNAPSHOT_FILE)
        self.snapshot_file = self.current_snapshot_file
        self._state = RuntimeState.INITIALIZING
        self._lock = threading.RLock()
        self._connections: dict[str, sqlite3.Connection] = {}
        self._cache_registry: dict[str, Callable[[], None]] = {}
        self._listeners: dict[str, Callable[[RuntimeChangedEvent], None]] = {}
        self._connections_opened = 0
        self._initialized = True
        self._set_state(RuntimeState.READY, "manager_initialized")

    def _set_state(self, new_state: RuntimeState, reason: str) -> None:
        old_state = getattr(self, "_state", RuntimeState.INITIALIZING)
        self._state = new_state
        logger.info("[RUNTIME] Estado anterior=%s Estado nuevo=%s reason=%s", old_state.value, new_state.value, reason)

    @property
    def state(self) -> RuntimeState:
        return self._state

    def register_cache(self, name: str, clear_callback: Callable[[], None]) -> None:
        with self._lock:
            self._cache_registry[name] = clear_callback
            logger.info("[RUNTIME] Caché registrada: %s", name)

    def unregister_cache(self, name: str) -> None:
        with self._lock:
            self._cache_registry.pop(name, None)
            logger.info("[RUNTIME] Caché desregistrada: %s", name)

    def subscribe(self, name: str, callback: Callable[[RuntimeChangedEvent], None]) -> None:
        with self._lock:
            self._listeners[name] = callback
            logger.info("[RUNTIME] Listener registrado: %s", name)

    def unsubscribe(self, name: str) -> None:
        with self._lock:
            self._listeners.pop(name, None)
            logger.info("[RUNTIME] Listener desregistrado: %s", name)

    def get_current_snapshot_dir(self) -> Path:
        snapshot_dir = self._resolve_current_snapshot_dir()
        if snapshot_dir is not None:
            return snapshot_dir
        ok, _errors = self.prepare_runtime_databases()
        if ok:
            snapshot_dir = self._resolve_current_snapshot_dir()
        if snapshot_dir is None:
            self._set_state(RuntimeState.ERROR, "missing_active_snapshot")
            raise RuntimeError("No hay snapshot local activo disponible")
        return snapshot_dir

    def get_runtime_path(self, db_name: str) -> Path:
        snapshot_dir = self.get_current_snapshot_dir()
        path = snapshot_dir / db_name
        current_value = self.current_snapshot_file.read_text(encoding="utf-8").strip() if self.current_snapshot_file.exists() else ""
        meta = _path_meta(path)
        logger.info("[DATA_PATH] op_id=%s db_name=%s snapshot_dir=%s path=%s exists=%s size=%s mtime=%s current_snapshot_file=%s current_snapshot_value=%s thread=%s", get_runtime_operation_id(), db_name, snapshot_dir, path, meta.get("exists"), meta.get("size"), meta.get("mtime"), self.current_snapshot_file, current_value, threading.current_thread().name)
        logger.info("[RUNTIME] Snapshot utilizado=%s Ruta SQLite utilizada=%s", snapshot_dir, path)
        return path

    def get_connection(self, db_name: str) -> sqlite3.Connection:
        with self._lock:
            path = self.get_runtime_path(db_name)
            key = str(path.resolve())
            conn = self._connections.get(key)
            if conn is None:
                conn = sqlite3.connect(path)
                conn.row_factory = sqlite3.Row
                self._connections[key] = conn
                self._connections_opened += 1
                logger.info("[DATA_CONN] db_name=%s path=%s action=open_new connection_key=%s snapshot_dir=%s thread=%s", db_name, path, key, path.parent, threading.current_thread().name)
                logger.info("[RUNTIME] Snapshot utilizado=%s Ruta SQLite utilizada=%s Abrió nueva conexión", path.parent, path)
            else:
                logger.info("[DATA_CONN] db_name=%s path=%s action=reuse connection_key=%s snapshot_dir=%s thread=%s", db_name, path, key, path.parent, threading.current_thread().name)
                logger.info("[RUNTIME] Snapshot utilizado=%s Ruta SQLite utilizada=%s Reutilizó conexión", path.parent, path)
            return conn

    def close_connections(self) -> int:
        with self._lock:
            items = list(self._connections.items())
            self._connections.clear()
        closed = 0
        for key, conn in items:
            try:
                conn.close()
                closed += 1
            except Exception:
                logger.exception("[RUNTIME] No se pudo cerrar conexión: %s", key)
        logger.info("[RUNTIME] Conexiones cerradas=%s", closed)
        return closed

    def invalidate_all(self, reason: str = "runtime_changed") -> int:
        cleared = 0
        with self._lock:
            callbacks = list(self._cache_registry.items())
        for name, callback in callbacks:
            try:
                callback()
                cleared += 1
                logger.info("[RUNTIME] Caché limpiada: %s reason=%s", name, reason)
            except Exception:
                logger.exception("[RUNTIME] No se pudo limpiar caché: %s", name)
        return cleared

    def notify_runtime_changed(self, event: RuntimeChangedEvent) -> None:
        with self._lock:
            listeners = list(self._listeners.items())
        for name, callback in listeners:
            try:
                callback(event)
                logger.info("[RUNTIME] Listener notificado: %s", name)
            except Exception:
                logger.exception("[RUNTIME] Error notificando listener: %s", name)

    def has_current_snapshot(self) -> bool:
        return self._resolve_current_snapshot_dir() is not None


    def debug_open_connections(self) -> list[str]:
        with self._lock:
            keys = list(self._connections.keys())
        rows: list[str] = []
        for key in keys:
            try:
                p = Path(key)
                snapshot = p.parent.name if p.parent else ""
                rows.append(f"key={key} path={p} snapshot={snapshot}")
            except Exception:
                rows.append(str(key))
        return rows

    def debug_snapshot_dirs(self) -> dict[str, Any]:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        dirs = [p for p in self.snapshots_dir.iterdir() if p.is_dir()] if self.snapshots_dir.exists() else []
        current_value = self.current_snapshot_file.read_text(encoding="utf-8").strip() if self.current_snapshot_file.exists() else ""
        resolved = self._resolve_current_snapshot_dir()
        return {"valid_snapshots": [p.name for p in dirs if not p.name.startswith("__building_") and self._is_valid_snapshot(p)], "building_snapshots": [p.name for p in dirs if p.name.startswith("__building_")], "current_snapshot_file_value": current_value, "resolved_current_snapshot": str(resolved) if resolved else None}

    def prepare_runtime_databases(self, force: bool = False, reason: str = "prepare_runtime_databases", operation_id: str | None = None) -> tuple[bool, list[str]]:
        op_id = operation_id or get_runtime_operation_id() or make_operation_id(reason)
        token = set_runtime_operation_id(op_id)
        started_at = datetime.now()
        t0 = perf_counter()
        previous = self._resolve_current_snapshot_dir()
        connections_opened_before = self._connections_opened
        closed = 0
        cleared = 0
        listeners_notified = 0
        try:
            logger.info("[RUNTIME_TRACE] op_id=%s evento=START_PREPARE force=%s reason=%s state_before=%s central_dir=%s runtime_dir=%s snapshots_dir=%s current_snapshot_file=%s current_snapshot_value_before=%s resolved_snapshot_before=%s snapshot_dirs=%s thread=%s", op_id, force, reason, self.state.value, self.central_dir, self.runtime_dir, self.snapshots_dir, self.current_snapshot_file, self.current_snapshot_file.read_text(encoding="utf-8").strip() if self.current_snapshot_file.exists() else "", previous, self.debug_snapshot_dirs(), threading.current_thread().name)
            self._set_state(RuntimeState.UPDATING, reason)
            if not force and previous is not None and not self.central_sqlite_is_newer_than_snapshot(previous):
                self._set_state(RuntimeState.READY, "snapshot_already_current")
                logger.info("[RUNTIME_TRACE] op_id=%s evento=END_PREPARE_OK duration=%.3fs snapshot_previous=%s snapshot_current=%s caches_cleared=%s connections_closed=%s listeners_notified=%s snapshot_dirs=%s", op_id, perf_counter() - t0, previous, previous, cleared, closed, listeners_notified, self.debug_snapshot_dirs())
                return True, []
            logger.info("[RUNTIME_TRACE] op_id=%s evento=BEFORE_CLEANUP_BUILDING building_dirs=%s", op_id, self.debug_snapshot_dirs().get("building_snapshots"))
            self.cleanup_building_snapshots()
            logger.info("[RUNTIME_TRACE] op_id=%s evento=AFTER_CLEANUP_BUILDING building_dirs=%s", op_id, self.debug_snapshot_dirs().get("building_snapshots"))
            logger.info("[RUNTIME_TRACE] op_id=%s evento=BEFORE_CREATE_NEW_SNAPSHOT open_connections=%s cache_registry=%s", op_id, self.debug_open_connections(), list(self._cache_registry.keys()))
            snapshot_dir = self.create_new_snapshot(operation_id=op_id)
            logger.info("[RUNTIME_TRACE] op_id=%s evento=AFTER_CREATE_NEW_SNAPSHOT snapshot_dir=%s snapshot_name=%s exists=%s is_building=%s", op_id, snapshot_dir, snapshot_dir.name, snapshot_dir.exists(), snapshot_dir.name.startswith("__building_"))
            if snapshot_dir.name.startswith("__building_"):
                raise RuntimeError("create_new_snapshot devolvió un snapshot temporal __building")
            if not snapshot_dir.exists():
                raise RuntimeError(f"Snapshot publicado no existe: {snapshot_dir}")
            self._verify_snapshot_integrity(snapshot_dir)
            self._set_state(RuntimeState.SWITCHING_SNAPSHOT, reason)
            logger.info("[RUNTIME_TRACE] op_id=%s evento=BEFORE_CLOSE_CONNECTIONS open_connections=%s", op_id, self.debug_open_connections())
            closed = self.close_connections()
            logger.info("[RUNTIME_TRACE] op_id=%s evento=AFTER_CLOSE_CONNECTIONS closed=%s open_connections=%s", op_id, closed, self.debug_open_connections())
            before_value = self.current_snapshot_file.read_text(encoding="utf-8").strip() if self.current_snapshot_file.exists() else ""
            logger.info("[RUNTIME_TRACE] op_id=%s evento=BEFORE_ACTIVATE snapshot_dir=%s current_snapshot_value_before=%s", op_id, snapshot_dir, before_value)
            self._activate_snapshot_file(snapshot_dir)
            current_snapshot_name = self.current_snapshot_file.read_text(encoding="utf-8").strip()
            active_after = self._resolve_current_snapshot_dir()
            logger.info("[RUNTIME_TRACE] op_id=%s evento=AFTER_ACTIVATE current_snapshot_value_after=%s resolved_snapshot_after=%s", op_id, current_snapshot_name, active_after)
            if DEBUG_PEDIDOS_COMPARE:
                self.debug_compare_dbpedidos_record(operation_id=op_id)
            if current_snapshot_name != snapshot_dir.name:
                raise RuntimeError(f"CURRENT_SNAPSHOT_FILE apunta a {current_snapshot_name!r}, no a {snapshot_dir.name!r}")
            cleared = self.invalidate_all(reason)
            event = RuntimeChangedEvent(previous, snapshot_dir, started_at, datetime.now(), perf_counter() - t0, cleared, closed, self._connections_opened - connections_opened_before, reason)
            self.notify_runtime_changed(event)
            listeners_notified = len(self._listeners)
            self.cleanup_old_snapshots(keep=3)
            self._set_state(RuntimeState.READY, "snapshot_switch_ok")
            logger.info("[RUNTIME_TRACE] op_id=%s evento=END_PREPARE_OK duration=%.3fs snapshot_previous=%s snapshot_current=%s caches_cleared=%s connections_closed=%s listeners_notified=%s snapshot_dirs=%s", op_id, event.duration_seconds, previous, snapshot_dir, cleared, closed, listeners_notified, self.debug_snapshot_dirs())
            return True, []
        except Exception as exc:
            self._set_state(RuntimeState.ERROR, reason)
            logger.exception("[RUNTIME_TRACE] op_id=%s evento=END_PREPARE_ERROR duration=%.3fs error_type=%s error=%s traceback=see_exc_info snapshot_previous=%s current_snapshot_value=%s resolved_snapshot_after_error=%s building_dirs_remaining=%s", op_id, perf_counter() - t0, type(exc).__name__, exc, previous, self.current_snapshot_file.read_text(encoding="utf-8").strip() if self.current_snapshot_file.exists() else "", self._resolve_current_snapshot_dir(), self.debug_snapshot_dirs().get("building_snapshots"))
            self._set_state(RuntimeState.READY if previous else RuntimeState.ERROR, "fallback_previous_snapshot")
            return (False, [str(exc) or RuntimeDatabaseService.ERROR_MESSAGE])
        finally:
            reset_runtime_operation_id(token)

    def create_new_snapshot(self, operation_id: str | None = None) -> Path:
        """Build and publish a complete snapshot from the central SQLite directory only."""
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        op_id = operation_id or get_runtime_operation_id() or make_operation_id("create_new_snapshot")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_dir = self.snapshots_dir / timestamp
        building_dir = self.snapshots_dir / f"__building_{timestamp}"
        counter = 1
        while final_dir.exists() or building_dir.exists():
            suffix = f"{counter:02d}"
            final_dir = self.snapshots_dir / f"{timestamp}_{suffix}"
            building_dir = self.snapshots_dir / f"__building_{timestamp}_{suffix}"
            counter += 1
        logger.info("[RUNTIME] Creando snapshot local atómico: build=%s final=%s origen_central=%s", building_dir, final_dir, self.central_dir)
        logger.info("[SNAPSHOT_PUBLISH] build_dir=%s", building_dir)
        logger.info("[SNAPSHOT_PUBLISH] final_dir=%s", final_dir)
        logger.info("[SNAPSHOT_TRACE] op_id=%s evento=START_CREATE timestamp=%s building_dir=%s final_dir=%s central_dir=%s sqlite_databases=%s", op_id, timestamp, building_dir, final_dir, self.central_dir, SQLITE_DATABASES)
        building_dir.mkdir(parents=True)
        try:
            for db_name in SQLITE_DATABASES:
                self._copy_central_sqlite_to_snapshot(db_name, building_dir, operation_id=op_id)
                if DEBUG_PEDIDOS_COMPARE and db_name == "DBPedidos.sqlite":
                    self.debug_compare_dbpedidos_record(operation_id=op_id)
            self._write_snapshot_info(building_dir)
            logger.info("[SNAPSHOT_TRACE] op_id=%s evento=BEFORE_VERIFY_BUILDING building_dir=%s", op_id, building_dir)
            verify_t0 = perf_counter()
            self._verify_snapshot_files_complete(building_dir)
            logger.info("[SNAPSHOT_TRACE] op_id=%s evento=AFTER_VERIFY_BUILDING building_dir=%s duration=%.3fs", op_id, building_dir, perf_counter() - verify_t0)
            logger.info("[SNAPSHOT_TRACE] op_id=%s evento=BEFORE_RENAME building_dir=%s final_dir=%s building_exists=%s final_exists=%s open_connections=%s dir_listing_before=%s", op_id, building_dir, final_dir, building_dir.exists(), final_dir.exists(), self.debug_open_connections(), [p.name for p in self.snapshots_dir.iterdir()] if self.snapshots_dir.exists() else [])
            last_exc = None
            for attempt in range(1, 11):
                logger.info("[SNAPSHOT_TRACE] op_id=%s evento=RENAME_ATTEMPT attempt=%s building_exists=%s final_exists=%s", op_id, attempt, building_dir.exists(), final_dir.exists())
                try:
                    building_dir.rename(final_dir)
                    logger.info("[SNAPSHOT_TRACE] op_id=%s evento=AFTER_RENAME attempt=%s building_exists=%s final_exists=%s final_dir=%s dir_listing_after=%s", op_id, attempt, building_dir.exists(), final_dir.exists(), final_dir, [p.name for p in self.snapshots_dir.iterdir()] if self.snapshots_dir.exists() else [])
                    last_exc = None
                    break
                except (OSError, PermissionError) as rename_exc:
                    last_exc = rename_exc
                    logger.warning("[SNAPSHOT_TRACE] op_id=%s evento=RENAME_ATTEMPT_ERROR attempt=%s error_type=%s errno=%s winerror=%s error=%s", op_id, attempt, type(rename_exc).__name__, getattr(rename_exc, "errno", None), getattr(rename_exc, "winerror", None), rename_exc)
                    sleep(0.1)
            if last_exc is not None:
                logger.exception("[SNAPSHOT_TRACE] op_id=%s evento=RENAME_FAILED_FINAL attempts=10 building_exists=%s final_exists=%s error_type=%s errno=%s winerror=%s error=%s traceback=see_exc_info", op_id, building_dir.exists(), final_dir.exists(), type(last_exc).__name__, getattr(last_exc, "errno", None), getattr(last_exc, "winerror", None), last_exc)
                raise RuntimeError(f"No se pudo publicar el snapshot final {final_dir.name}; no se activó la nueva foto local") from last_exc
            if building_dir.exists() or not final_dir.exists():
                raise RuntimeError(f"Publicación inconsistente: build_exists={building_dir.exists()} final_exists={final_dir.exists()}")
            self._verify_snapshot_integrity(final_dir)
            logger.info("[SNAPSHOT_AUDIT] publicación_atómica=OK build=%s final=%s", building_dir, final_dir)
            self._log_pedidos_snapshot_diagnostic(self.central_dir / "DBPedidos.sqlite", final_dir / "DBPedidos.sqlite", publish=True)
            if DEBUG_PEDIDOS_COMPARE:
                self.debug_compare_dbpedidos_record(operation_id=op_id)
            active_after = self._resolve_current_snapshot_dir()
            logger.info("[SNAPSHOT_PUBLISH] current_snapshot_file=%s", self.current_snapshot_file)
            logger.info("[SNAPSHOT_PUBLISH] active_snapshot_after=%s", active_after)
            return final_dir
        except Exception as exc:
            logger.exception("[SNAPSHOT_AUDIT] publicación_atómica=ERROR build=%s final=%s error=%s mensaje_usuario=%s", building_dir, final_dir, exc, "No se pudo crear la nueva foto local. Se conserva la anterior.")
            if building_dir.exists():
                if DEBUG_KEEP_FAILED_BUILDING and not os.environ.get("PYTEST_CURRENT_TEST"):
                    logger.warning("[SNAPSHOT_TRACE] op_id=%s evento=KEEP_FAILED_BUILDING build_dir=%s", op_id, building_dir)
                else:
                    try:
                        shutil.rmtree(building_dir)
                        logger.warning("[RUNTIME] Snapshot incompleto eliminado: %s", building_dir)
                    except Exception:
                        logger.exception("[SNAPSHOT_PUBLISH] warning no se pudo eliminar build_dir=%s", building_dir)
            raise RuntimeError("No se pudo crear la nueva foto local. Se conserva la anterior.") from exc

    def _copy_central_sqlite_to_snapshot(self, db_name: str, snapshot_dir: Path, operation_id: str | None = None) -> None:
        op_id = operation_id or get_runtime_operation_id()
        copy_t0 = perf_counter()
        source = self.central_dir / db_name
        destination = snapshot_dir / db_name
        self._checkpoint_central_sqlite(source, db_name)
        exists = source.exists()
        source_size = source.stat().st_size if exists else -1
        source_mtime = source.stat().st_mtime if exists else 0.0
        logger.info("[SNAPSHOT_TRACE] op_id=%s evento=BEFORE_COPY_DB db_name=%s source=%s source_exists=%s source_size=%s source_mtime=%s destination=%s", op_id, db_name, source, exists, source_size, source_mtime, destination)
        logger.info("[SNAPSHOT_AUDIT] base=%s origen_central=%s existe_origen=%s tamaño_origen_antes=%s mtime_origen_antes=%s destino_snapshot=%s", db_name, source, exists, source_size, source_mtime, destination)
        try:
            if not exists or source_size <= 0:
                raise RuntimeError(f"Base central vacía o inválida: {source}")
            shutil.copy2(source, destination)
            dest_stat = destination.stat()
            if dest_stat.st_size != source_size:
                raise RuntimeError(f"Tamaño distinto tras copiar {db_name}: origen={source_size} destino={dest_stat.st_size}")
            if abs(dest_stat.st_mtime - source_mtime) > 2.0:
                raise RuntimeError(f"mtime distinto tras copiar {db_name}: origen={source_mtime} destino={dest_stat.st_mtime}")
            if db_name == "DBPedidos.sqlite" or source_size <= SNAPSHOT_CHECKSUM_MAX_BYTES:
                source_hash = self._sha256_file(source)
                dest_hash = self._sha256_file(destination)
                if source_hash != dest_hash:
                    raise RuntimeError(f"Checksum distinto tras copiar {db_name}")
                logger.info("[SNAPSHOT_AUDIT] base=%s checksum_sha256=%s", db_name, source_hash)
            logger.info("[SNAPSHOT_TRACE] op_id=%s evento=AFTER_COPY_DB db_name=%s destination_exists=%s destination_size=%s destination_mtime=%s checksum_ok=%s duration=%.3fs", op_id, db_name, destination.exists(), dest_stat.st_size, dest_stat.st_mtime, True, perf_counter() - copy_t0)
            logger.info("[SNAPSHOT_AUDIT] base=%s origen_central=%s existe_origen=%s tamaño_origen_antes=%s mtime_origen_antes=%s destino_snapshot=%s tamaño_destino_despues=%s mtime_destino_despues=%s resultado=OK", db_name, source, exists, source_size, source_mtime, destination, dest_stat.st_size, dest_stat.st_mtime)
            if DIAG_SNAPSHOT_PEDIDOS and db_name == "DBPedidos.sqlite":
                self._log_pedidos_snapshot_diagnostic(source, destination)
        except Exception as exc:
            logger.exception("[SNAPSHOT_AUDIT] base=%s origen_central=%s existe_origen=%s tamaño_origen_antes=%s mtime_origen_antes=%s destino_snapshot=%s resultado=ERROR error=%s", db_name, source, exists, source_size, source_mtime, destination, exc)
            raise

    @staticmethod
    def _checkpoint_central_sqlite(source: Path, db_name: str) -> None:
        if not source.exists():
            return
        try:
            with sqlite3.connect(source, timeout=30) as conn:
                conn.execute("PRAGMA busy_timeout = 30000")
                result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            logger.info("[SNAPSHOT_AUDIT] base=%s checkpoint_wal=OK origen_central=%s resultado=%s", db_name, source, tuple(result) if result else None)
        except sqlite3.OperationalError as exc:
            if "database is locked" in str(exc).lower():
                logger.exception("[SNAPSHOT_AUDIT] base=%s checkpoint_wal=ERROR origen_central=%s error=%s", db_name, source, exc)
                raise RuntimeError(f"SQLite central bloqueada antes de snapshot: {source}") from exc
            raise

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _log_pedidos_snapshot_diagnostic(self, central_path: Path, snapshot_path: Path, publish: bool = False) -> None:
        query = "SELECT VarCliente FROM Pedidos WHERE IdPedidoLora = 'PS 26/00167'"
        central_value = self._fetch_optional_pedidos_diag(central_path, query)
        snapshot_value = self._fetch_optional_pedidos_diag(snapshot_path, query)
        if publish:
            logger.info("[SNAPSHOT_PUBLISH] DBPedidos central=%s final=%s", central_value, snapshot_value)
        else:
            logger.debug("[SNAPSHOT_AUDIT] diagnóstico_DBPedidos IdPedidoLora=PS 26/00167 central=%s snapshot=%s", central_value, snapshot_value)

    @staticmethod
    def _fetch_optional_pedidos_diag(db_path: Path, query: str) -> list[Any] | str:
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='Pedidos' LIMIT 1").fetchone()
                if not exists:
                    return "tabla Pedidos no existe"
                return [row[0] for row in conn.execute(query).fetchall()]
        except Exception as exc:
            return f"error: {exc}"


    def debug_compare_dbpedidos_record(self, id_pedido: str = "PS 26/00167", operation_id: str | None = None) -> None:
        op_id = operation_id or get_runtime_operation_id()
        query = 'SELECT IdPedidoLora, VarCliente, VarCoop, Cultivo, "Campaña", Empresa, FechaSalida FROM Pedidos WHERE IdPedidoLora = ?'
        central_path = self.central_dir / "DBPedidos.sqlite"
        active = self._resolve_current_snapshot_dir()
        active_path = active / "DBPedidos.sqlite" if active else None
        building_dirs = [p for p in self.snapshots_dir.iterdir() if p.is_dir() and p.name.startswith("__building_")] if self.snapshots_dir.exists() else []
        latest_building = max(building_dirs, key=lambda p: p.stat().st_mtime) if building_dirs else None
        building_path = latest_building / "DBPedidos.sqlite" if latest_building else None
        logger.info("[PEDIDOS_COMPARE] op_id=%s id_pedido=%s central_rows=%s active_snapshot=%s active_rows=%s latest_building=%s building_rows=%s", op_id, id_pedido, self._fetch_rows_for_compare(central_path, query, id_pedido), active, self._fetch_rows_for_compare(active_path, query, id_pedido) if active_path else [], latest_building, self._fetch_rows_for_compare(building_path, query, id_pedido) if building_path else [])

    @staticmethod
    def _fetch_rows_for_compare(db_path: Path, query: str, id_pedido: str) -> list[dict[str, Any]] | str:
        try:
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                return [dict(row) for row in conn.execute(query, (id_pedido,)).fetchall()]
        except Exception as exc:
            return f"error: {exc}"

    def activate_snapshot(self, snapshot_dir: Path, reason: str = "activate_snapshot") -> None:
        self._verify_snapshot_integrity(Path(snapshot_dir))
        self._activate_snapshot_file(Path(snapshot_dir))
        self.invalidate_all(reason)

    def _activate_snapshot_file(self, snapshot_dir: Path) -> None:
        if Path(snapshot_dir).name.startswith("__building_"):
            raise RuntimeError("No se puede activar un snapshot temporal __building")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.current_snapshot_file.with_suffix(".tmp")
        tmp.write_text(snapshot_dir.name, encoding="utf-8")
        tmp.replace(self.current_snapshot_file)
        logger.info("[RUNTIME] Snapshot activo cambiado: %s", snapshot_dir)

    def _verify_snapshot_files_complete(self, snapshot_dir: Path) -> None:
        snapshot_dir = Path(snapshot_dir)
        if not snapshot_dir.is_dir() or not all((snapshot_dir / db_name).exists() for db_name in SQLITE_DATABASES):
            raise RuntimeError(f"Snapshot inválido o incompleto: {snapshot_dir}")
        for db_name in SQLITE_DATABASES:
            db_path = snapshot_dir / db_name
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                conn.execute("PRAGMA quick_check").fetchone()

    def _verify_snapshot_integrity(self, snapshot_dir: Path) -> None:
        snapshot_dir = Path(snapshot_dir)
        if snapshot_dir.name.startswith("__building_"):
            raise RuntimeError("Snapshot temporal __building no puede usarse como snapshot activo")
        if not snapshot_dir.is_dir() or not all((snapshot_dir / db_name).exists() for db_name in SQLITE_DATABASES):
            raise RuntimeError(f"Snapshot inválido o incompleto: {snapshot_dir}")
        for db_name in SQLITE_DATABASES:
            db_path = snapshot_dir / db_name
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                conn.execute("PRAGMA quick_check").fetchone()

    def get_snapshot_info(self) -> dict[str, Any]:
        snapshot_dir = self.get_current_snapshot_dir()
        info_file = snapshot_dir / self.INFO_FILE
        raw_timestamp = snapshot_dir.name
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

    def central_sqlite_is_newer_than_snapshot(self, snapshot_dir: Path | None = None) -> bool:
        snapshot_dir = snapshot_dir or self._resolve_current_snapshot_dir()
        if snapshot_dir is None:
            return True
        for db_name in SQLITE_DATABASES:
            central = self.central_dir / db_name
            snapshot = snapshot_dir / db_name
            if not central.exists() or not snapshot.exists() or central.stat().st_mtime > snapshot.stat().st_mtime + 0.001:
                return True
        return False

    def cleanup_building_snapshots(self) -> None:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        for building in self.snapshots_dir.iterdir():
            if not building.is_dir() or not building.name.startswith("__building_"):
                continue
            try:
                shutil.rmtree(building)
                logger.info("[SNAPSHOT_PUBLISH] build_dir antiguo eliminado=%s", building)
            except Exception:
                logger.warning("[SNAPSHOT_PUBLISH] warning no se pudo eliminar build_dir antiguo=%s", building, exc_info=True)

    def _open_connection_paths_for_snapshot(self, *snapshot_dirs: Path) -> list[str]:
        roots = [str(path.resolve()) for path in snapshot_dirs if path.exists()]
        open_paths: list[str] = []
        with self._lock:
            keys = list(self._connections.keys())
        for key in keys:
            try:
                resolved = str(Path(key).resolve())
            except Exception:
                resolved = key
            if any(resolved.startswith(root) for root in roots):
                open_paths.append(resolved)
        return open_paths

    def cleanup_old_snapshots(self, keep: int = 3) -> None:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        valid = [p for p in self.snapshots_dir.iterdir() if p.is_dir() and not p.name.startswith("__building_") and self._is_valid_snapshot(p)]
        active = self._resolve_current_snapshot_dir()
        valid.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in valid[max(keep, 1):]:
            if active and old.resolve() == active.resolve():
                continue
            shutil.rmtree(old, ignore_errors=True)
            logger.info("[RUNTIME] Snapshot antiguo eliminado: %s", old)

    def _resolve_current_snapshot_dir(self) -> Path | None:
        if self.current_snapshot_file.exists():
            snapshot_name = self.current_snapshot_file.read_text(encoding="utf-8").strip()
            if snapshot_name:
                snapshot_dir = Path(snapshot_name)
                if not snapshot_dir.is_absolute():
                    snapshot_dir = self.snapshots_dir / snapshot_name
                if self._is_valid_snapshot(snapshot_dir):
                    return snapshot_dir
                logger.warning("[RUNTIME] Snapshot activo inválido o incompleto: %s", snapshot_dir)
        return self._get_latest_valid_snapshot()

    def _write_snapshot_info(self, snapshot_dir: Path) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        lines = [f"created_at={now}", f"source_dir={self.central_dir}", "databases=" + ",".join(SQLITE_DATABASES)]
        (snapshot_dir / self.INFO_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _is_valid_snapshot(self, snapshot_dir: Path) -> bool:
        return snapshot_dir.is_dir() and not snapshot_dir.name.startswith("__building_") and all((snapshot_dir / db_name).exists() for db_name in SQLITE_DATABASES)

    def _get_latest_valid_snapshot(self) -> Path | None:
        if not self.snapshots_dir.exists():
            return None
        valid = [p for p in self.snapshots_dir.iterdir() if p.is_dir() and not p.name.startswith("__building_") and self._is_valid_snapshot(p)]
        return max(valid, key=lambda p: p.stat().st_mtime) if valid else None


class RuntimeDatabaseService:
    SUCCESS_MESSAGE = "Se ha actualizado la foto local desde las bases SQLite centrales."
    STARTUP_USING_CURRENT_MESSAGE = "Usando última foto local disponible."
    STARTUP_CENTRAL_NEWER_MESSAGE = "Se detectó una SQLite central más reciente. Creando nueva foto local."
    WARNING_MESSAGE = "No se pudo actualizar la foto local. Se usará la última foto disponible."
    ERROR_MESSAGE = "No se pudo preparar ninguna foto local de datos."
    INFO_FILE = RuntimeDatabaseManager.INFO_FILE

    def __init__(self) -> None:
        self.manager = RuntimeDatabaseManager()
        self.central_dir = self.manager.central_dir
        self.runtime_dir = self.manager.runtime_dir
        self.snapshots_dir = self.manager.snapshots_dir
        self.current_snapshot_file = self.manager.current_snapshot_file
        self.snapshot_file = self.current_snapshot_file

    def __getattr__(self, name: str):
        return getattr(self.manager, name)

    def __setattr__(self, name: str, value) -> None:
        object.__setattr__(self, name, value)
        manager = self.__dict__.get("manager")
        if manager is not None and name in {"central_dir", "runtime_dir", "snapshots_dir", "current_snapshot_file", "snapshot_file"}:
            setattr(manager, name, Path(value))
            if name == "snapshot_file":
                manager.current_snapshot_file = Path(value)


    def debug_open_connections(self) -> list[str]:
        with self._lock:
            keys = list(self._connections.keys())
        rows: list[str] = []
        for key in keys:
            try:
                p = Path(key)
                snapshot = p.parent.name if p.parent else ""
                rows.append(f"key={key} path={p} snapshot={snapshot}")
            except Exception:
                rows.append(str(key))
        return rows

    def debug_snapshot_dirs(self) -> dict[str, Any]:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        dirs = [p for p in self.snapshots_dir.iterdir() if p.is_dir()] if self.snapshots_dir.exists() else []
        current_value = self.current_snapshot_file.read_text(encoding="utf-8").strip() if self.current_snapshot_file.exists() else ""
        resolved = self._resolve_current_snapshot_dir()
        return {"valid_snapshots": [p.name for p in dirs if not p.name.startswith("__building_") and self._is_valid_snapshot(p)], "building_snapshots": [p.name for p in dirs if p.name.startswith("__building_")], "current_snapshot_file_value": current_value, "resolved_current_snapshot": str(resolved) if resolved else None}

    def prepare_runtime_databases(self, force: bool = False, reason: str = "prepare_runtime_databases", operation_id: str | None = None) -> tuple[bool, list[str]]:
        return self.manager.prepare_runtime_databases(force=force, reason=reason, operation_id=operation_id)
