from __future__ import annotations

import sqlite3

import pytest

from services import runtime_database_service as runtime_module
from services.runtime_database_service import RuntimeDatabaseLockedError, RuntimeDatabaseService
from services.update_orchestrator_service import UpdateOrchestratorService


def _create_sqlite(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")


def test_prepare_runtime_databases_stops_before_copy_when_runtime_locked(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_module, "SQLITE_DATABASES", ["locked.sqlite", "other.sqlite"])
    service = RuntimeDatabaseService()
    service.central_dir = tmp_path / "central"
    service.runtime_dir = tmp_path / "runtime"
    service.snapshot_file = service.runtime_dir / "snapshot_info.txt"
    service.central_dir.mkdir()
    service.runtime_dir.mkdir()
    _create_sqlite(service.central_dir / "locked.sqlite")
    _create_sqlite(service.central_dir / "other.sqlite")
    _create_sqlite(service.runtime_dir / "locked.sqlite")

    copied: list[str] = []
    monkeypatch.setattr(service, "is_runtime_database_locked", lambda db_name: db_name == "locked.sqlite")
    monkeypatch.setattr(service, "copy_database_to_runtime", lambda db_name: copied.append(db_name) or True)

    with pytest.raises(RuntimeDatabaseLockedError) as exc_info:
        service.prepare_runtime_databases(force=True)

    assert exc_info.value.locked_databases == ["locked.sqlite"]
    assert copied == []
    assert not service.snapshot_file.exists()


def test_orchestrator_marks_update_all_partial_when_runtime_locked():
    class LegacyOK:
        def sync_active_settings(self):
            return [("central", True, "OK")]

    class RuntimeLocked:
        def prepare_runtime_databases(self, force=False):
            raise RuntimeDatabaseLockedError(["DBPedidos.sqlite"])

    orchestrator = UpdateOrchestratorService(legacy_sync_service=LegacyOK(), runtime_database_service=RuntimeLocked())

    result = orchestrator.update_all()

    assert result["ok"] is False
    assert result["partial"] is True
    assert result["legacy"]["ok"] is True
    assert result["runtime"]["error_type"] == "runtime_databases_locked"
    assert result["runtime"]["locked_databases"] == ["DBPedidos.sqlite"]
