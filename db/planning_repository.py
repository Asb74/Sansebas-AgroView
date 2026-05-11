from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
import sqlite3
import traceback
from typing import Any

from config import DB_CALIDAD, DB_DIR, DB_FRUTA, DB_LOTEADO


logger = logging.getLogger(__name__)


class PlanningRepository:
    def __init__(self, base_dir: str | Path = DB_DIR) -> None:
        self.base_dir = Path(base_dir)
        self.db_loteado = Path(DB_LOTEADO)

    def _db_path(self, filename: str) -> Path:
        return self.base_dir / filename

    @staticmethod
    def _build_neto_correcto(neto_partida: Any, neto: Any) -> float:
        neto_partida_val = float(neto_partida or 0)
        if neto_partida_val > 0:
            return neto_partida_val
        return float(neto or 0)

    @staticmethod
    def _find_column(table_columns: list[str], candidates: list[str]) -> str | None:
        normalized = {c.upper(): c for c in table_columns}
        for candidate in candidates:
            if candidate.upper() in normalized:
                return normalized[candidate.upper()]
        for col in table_columns:
            col_norm = col.upper().replace("Ñ", "N")
            for candidate in candidates:
                if col_norm == candidate.upper().replace("Ñ", "N"):
                    return col
        return None

    @staticmethod
    def _find_campana_column(table_columns: list[str]) -> str | None:
        exact = PlanningRepository._find_column(table_columns, ["CAMPAÑA", "Campaña"])
        if exact:
            return exact
        for col in table_columns:
            col_norm = col.upper().replace("Ñ", "N").replace(" ", "").replace("_", "")
            if col_norm.startswith("CAMPA"):
                return col
        return None

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _normalize_filter_values(value: Any) -> list[str]:
        if isinstance(value, list):
            raw = value
        elif value is None:
            raw = []
        else:
            raw = [value]
        return [str(v).strip() for v in raw if str(v or "").strip()]

    @staticmethod
    def _is_calibre_agrupado(calibre: Any) -> bool:
        text = str(calibre or "").strip()
        if not text:
            return False
        if "/" in text or "-" in text:
            return True
        tokens = [t.strip() for t in text.replace(",", " ").split() if t.strip()]
        return len(tokens) > 1

    @staticmethod
    def _find_table(conn: sqlite3.Connection, candidates: list[str]) -> str | None:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        normalized = {t.upper(): t for t in tables}
        for candidate in candidates:
            table = normalized.get(candidate.upper())
            if table:
                return table
        return None

    @staticmethod
    def read_text_safe(path: str | Path) -> str:
        text_path = Path(path)
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return text_path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        return text_path.read_bytes().decode("latin-1", errors="replace")

    def diagnose_loteado_tables(self) -> dict[str, Any]:
        path = self.db_loteado
        diagnosis: dict[str, Any] = {"path": str(path), "tables": [], "loteado_columns": [], "has_loteado": False, "has_lote": False, "warning": None}
        if not path.exists():
            diagnosis["warning"] = f"No existe la base de loteado: {path}"
            return diagnosis
        with sqlite3.connect(path) as conn:
            diagnosis["tables"] = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            ldo_table = self._find_table(conn, ["Loteado", "loteado", "LOTEADO"])
            lote_table = self._find_table(conn, ["Lote", "lote", "LOTE"])
            diagnosis["has_loteado"] = bool(ldo_table)
            diagnosis["has_lote"] = bool(lote_table)
            if ldo_table:
                diagnosis["loteado_columns"] = [r[1] for r in conn.execute(f'PRAGMA table_info("{ldo_table}")').fetchall()]
        if not diagnosis["has_lote"]:
            diagnosis["warning"] = "No existe la tabla Lote en bdloteado.sqlite. Puedes actualizarla desde Configuración > Actualización tablas legacy."
        logger.info("Diagnóstico de bdloteado.sqlite (%s): %s", path, diagnosis)
        return diagnosis

    def _get_loteado_filter_rows(self, filters: dict) -> list[dict]:
        path = self.db_loteado
        if not path.exists():
            return []
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            ldo_table = self._find_table(conn, ["Loteado", "loteado", "LOTEADO"])
            if not ldo_table:
                return []
            ldo_cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{ldo_table}")').fetchall()]
            camp_col = self._find_campana_column(ldo_cols)
            fecha_col = self._find_column(ldo_cols, ["FechaAlmacen", "FechaCreacion"])
            var_col = self._find_column(ldo_cols, ["Variedad"])
            if not camp_col or not fecha_col:
                return []
            var_expr = f'ldo."{var_col}"' if var_col else "''"
            rows = [dict(r) for r in conn.execute(f"""
                SELECT ldo."{camp_col}" as Campana, ldo.CULTIVO as Cultivo, COALESCE(ldo.{fecha_col}, '') as FechaAlmacen,
                       ldo.EMPRESA as Empresa, {var_expr} as Variedad
                FROM "{ldo_table}" ldo
                WHERE UPPER(TRIM(ldo.Estado)) = 'STOCK'
                  AND UPPER(TRIM(ldo.Terminado)) IN ('S','SI','SÍ')
                  AND UPPER(REPLACE(REPLACE(TRIM(ldo.Pedido), '/', ''), ' ', '')) IN ('SP','PRECALIBRADO','ESTANDAR','ESTÁNDAR')
                  AND UPPER(TRIM(ldo.Estado)) NOT IN ('BAJA','VOLCADO','EXPEDICION','EXPEDICIÓN')
            """).fetchall()]
        data: list[dict] = []
        for r in rows:
            dt = self._parse_date(r.get("FechaAlmacen"))
            data.append({"Campaña": r.get("Campana", ""), "Cultivo": r.get("Cultivo", ""), "Empresa": r.get("Empresa", ""), "Variedad": r.get("Variedad", ""), "Semana": dt.isocalendar().week if dt else "", "Fecha": dt.strftime("%Y-%m-%d") if dt else (r.get("FechaAlmacen") or "")})
        return data

    def get_stock_campo(self, filters: dict) -> tuple[list[dict], str | None, bool]:
        fruta_path = self._db_path(DB_FRUTA)
        calidad_path = self._db_path(DB_CALIDAD)
        if not fruta_path.exists():
            raise FileNotFoundError(f"No existe la base: {fruta_path}")
        if not calidad_path.exists():
            raise FileNotFoundError(f"No existe la base: {calidad_path}")

        with sqlite3.connect(fruta_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(f"ATTACH DATABASE '{calidad_path.as_posix()}' AS bdcalidad")
            db_eepl = self._db_path("DBEEPPL.sqlite")
            conn.execute(f"ATTACH DATABASE '{db_eepl.as_posix()}' AS dbeepl")
            eepl_tables = [r[0] for r in conn.execute("SELECT name FROM dbeepl.sqlite_master WHERE type='table'").fetchall()]
            if "MVariedad" not in eepl_tables:
                logger.warning("No existe tabla MVariedad en DBEEPPL.sqlite")
            query = """
                SELECT p.CULTIVO as Cultivo, p."CAMPAÑA" as Campana, p.Fcarga as FechaCarga,
                       p.Socio, p.Variedad, p.Boleta, p.Plataforma, p.EMPRESA as Empresa,
                       p.Restricciones, m.Valor as Color, p.Neto, p.NetoPartida,
                       TRIM(COALESCE(mv.GRUPO,'') || ' ' || COALESCE(mv.SUBGRUPO,'')) AS GrupoVarietal
                FROM PesosFres p
                LEFT JOIN MRestricciones m ON m.IdRestricciones = p.Restricciones AND m.CULTIVO = p.CULTIVO
                LEFT JOIN bdcalidad.PartidasIndex pi ON p.AlbaranDef = pi.IdPartida
                LEFT JOIN dbeepl.MVariedad mv
                  ON UPPER(TRIM(mv.Variedad)) = UPPER(TRIM(p.Variedad))
                 AND UPPER(TRIM(mv.CULTIVO)) = UPPER(TRIM(p.CULTIVO))
                WHERE p.AlbaranDef IS NOT NULL AND p.AlbaranDef <> '' AND pi.IdPartida IS NULL
                  AND p.Plataforma = 'SCA San Sebastian'
                  AND p.CULTIVO NOT IN ('DIRECTO','DIRECTOCHF','INDUSTRIA','VENTA','VENTACHF')
            """
            params: list[Any] = []
            for field, col in (("campana", 'p."CAMPAÑA"'), ("cultivo", "p.CULTIVO"), ("empresa", "p.EMPRESA"), ("var_coop", "p.Variedad")):
                values = self._normalize_filter_values(filters.get(field))
                if values:
                    placeholders = ",".join(["UPPER(TRIM(?))"] * len(values))
                    query += f" AND UPPER(TRIM({col})) IN ({placeholders})"
                    params.extend(values)
            grupo_varietal_values = self._normalize_filter_values(filters.get("grupo_varietal"))
            if grupo_varietal_values:
                placeholders = ",".join(["UPPER(TRIM(?))"] * len(grupo_varietal_values))
                query += f" AND UPPER(TRIM(COALESCE(mv.GRUPO,'') || ' ' || COALESCE(mv.SUBGRUPO,''))) IN ({placeholders})"
                params.extend(grupo_varietal_values)
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

        data: list[dict] = []
        f_desde = self._parse_date(filters.get("fecha_desde"))
        f_hasta = self._parse_date(filters.get("fecha_hasta"))
        semana_filter = set(self._normalize_filter_values(filters.get("semana")))
        for r in rows:
            dt = self._parse_date(r.get("FechaCarga"))
            semana = dt.isocalendar().week if dt else ""
            if f_desde and (dt is None or dt.date() < f_desde.date()):
                continue
            if f_hasta and (dt is None or dt.date() > f_hasta.date()):
                continue
            if semana_filter and str(semana) not in semana_filter:
                continue
            kg = self._build_neto_correcto(r.get("NetoPartida"), r.get("Neto"))
            data.append(
                {
                    "Cultivo": r.get("Cultivo", ""),
                    "Campaña": r.get("Campana", ""),
                    "Fecha carga": dt.strftime("%Y-%m-%d") if dt else (r.get("FechaCarga") or ""),
                    "Semana": semana,
                    "Socio": r.get("Socio", ""),
                    "Variedad": r.get("Variedad", ""),
                    "Grupo varietal": r.get("GrupoVarietal", ""),
                    "Boleta": r.get("Boleta", ""),
                    "Plataforma": r.get("Plataforma", ""),
                    "Empresa": r.get("Empresa", ""),
                    "Restricciones": r.get("Restricciones", ""),
                    "Color": r.get("Color", ""),
                    "Kg campo": round(kg, 2),
                }
            )

        update_file = self.base_dir / "ultima_actualizacion.txt"
        last_update = None
        update_warning = False
        if update_file.exists():
            try:
                last_update = self.read_text_safe(update_file).strip()
            except Exception:
                update_warning = True
                traceback.print_exc()
        return data, last_update, update_warning

    def get_stock_almacen(self, filters: dict) -> tuple[list[dict], str | None]:
        path = self.db_loteado
        logger.info("BD loteado usada: %s", path)
        if not path.exists():
            logger.warning("No existe la base de loteado: %s", path)
            return [], None
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            db_pedidos = self._db_path("DBPedidos.sqlite")
            db_eepl = self._db_path("DBEEPPL.sqlite")
            conn.execute(f"ATTACH DATABASE '{db_pedidos.as_posix()}' AS dbpedidos")
            conn.execute(f"ATTACH DATABASE '{db_eepl.as_posix()}' AS dbeepl")
            eepl_tables = [r[0] for r in conn.execute("SELECT name FROM dbeepl.sqlite_master WHERE type='table'").fetchall()]
            if "MVariedad" not in eepl_tables:
                logger.warning("No existe tabla MVariedad en DBEEPPL.sqlite")
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            logger.info("Tablas encontradas: %s", tables)
            ldo_table = self._find_table(conn, ["Loteado", "loteado", "LOTEADO"])
            lote_table = self._find_table(conn, ["Lote", "lote", "LOTE"])
            if not ldo_table or not lote_table:
                logger.warning("No se encontraron tablas requeridas en %s (Loteado: %s, Lote: %s)", path, bool(ldo_table), bool(lote_table))
                return [], "No existe la tabla Lote en bdloteado.sqlite. Puedes actualizarla desde Configuración > Actualización tablas legacy." if ldo_table and not lote_table else None
            ldo_cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{ldo_table}")').fetchall()]
            if not ldo_cols:
                logger.warning("No existe la tabla %s", ldo_table)
                return [], None
            lote_cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{lote_table}")').fetchall()]
            if not lote_cols:
                logger.warning("No existe la tabla %s", lote_table)
                return [], None
            camp_col = self._find_campana_column(ldo_cols)
            if not camp_col:
                logger.warning("No se encontró la columna de campaña en %s", ldo_table)
                return [], None
            fecha_col = self._find_column(ldo_cols, ["FechaAlmacen", "FechaCreacion"])
            if not fecha_col:
                logger.warning("No se encontró columna de fecha en %s", ldo_table)
                return [], None
            fecha_expr = f"COALESCE(ldo.{fecha_col}, '')"

            query = f"""
                SELECT ldo.CULTIVO as Cultivo, ldo."{camp_col}" as Campana, l.Variedad, l.Calibre,
                       l.Lote as Categoria, mc.MARCA as Marca, l.IdConfeccion, l.Confeccion,
                       TRIM(COALESCE(mv.GRUPO,'') || ' ' || COALESCE(mv.SUBGRUPO,'')) AS GrupoVarietal,
                       COUNT(DISTINCT ldo.IdPalet) AS Palets,
                       SUM(COALESCE(l.Cajas,0)) AS Cajas,
                       SUM(COALESCE(l.Neto,0)) AS KgStock
                FROM "{ldo_table}" ldo
                INNER JOIN "{lote_table}" l ON l.IdPalet = ldo.IdPalet
                LEFT JOIN dbpedidos.MConfecciones mc ON CAST(mc.CODIGO AS TEXT) = CAST(l.IdConfeccion AS TEXT)
                LEFT JOIN dbeepl.MVariedad mv
                  ON UPPER(TRIM(mv.Variedad)) = UPPER(TRIM(l.Variedad))
                 AND UPPER(TRIM(mv.CULTIVO)) = UPPER(TRIM(ldo.CULTIVO))
                WHERE UPPER(TRIM(ldo.Estado)) = 'STOCK'
                  AND UPPER(TRIM(ldo.Terminado)) IN ('S','SI','SÍ')
                  AND UPPER(REPLACE(REPLACE(TRIM(ldo.Pedido), '/', ''), ' ', '')) IN ('SP','PRECALIBRADO','ESTANDAR','ESTÁNDAR')
            """
            params: list[Any] = []
            for field, col in (("cultivo", "ldo.CULTIVO"), ("empresa", "ldo.EMPRESA"), ("var_coop", "l.Variedad"), ("marca", "mc.MARCA")):
                values = self._normalize_filter_values(filters.get(field))
                if values:
                    placeholders = ",".join(["UPPER(TRIM(?))"] * len(values))
                    query += f" AND UPPER(TRIM({col})) IN ({placeholders})"
                    params.extend(values)
            campana_values = self._normalize_filter_values(filters.get("campana"))
            if campana_values:
                placeholders = ",".join(["CAST(? AS TEXT)"] * len(campana_values))
                query += f' AND CAST(ldo."{camp_col}" AS TEXT) IN ({placeholders})'
                params.extend(campana_values)
            grupo_varietal_values = self._normalize_filter_values(filters.get("grupo_varietal"))
            if grupo_varietal_values:
                placeholders = ",".join(["UPPER(TRIM(?))"] * len(grupo_varietal_values))
                query += f" AND UPPER(TRIM(COALESCE(mv.GRUPO,'') || ' ' || COALESCE(mv.SUBGRUPO,''))) IN ({placeholders})"
                params.extend(grupo_varietal_values)
            query += """
                GROUP BY ldo.CULTIVO, ldo.""" + f'"{camp_col}"' + """, l.Variedad, l.Calibre,
                         l.Lote, mc.MARCA, l.IdConfeccion, l.Confeccion, mv.GRUPO, mv.SUBGRUPO
            """
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

        data: list[dict] = []
        for r in rows:
            data.append(
                {
                    "Campaña": r.get("Campana", ""), "Cultivo": r.get("Cultivo", ""), "Variedad": r.get("Variedad", ""), "Grupo varietal": r.get("GrupoVarietal", ""), "Calibre": r.get("Calibre", ""),
                    "Categoría": r.get("Categoria", ""), "Marca": r.get("Marca", ""), "IdConfeccion": r.get("IdConfeccion", ""), "Confección": r.get("Confeccion", ""),
                    "Palets": int(r.get("Palets") or 0),
                    "Cajas": round(float(r.get("Cajas") or 0), 2), "Kg stock": round(float(r.get("KgStock") or 0), 2),
                    "Agrupado": "Sí" if self._is_calibre_agrupado(r.get("Calibre", "")) else "No",
                }
            )
        return data, None

    def get_stock_almacen_detalle_palets(self, filters: dict) -> list[dict]:
        path = self.db_loteado
        if not path.exists():
            return []
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            db_pedidos = self._db_path("DBPedidos.sqlite")
            db_eepl = self._db_path("DBEEPPL.sqlite")
            conn.execute(f"ATTACH DATABASE '{db_pedidos.as_posix()}' AS dbpedidos")
            conn.execute(f"ATTACH DATABASE '{db_eepl.as_posix()}' AS dbeepl")
            eepl_tables = [r[0] for r in conn.execute("SELECT name FROM dbeepl.sqlite_master WHERE type='table'").fetchall()]
            if "MVariedad" not in eepl_tables:
                logger.warning("No existe tabla MVariedad en DBEEPPL.sqlite")
            ldo_table = self._find_table(conn, ["Loteado", "loteado", "LOTEADO"])
            lote_table = self._find_table(conn, ["Lote", "lote", "LOTE"])
            if not ldo_table or not lote_table:
                return []
            ldo_cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{ldo_table}")').fetchall()]
            camp_col = self._find_campana_column(ldo_cols)
            fecha_col = self._find_column(ldo_cols, ["FechaAlmacen", "FechaCreacion"])
            if not camp_col or not fecha_col:
                return []
            query = f"""
                SELECT ldo.IdPalet, ldo.Pedido, COALESCE(ldo.{fecha_col}, '') as FechaAlmacen,
                       ldo.Estado, ldo.Terminado, l.Variedad, l.Calibre, l.Lote as Categoria, mc.MARCA as Marca,
                       l.IdConfeccion, l.Confeccion, TRIM(COALESCE(mv.GRUPO,'') || ' ' || COALESCE(mv.SUBGRUPO,'')) AS GrupoVarietal,
                       SUM(COALESCE(l.Cajas,0)) AS Cajas, SUM(COALESCE(l.Neto,0)) AS Neto
                FROM "{ldo_table}" ldo
                INNER JOIN "{lote_table}" l ON l.IdPalet = ldo.IdPalet
                LEFT JOIN dbpedidos.MConfecciones mc ON CAST(mc.CODIGO AS TEXT) = CAST(l.IdConfeccion AS TEXT)
                LEFT JOIN dbeepl.MVariedad mv
                  ON UPPER(TRIM(mv.Variedad)) = UPPER(TRIM(l.Variedad))
                 AND UPPER(TRIM(mv.CULTIVO)) = UPPER(TRIM(ldo.CULTIVO))
                WHERE UPPER(TRIM(ldo.Estado)) = 'STOCK'
                  AND UPPER(TRIM(ldo.Terminado)) IN ('S','SI','SÍ')
                  AND UPPER(REPLACE(REPLACE(TRIM(ldo.Pedido), '/', ''), ' ', '')) IN ('SP','PRECALIBRADO','ESTANDAR','ESTÁNDAR')
            """
            params: list[Any] = []
            for field, col in (("cultivo", "ldo.CULTIVO"), ("empresa", "ldo.EMPRESA"), ("var_coop", "l.Variedad"), ("marca", "mc.MARCA")):
                values = self._normalize_filter_values(filters.get(field))
                if values:
                    placeholders = ",".join(["UPPER(TRIM(?))"] * len(values))
                    query += f" AND UPPER(TRIM({col})) IN ({placeholders})"
                    params.extend(values)
            campana_values = self._normalize_filter_values(filters.get("campana"))
            if campana_values:
                placeholders = ",".join(["CAST(? AS TEXT)"] * len(campana_values))
                query += f' AND CAST(ldo."{camp_col}" AS TEXT) IN ({placeholders})'
                params.extend(campana_values)
            grupo_varietal_values = self._normalize_filter_values(filters.get("grupo_varietal"))
            if grupo_varietal_values:
                placeholders = ",".join(["UPPER(TRIM(?))"] * len(grupo_varietal_values))
                query += f" AND UPPER(TRIM(COALESCE(mv.GRUPO,'') || ' ' || COALESCE(mv.SUBGRUPO,''))) IN ({placeholders})"
                params.extend(grupo_varietal_values)
            query += """
                GROUP BY ldo.IdPalet, ldo.Pedido, FechaAlmacen, ldo.Estado, ldo.Terminado,
                         l.Variedad, l.Calibre, l.Lote, mc.MARCA, l.IdConfeccion, l.Confeccion, mv.GRUPO, mv.SUBGRUPO
            """
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        return rows

    def _fecha_expr_sql(self, alias: str, col: str) -> str:
        raw = f'COALESCE({alias}."{col}", "")'
        ymd_iso = f"substr({raw},1,4)||'-'||substr({raw},6,2)||'-'||substr({raw},9,2)"
        ymd_dmy = f"substr({raw},7,4)||'-'||substr({raw},4,2)||'-'||substr({raw},1,2)"
        return f"CASE WHEN length({raw}) >= 10 AND substr({raw},5,1)='-' THEN {ymd_iso} WHEN length({raw}) >= 10 AND substr({raw},3,1)='/' THEN {ymd_dmy} ELSE {raw} END"

    def get_pedidos_pendientes(self, filters: dict, modo_pedidos: str = "10_dias") -> tuple[list[dict], dict[str, float]]:
        logger.info("Cargando pedidos pendientes. Modo=%s Filters=%s", modo_pedidos, filters)
        pedidos_path = self._db_path("DBPedidos.sqlite")
        logger.info("Ruta DBPedidos.sqlite usada: %s", pedidos_path)
        logger.info("DBPedidos.sqlite existe: %s", pedidos_path.exists())
        kpi_vacio = {"Kg pedido teórico total": 0.0, "Kg hecho real total": 0.0, "Kg pendiente total": 0.0, "Nº pedidos": 0, "Nº líneas": 0, "Nº líneas sin datos": 0, "Nº líneas parciales": 0}
        if not pedidos_path.exists():
            logger.warning("No existe DBPedidos.sqlite en la ruta esperada")
            return [], kpi_vacio

        with sqlite3.connect(pedidos_path) as conn:
            conn.row_factory = sqlite3.Row
            db_eepl = self._db_path("DBEEPPL.sqlite")
            db_loteado = self._db_path("bdloteado.sqlite")
            conn.execute(f"ATTACH DATABASE '{db_eepl.as_posix()}' AS dbeepl")
            conn.execute(f"ATTACH DATABASE '{db_loteado.as_posix()}' AS bdloteado")
            eepl_tables = [r[0] for r in conn.execute("SELECT name FROM dbeepl.sqlite_master WHERE type='table'").fetchall()]
            if "MVariedad" not in eepl_tables:
                logger.warning("No existe tabla MVariedad en DBEEPPL.sqlite")
            pedidos_cols = [r["name"] for r in conn.execute('PRAGMA table_info("Pedidos")').fetchall()]
            if not pedidos_cols:
                logger.warning("No existe la tabla Pedidos en DBPedidos.sqlite")
                return [], kpi_vacio

            query = """
                WITH palets_terminados AS (
                    SELECT DISTINCT
                        TRIM(ldo.Pedido) AS Pedido,
                        CAST(ldo.Linea AS TEXT) AS Linea,
                        ldo.IdPalet
                    FROM bdloteado.Loteado ldo
                    WHERE UPPER(TRIM(ldo.Terminado)) IN ('S','SI','SÍ')
                ),
                palets_resumen AS (
                    SELECT
                        pt.Pedido,
                        pt.Linea,
                        pt.IdPalet,
                        MAX(COALESCE(l.Cajas, 0)) AS CajasPalet,
                        MAX(COALESCE(l.Neto, 0)) AS KgPalet
                    FROM palets_terminados pt
                    LEFT JOIN bdloteado.Lote l
                        ON l.IdPalet = pt.IdPalet
                    GROUP BY
                        pt.Pedido,
                        pt.Linea,
                        pt.IdPalet
                ),
                hecho AS (
                    SELECT
                        Pedido,
                        Linea,
                        COUNT(DISTINCT IdPalet) AS PaletsHechos,
                        SUM(CajasPalet) AS CajasHechas,
                        SUM(KgPalet) AS KgHechoReal
                    FROM palets_resumen
                    GROUP BY
                        Pedido,
                        Linea
                )
                SELECT
                    p."Semana" AS "Semana",
                    p."FechaSalida" AS "Fecha salida",
                    p."Cliente" AS "Cliente",
                    p."IdPedidoLora" AS "IdPedidoLora",
                    p."Linea" AS "Línea",
                    p."Cultivo" AS "Cultivo",
                    p."Campaña" AS "Campaña",
                    p."VarCoop" AS "Variedad Coop",
                    TRIM(COALESCE(mv.GRUPO, '') || ' ' || COALESCE(mv.SUBGRUPO, '')) AS "Grupo varietal",
                    p."Calibre" AS "Calibre",
                    p."Categoria" AS "Categoría",
                    p."Marca" AS "Marca",
                    p."Confeccion" AS "Confección",
                    COALESCE(p."NPalet", 0) AS "Palets pedido",
                    COALESCE(h.PaletsHechos, 0) AS "Palets hechos",
                    MAX(0, COALESCE(p."NPalet", 0) - COALESCE(h.PaletsHechos, 0)) AS "Palets pendientes",
                    COALESCE(p."Cajas", 0) AS "Cajas pedido",
                    COALESCE(h.CajasHechas, 0) AS "Cajas hechas",
                    MAX(0, COALESCE(p."Cajas", 0) - COALESCE(h.CajasHechas, 0)) AS "Cajas pendientes",
                    CASE
                      WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."Cajas", 0) * mc."NETO"
                      WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."Cajas", 0) * p."ExigePeso"
                      ELSE 0
                    END AS "Kg pedido teórico",
                    COALESCE(h.KgHechoReal, 0) AS "Kg hecho real",
                    MAX(0, (
                      CASE
                        WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."Cajas", 0) * mc."NETO"
                        WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."Cajas", 0) * p."ExigePeso"
                        ELSE 0
                      END
                    ) - COALESCE(h.KgHechoReal, 0)) AS "Kg pendiente",
                    CASE
                      WHEN NULLIF((
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ), 0) IS NULL THEN 0
                      ELSE ROUND((COALESCE(h.KgHechoReal, 0) / NULLIF((
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ), 0)) * 100, 2)
                    END AS "% hecho",
                    CASE
                      WHEN (
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ) = 0 THEN 'Sin datos'
                      WHEN COALESCE(h.KgHechoReal, 0) = 0 THEN 'Pendiente'
                      WHEN COALESCE(h.KgHechoReal, 0) > (
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ) * 1.02 THEN 'Excedido'
                      WHEN COALESCE(h.KgHechoReal, 0) >= (
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ) * 0.98 THEN 'Completo'
                      WHEN COALESCE(h.KgHechoReal, 0) > 0
                       AND COALESCE(h.KgHechoReal, 0) < (
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ) THEN 'Parcial'
                      ELSE 'Parcial'
                    END AS "Estado",
                    CASE
                      WHEN (
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ) = 0 THEN 'Faltan datos peso caja'
                      ELSE ''
                    END AS "Aviso"
                FROM "Pedidos" p
                LEFT JOIN dbeepl.MVariedad mv
                  ON UPPER(TRIM(mv.Variedad)) = UPPER(TRIM(p."VarCoop"))
                 AND UPPER(TRIM(mv.CULTIVO)) = UPPER(TRIM(p."Cultivo"))
                LEFT JOIN hecho h
                  ON h.Pedido = TRIM(p."IdPedidoLora")
                 AND h.Linea = CAST(p."Linea" AS TEXT)
                LEFT JOIN MConfecciones mc
                  ON CAST(mc.CODIGO AS TEXT) = CAST(p."Confeccion" AS TEXT)
                WHERE COALESCE(p."Cancelado", 0) = 0
                  AND UPPER(TRIM(COALESCE(p."IdPedidoLora", ""))) NOT IN ('S/P', 'PRECALIBRADO', 'ESTANDAR')
            """
            params: list[Any] = []

            for field, col in (
                ("campana", 'p."Campaña"'),
                ("cultivo", 'p."Cultivo"'),
                ("empresa", 'p."EMPRESA"'),
                ("semana", 'p."Semana"'),
                ("var_coop", 'p."VarCoop"'),
                ("marca", 'p."Marca"'),
            ):
                values = self._normalize_filter_values(filters.get(field))
                if values:
                    placeholders = ",".join(["UPPER(TRIM(?))"] * len(values))
                    query += f" AND UPPER(TRIM(COALESCE({col}, ''))) IN ({placeholders})"
                    params.extend(values)

            if modo_pedidos == "10_dias":
                query += " AND date(p.\"FechaSalida\") BETWEEN date('now') AND date('now', '+10 days')"
            elif modo_pedidos == "todos_futuros":
                query += " AND date(p.\"FechaSalida\") >= date('now')"
            elif modo_pedidos == "rango":
                fecha_desde = str(filters.get("fecha_desde") or "").strip()
                fecha_hasta = str(filters.get("fecha_hasta") or "").strip()
                if fecha_desde:
                    query += " AND date(p.\"FechaSalida\") >= date(?)"
                    params.append(fecha_desde)
                if fecha_hasta:
                    query += " AND date(p.\"FechaSalida\") <= date(?)"
                    params.append(fecha_hasta)
            elif modo_pedidos == "semana_actual":
                semana_actual = str(datetime.now().isocalendar()[1])
                query += " AND CAST(COALESCE(p.\"Semana\", '') AS TEXT) = ?"
                params.append(semana_actual)
            elif modo_pedidos == "proximas_semanas":
                # Se aplica a través del filtro global "semana" cuando venga informado.
                pass
            elif modo_pedidos == "todos":
                # Sin filtro de fecha.
                pass

            query += """
                ORDER BY date(p."FechaSalida") ASC,
                         p."Cliente" ASC,
                         p."IdPedidoLora" ASC,
                         p."Linea" ASC
            """
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
            logger.info("Pedidos pendientes finales: %s", len(rows))
            if not rows:
                logger.warning("No se encontraron pedidos pendientes con los filtros aplicados.")
                return [], kpi_vacio

        pedidos_unicos = {str(r.get("IdPedidoLora") or "").strip() for r in rows if str(r.get("IdPedidoLora") or "").strip()}
        kpi = {
            "Kg pedido teórico total": 0.0,
            "Kg hecho real total": 0.0,
            "Kg pendiente total": 0.0,
            "Nº pedidos": len(pedidos_unicos),
            "Nº líneas": len(rows),
            "Nº líneas sin datos": 0,
            "Nº líneas parciales": 0,
        }
        return rows, kpi
    def get_aprovechamientos_reales(self, filters: dict) -> list[dict]:
        fruta_path = self._db_path(DB_FRUTA)
        if not fruta_path.exists():
            return []
        with sqlite3.connect(fruta_path) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT CULTIVO, "CAMPAÑA" as Campana, EMPRESA, Variedad, Fcarga,
                       Neto, NetoPartida, Cal0, Cal1, Cal2, Cal3, Cal4, Cal5, Cal6, Cal7, Cal8, Cal9, Cal10, Cal11,
                       "%Cal0", "%Cal1", "%Cal2", "%Cal3", "%Cal4", "%Cal5", "%Cal6", "%Cal7", "%Cal8", "%Cal9", "%Cal10", "%Cal11"
                FROM PesosFres
                WHERE 1=1
            """
            params: list[Any] = []
            for field, col in (("cultivo", "CULTIVO"), ("empresa", "EMPRESA"), ("var_coop", "Variedad")):
                values = self._normalize_filter_values(filters.get(field))
                if values:
                    placeholders = ",".join(["UPPER(TRIM(?))"] * len(values))
                    query += f" AND UPPER(TRIM({col})) IN ({placeholders})"
                    params.extend(values)
            campana_values = self._normalize_filter_values(filters.get("campana"))
            if campana_values:
                placeholders = ",".join(["CAST(? AS TEXT)"] * len(campana_values))
                query += f' AND CAST("CAMPAÑA" AS TEXT) IN ({placeholders})'
                params.extend(campana_values)
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        for row in rows:
            row["NetoCalculado"] = round(self._build_neto_correcto(row.get("NetoPartida"), row.get("Neto")), 2)
        return rows

    def get_correspondencias_calibres(self, cultivo: str) -> list[dict[str, Any]]:
        calidad_path = self._db_path(DB_CALIDAD)
        if not calidad_path.exists():
            raise FileNotFoundError(f"No existe la base: {calidad_path}")

        cultivo_norm = str(cultivo or "").strip().upper()
        if not cultivo_norm:
            return []

        with sqlite3.connect(calidad_path) as conn:
            conn.row_factory = sqlite3.Row
            table = self._find_table(conn, ["CorrespondenciasCalibres"])
            if not table:
                return []
            table_cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
            base_col = self._find_column(table_cols, ["BASE"])
            cultivo_col = self._find_column(table_cols, [cultivo_norm])
            if not base_col or not cultivo_col:
                return []

            rows = [dict(r) for r in conn.execute(f'SELECT "{base_col}" AS BaseCal, "{cultivo_col}" AS CalibreNorm FROM "{table}"').fetchall()]

        result: list[dict[str, Any]] = []
        for r in rows:
            base_val = str(r.get("BaseCal") or "").strip().upper()
            if not base_val.startswith("CAL "):
                continue
            idx_raw = base_val.replace("CAL", "", 1).strip()
            if not idx_raw.isdigit():
                continue

            calibre_norm = str(r.get("CalibreNorm") or "").strip()
            if not calibre_norm or calibre_norm.upper() == "(VACÍAS)":
                continue

            orden = int(idx_raw)
            result.append(
                {
                    "campo_base": f"Cal{orden}",
                    "campo_pct": f"%Cal{orden}",
                    "calibre_normalizado": calibre_norm,
                    "orden": orden,
                }
            )

        result.sort(key=lambda x: x["orden"])
        return result

    def get_filter_options(self, key: str) -> list[str]:
        if key == "grupo_varietal":
            path = self.db_loteado
            if not path.exists():
                return []
            with sqlite3.connect(path) as conn:
                db_eepl = self._db_path("DBEEPPL.sqlite")
                conn.execute(f"ATTACH DATABASE '{db_eepl.as_posix()}' AS dbeepl")
                eepl_tables = [r[0] for r in conn.execute("SELECT name FROM dbeepl.sqlite_master WHERE type='table'").fetchall()]
                if "MVariedad" not in eepl_tables:
                    logger.warning("No existe tabla MVariedad en DBEEPPL.sqlite")
                ldo_table = self._find_table(conn, ["Loteado", "loteado", "LOTEADO"])
                lote_table = self._find_table(conn, ["Lote", "lote", "LOTE"])
                if not ldo_table or not lote_table:
                    return []
                rows = conn.execute(
                    f"""
                    SELECT DISTINCT TRIM(COALESCE(mv.GRUPO,'') || ' ' || COALESCE(mv.SUBGRUPO,'')) AS GrupoVarietal
                    FROM "{ldo_table}" ldo
                    INNER JOIN "{lote_table}" l ON l.IdPalet = ldo.IdPalet
                    LEFT JOIN dbeepl.MVariedad mv
                      ON UPPER(TRIM(mv.Variedad)) = UPPER(TRIM(l.Variedad))
                     AND UPPER(TRIM(mv.CULTIVO)) = UPPER(TRIM(ldo.CULTIVO))
                    WHERE UPPER(TRIM(ldo.Estado)) = 'STOCK'
                      AND UPPER(TRIM(ldo.Terminado)) IN ('S','SI','SÍ')
                      AND UPPER(REPLACE(REPLACE(TRIM(ldo.Pedido), '/', ''), ' ', '')) IN ('SP','PRECALIBRADO','ESTANDAR','ESTÁNDAR')
                    """
                ).fetchall()
            return sorted({str(r[0] or "").strip() for r in rows if str(r[0] or "").strip()})

        filters = {"campana": [], "cultivo": [], "empresa": [], "semana": [], "var_coop": [], "fecha_desde": "", "fecha_hasta": ""}
        rows = self._get_loteado_filter_rows(filters)
        mapping = {
            "campana": "Campaña",
            "cultivo": "Cultivo",
            "empresa": "Empresa",
            "semana": "Semana",
            "var_coop": "Variedad",
            "marca": "Marca",
            "fecha": "Fecha",
        }
        col = mapping.get(key)
        if not col:
            return []
        values = sorted({str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()})
        return values
