import sqlite3
from pathlib import Path

import pytest

from services.legacy_sync_service import (
    CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE,
    LegacySyncService,
    is_central_sqlite_path,
)


def test_is_central_sqlite_path_detects_unc_central_children():
    assert is_central_sqlite_path(Path(r"\\Personal\C\BasesSQLite\DBPedidos.sqlite"))
    assert is_central_sqlite_path(Path(r"//Personal/C/BasesSQLite/DBfruta.sqlite"))
    assert not is_central_sqlite_path(Path(r"C:\Sansebas AgroView\runtime_db\DBPedidos.sqlite"))


def test_import_csv_to_sqlite_blocks_replacing_central_sqlite(tmp_path):
    service = LegacySyncService.__new__(LegacySyncService)
    csv_path = tmp_path / "pedidos.csv"
    csv_path.write_text("Id;Nombre\n1;Pedido\n", encoding="utf-8")

    with pytest.raises(PermissionError, match=CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE):
        service._import_csv_to_sqlite(
            csv_path=csv_path,
            sqlite_path=Path(r"\\Personal\C\BasesSQLite\DBPedidos.sqlite"),
            table_name="Pedidos",
            mode="REEMPLAZAR_TABLA",
        )


def test_safe_replace_table_from_csv_keeps_existing_table_when_csv_empty(tmp_path):
    service = LegacySyncService.__new__(LegacySyncService)
    db = tmp_path / "central.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE Pedidos (Id TEXT, Nombre TEXT)')
        conn.execute('INSERT INTO Pedidos VALUES (?, ?)', ('1', 'Anterior'))
    csv_path = tmp_path / "pedidos.csv"
    csv_path.write_text("Id;Nombre\n", encoding="utf-8")

    with pytest.raises(ValueError, match="AllowEmpty"):
        service.safe_replace_table_from_csv(csv_path, db, "Pedidos")

    with sqlite3.connect(db) as conn:
        rows = conn.execute('SELECT * FROM Pedidos').fetchall()
        staging = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'staging_Pedidos_%'").fetchall()
    assert rows == [('1', 'Anterior')]
    assert staging == []


def test_safe_replace_table_from_csv_replaces_after_valid_staging(tmp_path):
    service = LegacySyncService.__new__(LegacySyncService)
    db = tmp_path / "central.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE Pedidos (Id TEXT, Nombre TEXT)')
        conn.execute('INSERT INTO Pedidos VALUES (?, ?)', ('1', 'Anterior'))
    csv_path = tmp_path / "pedidos.csv"
    csv_path.write_text("Id;Nombre\n2;Nuevo\n3;Otro\n", encoding="utf-8")

    imported, existed, created = service.safe_replace_table_from_csv(csv_path, db, "Pedidos")

    assert (imported, existed, created) == (2, True, False)
    with sqlite3.connect(db) as conn:
        rows = conn.execute('SELECT * FROM Pedidos ORDER BY Id').fetchall()
        backups = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'backup_Pedidos_%'").fetchall()
    assert rows == [('2', 'Nuevo'), ('3', 'Otro')]
    assert backups == []


def test_safe_replace_partition_from_staging_replaces_only_requested_campaign(tmp_path):
    service = LegacySyncService.__new__(LegacySyncService)
    target = tmp_path / "DBPedidos.sqlite"
    staging = tmp_path / "staging.sqlite"
    with sqlite3.connect(target) as conn:
        conn.execute('CREATE TABLE Pedidos (Id TEXT, "Campaña" TEXT, Nombre TEXT)')
        conn.execute('INSERT INTO Pedidos VALUES (?, ?, ?)', ('old-2025', '2025', 'Anterior 2025'))
        conn.execute('INSERT INTO Pedidos VALUES (?, ?, ?)', ('old-2026', '2026', 'Anterior 2026'))
    with sqlite3.connect(staging) as conn:
        conn.execute('CREATE TABLE Pedidos (Id TEXT, "Campaña" TEXT, Nombre TEXT)')
        conn.execute('INSERT INTO Pedidos VALUES (?, ?, ?)', ('new-2026', '2026', 'Nuevo 2026'))

    result = service.safe_replace_partition_from_staging(staging, target, "Pedidos", "Campaña", "2026")

    assert result["RegistrosBorradosParticion"] == 1
    assert result["RegistrosInsertadosParticion"] == 1
    with sqlite3.connect(target) as conn:
        rows = conn.execute('SELECT Id, "Campaña", Nombre FROM Pedidos ORDER BY Id').fetchall()
    assert rows == [('new-2026', '2026', 'Nuevo 2026'), ('old-2025', '2025', 'Anterior 2025')]


