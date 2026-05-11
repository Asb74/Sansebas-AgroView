from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import traceback
from typing import Any

from config import DB_DIR


class PlanningRepository:
    def __init__(self, base_dir: str | Path = DB_DIR) -> None:
        self.base_dir = Path(base_dir)

    def _db_path(self, filename: str) -> Path:
        return self.base_dir / filename

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
    def read_text_safe(path: str | Path) -> str:
        text_path = Path(path)
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return text_path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        return text_path.read_bytes().decode("latin-1", errors="replace")

    def get_stock_campo(self, filters: dict) -> tuple[list[dict], str | None, bool]:
        fruta_path = self._db_path("DBfruta.sqlite")
        calidad_path = self._db_path("BdCalidad.sqlite")
        if not fruta_path.exists():
            raise FileNotFoundError(f"No existe la base: {fruta_path}")
        if not calidad_path.exists():
            raise FileNotFoundError(f"No existe la base: {calidad_path}")

        with sqlite3.connect(fruta_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(f"ATTACH DATABASE '{calidad_path.as_posix()}' AS bdcalidad")
            query = """
                SELECT p.CULTIVO as Cultivo, p."CAMPAÑA" as Campana, p.Fcarga as FechaCarga,
                       p.Socio, p.Variedad, p.Boleta, p.Plataforma, p.EMPRESA as Empresa,
                       p.Restricciones, m.Valor as Color, p.Neto, p.NetoPartida
                FROM PesosFres p
                LEFT JOIN MRestricciones m ON m.IdRestricciones = p.Restricciones AND m.CULTIVO = p.CULTIVO
                LEFT JOIN bdcalidad.PartidasIndex pi ON p.AlbaranDef = pi.IdPartida
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
            neto_partida = float(r.get("NetoPartida") or 0)
            neto = float(r.get("Neto") or 0)
            kg = neto_partida if neto_partida != 0 else neto
            data.append(
                {
                    "Cultivo": r.get("Cultivo", ""),
                    "Campaña": r.get("Campana", ""),
                    "Fecha carga": dt.strftime("%Y-%m-%d") if dt else (r.get("FechaCarga") or ""),
                    "Semana": semana,
                    "Socio": r.get("Socio", ""),
                    "Variedad": r.get("Variedad", ""),
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

    def get_stock_almacen(self, filters: dict) -> list[dict]:
        path = self._db_path("BDPerceco.sqlite")
        if not path.exists():
            raise FileNotFoundError(f"No existe la base: {path}")
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            ldo_cols = [r[1] for r in conn.execute("PRAGMA table_info(Loteado)").fetchall()]
            if not ldo_cols:
                raise ValueError("No existe la tabla Loteado")
            lote_cols = [r[1] for r in conn.execute("PRAGMA table_info(Lote)").fetchall()]
            if not lote_cols:
                raise ValueError("No existe la tabla Lote")
            camp_col = self._find_column(ldo_cols, ["CAMPAÑA", "Campaña"])
            if not camp_col:
                raise ValueError("No se encontró la columna de campaña en Loteado")
            fecha_col = self._find_column(ldo_cols, ["FechaAlmacen", "FechaCreacion"])
            fecha_expr = f"COALESCE(ldo.{fecha_col}, '')"

            query = f"""
                SELECT ldo.IdPalet, ldo."{camp_col}" as Campana, ldo.CULTIVO as Cultivo, ldo.Pedido,
                       ldo.Estado, ldo.Terminado, {fecha_expr} as FechaAlmacen, ldo.Categoria,
                       ldo.Marca, ldo.EMPRESA as Empresa, l.IdConfeccion, l.Confeccion,
                       l.Calibre, l.Variedad,
                       SUM(COALESCE(l.Cajas,0)) AS Cajas,
                       SUM(COALESCE(l.Neto,0)) AS KgStock
                FROM Loteado ldo
                INNER JOIN Lote l ON l.IdPalet = ldo.IdPalet
                WHERE UPPER(TRIM(ldo.Estado)) = 'STOCK'
                  AND UPPER(TRIM(ldo.Terminado)) IN ('S','SI','SÍ')
                  AND UPPER(REPLACE(REPLACE(TRIM(ldo.Pedido), '/', ''), ' ', '')) IN ('SP','PRECALIBRADO','ESTANDAR','ESTÁNDAR')
                  AND UPPER(TRIM(ldo.Estado)) NOT IN ('BAJA','VOLCADO','EXPEDICION','EXPEDICIÓN')
            """
            params: list[Any] = []
            for field, col in (("campana", f'ldo."{camp_col}"'), ("cultivo", "ldo.CULTIVO"), ("empresa", "ldo.EMPRESA"), ("var_coop", "l.Variedad")):
                values = self._normalize_filter_values(filters.get(field))
                if values:
                    placeholders = ",".join(["UPPER(TRIM(?))"] * len(values))
                    query += f" AND UPPER(TRIM({col})) IN ({placeholders})"
                    params.extend(values)
            query += """
                GROUP BY ldo.IdPalet, ldo.""" + f'"{camp_col}"' + """, ldo.CULTIVO, ldo.Pedido, ldo.Estado,
                         ldo.Terminado, FechaAlmacen, ldo.Categoria, ldo.Marca, ldo.EMPRESA,
                         l.IdConfeccion, l.Confeccion, l.Calibre, l.Variedad
            """
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

        data: list[dict] = []
        f_desde = self._parse_date(filters.get("fecha_desde"))
        f_hasta = self._parse_date(filters.get("fecha_hasta"))
        semana_filter = set(self._normalize_filter_values(filters.get("semana")))
        for r in rows:
            dt = self._parse_date(r.get("FechaAlmacen"))
            semana = dt.isocalendar().week if dt else ""
            if f_desde and (dt is None or dt.date() < f_desde.date()):
                continue
            if f_hasta and (dt is None or dt.date() > f_hasta.date()):
                continue
            if semana_filter and str(semana) not in semana_filter:
                continue
            data.append(
                {
                    "Campaña": r.get("Campana", ""), "Cultivo": r.get("Cultivo", ""), "IdPalet": r.get("IdPalet", ""),
                    "Pedido": r.get("Pedido", ""), "Fecha almacén": dt.strftime("%Y-%m-%d") if dt else (r.get("FechaAlmacen") or ""),
                    "Variedad": r.get("Variedad", ""), "Calibre": r.get("Calibre", ""), "Categoría": r.get("Categoria", ""),
                    "Marca": r.get("Marca", ""), "IdConfeccion": r.get("IdConfeccion", ""), "Confección": r.get("Confeccion", ""),
                    "Cajas": round(float(r.get("Cajas") or 0), 2), "Kg stock": round(float(r.get("KgStock") or 0), 2),
                    "Estado": r.get("Estado", ""), "Semana": semana,
                }
            )
        return data

    def get_filter_options(self, key: str) -> list[str]:
        filters = {"campana": [], "cultivo": [], "empresa": [], "semana": [], "var_coop": [], "fecha_desde": "", "fecha_hasta": ""}
        campo, _, _ = self.get_stock_campo(filters)
        almacen = self.get_stock_almacen(filters)
        rows = campo + almacen
        mapping = {
            "campana": "Campaña",
            "cultivo": "Cultivo",
            "empresa": "Empresa",
            "semana": "Semana",
            "var_coop": "Variedad",
            "marca": "Marca",
        }
        col = mapping.get(key)
        if not col:
            return []
        values = sorted({str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()})
        return values
