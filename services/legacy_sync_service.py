from __future__ import annotations

import csv
from datetime import date, datetime
import logging
from pathlib import Path
import re
import sqlite3
import subprocess
from typing import Any

from config import CENTRAL_SQLITE_DIR, DB_LOTEADO
from db.legacy_sync_repository import LegacySyncRepository
from services.runtime_database_service import RuntimeDatabaseService


VALID_MODES = {"REEMPLAZAR_TABLA", "CREAR_O_REEMPLAZAR", "PLANIFICACION_HOY_EN_ADELANTE"}
logger = logging.getLogger(__name__)


CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE = (
    "Operación bloqueada: no se permite reemplazar tablas directamente sobre SQLite central."
)
CENTRAL_SQLITE_WRITE_BLOCK_RECOMMENDATION = "Usar sincronización segura/staging."


def _normalize_path_for_safety(path: Path | str) -> str:
    raw = str(path or "").strip().replace("/", "\\")
    while "\\\\" in raw[2:]:
        raw = raw[:2] + raw[2:].replace("\\\\", "\\")
    return raw.rstrip("\\").casefold()


def is_central_sqlite_path(path: Path) -> bool:
    """Return True when *path* points inside CENTRAL_SQLITE_DIR.

    Network UNC paths are best-effort here: on non-Windows hosts pathlib cannot
    resolve them as UNC roots, so we compare normalized textual paths first and
    use resolved paths as an additional fallback.
    """
    central = _normalize_path_for_safety(CENTRAL_SQLITE_DIR)
    target = _normalize_path_for_safety(path)
    if target == central or target.startswith(f"{central}\\"):
        return True
    try:
        resolved_central = _normalize_path_for_safety(Path(CENTRAL_SQLITE_DIR).resolve(strict=False))
        resolved_target = _normalize_path_for_safety(path.resolve(strict=False))
        return resolved_target == resolved_central or resolved_target.startswith(f"{resolved_central}\\")
    except Exception:
        return False


