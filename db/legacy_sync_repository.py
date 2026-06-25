from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

from db.connection import get_db_path
import logging

logger = logging.getLogger(__name__)

FILTER_COLUMNS = {
    "FiltroCampanaModo": "TEXT NOT NULL DEFAULT 'NINGUNO'",
    "FiltroCampanaCampo": "TEXT",
    "FiltroCampanaTipo": "TEXT NOT NULL DEFAULT 'TEXTO'",
    "FiltroCampanaValorOrigen": "TEXT NOT NULL DEFAULT 'CAMPANA_ACTIVA'",
    "FiltroCampanaValorFijo": "TEXT",
    "FiltroRelacionTabla": "TEXT",
    "FiltroRelacionCampoLocal": "TEXT",
    "FiltroRelacionCampoRemoto": "TEXT",
    "FiltroRelacionCampoCampana": "TEXT",
    "FiltroRelacionTipoCampana": "TEXT NOT NULL DEFAULT 'TEXTO'",
    "FiltroActivo": "INTEGER NOT NULL DEFAULT 0",
}

DEFAULT_CAMPAIGN_FILTERS = {
    "pedidos": {"FiltroActivo": 1, "FiltroCampanaModo": "DIRECTO", "FiltroCampanaCampo": "Campaña", "FiltroCampanaTipo": "TEXTO", "FiltroCampanaValorOrigen": "CAMPANA_ACTIVA"},
    "loteado": {"FiltroActivo": 1, "FiltroCampanaModo": "DIRECTO", "FiltroCampanaCampo": "CAMPAÑA", "FiltroCampanaTipo": "ENTERO", "FiltroCampanaValorOrigen": "CAMPANA_ACTIVA"},
    "lote": {"FiltroActivo": 1, "FiltroCampanaModo": "PREFIJO", "FiltroCampanaCampo": "IdPalet", "FiltroCampanaTipo": "ENTERO", "FiltroCampanaValorOrigen": "CAMPANA_ACTIVA"},
    "pesosfres": {"FiltroActivo": 1, "FiltroCampanaModo": "DIRECTO", "FiltroCampanaCampo": "CAMPAÑA", "FiltroCampanaTipo": "ENTERO", "FiltroCampanaValorOrigen": "CAMPANA_ACTIVA"},
    "datoscalibre": {"FiltroActivo": 1, "FiltroCampanaModo": "DIRECTO", "FiltroCampanaCampo": "CAMPAÑA", "FiltroCampanaTipo": "ENTERO", "FiltroCampanaValorOrigen": "CAMPANA_ACTIVA"},
    "partidas": {"FiltroActivo": 1, "FiltroCampanaModo": "PREFIJO", "FiltroCampanaCampo": "IdPartidaP", "FiltroCampanaTipo": "TEXTO", "FiltroCampanaValorOrigen": "CAMPANA_ACTIVA"},
}