def test_safe_replace_partition_from_staging_keeps_destination_when_staging_empty(tmp_path):
    service = LegacySyncService.__new__(LegacySyncService)
    target = tmp_path / "DBPedidos.sqlite"
    staging = tmp_path / "staging.sqlite"
    with sqlite3.connect(target) as conn:
        conn.execute('CREATE TABLE Pedidos (Id TEXT, Campana TEXT, Nombre TEXT)')
        conn.execute('INSERT INTO Pedidos VALUES (?, ?, ?)', ('old-2026', '2026', 'Anterior 2026'))
    with sqlite3.connect(staging) as conn:
        conn.execute('CREATE TABLE Pedidos (Id TEXT, Campana TEXT, Nombre TEXT)')

    try:
        service.safe_replace_partition_from_staging(staging, target, "Pedidos", "Campana", "2026")
    except ValueError as exc:
        assert "staging" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError")

    with sqlite3.connect(target) as conn:
        rows = conn.execute('SELECT Id, Campana, Nombre FROM Pedidos').fetchall()
    assert rows == [('old-2026', '2026', 'Anterior 2026')]


def test_normalize_cancelado_values_and_staging_import(tmp_path):
    from services.legacy_sync_service import normalize_cancelado

    service = LegacySyncService.__new__(LegacySyncService)
    csv_path = tmp_path / "pedidos.csv"
    csv_path.write_text(
        "Id;Cancelado\n"
        "1;Falso\n"
        "2;Verdadero\n"
        "3;-1\n"
        "4;No\n"
        "5;desconocido\n",
        encoding="utf-8",
    )
    staging = tmp_path / "staging.sqlite"

    assert normalize_cancelado(None) == 0
    assert normalize_cancelado("Sí") == 1
    assert normalize_cancelado("Falso") == 0
    assert normalize_cancelado(-1) == 1

    service._import_csv_to_staging_sqlite(csv_path, staging, "Pedidos")

    with sqlite3.connect(staging) as conn:
        schema = conn.execute('PRAGMA table_info("Pedidos")').fetchall()
        rows = conn.execute('SELECT Id, Cancelado, typeof(Cancelado) FROM Pedidos ORDER BY Id').fetchall()
    assert [col[2] for col in schema if col[1] == "Cancelado"] == ["INTEGER"]
    assert rows == [("1", 0, "integer"), ("2", 1, "integer"), ("3", 1, "integer"), ("4", 0, "integer"), ("5", 0, "integer")]


def test_normalize_pedidos_cancelado_in_existing_db(tmp_path):
    service = LegacySyncService.__new__(LegacySyncService)
    db = tmp_path / "DBPedidos.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE Pedidos (Id TEXT, Cancelado TEXT)')
        conn.executemany(
            'INSERT INTO Pedidos VALUES (?, ?)',
            [("1", "Falso"), ("2", "Verdadero"), ("3", "False"), ("4", "True"), ("5", "-1"), ("6", None)],
        )
        service._normalize_pedidos_cancelado_in_db(conn, "Pedidos")
        rows = conn.execute('SELECT Cancelado, COUNT(*) FROM Pedidos GROUP BY Cancelado ORDER BY Cancelado').fetchall()

    assert rows == [(0, 3), (1, 3)]

