from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

from db.connection import get_db_path


class LegacySyncRepository:
    def __init__(self) -> None:
        self.db_path = get_db_path()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS LegacyTableSyncSettings (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Nombre TEXT NOT NULL UNIQUE,
                    AccessPath TEXT NOT NULL,
                    AccessTable TEXT NOT NULL,
                    SqlitePath TEXT NOT NULL,
                    SqliteTable TEXT NOT NULL,
                    Modo TEXT NOT NULL DEFAULT 'REEMPLAZAR_TABLA',
                    Activa INTEGER NOT NULL DEFAULT 1,
                    UltimaActualizacion TEXT,
                    UltimoResultado TEXT,
                    UltimoError TEXT,
                    Observaciones TEXT,
                    FechaCreacion TEXT,
                    FechaModificacion TEXT
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS LegacyTableSyncLog (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    SettingId INTEGER,
                    Nombre TEXT,
                    AccessPath TEXT,
                    AccessTable TEXT,
                    SqlitePath TEXT,
                    SqliteTable TEXT,
                    Inicio TEXT,
                    Fin TEXT,
                    Ok INTEGER,
                    FilasExportadas INTEGER,
                    FilasImportadas INTEGER,
                    Mensaje TEXT,
                    Error TEXT
                )
                '''
            )

    def get_settings(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM LegacyTableSyncSettings ORDER BY Nombre").fetchall()
        return [dict(r) for r in rows]

    def add_setting(self, data: dict[str, Any]) -> int:
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute(
                '''
                INSERT INTO LegacyTableSyncSettings
                (Nombre, AccessPath, AccessTable, SqlitePath, SqliteTable, Modo, Activa, Observaciones, FechaCreacion, FechaModificacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    data["Nombre"], data["AccessPath"], data["AccessTable"], data["SqlitePath"], data["SqliteTable"],
                    data.get("Modo", "REEMPLAZAR_TABLA"), int(data.get("Activa", 1)), data.get("Observaciones", ""), now, now,
                ),
            )
            return int(cur.lastrowid)

    def update_setting(self, setting_id: int, data: dict[str, Any]) -> None:
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                '''
                UPDATE LegacyTableSyncSettings
                SET Nombre=?, AccessPath=?, AccessTable=?, SqlitePath=?, SqliteTable=?,
                    Modo=?, Activa=?, Observaciones=?, FechaModificacion=?
                WHERE Id=?
                ''',
                (
                    data["Nombre"], data["AccessPath"], data["AccessTable"], data["SqlitePath"], data["SqliteTable"],
                    data.get("Modo", "REEMPLAZAR_TABLA"), int(data.get("Activa", 1)), data.get("Observaciones", ""), now, setting_id,
                ),
            )

    def delete_setting(self, setting_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM LegacyTableSyncSettings WHERE Id=?", (setting_id,))

    def get_setting(self, setting_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM LegacyTableSyncSettings WHERE Id=?", (setting_id,)).fetchone()
        return dict(row) if row else None

    def get_active_settings(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM LegacyTableSyncSettings WHERE Activa=1 ORDER BY Nombre").fetchall()
        return [dict(r) for r in rows]

    def update_sync_result(self, setting_id: int, ok: bool, result: str, error: str | None = None) -> None:
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "UPDATE LegacyTableSyncSettings SET UltimaActualizacion=?, UltimoResultado=?, UltimoError=?, FechaModificacion=? WHERE Id=?",
                (now, result, error, now, setting_id),
            )

    def add_log(self, log_data: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO LegacyTableSyncLog
                (SettingId, Nombre, AccessPath, AccessTable, SqlitePath, SqliteTable, Inicio, Fin, Ok,
                 FilasExportadas, FilasImportadas, Mensaje, Error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    log_data.get("SettingId"), log_data.get("Nombre"), log_data.get("AccessPath"), log_data.get("AccessTable"),
                    log_data.get("SqlitePath"), log_data.get("SqliteTable"), log_data.get("Inicio"), log_data.get("Fin"),
                    int(log_data.get("Ok", 0)), log_data.get("FilasExportadas", 0), log_data.get("FilasImportadas", 0),
                    log_data.get("Mensaje", ""), log_data.get("Error", ""),
                ),
            )

    def get_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM LegacyTableSyncLog ORDER BY Id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
