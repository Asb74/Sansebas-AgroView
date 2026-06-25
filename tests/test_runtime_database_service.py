from __future__ import annotations

import sqlite3

from services import runtime_database_service as runtime_module
from services.runtime_database_service import RuntimeDatabaseService
from services.update_orchestrator_service import UpdateOrchestratorService


def _create_sqlite(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")


def _service(tmp_path, monkeypatch, dbs=None):
    dbs = dbs or ["a.sqlite", "b.sqlite"]
    monkeypatch.setattr(runtime_module, "SQLITE_DATABASES", dbs)
    service = RuntimeDatabaseService()
    service.central_dir = tmp_path / "central"
    service.runtime_dir = tmp_path / "runtime"
    service.snapshots_dir = service.runtime_dir / "snapshots"
    service.current_snapshot_file = service.runtime_dir / "current_snapshot.txt"
    service.snapshot_file = service.current_snapshot_file
    service.central_dir.mkdir()
    for db in dbs:
        _create_sqlite(service.central_dir / db)
    return service, dbs


def test_prepare_runtime_databases_creates_and_activates_snapshot(tmp_path, monkeypatch):
    service, dbs = _service(tmp_path, monkeypatch)

    ok, errors = service.prepare_runtime_databases(force=True)

    assert ok is True
    assert errors == []
    active = service.get_current_snapshot_dir()
    assert active is not None
    assert active.parent == service.snapshots_dir
    assert service.current_snapshot_file.read_text(encoding="utf-8").strip() == active.name
    assert (active / "snapshot_info.txt").exists()
    assert (active / ".ready").exists()
    assert not (active / ".building").exists()
    assert all((active / db).exists() for db in dbs)
    assert service.get_runtime_path(dbs[0]) == active / dbs[0]


def test_prepare_runtime_databases_removes_incomplete_snapshot_and_keeps_current(tmp_path, monkeypatch):
    service, dbs = _service(tmp_path, monkeypatch)
    ok, _ = service.prepare_runtime_databases()
    assert ok is True
    first = service.get_current_snapshot_dir()
    assert first is not None

    (service.central_dir / dbs[-1]).unlink()
    ok, errors = service.prepare_runtime_databases(force=True)

    assert ok is False
    assert errors
    assert service.get_current_snapshot_dir() == first
    snapshots = [p for p in service.snapshots_dir.iterdir() if p.is_dir()]
    assert snapshots == [first]


def test_cleanup_old_snapshots_keeps_three_latest(tmp_path, monkeypatch):
    service, dbs = _service(tmp_path, monkeypatch)
    created = []
    for idx in range(4):
        snap = service.snapshots_dir / f"20260625_12000{idx}"
        snap.mkdir(parents=True)
        for db in dbs:
            _create_sqlite(snap / db)
        (snap / ".ready").write_text("", encoding="utf-8")
        created.append(snap)

    service.cleanup_old_snapshots(keep=3)

    remaining = {p.name for p in service.snapshots_dir.iterdir() if p.is_dir()}
    assert len(remaining) == 3
    assert created[0].name not in remaining


def test_is_valid_snapshot_requires_ready_marker_and_no_building_marker(tmp_path, monkeypatch):
    service, dbs = _service(tmp_path, monkeypatch)
    snap = service.snapshots_dir / "20260625_120000"
    snap.mkdir(parents=True)
    for db in dbs:
        _create_sqlite(snap / db)

    assert service._is_valid_snapshot(snap) is False

    (snap / ".ready").write_text("", encoding="utf-8")
    assert service._is_valid_snapshot(snap) is True

    (snap / ".building").write_text("", encoding="utf-8")
    assert service._is_valid_snapshot(snap) is False


def test_cleanup_building_snapshots_removes_legacy_and_marker_builds(tmp_path, monkeypatch):
    service, dbs = _service(tmp_path, monkeypatch)
    legacy = service.snapshots_dir / "__building_20260625_120000"
    marker_build = service.snapshots_dir / "20260625_120001"
    ready = service.snapshots_dir / "20260625_120002"
    for snap in (legacy, marker_build, ready):
        snap.mkdir(parents=True)
        for db in dbs:
            _create_sqlite(snap / db)
    (marker_build / ".building").write_text("", encoding="utf-8")
    (ready / ".ready").write_text("", encoding="utf-8")

    service.cleanup_building_snapshots()

    assert not legacy.exists()
    assert not marker_build.exists()
    assert ready.exists()


def test_orchestrator_marks_update_all_partial_when_previous_snapshot_is_used(tmp_path, monkeypatch):
    service, dbs = _service(tmp_path, monkeypatch)
    assert service.prepare_runtime_databases()[0] is True
    (service.central_dir / dbs[0]).unlink()

    class LegacyOK:
        def sync_active_settings(self):
            return [("central", True, "OK")]

    orchestrator = UpdateOrchestratorService(legacy_sync_service=LegacyOK(), runtime_database_service=service)

    result = orchestrator.update_all()

    assert result["ok"] is False
    assert result["partial"] is True
    assert result["legacy"]["ok"] is True
    assert result["runtime"]["using_previous_snapshot"] is True