class LegacySyncService:
    def __init__(self) -> None:
        self.repository = LegacySyncRepository()
        self.temp_dir = Path("temp") / "legacy_sync"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.vbs_path = Path("legacy_scripts") / "export_access_table.vbs"
        self._sync_running = False
        self.runtime_db = RuntimeDatabaseService()
        self.ensure_default_planificacion_settings()

    def ensure_default_planificacion_settings(self) -> None:
        settings = self.repository.get_settings()
        access_loteado = self._find_existing_access_path(settings, ["Loteado", "Lote"])
        access_fruta = self._find_existing_access_path(settings, ["PesosFres", "DBfruta"])
        access_pedidos = self._find_existing_access_path(settings, ["Pedidos"])
        missing_access_groups: list[str] = []
        if not access_pedidos:
            missing_access_groups.append("Pedidos")
        if not access_loteado:
            missing_access_groups.append("Loteado")
        if not access_fruta:
            missing_access_groups.append("PesosFres")
        if missing_access_groups:
            logger.warning(
                "Falta configurar ruta MDB origen para %s",
                "/".join(missing_access_groups),
            )
            return
        defaults = [
            {
                "Nombre": "Pedidos",
                "AccessTable": "Pedidos",
                "AccessPath": access_pedidos,
                "SqliteTable": "Pedidos",
                "SqlitePath": str(Path(CENTRAL_SQLITE_DIR) / "DBPedidos.sqlite"),
                "Modo": "PLANIFICACION_HOY_EN_ADELANTE",
                "Activa": 1,
            },
            {
                "Nombre": "Loteado",
                "AccessTable": "Loteado",
                "AccessPath": access_loteado,
                "SqliteTable": "Loteado",
                "SqlitePath": str(Path(CENTRAL_SQLITE_DIR) / "bdloteado.sqlite"),
                "Modo": "PLANIFICACION_HOY_EN_ADELANTE",
                "Activa": 1,
            },
            {
                "Nombre": "Lote",
                "AccessTable": "Lote",
                "AccessPath": access_loteado,
                "SqliteTable": "Lote",
                "SqlitePath": str(Path(CENTRAL_SQLITE_DIR) / "bdloteado.sqlite"),
                "Modo": "PLANIFICACION_HOY_EN_ADELANTE",
                "Activa": 1,
            },
            {
                "Nombre": "PesosFres",
                "AccessTable": "PesosFres",
                "AccessPath": access_fruta,
                "SqliteTable": "PesosFres",
                "SqlitePath": str(Path(CENTRAL_SQLITE_DIR) / "DBfruta.sqlite"),
                "Modo": "PLANIFICACION_HOY_EN_ADELANTE",
                "Activa": 1,
            },
        ]
        for default in defaults:
            sqlite_file = Path(default["SqlitePath"]).name.lower()
            sqlite_table = default["SqliteTable"].lower()
            access_table = default["AccessTable"].lower()
            exists = any(
                Path(str(s.get("SqlitePath", ""))).name.lower() == sqlite_file
                and str(s.get("SqliteTable", "")).lower() == sqlite_table
                and str(s.get("AccessTable", "")).lower() == access_table
                for s in settings
            )
            if exists:
                continue
            data = dict(default)
            self.repository.add_setting(data)
            settings.append(data)
            logger.info("Configuración legacy creada automáticamente: %s", default["Nombre"])

    def get_settings(self) -> list[dict[str, Any]]:
        return self.repository.get_settings()

    def add_setting(self, data: dict[str, Any]) -> int:
        self._validate(data)
        return self.repository.add_setting(data)

    def update_setting(self, setting_id: int, data: dict[str, Any]) -> None:
        self._validate(data)
        self.repository.update_setting(setting_id, data)

    def delete_setting(self, setting_id: int) -> None:
        self.repository.delete_setting(setting_id)

    def get_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.repository.get_logs(limit)

    def setting_targets_central_sqlite(self, setting: dict[str, Any]) -> bool:
        return is_central_sqlite_path(Path(str(setting.get("SqlitePath", ""))))

    def get_central_sqlite_blocked_settings(self, active_only: bool = False) -> list[dict[str, Any]]:
        settings = self.repository.get_active_settings() if active_only else self.repository.get_settings()
        return [
            row
            for row in settings
            if self.setting_targets_central_sqlite(row)
            and self._normalize_mode(str(row.get("Modo", "REEMPLAZAR_TABLA"))) != "REEMPLAZAR_TABLA"
        ]

    def _central_sqlite_block_error(self, setting: dict[str, Any], mode: str) -> str:
        sqlite_path = Path(str(setting.get("SqlitePath", "")))
        logger.error(
            "Operación destructiva bloqueada sobre SQLite central. destino=%s modo=%s legacy=%s recomendacion=%s",
            sqlite_path,
            mode,
            setting.get("Nombre", ""),
            CENTRAL_SQLITE_WRITE_BLOCK_RECOMMENDATION,
        )
        return CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE

    def _ensure_not_central_sqlite_write(self, setting: dict[str, Any], mode: str) -> None:
        if self.setting_targets_central_sqlite(setting):
            raise PermissionError(self._central_sqlite_block_error(setting, mode))

    def test_access_table(self, setting_id: int) -> tuple[bool, str]:
        ok, msg, _, _ = self._run_export(setting_id)
        return ok, msg

    def sync_setting(self, setting_id: int) -> tuple[bool, str]:
        start = datetime.utcnow().isoformat(timespec="seconds")
        setting = self.repository.get_setting(setting_id)
        if not setting:
            return False, "Configuración no encontrada"
        mode = self._normalize_mode(str(setting.get("Modo", "REEMPLAZAR_TABLA")))
        if mode == "PLANIFICACION_HOY_EN_ADELANTE":
            if self.setting_targets_central_sqlite(setting):
                msg = self._central_sqlite_block_error(setting, mode)
                self.repository.update_sync_result(setting_id, False, "Operación bloqueada por seguridad", msg)
                return False, msg
            return self.sync_planificacion_hoy_en_adelante(setting_id)
        if mode == "REEMPLAZAR_TABLA":
            ok, message, metrics = self.safe_sync_table(setting)
            end = datetime.utcnow().isoformat(timespec="seconds")
            err = "" if ok else str(metrics.get("Error") or message)
            self.repository.update_sync_result(setting_id, ok, message, err or None)
            self.repository.add_log(
                {
                    "SettingId": setting_id,
                    "Nombre": setting["Nombre"],
                    "AccessPath": setting["AccessPath"],
                    "AccessTable": setting["AccessTable"],
                    "SqlitePath": setting["SqlitePath"],
                    "SqliteTable": setting["SqliteTable"],
                    "Inicio": start,
                    "Fin": end,
                    "Ok": 1 if ok else 0,
                    "FilasExportadas": metrics.get("FilasExportadas", 0),
                    "FilasImportadas": metrics.get("FilasImportadas", 0),
                    "Mensaje": message,
                    "Error": err,
                    "ModoUsado": mode,
                    "TablaDestinoExistia": 1 if metrics.get("TablaDestinoExistia") else 0,
                    "TablaDestinoCreada": 1 if metrics.get("TablaDestinoCreada") else 0,
                }
            )
            return ok, message
        return False, "Modo no soportado todavía"

    def safe_sync_table(self, setting: dict[str, Any]) -> tuple[bool, str, dict]:
        """Synchronize a legacy Access table via CSV and local staging SQLite."""
        metrics: dict[str, Any] = {
            "FilasExportadas": 0,
            "FilasImportadas": 0,
            "ModoUsado": self._normalize_mode(str(setting.get("Modo", "REEMPLAZAR_TABLA"))),
            "TablaDestinoExistia": False,
            "TablaDestinoCreada": False,
        }
        setting_id = int(setting.get("Id") or 0)
        table_name = str(setting.get("SqliteTable", "")).strip()
        target_sqlite_path = Path(str(setting.get("SqlitePath", "")))
        allow_empty = bool(int(setting.get("AllowEmpty", 0) or 0))
        logger.info("Inicio safe sync legacy=%s tabla=%s destino=%s", setting.get("Nombre", ""), table_name, target_sqlite_path)
        try:
            self._validate_identifier(table_name)
            ok, export_msg, csv_path, exported = self._run_export(setting_id)
            metrics["FilasExportadas"] = exported
            if not ok or not csv_path:
                raise RuntimeError(export_msg)
            logger.info("CSV generado tabla=%s path=%s filas_exportadas=%s", table_name, csv_path, exported)
            csv_info = self._validate_csv_for_sync(csv_path, allow_empty=allow_empty)
            logger.info("CSV validado tabla=%s columnas=%s filas=%s", table_name, csv_info["columns"], csv_info["rows"])
            staging_dir = self.temp_dir / "staging"
            staging_dir.mkdir(parents=True, exist_ok=True)
            staging_sqlite_path = staging_dir / f"{table_name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}.sqlite"
            staging_info = self._import_csv_to_staging_sqlite(csv_path, staging_sqlite_path, table_name)
            logger.info("SQLite staging creada tabla=%s path=%s", table_name, staging_sqlite_path)
            logger.info("Filas importadas en staging tabla=%s filas=%s", table_name, staging_info["rows"])
            staging_validation = self._validate_staging_table(staging_sqlite_path, table_name, allow_empty=allow_empty)
            logger.info("Staging validada tabla=%s filas=%s columnas=%s", table_name, staging_validation["rows"], staging_validation["columns"])
            replace_info = self._replace_table_from_staging(staging_sqlite_path, target_sqlite_path, table_name, allow_empty=allow_empty)
            metrics.update(replace_info)
            metrics["FilasImportadas"] = int(staging_validation["rows"])
            message = f"Sincronización segura completada. Exportados={exported} Importados={metrics['FilasImportadas']}"
            return True, message, metrics
        except Exception as exc:
            logger.exception("Sincronización segura cancelada. La tabla anterior se ha conservado. tabla=%s", table_name)
            metrics["Error"] = str(exc)
            return False, "Sincronización cancelada. La tabla anterior se ha conservado.", metrics

    def sync_active_settings(self) -> list[tuple[int, bool, str]]:
        results = []
        for row in self.repository.get_active_settings():
            ok, msg = self.sync_setting(int(row["Id"]))
            results.append((int(row["Id"]), ok, msg))
        return results

    def sync_planificacion_hoy_en_adelante(self, setting_id: int | None = None) -> tuple[bool, str]:
        if self._sync_running:
            return False, "Actualización ya en curso"
        self._sync_running = True
        start = datetime.utcnow()
        fecha_corte = date.today().isoformat()
        try:
            ok_required, required_msg = self._validate_required_planificacion_settings()
            if not ok_required:
                return False, required_msg
            blocked = self.get_central_sqlite_blocked_settings(active_only=True)
            if blocked:
                first = blocked[0]
                msg = self._central_sqlite_block_error(first, str(first.get("Modo", "PLANIFICACION_HOY_EN_ADELANTE")))
                if setting_id:
                    self.repository.update_sync_result(setting_id, False, "Operación bloqueada por seguridad", msg)
                return False, msg
            logger.info("Sync planificación usando CENTRAL_SQLITE_DIR=%s", CENTRAL_SQLITE_DIR)
            logger.info("Iniciando actualización planificación rápida. Fecha corte=%s", fecha_corte)
            pedidos = self._actualizar_pedidos_desde_hoy(fecha_corte)
            id_palets, loteado = self._actualizar_loteado_desde_hoy(fecha_corte)
            lote = self._actualizar_lote_por_palets(id_palets)
            pesos = self._actualizar_pesosfres_desde_hoy(fecha_corte)
            elapsed = (datetime.utcnow() - start).total_seconds()
            msg = (
                f"Planificación rápida OK. Pedidos: {pedidos} | Loteado: {loteado} | "
                f"Lote: {lote} | PesosFres: {pesos}"
            )
            logger.info("%s | tiempo=%.2fs", msg, elapsed)
            runtime_ok, runtime_errors = self.runtime_db.prepare_runtime_databases(force=True)
            if not runtime_ok:
                logger.warning("No se pudo refrescar totalmente runtime_db tras actualización legacy. Errores en: %s", runtime_errors)
                msg = f"{msg}. {self.runtime_db.WARNING_MESSAGE}"
            if setting_id:
                self.repository.update_sync_result(setting_id, True, msg, None)
            return True, msg
        except sqlite3.OperationalError as exc:
            if "database is locked" in str(exc).lower():
                msg = "La base de datos está en uso. Cierra pantallas abiertas o espera unos segundos y vuelve a intentar."
                logger.exception("Bloqueo SQLite en planificación rápida: %s", exc)
                if setting_id:
                    self.repository.update_sync_result(setting_id, False, "Error en planificación rápida", msg)
                return False, msg
            err = f"Error actualización planificación rápida: {exc}"
            logger.exception(err)
            if setting_id:
                self.repository.update_sync_result(setting_id, False, "Error en planificación rápida", str(exc))
            return False, err
        except Exception as exc:
            err = f"Error actualización planificación rápida: {exc}"
            logger.exception(err)
            if setting_id:
                self.repository.update_sync_result(setting_id, False, "Error en planificación rápida", str(exc))
            return False, err
        finally:
            self._sync_running = False

    def _actualizar_pedidos_desde_hoy(self, fecha_corte: str) -> int:
        return self._sync_filtered_table("DBPedidos.sqlite", "Pedidos", f"SELECT * FROM Pedidos WHERE FechaSalida >= #{fecha_corte}#", "date(FechaSalida) >= date('now')")

    def _actualizar_loteado_desde_hoy(self, fecha_corte: str) -> tuple[list[str], int]:
        table_name = "Loteado"
        where = f"FechaCreacion >= #{fecha_corte}# OR FechaAlmacen >= #{fecha_corte}# OR FechaExpedicion >= #{fecha_corte}#"
        query = f"SELECT * FROM {table_name} WHERE {where}"
        setting = self._find_setting("BDLoteado.sqlite", table_name)
        ok, msg, csv_path, _ = self._run_export_custom(setting, query)
        if not ok or not csv_path:
            raise RuntimeError(msg)
        rows = self._read_csv_rows(csv_path)
        if len(rows) <= 1:
            return [], 0
        header = self._sanitize_headers(rows[0])
        idx = next((i for i,c in enumerate(header) if c.lower()=="idpalet"), -1)
        palets = sorted({r[idx] for r in rows[1:] if idx >= 0 and idx < len(r) and str(r[idx]).strip()})
        self._ensure_not_central_sqlite_write(setting, str(setting.get("Modo", "PLANIFICACION_HOY_EN_ADELANTE")))
        sqlite_path = Path(setting["SqlitePath"])
        logger.info("Inicio escritura DB sqlite_path=%s tabla=%s", sqlite_path, table_name)
        with sqlite3.connect(sqlite_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("BEGIN")
            deleted = conn.execute("DELETE FROM Loteado WHERE FechaCreacion >= date('now') OR FechaAlmacen >= date('now') OR FechaExpedicion >= date('now')").rowcount
            imported, _, _ = self._import_csv_to_sqlite_append(csv_path, sqlite_path, table_name, conn=conn)
            conn.commit()
        logger.info("Fin escritura DB sqlite_path=%s tabla=%s", sqlite_path, table_name)
        logger.info("Loteado fecha_corte=%s query=%s borrados=%s importados=%s", fecha_corte, query, deleted, imported)
        return palets, imported

    def _actualizar_lote_por_palets(self, id_palets: list[str]) -> int:
        if not id_palets:
            return 0
        chunk_size = 200
        chunks = [id_palets[i:i + chunk_size] for i in range(0, len(id_palets), chunk_size)]
        setting = self._find_setting("BDLoteado.sqlite", "Lote")
        self._ensure_not_central_sqlite_write(setting, str(setting.get("Modo", "PLANIFICACION_HOY_EN_ADELANTE")))
        sqlite_path = Path(setting["SqlitePath"])
        total_imported = 0
        failed_chunks: list[int] = []
        logger.info("Lote actualización por palets: total_idpalet=%s chunks=%s chunk_size=%s", len(id_palets), len(chunks), chunk_size)
        logger.info("Inicio escritura DB sqlite_path=%s tabla=%s", sqlite_path, "Lote")
        with sqlite3.connect(sqlite_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("BEGIN")
            for idx, chunk in enumerate(chunks, start=1):
                logger.info("Lote chunk=%03d/%03d ids_en_chunk=%s", idx, len(chunks), len(chunk))
                placeholders = ",".join(["?"] * len(chunk))
                deleted = conn.execute(f"DELETE FROM Lote WHERE IdPalet IN ({placeholders})", chunk).rowcount
                ids_sql = ",".join(
                    "'" + p.replace("'", "''") + "'"
                    for p in chunk
                )
                query = f"SELECT * FROM Lote WHERE IdPalet IN ({ids_sql})"
                ok, msg, csv_path, _ = self._run_export_custom(setting, query, output_tag=f"lote_{idx:03d}")
                if not ok or not csv_path:
                    failed_chunks.append(idx)
                    logger.error("Error exportando chunk lote=%03d ids=%s error=%s", idx, len(chunk), msg)
                    continue
                try:
                    imported, _, _ = self._import_csv_to_sqlite_append(csv_path, sqlite_path, "Lote", conn=conn)
                    total_imported += imported
                    logger.info("Lote chunk=%03d borrados=%s importados=%s", idx, deleted, imported)
                except Exception as exc:
                    failed_chunks.append(idx)
                    logger.exception("Error importando chunk lote=%03d ids=%s", idx, len(chunk))
                    logger.error("Detalle error chunk=%03d: %s", idx, exc)
            conn.commit()
        logger.info("Fin escritura DB sqlite_path=%s tabla=%s", sqlite_path, "Lote")
        if failed_chunks:
            logger.warning("Lote por palets finalizado con chunks fallidos=%s total_chunks=%s importados=%s", failed_chunks, len(chunks), total_imported)
        else:
            logger.info("Lote por palets borrados=%s importados=%s", len(id_palets), total_imported)
        return total_imported

    def _actualizar_pesosfres_desde_hoy(self, fecha_corte: str) -> int:
        return self._sync_filtered_table("DBfruta.sqlite", "PesosFres", f"SELECT * FROM PesosFres WHERE Fcarga >= #{fecha_corte}#", "date(Fcarga) >= date('now')")

    @staticmethod
    def get_campana_actual(base_date: date | None = None) -> int:
        d = base_date or date.today()
        return d.year + 1 if d.month >= 9 else d.year

    def _validate(self, data: dict[str, Any]) -> None:
        access = Path(str(data.get("AccessPath", "")).strip())
        if not access.exists():
            raise ValueError("AccessPath no existe")
        if not str(data.get("AccessTable", "")).strip():
            raise ValueError("AccessTable es obligatorio")
        if not str(data.get("SqlitePath", "")).strip():
            raise ValueError("SqlitePath es obligatorio")
        if not str(data.get("SqliteTable", "")).strip():
            raise ValueError("SqliteTable es obligatorio")
        if self._normalize_mode(str(data.get("Modo", "REEMPLAZAR_TABLA"))) not in VALID_MODES:
            raise ValueError("Modo no válido")
        self._validate_identifier(str(data.get("SqliteTable")))

    @staticmethod
    def _validate_identifier(name: str) -> None:
        if not name or name.strip() != name or any(c in name for c in [';', '"', "'", "`"]):
            raise ValueError("Nombre de tabla inválido")

    @staticmethod
    def quote_identifier(name: str) -> str:
        cleaned = (name or "").strip()
        if not cleaned or any(token in cleaned for token in ["\x00", ";", "--", "`", "\n", "\r"]):
            raise ValueError("Identificador SQL inválido")
        return '"' + cleaned.replace('"', '""') + '"'

    def _run_export(self, setting_id: int) -> tuple[bool, str, Path | None, int]:
        setting = self.repository.get_setting(setting_id)
        if not setting:
            return False, "Configuración no encontrada", None, 0
        vbs_path = self.vbs_path.resolve()
        mdb_path = Path(setting["AccessPath"]).resolve()
        temp_dir = self.temp_dir.resolve()
        csv_path = temp_dir / f"{setting['Nombre']}_{setting_id}.csv"
        log_path = temp_dir / f"{setting['Nombre']}_{setting_id}.log"
        if not vbs_path.exists():
            return False, self._build_missing_path_error("Script VBS no existe", vbs_path, mdb_path, csv_path, log_path), None, 0
        if not mdb_path.exists():
            return False, self._build_missing_path_error("MDB no existe", vbs_path, mdb_path, csv_path, log_path), None, 0
        if not temp_dir.exists():
            return False, self._build_missing_path_error("Carpeta temporal no existe", vbs_path, mdb_path, csv_path, log_path), None, 0
        command = self._build_vbs_command(vbs_path, mdb_path, setting["AccessTable"], csv_path, log_path)
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="cp1252",
            timeout=120,
        )
        logger.error("Legacy sync command: %s", command)
        logger.error("Legacy sync returncode: %s", result.returncode)
        logger.error("Legacy sync stdout: %s", result.stdout)
        logger.error("Legacy sync stderr: %s", result.stderr)
        if result.returncode != 0:
            return False, self._build_export_error_message(result, command, vbs_path, mdb_path, csv_path, log_path), None, 0
        exported = self._read_exported_rows(log_path)
        if not csv_path.exists():
            return (
                False,
                self._build_export_error_message(result, command, vbs_path, mdb_path, csv_path, log_path, "VBS terminó sin generar CSV"),
                None,
                exported,
            )
        return True, "Exportación OK", csv_path, exported



    def _sync_filtered_table(self, sqlite_name: str, table_name: str, access_query: str, sqlite_where: str) -> int:
        setting = self._find_setting(sqlite_name, table_name)
        ok, msg, csv_path, _ = self._run_export_custom(setting, access_query)
        if not ok or not csv_path:
            raise RuntimeError(msg)
        self._ensure_not_central_sqlite_write(setting, str(setting.get("Modo", "PLANIFICACION_HOY_EN_ADELANTE")))
        sqlite_path = Path(setting["SqlitePath"])
        logger.info("Inicio escritura DB sqlite_path=%s tabla=%s", sqlite_path, table_name)
        with sqlite3.connect(sqlite_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("BEGIN")
            deleted = conn.execute(f"DELETE FROM {self.quote_identifier(table_name)} WHERE {sqlite_where}").rowcount
            imported, _, _ = self._import_csv_to_sqlite_append(csv_path, sqlite_path, table_name, conn=conn)
            conn.commit()
        logger.info("Fin escritura DB sqlite_path=%s tabla=%s", sqlite_path, table_name)
        logger.info("Tabla=%s query=%s borrados=%s importados=%s", table_name, access_query, deleted, imported)
        return imported

    def _find_setting(self, sqlite_name: str, sqlite_table: str) -> dict[str, Any]:
        settings = self.repository.get_settings()
        for s in settings:
            if Path(str(s.get("SqlitePath", ""))).name.lower() == sqlite_name.lower() and str(s.get("SqliteTable", "")).lower() == sqlite_table.lower():
                return s
        raise ValueError(
            f"No existe configuración legacy para {sqlite_name}:{sqlite_table}.\n"
            f"Base configuración: {self.repository.db_path}.\n"
            f"Configuraciones encontradas: {len(settings)}"
        )

    def resolve_default_access_path_for_planificacion(self) -> str:
        settings = self.repository.get_settings()
        return (
            self._find_existing_access_path(settings, ["Pedidos", "Loteado", "Lote", "PesosFres", "DBfruta"])
            or self._resolve_default_access_path(settings, "dbpedidos.sqlite", "pedidos")
        )

    def create_or_update_planificacion_defaults(self, access_path: str) -> int:
        access = str(access_path or "").strip()
        if not access:
            raise ValueError("AccessPath obligatorio para crear configuración por defecto.")
        defaults = [
            ("Pedidos", "Pedidos", "DBPedidos.sqlite", "Pedidos"),
            ("Loteado", "Loteado", "bdloteado.sqlite", "Loteado"),
            ("Lote", "Lote", "bdloteado.sqlite", "Lote"),
            ("PesosFres", "PesosFres", "DBfruta.sqlite", "PesosFres"),
        ]
        settings = self.repository.get_settings()
        updated = 0
        for nombre, access_table, sqlite_file, sqlite_table in defaults:
            payload = {
                "Nombre": nombre,
                "AccessPath": access,
                "AccessTable": access_table,
                "SqlitePath": str(Path(CENTRAL_SQLITE_DIR) / sqlite_file),
                "SqliteTable": sqlite_table,
                "Modo": "PLANIFICACION_HOY_EN_ADELANTE",
                "Activa": 1,
                "Observaciones": "",
            }
            existing = next(
                (
                    row for row in settings
                    if Path(str(row.get("SqlitePath", ""))).name.lower() == sqlite_file.lower()
                    and str(row.get("SqliteTable", "")).lower() == sqlite_table.lower()
                ),
                None,
            )
            if existing:
                self.repository.update_setting(int(existing["Id"]), payload)
            else:
                self.repository.add_setting(payload)
            updated += 1
        return updated

    @staticmethod
    def _resolve_default_access_path(settings: list[dict[str, Any]], sqlite_file: str, access_table: str) -> str:
        for setting in settings:
            if Path(str(setting.get("SqlitePath", ""))).name.lower() == sqlite_file:
                access_path = str(setting.get("AccessPath", "")).strip()
                if access_path:
                    return access_path
        for setting in settings:
            if str(setting.get("AccessTable", "")).lower() == access_table:
                access_path = str(setting.get("AccessPath", "")).strip()
                if access_path:
                    return access_path
        for setting in settings:
            access_path = str(setting.get("AccessPath", "")).strip()
            if access_path:
                return access_path
        return ""

    @staticmethod
    def _find_existing_access_path(settings: list[dict[str, Any]], aliases: list[str]) -> str:
        aliases_lower = {a.lower() for a in aliases}
        for setting in settings:
            if not int(setting.get("Activa", 1)):
                continue
            sqlite_name = Path(str(setting.get("SqlitePath", ""))).name.lower()
            access_table = str(setting.get("AccessTable", "")).lower()
            nombre = str(setting.get("Nombre", "")).lower()
            if sqlite_name in {f"{a.lower()}.sqlite" for a in aliases} or access_table in aliases_lower or nombre in aliases_lower:
                access_path = str(setting.get("AccessPath", "")).strip()
                if access_path:
                    return access_path
        return ""

    def _validate_required_planificacion_settings(self) -> tuple[bool, str]:
        required = [
            ("DBPedidos.sqlite", "Pedidos"),
            ("bdloteado.sqlite", "Loteado"),
            ("bdloteado.sqlite", "Lote"),
            ("DBfruta.sqlite", "PesosFres"),
        ]
        missing: list[str] = []
        for sqlite_name, sqlite_table in required:
            try:
                setting = self._find_setting(sqlite_name, sqlite_table)
            except Exception:
                missing.append(f"Falta configuración: {sqlite_name}:{sqlite_table}")
                continue
            access_path_raw = str(setting.get("AccessPath", "")).strip()
            if not access_path_raw:
                missing.append(f"AccessPath vacío para {sqlite_name}:{sqlite_table}")
            else:
                access_path = Path(access_path_raw).resolve()
                if not access_path.exists():
                    missing.append(f"MDB origen no existe para {sqlite_name}:{sqlite_table}: {access_path}")
            sqlite_path_raw = str(setting.get("SqlitePath", "")).strip()
            if not sqlite_path_raw:
                missing.append(f"SqlitePath vacío para {sqlite_name}:{sqlite_table}")
            else:
                sqlite_parent = Path(sqlite_path_raw).resolve().parent
                try:
                    sqlite_parent.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    missing.append(f"No se pudo crear carpeta SQLite para {sqlite_name}:{sqlite_table}: {sqlite_parent} ({exc})")
            if not self.vbs_path.resolve().exists():
                missing.append(f"Script VBS no existe: {self.vbs_path.resolve()}")
        if missing:
            return False, "Rutas inválidas para exportación:\n" + "\n".join(missing)
        return True, ""

    def _run_export_custom(self, setting: dict[str, Any], table_or_query: str, output_tag: str | None = None) -> tuple[bool, str, Path | None, int]:
        tmp = dict(setting)
        tmp["AccessTable"] = table_or_query
        if output_tag:
            tmp["ExportTag"] = output_tag
        return self._run_export_from_setting(tmp)

    def _run_export_from_setting(self, setting: dict[str, Any]) -> tuple[bool, str, Path | None, int]:
        vbs_path = self.vbs_path.resolve()
        mdb_path = Path(setting["AccessPath"]).resolve()
        temp_dir = self.temp_dir.resolve()
        export_tag = setting.get('ExportTag') or f"{setting['Nombre']}_{setting.get('Id','adhoc')}"
        csv_path = temp_dir / f"{export_tag}.csv"
        log_path = temp_dir / f"{export_tag}.log"
        logger.info("Export legacy VBS=%s", vbs_path)
        logger.info("Export legacy MDB=%s existe=%s", mdb_path, mdb_path.exists())
        logger.info("Export legacy CSV=%s", csv_path)
        logger.info("Export legacy LOG=%s", log_path)
        missing = []
        if not vbs_path.exists():
            missing.append(f"Script VBS no existe: {vbs_path}")
        if not mdb_path.exists():
            missing.append(f"MDB origen no existe: {mdb_path}")
        if not temp_dir.exists():
            try:
                temp_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                missing.append(f"No se pudo crear carpeta temporal: {temp_dir} ({exc})")
        if missing:
            return False, "Rutas inválidas para exportación:\n" + "\n".join(missing), None, 0
        command = self._build_vbs_command(vbs_path, mdb_path, setting["AccessTable"], csv_path, log_path)
        result = subprocess.run(command, capture_output=True, text=True, encoding="cp1252", timeout=120)
        if result.returncode != 0:
            return False, self._build_export_error_message(result, command, vbs_path, mdb_path, csv_path, log_path), None, 0
        return True, "Exportación OK", csv_path, self._read_exported_rows(log_path)

    def _import_csv_to_sqlite_append(self, csv_path: Path, sqlite_path: Path, table_name: str, conn: sqlite3.Connection | None = None) -> tuple[int, bool, bool]:
        rows = self._read_csv_rows(csv_path)
        if not rows:
            return 0, True, False
        header = self._sanitize_headers(rows[0])
        data_rows = rows[1:]
        table = self.quote_identifier(table_name)
        columns = ", ".join(self.quote_identifier(c) for c in header)
        placeholders = ",".join(["?"] * len(header))
        if conn is None:
            with sqlite3.connect(sqlite_path, timeout=30) as new_conn:
                new_conn.execute("PRAGMA busy_timeout = 30000")
                new_conn.execute("PRAGMA journal_mode = WAL")
                new_conn.execute("PRAGMA synchronous = NORMAL")
                new_conn.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", [tuple(r[:len(header)] + [""]*(len(header)-len(r))) for r in data_rows])
                new_conn.commit()
        else:
            conn.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", [tuple(r[:len(header)] + [""]*(len(header)-len(r))) for r in data_rows])
        return len(data_rows), True, False

    @staticmethod
    def get_cscript_path() -> str:
        candidates = [
            r"C:\Windows\SysWOW64\cscript.exe",
            r"C:\Windows\System32\cscript.exe",
            "cscript.exe",
        ]
        for candidate in candidates:
            if candidate == "cscript.exe" or Path(candidate).exists():
                return candidate
        return "cscript.exe"

    @staticmethod
    def _to_windows_path(path: Path) -> str:
        return str(path).replace("/", "\\")

    def _build_vbs_command(self, vbs_path: Path, mdb_path: Path, table: str, csv_path: Path, log_path: Path) -> list[str]:
        return [
            self.get_cscript_path(),
            "//nologo",
            self._to_windows_path(vbs_path),
            self._to_windows_path(mdb_path),
            table,
            self._to_windows_path(csv_path),
            self._to_windows_path(log_path),
        ]

    def build_command_preview(self, setting_id: int) -> tuple[bool, str]:
        setting = self.repository.get_setting(setting_id)
        if not setting:
            return False, "Configuración no encontrada"
        vbs_path = self.vbs_path.resolve()
        mdb_path = Path(setting["AccessPath"]).resolve()
        temp_dir = self.temp_dir.resolve()
        csv_path = temp_dir / f"{setting['Nombre']}_{setting_id}.csv"
        log_path = temp_dir / f"{setting['Nombre']}_{setting_id}.log"
        command = self._build_vbs_command(vbs_path, mdb_path, setting["AccessTable"], csv_path, log_path)
        return True, " ".join(command)

    def _build_export_error_message(
        self,
        result: subprocess.CompletedProcess[str],
        command: list[str],
        vbs_path: Path,
        mdb_path: Path,
        csv_path: Path,
        log_path: Path,
        extra: str = "",
    ) -> str:
        extra_block = f"{extra}\n\n" if extra else ""
        return (
            f"{extra_block}"
            "VBS falló.\n\n"
            f"Código retorno: {result.returncode}\n\n"
            f"Ruta VBS: {vbs_path}\n"
            f"Ruta MDB: {mdb_path}\n"
            f"Ruta CSV temporal: {csv_path}\n"
            f"Ruta LOG: {log_path}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}\n\n"
            f"Comando:\n{' '.join(command)}"
        )

    @staticmethod
    def _build_missing_path_error(reason: str, vbs_path: Path, mdb_path: Path, csv_path: Path, log_path: Path) -> str:
        return (
            f"{reason}.\n\n"
            f"Ruta VBS: {vbs_path}\n"
            f"Ruta MDB: {mdb_path}\n"
            f"Ruta CSV temporal: {csv_path}\n"
            f"Ruta LOG: {log_path}"
        )

    @staticmethod
    def _read_exported_rows(log_path: Path) -> int:
        if not log_path.exists():
            return 0
        text = log_path.read_text(encoding="cp1252", errors="ignore")
        m = re.search(r"RegistrosExportados=(\d+)", text)
        return int(m.group(1)) if m else 0

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        normalized = (mode or "REEMPLAZAR_TABLA").strip().upper()
        if normalized == "CREAR_O_REEMPLAZAR":
            return "REEMPLAZAR_TABLA"
        return normalized

    def _import_csv_to_sqlite(self, csv_path: Path, sqlite_path: Path, table_name: str, mode: str) -> tuple[int, bool, bool]:
        mode = self._normalize_mode(mode)
        if is_central_sqlite_path(sqlite_path):
            logger.error(
                "Operación destructiva bloqueada sobre SQLite central. destino=%s modo=%s legacy=%s recomendacion=%s",
                sqlite_path,
                mode,
                table_name,
                CENTRAL_SQLITE_WRITE_BLOCK_RECOMMENDATION,
            )
            raise PermissionError(CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE)
        if mode != "REEMPLAZAR_TABLA":
            raise ValueError("Modo no soportado todavía")

        rows = self._read_csv_rows(csv_path)
        if not rows:
            raise ValueError("CSV vacío")
        header = self._sanitize_headers(rows[0])
        data_rows = rows[1:]
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        table = self.quote_identifier(table_name)
        col_defs = ", ".join(f"{self.quote_identifier(c)} TEXT" for c in header)
        columns = ", ".join(self.quote_identifier(c) for c in header)
        placeholders = ",".join(["?"] * len(header))

        with sqlite3.connect(sqlite_path) as conn:
            table_existed = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
            ).fetchone() is not None
            conn.execute("BEGIN")
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.execute(f"CREATE TABLE {table} ({col_defs})")
            conn.executemany(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                [tuple(r[: len(header)] + [""] * (len(header) - len(r))) for r in data_rows],
            )
            conn.commit()
        return len(data_rows), table_existed, True

    def _validate_csv_for_sync(self, csv_path: Path, allow_empty: bool = False) -> dict[str, Any]:
        """Validate a CSV before it can be imported into staging."""
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise ValueError(f"CSV no existe: {csv_path}")
        if csv_path.stat().st_size <= 0:
            raise ValueError("CSV vacío: archivo sin contenido")
        rows = self._read_csv_rows(csv_path)
        if not rows:
            raise ValueError("CSV vacío: falta cabecera")
        header = self._sanitize_headers(rows[0])
        if not header or any(not c.strip() for c in header):
            raise ValueError("CSV inválido: cabecera sin columnas válidas")
        for column in header:
            self.quote_identifier(column)
        data_rows = rows[1:]
        if not data_rows and not allow_empty:
            raise ValueError("CSV sin filas de datos: AllowEmpty no está habilitado")
        return {"columns": header, "rows": len(data_rows)}

    def _import_csv_to_staging_sqlite(self, csv_path: Path, staging_sqlite_path: Path, table_name: str) -> dict[str, Any]:
        """Create a local staging SQLite and import all CSV rows into it."""
        self._validate_identifier(table_name)
        csv_info = self._validate_csv_for_sync(csv_path, allow_empty=True)
        rows = self._read_csv_rows(csv_path)
        header = list(csv_info["columns"])
        data_rows = rows[1:]
        staging_sqlite_path = Path(staging_sqlite_path)
        staging_sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        if staging_sqlite_path.exists():
            staging_sqlite_path.unlink()
        table = self.quote_identifier(table_name)
        col_defs = ", ".join(f"{self.quote_identifier(c)} TEXT" for c in header)
        columns = ", ".join(self.quote_identifier(c) for c in header)
        placeholders = ",".join(["?"] * len(header))
        normalized_rows = [tuple(r[: len(header)] + [""] * (len(header) - len(r))) for r in data_rows]
        with sqlite3.connect(staging_sqlite_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute(f"CREATE TABLE {table} ({col_defs})")
            conn.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", normalized_rows)
            conn.commit()
        return {"columns": header, "rows": len(normalized_rows), "path": str(staging_sqlite_path)}

    def _validate_staging_table(self, staging_sqlite_path: Path, table_name: str, allow_empty: bool = False) -> dict[str, Any]:
        """Validate the staging table before touching the real destination table."""
        self._validate_identifier(table_name)
        staging_sqlite_path = Path(staging_sqlite_path)
        if not staging_sqlite_path.exists():
            raise ValueError(f"SQLite staging no existe: {staging_sqlite_path}")
        with sqlite3.connect(staging_sqlite_path, timeout=30) as conn:
            if not self._table_exists(conn, table_name):
                raise ValueError(f"Tabla staging no existe: {table_name}")
            columns = self._table_columns(conn, table_name)
            if not columns:
                raise ValueError("Tabla staging sin columnas")
            rows = self._count_rows(conn, table_name)
            if rows <= 0 and not allow_empty:
                raise ValueError("Tabla staging sin registros: AllowEmpty no está habilitado")
            return {"columns": columns, "rows": rows}

    def _replace_table_from_staging(
        self,
        staging_sqlite_path: Path,
        target_sqlite_path: Path,
        table_name: str,
        allow_empty: bool = False,
    ) -> dict[str, Any]:
        """Safely swap a validated staging table into the target SQLite."""
        self._validate_identifier(table_name)
        staging_sqlite_path = Path(staging_sqlite_path)
        target_sqlite_path = Path(target_sqlite_path)
        target_sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        backup_name = f"__backup_{table_name}_{timestamp}"
        incoming_name = f"__incoming_{table_name}_{timestamp}"
        table = self.quote_identifier(table_name)
        backup = self.quote_identifier(backup_name)
        incoming = self.quote_identifier(incoming_name)
        logger.info("SQLite destino detectada path=%s tabla=%s central=%s", target_sqlite_path, table_name, is_central_sqlite_path(target_sqlite_path))
        staging_validation = self._validate_staging_table(staging_sqlite_path, table_name, allow_empty=allow_empty)
        if int(staging_validation["rows"]) <= 0 and not allow_empty:
            raise ValueError("Incoming bloqueada: staging sin registros")
        with sqlite3.connect(target_sqlite_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            table_existed = self._table_exists(conn, table_name)
            previous_count = self._count_rows(conn, table_name) if table_existed else 0
            logger.info("Tabla real anterior tabla=%s existe=%s registros_anteriores=%s", table_name, table_existed, previous_count)
            conn.execute(f"DROP TABLE IF EXISTS {incoming}")
            conn.execute("ATTACH DATABASE ? AS staging", (str(staging_sqlite_path),))
            try:
                conn.execute(f"CREATE TABLE {incoming} AS SELECT * FROM staging.{table}")
            finally:
                conn.execute("DETACH DATABASE staging")
            incoming_count = self._count_rows(conn, incoming_name)
            incoming_columns = self._table_columns(conn, incoming_name)
            logger.info("Incoming creada tabla=%s incoming=%s registros_incoming=%s columnas=%s", table_name, incoming_name, incoming_count, incoming_columns)
            if not incoming_columns:
                conn.execute(f"DROP TABLE IF EXISTS {incoming}")
                conn.commit()
                raise ValueError("Incoming sin columnas")
            if incoming_count <= 0 and not allow_empty:
                conn.execute(f"DROP TABLE IF EXISTS {incoming}")
                conn.commit()
                raise ValueError("Incoming sin registros: tabla real anterior conservada")
            conn.commit()
            try:
                conn.execute("BEGIN")
                if table_existed:
                    conn.execute(f"DROP TABLE IF EXISTS {backup}")
                    conn.execute(f"ALTER TABLE {table} RENAME TO {backup}")
                    logger.info("Backup temporal creado tabla=%s backup=%s", table_name, backup_name)
                conn.execute(f"ALTER TABLE {incoming} RENAME TO {table}")
                final_count = self._count_rows(conn, table_name)
                if final_count <= 0 and not allow_empty:
                    raise ValueError("Conteo final inválido: tabla real quedaría vacía")
                if table_existed:
                    conn.execute(f"DROP TABLE {backup}")
                    logger.info("Backup eliminado tabla=%s backup=%s", table_name, backup_name)
                conn.commit()
                logger.info("Tabla real sustituida tabla=%s registros_finales=%s", table_name, final_count)
                return {
                    "TablaDestinoExistia": table_existed,
                    "TablaDestinoCreada": not table_existed,
                    "RegistrosAnteriores": previous_count,
                    "RegistrosIncoming": incoming_count,
                    "RegistrosFinales": final_count,
                }
            except Exception:
                logger.exception("Rollback safe sync tabla=%s; intentando conservar/restaurar tabla anterior", table_name)
                conn.rollback()
                if not self._table_exists(conn, table_name) and self._table_exists(conn, backup_name):
                    conn.execute(f"ALTER TABLE {backup} RENAME TO {table}")
                    conn.commit()
                    logger.info("Tabla anterior restaurada tabla=%s desde backup=%s", table_name, backup_name)
                if self._table_exists(conn, incoming_name):
                    conn.execute(f"DROP TABLE IF EXISTS {incoming}")
                    conn.commit()
                logger.info("Tabla anterior conservada tabla=%s", table_name)
                raise

    def safe_replace_table_from_csv(
        self,
        csv_path: Path,
        sqlite_path: Path,
        table_name: str,
        allow_empty: bool = False,
    ) -> tuple[int, bool, bool]:
        """Replace a table through a validated staging table.

        This is the only full-table replacement path allowed for central
        SQLite files. The existing table is only swapped after the CSV and the
        staging table have both been validated.
        """
        self._validate_identifier(table_name)
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        staging_name = f"staging_{table_name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        backup_name = f"backup_{table_name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        table = self.quote_identifier(table_name)
        staging = self.quote_identifier(staging_name)
        backup = self.quote_identifier(backup_name)
        logger.info("Inicio sync segura sqlite_path=%s tabla=%s csv=%s allow_empty=%s", sqlite_path, table_name, csv_path, allow_empty)

        rows = self._read_and_validate_csv_for_replace(csv_path, allow_empty=allow_empty)
        header = self._sanitize_headers(rows[0])
        data_rows = rows[1:]
        col_defs = ", ".join(f"{self.quote_identifier(c)} TEXT" for c in header)
        columns = ", ".join(self.quote_identifier(c) for c in header)
        placeholders = ",".join(["?"] * len(header))
        normalized_rows = [tuple(r[: len(header)] + [""] * (len(header) - len(r))) for r in data_rows]
        logger.info("CSV validado tabla=%s columnas=%s filas=%s", table_name, header, len(data_rows))

        with sqlite3.connect(sqlite_path, timeout=30) as conn:
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            table_existed = self._table_exists(conn, table_name)
            previous_count = self._count_rows(conn, table_name) if table_existed else 0
            previous_columns = self._table_columns(conn, table_name) if table_existed else []
            if table_existed and previous_columns and previous_columns != header:
                raise ValueError(
                    f"Columnas CSV no coinciden con tabla destino. anteriores={previous_columns} nuevas={header}"
                )
            conn.execute(f"DROP TABLE IF EXISTS {staging}")
            conn.execute(f"CREATE TABLE {staging} ({col_defs})")
            logger.info("Staging creada tabla=%s staging=%s", table_name, staging_name)
            conn.executemany(f"INSERT INTO {staging} ({columns}) VALUES ({placeholders})", normalized_rows)
            staging_count = self._count_rows(conn, staging_name)
            staging_columns = self._table_columns(conn, staging_name)
            logger.info("Staging importada tabla=%s staging=%s filas=%s columnas=%s", table_name, staging_name, staging_count, staging_columns)
            if staging_columns != header:
                raise ValueError(f"Columnas staging inválidas. esperadas={header} reales={staging_columns}")
            if staging_count == 0 and table_existed and not allow_empty:
                raise ValueError("Sustitución bloqueada: staging sin filas y AllowEmpty no está habilitado")
            logger.info(
                "Validación OK tabla=%s registros_anteriores=%s registros_staging=%s columnas_anteriores=%s columnas_nuevas=%s",
                table_name,
                previous_count,
                staging_count,
                previous_columns,
                staging_columns,
            )
            conn.commit()
            try:
                conn.execute("BEGIN")
                if table_existed:
                    conn.execute(f"ALTER TABLE {table} RENAME TO {backup}")
                    logger.info("Backup creado tabla=%s backup=%s", table_name, backup_name)
                conn.execute(f"ALTER TABLE {staging} RENAME TO {table}")
                logger.info("Tabla real sustituida tabla=%s staging=%s", table_name, staging_name)
                if table_existed:
                    conn.execute(f"DROP TABLE {backup}")
                    logger.info("Backup eliminado tabla=%s backup=%s", table_name, backup_name)
                final_count = self._count_rows(conn, table_name)
                conn.commit()
                logger.info(
                    "Sync segura OK tabla=%s registros_anteriores=%s registros_staging=%s registros_finales=%s",
                    table_name,
                    previous_count,
                    staging_count,
                    final_count,
                )
                return staging_count, table_existed, not table_existed
            except Exception:
                conn.rollback()
                logger.exception("Rollback sync segura tabla=%s. Tabla anterior conservada.", table_name)
                raise
            finally:
                if self._table_exists(conn, staging_name):
                    conn.execute(f"DROP TABLE IF EXISTS {staging}")
                    conn.commit()
                    logger.info("Staging eliminada tras fallo/limpieza tabla=%s staging=%s", table_name, staging_name)

    def _read_and_validate_csv_for_replace(self, csv_path: Path, allow_empty: bool = False) -> list[list[str]]:
        if not csv_path.exists():
            raise ValueError(f"CSV no existe: {csv_path}")
        rows = self._read_csv_rows(csv_path)
        if not rows:
            raise ValueError("CSV vacío: falta cabecera")
        header = self._sanitize_headers(rows[0])
        if not header or any(not c.strip() for c in header):
            raise ValueError("CSV inválido: cabecera sin columnas válidas")
        for column in header:
            self.quote_identifier(column)
        if len(rows) <= 1 and not allow_empty:
            raise ValueError("CSV sin filas: AllowEmpty no está habilitado")
        return rows

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None

    def _count_rows(self, conn: sqlite3.Connection, table_name: str) -> int:
        return int(conn.execute(f"SELECT COUNT(*) FROM {self.quote_identifier(table_name)}").fetchone()[0])

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> list[str]:
        return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({self.quote_identifier(table_name)})").fetchall()]

    @staticmethod
    def _read_csv_rows(path: Path) -> list[list[str]]:
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                with path.open("r", encoding=enc, newline="") as fh:
                    return list(csv.reader(fh, delimiter=";"))
            except UnicodeDecodeError:
                continue
        raise ValueError("No se pudo leer CSV")

    @staticmethod
    def _sanitize_headers(headers: list[str]) -> list[str]:
        out: list[str] = []
        seen: dict[str, int] = {}
        empty_count = 1
        for h in headers:
            name = (h or "").strip()
            if not name:
                name = f"Campo{empty_count}"
                empty_count += 1
            name = re.sub(r"\s+", "_", name)
            if name in seen:
                seen[name] += 1
                name = f"{name}_{seen[name]}"
            else:
                seen[name] = 0
            out.append(name)
        return out

    @staticmethod
    def default_sqlite_path() -> str:
        return str(Path(CENTRAL_SQLITE_DIR) / DB_LOTEADO)
