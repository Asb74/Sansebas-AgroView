from __future__ import annotations

import csv
from datetime import date, datetime
import logging
from pathlib import Path
import re
import sqlite3
import subprocess
from typing import Any

from config import DB_LOTEADO
from db.legacy_sync_repository import LegacySyncRepository


VALID_MODES = {"REEMPLAZAR_TABLA", "CREAR_O_REEMPLAZAR", "PLANIFICACION_HOY_EN_ADELANTE"}
logger = logging.getLogger(__name__)


class LegacySyncService:
    def __init__(self) -> None:
        self.repository = LegacySyncRepository()
        self.temp_dir = Path("temp") / "legacy_sync"
        self.vbs_path = Path("legacy_scripts") / "export_access_table.vbs"

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
            return self.sync_planificacion_hoy_en_adelante(setting_id)
        ok, message, csv_path, exported = self._run_export(setting_id)
        imported = 0
        err = None
        table_existed = False
        table_created = False
        if ok and csv_path:
            try:
                imported, table_existed, table_created = self._import_csv_to_sqlite(
                    csv_path=csv_path,
                    sqlite_path=Path(setting["SqlitePath"]),
                    table_name=setting["SqliteTable"],
                    mode=mode,
                )
                base_message = f"Exportados={exported} Importados={imported}"
                if not table_existed:
                    message = f"{base_message}. La tabla destino no existía. Se ha creado correctamente."
                else:
                    message = base_message
            except Exception as exc:
                ok = False
                err = str(exc)
                message = "Error importando CSV en SQLite"
        end = datetime.utcnow().isoformat(timespec="seconds")
        self.repository.update_sync_result(setting_id, ok, message, err)
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
                "FilasExportadas": exported,
                "FilasImportadas": imported,
                "Mensaje": message,
                "Error": err or "",
                "ModoUsado": self._normalize_mode(str(setting.get("Modo", "REEMPLAZAR_TABLA"))),
                "TablaDestinoExistia": 1 if table_existed else 0,
                "TablaDestinoCreada": 1 if table_created else 0,
            }
        )
        return ok, message if ok else f"{message}. {err or ''}".strip()

    def sync_active_settings(self) -> list[tuple[int, bool, str]]:
        results = []
        for row in self.repository.get_active_settings():
            ok, msg = self.sync_setting(int(row["Id"]))
            results.append((int(row["Id"]), ok, msg))
        return results

    def sync_planificacion_hoy_en_adelante(self, setting_id: int | None = None) -> tuple[bool, str]:
        start = datetime.utcnow()
        fecha_corte = date.today().isoformat()
        logger.info("Iniciando actualización planificación rápida. Fecha corte=%s", fecha_corte)
        try:
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
            if setting_id:
                self.repository.update_sync_result(setting_id, True, msg, None)
            return True, msg
        except Exception as exc:
            err = f"Error actualización planificación rápida: {exc}"
            logger.exception(err)
            if setting_id:
                self.repository.update_sync_result(setting_id, False, "Error en planificación rápida", str(exc))
            return False, err

    def _actualizar_pedidos_desde_hoy(self, fecha_corte: str) -> int:
        return self._sync_filtered_table("DBPedidos.sqlite", "Pedidos", f"SELECT * FROM Pedidos WHERE FechaSalida >= #{fecha_corte}#", "date(FechaSalida) >= date('now')")

    def _actualizar_loteado_desde_hoy(self, fecha_corte: str) -> tuple[list[str], int]:
        where = f"FechaCreacion >= #{fecha_corte}# OR FechaAlmacen >= #{fecha_corte}# OR FechaExpedicion >= #{fecha_corte}#"
        query = f"SELECT * FROM Loteado WHERE {where}"
        setting = self._find_setting("BDLoteado.sqlite", "Loteado")
        ok, msg, csv_path, _ = self._run_export_custom(setting, query)
        if not ok or not csv_path:
            raise RuntimeError(msg)
        rows = self._read_csv_rows(csv_path)
        if len(rows) <= 1:
            return [], 0
        header = self._sanitize_headers(rows[0])
        idx = next((i for i,c in enumerate(header) if c.lower()=="idpalet"), -1)
        palets = sorted({r[idx] for r in rows[1:] if idx >= 0 and idx < len(r) and str(r[idx]).strip()})
        sqlite_path = Path(setting["SqlitePath"])
        with sqlite3.connect(sqlite_path) as conn:
            conn.execute("BEGIN")
            deleted = conn.execute("DELETE FROM Loteado WHERE FechaCreacion >= date('now') OR FechaAlmacen >= date('now') OR FechaExpedicion >= date('now')").rowcount
            imported, _, _ = self._import_csv_to_sqlite_append(csv_path, sqlite_path, "Loteado")
            conn.commit()
        logger.info("Loteado fecha_corte=%s query=%s borrados=%s importados=%s", fecha_corte, query, deleted, imported)
        return palets, imported

    def _actualizar_lote_por_palets(self, id_palets: list[str]) -> int:
        if not id_palets:
            return 0
        setting = self._find_setting("BDLoteado.sqlite", "Lote")
        ids_sql = ",".join(f"'{p.replace("'", "''")}'" for p in id_palets)
        query = f"SELECT * FROM Lote WHERE IdPalet IN ({ids_sql})"
        ok, msg, csv_path, _ = self._run_export_custom(setting, query)
        if not ok or not csv_path:
            raise RuntimeError(msg)
        sqlite_path = Path(setting["SqlitePath"])
        with sqlite3.connect(sqlite_path) as conn:
            conn.execute("BEGIN")
            placeholders = ",".join(["?"] * len(id_palets))
            conn.execute(f"DELETE FROM Lote WHERE IdPalet IN ({placeholders})", id_palets)
            imported, _, _ = self._import_csv_to_sqlite_append(csv_path, sqlite_path, "Lote")
            conn.commit()
        return imported

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
        sqlite_path = Path(setting["SqlitePath"])
        with sqlite3.connect(sqlite_path) as conn:
            conn.execute("BEGIN")
            deleted = conn.execute(f"DELETE FROM {self.quote_identifier(table_name)} WHERE {sqlite_where}").rowcount
            imported, _, _ = self._import_csv_to_sqlite_append(csv_path, sqlite_path, table_name)
            conn.commit()
        logger.info("Tabla=%s query=%s borrados=%s importados=%s", table_name, access_query, deleted, imported)
        return imported

    def _find_setting(self, sqlite_name: str, sqlite_table: str) -> dict[str, Any]:
        for s in self.repository.get_settings():
            if Path(str(s.get("SqlitePath", ""))).name.lower() == sqlite_name.lower() and str(s.get("SqliteTable", "")).lower() == sqlite_table.lower():
                return s
        raise ValueError(f"No existe configuración legacy para {sqlite_name}:{sqlite_table}")

    def _run_export_custom(self, setting: dict[str, Any], table_or_query: str) -> tuple[bool, str, Path | None, int]:
        tmp = dict(setting)
        tmp["AccessTable"] = table_or_query
        return self._run_export_from_setting(tmp)

    def _run_export_from_setting(self, setting: dict[str, Any]) -> tuple[bool, str, Path | None, int]:
        vbs_path = self.vbs_path.resolve()
        mdb_path = Path(setting["AccessPath"]).resolve()
        temp_dir = self.temp_dir.resolve()
        csv_path = temp_dir / f"{setting['Nombre']}_{setting.get('Id','adhoc')}.csv"
        log_path = temp_dir / f"{setting['Nombre']}_{setting.get('Id','adhoc')}.log"
        if not vbs_path.exists() or not mdb_path.exists() or not temp_dir.exists():
            return False, "Rutas inválidas para exportación", None, 0
        command = self._build_vbs_command(vbs_path, mdb_path, setting["AccessTable"], csv_path, log_path)
        result = subprocess.run(command, capture_output=True, text=True, encoding="cp1252", timeout=120)
        if result.returncode != 0:
            return False, self._build_export_error_message(result, command, vbs_path, mdb_path, csv_path, log_path), None, 0
        return True, "Exportación OK", csv_path, self._read_exported_rows(log_path)

    def _import_csv_to_sqlite_append(self, csv_path: Path, sqlite_path: Path, table_name: str) -> tuple[int, bool, bool]:
        rows = self._read_csv_rows(csv_path)
        if not rows:
            return 0, True, False
        header = self._sanitize_headers(rows[0])
        data_rows = rows[1:]
        table = self.quote_identifier(table_name)
        columns = ", ".join(self.quote_identifier(c) for c in header)
        placeholders = ",".join(["?"] * len(header))
        with sqlite3.connect(sqlite_path) as conn:
            conn.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", [tuple(r[:len(header)] + [""]*(len(header)-len(r))) for r in data_rows])
            conn.commit()
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
        return str(DB_LOTEADO)
