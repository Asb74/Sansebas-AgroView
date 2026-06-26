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