class _FakeLegacyDefaultsRepository:
    def __init__(self, settings):
        self.settings = settings
        self.added = []
        self.updated = []

    def get_settings(self):
        return [dict(setting) for setting in self.settings]

    def add_setting(self, data):
        self.added.append(dict(data))
        stored = dict(data)
        stored.setdefault("Id", len(self.settings) + 1)
        self.settings.append(stored)
        return stored["Id"]

    def update_setting(self, setting_id, data):
        self.updated.append((setting_id, dict(data)))
        for index, setting in enumerate(self.settings):
            if setting.get("Id") == setting_id:
                self.settings[index] = dict(data)
                self.settings[index]["Id"] = setting_id
                break


def _planificacion_service_with_settings(monkeypatch, settings):
    service = LegacySyncService.__new__(LegacySyncService)
    service.repository = _FakeLegacyDefaultsRepository(settings)
    paths = {
        "Pedidos": r"C:\usuario\pedidos.mdb",
        "Loteado": r"C:\usuario\loteado.mdb",
        "PesosFres": r"C:\usuario\fruta.mdb",
    }
    monkeypatch.setattr(
        service,
        "_find_existing_access_path",
        lambda _settings, names: paths.get(names[0]),
    )
    return service


def test_default_planificacion_settings_skip_existing_by_nombre_without_duplicate(monkeypatch):
    settings = [
        {
            "Id": 1,
            "Nombre": "Pedidos",
            "AccessPath": r"D:\manual\pedidos.mdb",
            "AccessTable": "Pedidos",
            "SqlitePath": r"D:\manual\DBPedidos.sqlite",
            "SqliteTable": "Pedidos",
            "Modo": "PLANIFICACION_HOY_EN_ADELANTE",
            "Activa": 1,
        }
    ]
    service = _planificacion_service_with_settings(monkeypatch, settings)

    service.ensure_default_planificacion_settings()
    service.ensure_default_planificacion_settings()

    pedidos = [setting for setting in service.repository.settings if setting["Nombre"] == "Pedidos"]
    assert len(pedidos) == 1
    assert pedidos[0]["AccessPath"] == r"D:\manual\pedidos.mdb"
    assert pedidos[0]["SqlitePath"] == r"D:\manual\DBPedidos.sqlite"


def test_default_planificacion_settings_updates_only_empty_essential_fields(monkeypatch):
    settings = [
        {
            "Id": 1,
            "Nombre": "Pedidos",
            "AccessPath": r"D:\manual\pedidos.mdb",
            "AccessTable": "",
            "SqlitePath": r"D:\manual\DBPedidos.sqlite",
            "SqliteTable": "",
            "Modo": "",
            "Activa": None,
        }
    ]
    service = _planificacion_service_with_settings(monkeypatch, settings)

    service.ensure_default_planificacion_settings()

    assert service.repository.updated
    updated = service.repository.updated[0][1]
    assert updated["AccessPath"] == r"D:\manual\pedidos.mdb"
    assert updated["SqlitePath"] == r"D:\manual\DBPedidos.sqlite"
    assert updated["AccessTable"] == "Pedidos"
    assert updated["SqliteTable"] == "Pedidos"
    assert updated["Modo"] == "PLANIFICACION_HOY_EN_ADELANTE"
    assert updated["Activa"] == 1


def test_default_planificacion_settings_recovers_unique_nombre_integrity_error(monkeypatch):
    class RaceRepository(_FakeLegacyDefaultsRepository):
        def add_setting(self, data):
            if data["Nombre"] == "Pedidos":
                self.settings.append(
                    {
                        "Id": 99,
                        "Nombre": "Pedidos",
                        "AccessPath": r"D:\manual\pedidos.mdb",
                        "AccessTable": "Pedidos",
                        "SqlitePath": r"D:\manual\DBPedidos.sqlite",
                        "SqliteTable": "Pedidos",
                        "Modo": "PLANIFICACION_HOY_EN_ADELANTE",
                        "Activa": 1,
                    }
                )
                raise sqlite3.IntegrityError(
                    "UNIQUE constraint failed: LegacyTableSyncSettings.Nombre"
                )
            return super().add_setting(data)

    service = _planificacion_service_with_settings(monkeypatch, [])
    service.repository = RaceRepository([])

    service.ensure_default_planificacion_settings()

    pedidos = [setting for setting in service.repository.settings if setting["Nombre"] == "Pedidos"]
    assert len(pedidos) == 1