class LegacySyncRepository:
    def __init__(self) -> None:
        self.db_path = get_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("LegacySyncRepository DB path: %s", self.db_path)
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
                    FechaModificacion TEXT,
                    FiltroCampanaModo TEXT NOT NULL DEFAULT 'NINGUNO',
                    FiltroCampanaCampo TEXT,
                    FiltroCampanaTipo TEXT NOT NULL DEFAULT 'TEXTO',
                    FiltroCampanaValorOrigen TEXT NOT NULL DEFAULT 'CAMPANA_ACTIVA',
                    FiltroCampanaValorFijo TEXT,
                    FiltroRelacionTabla TEXT,
                    FiltroRelacionCampoLocal TEXT,
                    FiltroRelacionCampoRemoto TEXT,
                    FiltroRelacionCampoCampana TEXT,
                    FiltroRelacionTipoCampana TEXT NOT NULL DEFAULT 'TEXTO',
                    FiltroActivo INTEGER NOT NULL DEFAULT 0
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
                    ModoUsado TEXT,
                    TablaDestinoExistia INTEGER DEFAULT 0,
                    TablaDestinoCreada INTEGER DEFAULT 0,
                    Mensaje TEXT,
                    Error TEXT
                )
                '''
            )
            settings_cols = {r[1] for r in conn.execute("PRAGMA table_info(LegacyTableSyncSettings)").fetchall()}
            for column, definition in FILTER_COLUMNS.items():
                if column not in settings_cols:
                    conn.execute(f"ALTER TABLE LegacyTableSyncSettings ADD COLUMN {column} {definition}")
            self._apply_default_campaign_filters(conn)

            cols = {r[1] for r in conn.execute("PRAGMA table_info(LegacyTableSyncLog)").fetchall()}
            if "ModoUsado" not in cols:
                conn.execute("ALTER TABLE LegacyTableSyncLog ADD COLUMN ModoUsado TEXT")
            if "TablaDestinoExistia" not in cols:
                conn.execute("ALTER TABLE LegacyTableSyncLog ADD COLUMN TablaDestinoExistia INTEGER DEFAULT 0")
            if "TablaDestinoCreada" not in cols:
                conn.execute("ALTER TABLE LegacyTableSyncLog ADD COLUMN TablaDestinoCreada INTEGER DEFAULT 0")

    def _apply_default_campaign_filters(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT Id, Nombre, AccessTable, SqliteTable FROM LegacyTableSyncSettings").fetchall()
        for row in rows:
            names = [str(row["AccessTable"] or "").lower(), str(row["SqliteTable"] or "").lower(), str(row["Nombre"] or "").lower()]
            defaults = next((DEFAULT_CAMPAIGN_FILTERS[name] for name in names if name in DEFAULT_CAMPAIGN_FILTERS), None)
            if not defaults:
                continue
            assignments = ", ".join(f"{key}=?" for key in defaults)
            conn.execute(f"UPDATE LegacyTableSyncSettings SET {assignments} WHERE Id=? AND COALESCE(FiltroActivo, 0)=0 AND COALESCE(FiltroCampanaModo, 'NINGUNO')='NINGUNO'", (*defaults.values(), row["Id"]))

    @staticmethod
    def _with_campaign_defaults(data: dict[str, Any]) -> dict[str, Any]:
        merged = dict(data)
        names = [str(merged.get("AccessTable", "")).lower(), str(merged.get("SqliteTable", "")).lower(), str(merged.get("Nombre", "")).lower()]
        defaults = next((DEFAULT_CAMPAIGN_FILTERS[name] for name in names if name in DEFAULT_CAMPAIGN_FILTERS), {})
        for key, value in defaults.items():
            if merged.get(key) in (None, ""):
                merged[key] = value
        return merged

    def get_settings(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM LegacyTableSyncSettings ORDER BY Nombre").fetchall()
        logger.info("Configuraciones legacy cargadas desde %s: %s", self.db_path, len(rows))
        return [dict(r) for r in rows]

    def add_setting(self, data: dict[str, Any]) -> int:
        data = self._with_campaign_defaults(data)
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute(
                '''
                INSERT INTO LegacyTableSyncSettings
                (Nombre, AccessPath, AccessTable, SqlitePath, SqliteTable, Modo, Activa, Observaciones, FechaCreacion, FechaModificacion,
                 FiltroCampanaModo, FiltroCampanaCampo, FiltroCampanaTipo, FiltroCampanaValorOrigen, FiltroCampanaValorFijo,
                 FiltroRelacionTabla, FiltroRelacionCampoLocal, FiltroRelacionCampoRemoto, FiltroRelacionCampoCampana,
                 FiltroRelacionTipoCampana, FiltroActivo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    data["Nombre"], data["AccessPath"], data["AccessTable"], data["SqlitePath"], data["SqliteTable"],
                    data.get("Modo", "REEMPLAZAR_TABLA"), int(data.get("Activa", 1)), data.get("Observaciones", ""), now, now,
                    data.get("FiltroCampanaModo", "NINGUNO"), data.get("FiltroCampanaCampo", ""), data.get("FiltroCampanaTipo", "TEXTO"),
                    data.get("FiltroCampanaValorOrigen", "CAMPANA_ACTIVA"), data.get("FiltroCampanaValorFijo", ""),
                    data.get("FiltroRelacionTabla", ""), data.get("FiltroRelacionCampoLocal", ""), data.get("FiltroRelacionCampoRemoto", ""),
                    data.get("FiltroRelacionCampoCampana", ""), data.get("FiltroRelacionTipoCampana", "TEXTO"), int(data.get("FiltroActivo", 0) or 0),
                ),
            )
            conn.commit()
            logger.info(
                "Configuración legacy guardada: %s -> %s:%s",
                data["Nombre"],
                data["SqlitePath"],
                data["SqliteTable"],
            )
            return int(cur.lastrowid)

    def update_setting(self, setting_id: int, data: dict[str, Any]) -> None:
        data = self._with_campaign_defaults(data)
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                '''
                UPDATE LegacyTableSyncSettings
                SET Nombre=?, AccessPath=?, AccessTable=?, SqlitePath=?, SqliteTable=?,
                    Modo=?, Activa=?, Observaciones=?, FechaModificacion=?,
                    FiltroCampanaModo=?, FiltroCampanaCampo=?, FiltroCampanaTipo=?, FiltroCampanaValorOrigen=?, FiltroCampanaValorFijo=?,
                    FiltroRelacionTabla=?, FiltroRelacionCampoLocal=?, FiltroRelacionCampoRemoto=?, FiltroRelacionCampoCampana=?,
                    FiltroRelacionTipoCampana=?, FiltroActivo=?
                WHERE Id=?
                ''',
                (
                    data["Nombre"], data["AccessPath"], data["AccessTable"], data["SqlitePath"], data["SqliteTable"],
                    data.get("Modo", "REEMPLAZAR_TABLA"), int(data.get("Activa", 1)), data.get("Observaciones", ""), now,
                    data.get("FiltroCampanaModo", "NINGUNO"), data.get("FiltroCampanaCampo", ""), data.get("FiltroCampanaTipo", "TEXTO"),
                    data.get("FiltroCampanaValorOrigen", "CAMPANA_ACTIVA"), data.get("FiltroCampanaValorFijo", ""),
                    data.get("FiltroRelacionTabla", ""), data.get("FiltroRelacionCampoLocal", ""), data.get("FiltroRelacionCampoRemoto", ""),
                    data.get("FiltroRelacionCampoCampana", ""), data.get("FiltroRelacionTipoCampana", "TEXTO"), int(data.get("FiltroActivo", 0) or 0), setting_id,
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
                 FilasExportadas, FilasImportadas, ModoUsado, TablaDestinoExistia, TablaDestinoCreada, Mensaje, Error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    log_data.get("SettingId"), log_data.get("Nombre"), log_data.get("AccessPath"), log_data.get("AccessTable"),
                    log_data.get("SqlitePath"), log_data.get("SqliteTable"), log_data.get("Inicio"), log_data.get("Fin"),
                    int(log_data.get("Ok", 0)), log_data.get("FilasExportadas", 0), log_data.get("FilasImportadas", 0),
                    log_data.get("ModoUsado", "REEMPLAZAR_TABLA"),
                    int(log_data.get("TablaDestinoExistia", 0)),
                    int(log_data.get("TablaDestinoCreada", 0)),
                    log_data.get("Mensaje", ""), log_data.get("Error", ""),
                ),
            )

    def get_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM LegacyTableSyncLog ORDER BY Id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
