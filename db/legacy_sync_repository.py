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

SYNC_MANAGER_COLUMNS = {
    "Grupo": "TEXT",
    "Descripcion": "TEXT",
    "OrigenTipo": "TEXT NOT NULL DEFAULT 'ACCESS'",
    "DestinoTipo": "TEXT NOT NULL DEFAULT 'SQLITE'",
    "FiltroModo": "TEXT NOT NULL DEFAULT 'NINGUNO'",
    "FiltroCampo": "TEXT",
    "FiltroTipo": "TEXT NOT NULL DEFAULT 'TEXTO'",
    "FiltroValorOrigen": "TEXT NOT NULL DEFAULT 'CAMPANA_ACTIVA'",
    "FiltroValorFijo": "TEXT",
    "ReemplazoModo": "TEXT NOT NULL DEFAULT 'TABLA_COMPLETA'",
    "CrearSnapshotDespues": "INTEGER NOT NULL DEFAULT 1",
    "LimpiarCacheDespues": "INTEGER NOT NULL DEFAULT 1",
    "OrdenEjecucion": "INTEGER NOT NULL DEFAULT 100",
    "RequiereConfirmacion": "INTEGER NOT NULL DEFAULT 0",
}

DEFAULT_SYNC_MANAGER_SETTINGS = {
    "pedidos": {"Grupo": "Planificación", "FiltroActivo": 1, "FiltroModo": "DIRECTO", "FiltroCampo": "Campaña", "FiltroTipo": "TEXTO", "ReemplazoModo": "PARTICION"},
    "loteado": {"Grupo": "Producción", "FiltroActivo": 1, "FiltroModo": "DIRECTO", "FiltroCampo": "CAMPAÑA", "FiltroTipo": "ENTERO", "ReemplazoModo": "PARTICION"},
    "lote": {"Grupo": "Producción", "FiltroActivo": 1, "FiltroModo": "PREFIJO_NUMERICO", "FiltroCampo": "IdPalet", "FiltroTipo": "ENTERO", "ReemplazoModo": "PARTICION"},
    "pesosfres": {"Grupo": "Stock", "FiltroActivo": 1, "FiltroModo": "DIRECTO", "FiltroCampo": "CAMPAÑA", "FiltroTipo": "ENTERO", "ReemplazoModo": "PARTICION"},
    "datoscalibre": {"Grupo": "Calidad", "FiltroActivo": 1, "FiltroModo": "DIRECTO", "FiltroCampo": "CAMPAÑA", "FiltroTipo": "ENTERO", "ReemplazoModo": "PARTICION"},
    "partidas": {"Grupo": "Calidad", "FiltroActivo": 1, "FiltroModo": "PREFIJO_TEXTO", "FiltroCampo": "IdPartidaP", "FiltroTipo": "TEXTO", "ReemplazoModo": "PARTICION"},
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
            for column, definition in {**FILTER_COLUMNS, **SYNC_MANAGER_COLUMNS}.items():
                if column not in settings_cols:
                    conn.execute(f"ALTER TABLE LegacyTableSyncSettings ADD COLUMN {column} {definition}")
            self._apply_default_campaign_filters(conn)
            self._apply_default_sync_manager_settings(conn)

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

    def _apply_default_sync_manager_settings(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT Id, Nombre, AccessTable, SqliteTable FROM LegacyTableSyncSettings").fetchall()
        for row in rows:
            names = [str(row["AccessTable"] or "").lower(), str(row["SqliteTable"] or "").lower(), str(row["Nombre"] or "").lower()]
            defaults = next((DEFAULT_SYNC_MANAGER_SETTINGS[name] for name in names if name in DEFAULT_SYNC_MANAGER_SETTINGS), None)
            if not defaults:
                continue
            assignments = ", ".join(f"{key}=?" for key in defaults)
            conn.execute(
                f"UPDATE LegacyTableSyncSettings SET {assignments} WHERE Id=? AND (Grupo IS NULL OR Grupo='' OR COALESCE(FiltroModo, 'NINGUNO')='NINGUNO')",
                (*defaults.values(), row["Id"]),
            )
            self._sync_new_filter_aliases(conn, row["Id"], defaults)

    @staticmethod
    def _sync_alias_payload(data: dict[str, Any]) -> dict[str, Any]:
        merged = dict(data)
        alias_pairs = {
            "FiltroModo": "FiltroCampanaModo",
            "FiltroCampo": "FiltroCampanaCampo",
            "FiltroTipo": "FiltroCampanaTipo",
            "FiltroValorOrigen": "FiltroCampanaValorOrigen",
            "FiltroValorFijo": "FiltroCampanaValorFijo",
        }
        for new_key, old_key in alias_pairs.items():
            if merged.get(new_key) not in (None, ""):
                value = merged[new_key]
                if new_key == "FiltroModo" and str(value).upper().startswith("PREFIJO_"):
                    value = "PREFIJO"
                merged[old_key] = value
            elif merged.get(old_key) not in (None, ""):
                merged[new_key] = merged[old_key]
        if merged.get("Descripcion") and not merged.get("Observaciones"):
            merged["Observaciones"] = merged["Descripcion"]
        elif merged.get("Observaciones") and not merged.get("Descripcion"):
            merged["Descripcion"] = merged["Observaciones"]
        return merged

    def _sync_new_filter_aliases(self, conn: sqlite3.Connection, setting_id: int, data: dict[str, Any]) -> None:
        payload = self._sync_alias_payload(data)
        conn.execute(
            """UPDATE LegacyTableSyncSettings SET
               FiltroCampanaModo=?, FiltroCampanaCampo=?, FiltroCampanaTipo=?, FiltroCampanaValorOrigen=?, FiltroCampanaValorFijo=?
               WHERE Id=?""",
            (payload.get("FiltroCampanaModo", "NINGUNO"), payload.get("FiltroCampanaCampo", ""), payload.get("FiltroCampanaTipo", "TEXTO"),
             payload.get("FiltroCampanaValorOrigen", "CAMPANA_ACTIVA"), payload.get("FiltroCampanaValorFijo", ""), setting_id),
        )

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
        data = self._sync_alias_payload(self._with_campaign_defaults(data))
        now = datetime.utcnow().isoformat(timespec="seconds")
        columns = [
            "Nombre", "Grupo", "Descripcion", "AccessPath", "AccessTable", "OrigenTipo", "SqlitePath", "SqliteTable", "DestinoTipo",
            "Modo", "Activa", "Observaciones", "FechaCreacion", "FechaModificacion", "FiltroActivo", "FiltroModo", "FiltroCampo",
            "FiltroTipo", "FiltroValorOrigen", "FiltroValorFijo", "ReemplazoModo", "CrearSnapshotDespues", "LimpiarCacheDespues",
            "OrdenEjecucion", "RequiereConfirmacion", "FiltroCampanaModo", "FiltroCampanaCampo", "FiltroCampanaTipo",
            "FiltroCampanaValorOrigen", "FiltroCampanaValorFijo", "FiltroRelacionTabla", "FiltroRelacionCampoLocal",
            "FiltroRelacionCampoRemoto", "FiltroRelacionCampoCampana", "FiltroRelacionTipoCampana",
        ]
        defaults = {"OrigenTipo": "ACCESS", "DestinoTipo": "SQLITE", "Modo": "REEMPLAZAR_TABLA", "Activa": 1, "FiltroActivo": 0,
                    "FiltroModo": "NINGUNO", "FiltroTipo": "TEXTO", "FiltroValorOrigen": "CAMPANA_ACTIVA", "ReemplazoModo": "TABLA_COMPLETA",
                    "CrearSnapshotDespues": 1, "LimpiarCacheDespues": 1, "OrdenEjecucion": 100, "RequiereConfirmacion": 0,
                    "FiltroCampanaModo": "NINGUNO", "FiltroCampanaTipo": "TEXTO", "FiltroCampanaValorOrigen": "CAMPANA_ACTIVA",
                    "FiltroRelacionTipoCampana": "TEXTO", "FechaCreacion": now, "FechaModificacion": now}
        values = [data.get(c, defaults.get(c, "")) for c in columns]
        with self._connect() as conn:
            cur = conn.execute(f"INSERT INTO LegacyTableSyncSettings ({', '.join(columns)}) VALUES ({', '.join(['?']*len(columns))})", values)
            conn.commit()
            logger.info("Configuración legacy guardada: %s -> %s:%s", data["Nombre"], data["SqlitePath"], data["SqliteTable"])
            return int(cur.lastrowid)

    def update_setting(self, setting_id: int, data: dict[str, Any]) -> None:
        data = self._sync_alias_payload(self._with_campaign_defaults(data))
        now = datetime.utcnow().isoformat(timespec="seconds")
        columns = [
            "Nombre", "Grupo", "Descripcion", "AccessPath", "AccessTable", "OrigenTipo", "SqlitePath", "SqliteTable", "DestinoTipo",
            "Modo", "Activa", "Observaciones", "FechaModificacion", "FiltroActivo", "FiltroModo", "FiltroCampo", "FiltroTipo",
            "FiltroValorOrigen", "FiltroValorFijo", "ReemplazoModo", "CrearSnapshotDespues", "LimpiarCacheDespues", "OrdenEjecucion",
            "RequiereConfirmacion", "FiltroCampanaModo", "FiltroCampanaCampo", "FiltroCampanaTipo", "FiltroCampanaValorOrigen",
            "FiltroCampanaValorFijo", "FiltroRelacionTabla", "FiltroRelacionCampoLocal", "FiltroRelacionCampoRemoto",
            "FiltroRelacionCampoCampana", "FiltroRelacionTipoCampana",
        ]
        defaults = {"OrigenTipo": "ACCESS", "DestinoTipo": "SQLITE", "Modo": "REEMPLAZAR_TABLA", "Activa": 1, "FiltroActivo": 0,
                    "FiltroModo": "NINGUNO", "FiltroTipo": "TEXTO", "FiltroValorOrigen": "CAMPANA_ACTIVA", "ReemplazoModo": "TABLA_COMPLETA",
                    "CrearSnapshotDespues": 1, "LimpiarCacheDespues": 1, "OrdenEjecucion": 100, "RequiereConfirmacion": 0,
                    "FiltroCampanaModo": "NINGUNO", "FiltroCampanaTipo": "TEXTO", "FiltroCampanaValorOrigen": "CAMPANA_ACTIVA",
                    "FiltroRelacionTipoCampana": "TEXTO", "FechaModificacion": now}
        values = [data.get(c, defaults.get(c, "")) for c in columns]
        with self._connect() as conn:
            conn.execute(f"UPDATE LegacyTableSyncSettings SET {', '.join(c+'=?' for c in columns)} WHERE Id=?", (*values, setting_id))
            conn.commit()
            logger.info("Configuración legacy actualizada: %s", data.get("Nombre", setting_id))

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
