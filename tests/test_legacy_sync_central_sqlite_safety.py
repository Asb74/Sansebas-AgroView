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
