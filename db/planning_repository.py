from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
import sqlite3
import time
import traceback
from typing import Any

from config import DB_CALIDAD, DB_DIR, DB_EEPPL, DB_FRUTA, DB_LOTEADO, DB_PEDIDOS


logger = logging.getLogger(__name__)


CANONICAL_ALIASES = {
    "campana": ["campana", "campaña", "CAMPAÑA", "Campana", "Campaña"],
    "categoria": ["categoria", "categoría", "Categoria", "Categoría", "categoria stock", "Categoria stock"],
    "grupo_varietal": ["grupo_varietal", "grupo varietal", "Grupo varietal", "GrupoVarietal", "GrupoVar"],
    "id_confeccion": ["id_confeccion", "IdConfeccion", "ID Confección"],
    "confeccion": ["confeccion", "Confección", "Confeccion"],
    "kg": ["kg", "Kg", "Kg disponibles", "Neto", "kg_neto"],
}

def normalizar_texto(valor: Any) -> str:
    return str(valor or "").strip()

def normalizar_numero(valor: Any) -> float:
    try:
        return float(valor or 0)
    except Exception:
        return 0.0

def normalizar_campana(valor: Any) -> str:
    txt = normalizar_texto(valor)
    return str(int(float(txt))) if txt.replace('.', '', 1).isdigit() else txt

def normalizar_categoria(valor: Any) -> str:
    return normalizar_texto(valor).upper()

def canonical_get(row: dict[str, Any], key: str, default: Any = "") -> Any:
    aliases = CANONICAL_ALIASES.get(key, [key])
    norm_map = {str(k).strip().lower().replace("ñ", "n"): v for k, v in row.items()}
    for alias in aliases:
        k = alias.strip().lower().replace("ñ", "n")
        if k in norm_map:
            value = norm_map[k]
            if key == "campana":
                return normalizar_campana(value)
            if key == "categoria":
                return normalizar_categoria(value)
            if key in {"id_confeccion", "confeccion", "grupo_varietal"}:
                return normalizar_texto(value)
            if key == "kg":
                return normalizar_numero(value)
            return value
    return default


class PlanningRepository:
    def __init__(self, base_dir: str | Path = DB_DIR) -> None:
        self.base_dir = Path(base_dir)
        self.db_loteado = self._db_path(DB_LOTEADO)

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
    def normalizar_calibre(calibre_texto: Any) -> list[str]:
        return sorted(PlanningRepository.normalizar_calibre_a_set(calibre_texto))

    @staticmethod
    def normalizar_calibre_a_set(calibre_texto: Any, calibre_map: dict[str, str] | None = None) -> set[str]:
        text = str(calibre_texto or "").strip().upper()
        if not text:
            return set()
        text = re.sub(r"\bCAL(?:\.)?\b", " ", text)
        text = re.sub(r"\bPZS?\b|\bPIEZAS?\b", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        mapped = (calibre_map or {}).get(text)
        if mapped and str(mapped).strip().upper() != text:
            return PlanningRepository.normalizar_calibre_a_set(mapped, calibre_map=calibre_map)

        raw_text = str(calibre_texto or "")
        raw_upper = raw_text.upper()

        es_formato_piezas = bool(re.search(r"\bPZS?\b|\bPIEZA(?:S)?\b", raw_upper))
        if not es_formato_piezas:
            m_formato_simple = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", raw_text)
            if m_formato_simple:
                es_formato_piezas = int(m_formato_simple.group(2)) >= 10

        if es_formato_piezas:
            m = re.match(r"^\s*(\d+)\s*/", raw_text)
            return {m.group(1)} if m else set()

        if "/" in text:
            nums = [n for n in re.split(r"\s*/\s*", text) if re.fullmatch(r"\d+", n)]
            if len(nums) >= 3:
                return set(nums)
            if len(nums) == 2:
                a, b = nums
                if len(b) >= 2 and int(b) >= 10:
                    return {a}
                return {a, b}
        if "-" in text:
            nums = [n for n in re.split(r"\s*-\s*", text) if re.fullmatch(r"\d+", n)]
            if len(nums) >= 2:
                return set(nums)

        parts = re.findall(r"\d+", text)
        return set(parts)

    def get_mcalibres_map(self) -> dict[str, str]:
        path = self._db_path(DB_PEDIDOS)
        if not path.exists():
            return {}
        try:
            with sqlite3.connect(path) as conn:
                conn.row_factory = sqlite3.Row
                table = self._find_table(conn, ["MCalibres", "MCALIBRES"])
                if not table:
                    return {}
                cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
                col_calibre = self._find_column(cols, ["Calibre", "CalibreOriginal", "CalibreTxt"])
                col_unif = self._find_column(cols, ["CalibreU"])
                if not col_calibre or not col_unif:
                    return {}
                out: dict[str, str] = {}
                for row in conn.execute(f'SELECT "{col_calibre}" AS calibre, "{col_unif}" AS calibre_u FROM "{table}"').fetchall():
                    raw = str(row["calibre"] or "").strip().upper()
                    uni = str(row["calibre_u"] or "").strip().upper()
                    if raw and uni:
                        out[raw] = uni
                return out
        except Exception:
            logger.exception("No se pudo cargar mapa MCalibres")
            return {}


    @staticmethod
    def default_politica_compatibilidad() -> dict[str, bool]:
        return {
            "mismo_grupo_varietal": True,
            "permitir_grupo_varietal_alternativo": False,
            "permitir_variedad_alternativa": True,
            "permitir_calibre_admitido": True,
            "permitir_calibre_agrupado": True,
            "permitir_solape_parcial": False,
            "permitir_categoria_inferior": False,
            "permitir_categoria_superior": False,
            "usar_stock_industrial": True,
            "usar_stock_comercial": False,
            "usar_entrada_estimada": False,
            "usar_reservas_amplias": False,
        }

    def _merge_policy(self, policy: dict[str, Any] | None) -> dict[str, bool]:
        out = self.default_politica_compatibilidad()
        if isinstance(policy, dict):
            for k in out:
                if k in policy:
                    out[k] = bool(policy.get(k))
        return out

    def comparar_calibres(self, calibre_pedido: Any, calibre_stock: Any, calibre_map: dict[str, str] | None = None) -> str:
        result = self.comparar_calibres_para_cobertura(calibre_pedido, calibre_stock, calibre_map=calibre_map)
        legacy = {"EXACTA": "EXACTO", "CALIBRE_ADMITIDO": "COBERTURA_ADMITIDA", "AGRUPADA": "COBERTURA_AGRUPADA", "SOLAPE_PARCIAL": "SOLAPE_PARCIAL", "SIN_COBERTURA": "SIN_COBERTURA"}
        return legacy.get(result["tipo"], "SIN_COBERTURA")

    def comparar_calibres_para_cobertura(self, calibre_pedido: Any, calibre_stock: Any, calibre_map: dict[str, str] | None = None) -> dict[str, Any]:
        pedido = self.normalizar_calibre_a_set(calibre_pedido, calibre_map=calibre_map)
        stock = self.normalizar_calibre_a_set(calibre_stock, calibre_map=calibre_map)
        if not pedido or not stock:
            return {"tipo": "SIN_COBERTURA", "pedido_set": pedido, "stock_set": stock, "coincidentes": []}
        coincidentes = sorted(pedido.intersection(stock), key=lambda x: int(x) if x.isdigit() else 9999)
        if pedido == stock:
            tipo = "EXACTA"
        elif not coincidentes:
            tipo = "SIN_COBERTURA"
        elif stock.issubset(pedido):
            tipo = "CALIBRE_ADMITIDO"
        elif pedido.issubset(stock):
            tipo = "AGRUPADA"
        else:
            tipo = "SOLAPE_PARCIAL"
        return {"tipo": tipo, "pedido_set": pedido, "stock_set": stock, "coincidentes": coincidentes}

    @staticmethod
    def calibres_coincidentes(calibre_pedido: Any, calibre_stock: Any, calibre_map: dict[str, str] | None = None) -> str:
        pedido = PlanningRepository.normalizar_calibre_a_set(calibre_pedido, calibre_map=calibre_map)
        stock = PlanningRepository.normalizar_calibre_a_set(calibre_stock, calibre_map=calibre_map)
        coincidentes = pedido.intersection(stock)
        if not coincidentes:
            return ""
        return ",".join(
            sorted(
                coincidentes,
                key=lambda x: (float(x) if str(x).replace(".", "", 1).isdigit() else 10_000, x),
            )
        )

    def _is_stock_industrial(self, pedido: Any, confeccion: Any, id_confeccion: Any = None) -> bool:
        pedido_norm = str(pedido or "").strip().upper().replace("/", "").replace(" ", "")
        confe_norm = str(confeccion or "").strip().upper()
        id_conf_norm = str(id_confeccion or "").strip()
        if pedido_norm in {"PRECALIBRADO", "ESTANDAR", "ESTÁNDAR"}:
            return True
        if any(token in confe_norm for token in ("PRECAL", "GRANEL", "GRAI", "GRANELADO")):
            return True
        # TODO: mover esta lista a configuración persistente.
        industrial_ids = {"1308"}
        return id_conf_norm in industrial_ids

    def _is_stock_sp_comercial(self, pedido: Any, confeccion: Any, id_confeccion: Any = None) -> bool:
        pedido_norm = str(pedido or "").strip().upper().replace("/", "").replace(" ", "")
        return pedido_norm == "SP" and not self._is_stock_industrial(pedido, confeccion, id_confeccion)

    @classmethod
    def calibres_solapan(cls, calibre_pedido: Any, calibre_stock: Any) -> bool:
        pedido = cls.normalizar_calibre_a_set(calibre_pedido)
        stock = cls.normalizar_calibre_a_set(calibre_stock)
        return bool(pedido and stock and pedido.intersection(stock))

    @staticmethod
    def _find_table(conn: sqlite3.Connection, candidates: list[str]) -> str | None:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        normalized = {t.upper(): t for t in tables}
        for candidate in candidates:
            table = normalized.get(candidate.upper())
            if table:
                return table
        return None

    def _get_pesosfres_campo_disponibilidad_real(self, stock_campo_rows: list[dict[str, Any]], filters: dict) -> tuple[list[dict[str, Any]], int]:
        fruta_path = self._db_path(DB_FRUTA)
        if not fruta_path.exists():
            return [], 0
        if not stock_campo_rows:
            return [], 0

        logger.info("CAMPO PesosFres: stock_campo filas=%s", len(stock_campo_rows))
        candidates: list[dict[str, Any]] = []
        sin_datos = 0
        with sqlite3.connect(fruta_path) as conn:
            conn.row_factory = sqlite3.Row
            cols = [r[1] for r in conn.execute('PRAGMA table_info("PesosFres")').fetchall()]
            if not cols:
                return [], len(stock_campo_rows)
            boleta_col = self._find_column(cols, ["Boleta"])
            campana_col = self._find_campana_column(cols) or '"CAMPAÑA"'
            cultivo_col = self._find_column(cols, ["CULTIVO"]) or "CULTIVO"
            socio_col = self._find_column(cols, ["Socio"]) or "Socio"
            variedad_col = self._find_column(cols, ["Variedad"]) or "Variedad"
            fecha_col = self._find_column(cols, ["Fcarga", "FechaCarga"]) or "Fcarga"
            neto_col = self._find_column(cols, ["Neto"])
            neto_partida_col = self._find_column(cols, ["NetoPartida"])
            categoria_col = self._find_column(cols, ["Categoria", "Categoría"])
            cal_cols: list[tuple[str, str]] = []
            for i in range(0, 12):
                col = self._find_column(cols, [f"Cal{i}"])
                if col:
                    cal_cols.append((f"CAL {i}", col))
            if not cal_cols:
                return [], len(stock_campo_rows)

            for row in stock_campo_rows:
                boleta = str(row.get("Boleta", "") or "").strip()
                kg_campo = float(row.get("Kg campo", 0) or 0)
                if kg_campo <= 0:
                    continue
                query_params: list[Any] = []
                match_row: dict[str, Any] | None = None
                match = False
                if boleta_col and boleta:
                    q = f'SELECT * FROM "PesosFres" WHERE TRIM(CAST("{boleta_col}" AS TEXT)) = TRIM(CAST(? AS TEXT)) LIMIT 1'
                    query_params = [boleta]
                    found = conn.execute(q, query_params).fetchone()
                    match_row = dict(found) if found else None
                    match = bool(match_row)
                if not match_row:
                    q = (
                        f'SELECT * FROM "PesosFres" WHERE UPPER(TRIM("{cultivo_col}")) = UPPER(TRIM(?)) '
                        f'AND TRIM(CAST("{campana_col}" AS TEXT)) = TRIM(CAST(? AS TEXT)) '
                        f'AND UPPER(TRIM("{socio_col}")) = UPPER(TRIM(?)) AND UPPER(TRIM("{variedad_col}")) = UPPER(TRIM(?)) '
                        f'ORDER BY ABS(julianday("{fecha_col}") - julianday(?)) ASC LIMIT 1'
                    )
                    query_params = [
                        str(row.get("Cultivo", "") or "").strip(),
                        str(row.get("Campaña", row.get("Campana", "")) or "").strip(),
                        str(row.get("Socio", "") or "").strip(),
                        str(row.get("Variedad", "") or "").strip(),
                        str(row.get("Fecha carga", row.get("FechaCarga", "")) or "").strip(),
                    ]
                    found = conn.execute(q, query_params).fetchone()
                    match_row = dict(found) if found else None
                    if match_row:
                        dt_row = self._parse_date(match_row.get(fecha_col))
                        dt_src = self._parse_date(row.get("Fecha carga", row.get("FechaCarga", "")))
                        match = bool(dt_row and dt_src and abs((dt_row - dt_src).days) <= 2)
                    else:
                        match = False
                logger.info("CAMPO PesosFres: boleta=%s kg_campo=%s match=%s", boleta, kg_campo, match)
                if not match_row or not match:
                    sin_datos += 1
                    logger.info("Stock campo sin aprovechamiento real: boleta %s", boleta or "(sin boleta)")
                    continue

                kg_total_real = self._build_neto_correcto(
                    match_row.get(neto_partida_col) if neto_partida_col else 0,
                    match_row.get(neto_col) if neto_col else 0,
                )
                distribucion: dict[str, float] = {}
                if kg_total_real > 0:
                    for cal_label, cal_col in cal_cols:
                        kg_cal = float(match_row.get(cal_col, 0) or 0)
                        if kg_cal <= 0:
                            continue
                        distribucion[cal_label] = round(kg_cal / kg_total_real, 8)
                logger.info("CAMPO PesosFres: boleta=%s kg_total_real=%s calibres=%s", boleta, kg_total_real, distribucion)
                if not distribucion:
                    sin_datos += 1
                    continue
                categoria = str(match_row.get(categoria_col, "") if categoria_col else "").strip()
                for calibre, pct in distribucion.items():
                    kg_estimado = round(kg_campo * pct, 2)
                    logger.info("CAMPO disponibilidad creada boleta=%s calibre=%s kg=%s pct=%s", boleta, calibre, kg_estimado, pct)
                    candidates.append({
                        "Origen": "CAMPO_REAL_PESOSFRES",
                        "Tipo stock": "CAMPO",
                        "Cultivo": row.get("Cultivo", ""),
                        "Campaña": row.get("Campaña", row.get("Campana", "")),
                        "Grupo varietal": row.get("Grupo varietal", ""),
                        "Variedad": row.get("Variedad", ""),
                        "Calibre": calibre,
                        "Categoría": categoria,
                        "Kg disponibles": kg_estimado,
                        "Kg campo origen": kg_campo,
                        "Boleta": boleta,
                        "Socio": row.get("Socio", ""),
                        "Fecha carga": row.get("Fecha carga", row.get("FechaCarga", "")),
                        "% aprovechamiento": round(pct * 100, 4),
                        "Origen aprovechamiento": "REAL",
                        "Aviso": f"Aprovechamiento real PesosFres boleta {boleta}".strip(),
                        "Explicación": "Kg estimados por calibre calculados desde aprovechamiento real de PesosFres",
                    })
        return candidates, sin_datos

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
            score = 0
            flex = []
            if kg_cobertura_exacta > 0: score = 100
            elif kg_cobertura_agrupada > 0: score = 85 if "admitido" in coincidencia.lower() else 70
            elif kg_cobertura_solape_parcial > 0: score = 40
            if policy_cfg["usar_entrada_estimada"] and kg_entrada_estimada > 0: score -= 10
            if policy_cfg["usar_stock_comercial"] and kg_stock_comercial > 0: score -= 20
            if not (str(categoria).strip()): score -= 15
            explicacion = "Sin cobertura con la política actual" if (necesita_cobertura and kg_cobertura_potencial <= 0) else ("Stock industrial compatible por calibre admitido" if kg_cobertura_agrupada > 0 else "Stock industrial compatible por calibre exacto")
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
            db_eepl = self._db_path(DB_EEPPL)
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
            db_pedidos = self._db_path(DB_PEDIDOS)
            db_eepl = self._db_path(DB_EEPPL)
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
            db_pedidos = self._db_path(DB_PEDIDOS)
            db_eepl = self._db_path(DB_EEPPL)
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
                SELECT ldo.CULTIVO as Cultivo, ldo."{camp_col}" as Campana, ldo.IdPalet, ldo.Pedido, COALESCE(ldo.{fecha_col}, '') as FechaAlmacen,
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
        t0_total = time.perf_counter()
        logger.info("get_pedidos_pendientes: inicio")
        pedidos_path = self._db_path(DB_PEDIDOS)
        logger.info("Ruta DBPedidos.sqlite usada: %s", pedidos_path)
        logger.info("DBPedidos.sqlite existe: %s", pedidos_path.exists())
        kpi_vacio = {"Kg pedido teórico total": 0.0, "Kg hecho real total": 0.0, "Kg pendiente total": 0.0, "Merma kg total": 0.0, "% merma total": 0.0, "Nº pedidos": 0, "Nº líneas": 0, "Nº líneas sin datos": 0, "Nº líneas parciales": 0}
        if not pedidos_path.exists():
            logger.warning("No existe DBPedidos.sqlite en la ruta esperada")
            return [], kpi_vacio

        with sqlite3.connect(pedidos_path) as conn:
            conn.row_factory = sqlite3.Row
            db_eepl = self._db_path(DB_EEPPL)
            db_loteado = self._db_path(DB_LOTEADO)
            conn.execute(f"ATTACH DATABASE '{db_eepl.as_posix()}' AS dbeepl")
            conn.execute(f"ATTACH DATABASE '{db_loteado.as_posix()}' AS bdloteado")
            eepl_tables = [r[0] for r in conn.execute("SELECT name FROM dbeepl.sqlite_master WHERE type='table'").fetchall()]
            if "MVariedad" not in eepl_tables:
                logger.warning("No existe tabla MVariedad en DBEEPPL.sqlite")
            pedidos_cols = [r["name"] for r in conn.execute('PRAGMA table_info("Pedidos")').fetchall()]
            if not pedidos_cols:
                logger.warning("No existe la tabla Pedidos en DBPedidos.sqlite")
                return [], kpi_vacio
            self._ensure_planning_indexes(conn)

            query = """
                WITH pedidos_filtrados AS (
                    SELECT
                        p."Semana",
                        p."FechaSalida",
                        p."Cliente",
                        p."IdPedidoLora",
                        p."Linea",
                        p."Cultivo",
                        p."Campaña",
                        p."VarCoop",
                        p."Calibre",
                        p."Categoria",
                        p."Marca",
                        p."Confeccion",
                        p."NPalet",
                        p."Cajas",
                        p."ExigePeso",
                        p."EMPRESA"
                    FROM "Pedidos" p
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
            query += """
                ),
                palets_terminados AS (
                    SELECT DISTINCT
                        TRIM(ldo.Pedido) AS Pedido,
                        CAST(ldo.Linea AS TEXT) AS Linea,
                        ldo.IdPalet
                    FROM bdloteado.Loteado ldo
                    INNER JOIN pedidos_filtrados pf
                        ON TRIM(ldo.Pedido) = TRIM(pf.IdPedidoLora)
                       AND CAST(ldo.Linea AS TEXT) = CAST(pf.Linea AS TEXT)
                    WHERE UPPER(TRIM(ldo.Terminado)) IN ('S','SI','SÍ')
                ),
                palets_resumen AS (
                    SELECT
                        pt.Pedido,
                        pt.Linea,
                        pt.IdPalet,
                        SUM(COALESCE(l.Cajas, 0)) AS CajasPalet,
                        SUM(COALESCE(l.Neto, 0)) AS KgPalet
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
                    p."Confeccion" AS "IdConfeccion",
                    COALESCE(NULLIF(mc."NOMBRE", ''), CAST(p."Confeccion" AS TEXT)) AS "Confección",
                    COALESCE(p."NPalet", 0) AS "Palets pedido",
                    COALESCE(h.PaletsHechos, 0) AS "Palets hechos",
                    MAX(0, COALESCE(p."NPalet", 0) - COALESCE(h.PaletsHechos, 0)) AS "Palets pendientes",
                    COALESCE(p."Cajas", 0) AS "Cajas/palet",
                    COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) AS "Cajas pedido",
                    COALESCE(h.CajasHechas, 0) AS "Cajas hechas",
                    MAX(0, (COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0)) - COALESCE(h.CajasHechas, 0)) AS "Cajas pendientes",
                    CASE
                      WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                      WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                      ELSE 0
                    END AS "Kg pedido teórico",
                    COALESCE(h.KgHechoReal, 0) AS "Kg hecho real",
                    MAX(0, (
                      CASE
                        WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                        WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                        ELSE 0
                      END
                    ) - COALESCE(h.KgHechoReal, 0)) AS "Kg pendiente",
                    CASE
                      WHEN NULLIF((
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ), 0) IS NULL THEN 0
                      ELSE ROUND(MIN(100, (COALESCE(h.KgHechoReal, 0) / NULLIF((
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ), 0)) * 100), 2)
                    END AS "% hecho",
                    MAX(0, COALESCE(h.KgHechoReal, 0) - (
                      CASE
                        WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                        WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                        ELSE 0
                      END
                    )) AS "Merma kg",
                    CASE
                      WHEN NULLIF((
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ), 0) IS NULL THEN 0
                      ELSE ROUND(MAX(0, ((COALESCE(h.KgHechoReal, 0) / NULLIF((
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ), 0)) * 100) - 100), 2)
                    END AS "% merma",
                    CASE
                      WHEN (
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ) = 0 THEN 'Sin datos'
                      WHEN COALESCE(h.KgHechoReal, 0) = 0 THEN 'Pendiente'
                      WHEN COALESCE(h.KgHechoReal, 0) >= (
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ) THEN 'Completo'
                      WHEN COALESCE(h.KgHechoReal, 0) > 0
                       AND COALESCE(h.KgHechoReal, 0) < (
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ) THEN 'Parcial'
                      ELSE 'Parcial'
                    END AS "Estado",
                    CASE
                      WHEN (
                        CASE
                          WHEN COALESCE(mc."NETO", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * mc."NETO"
                          WHEN COALESCE(p."ExigePeso", 0) > 0 THEN COALESCE(p."NPalet", 0) * COALESCE(p."Cajas", 0) * p."ExigePeso"
                          ELSE 0
                        END
                      ) = 0 THEN 'Faltan datos peso caja'
                      ELSE ''
                    END AS "Aviso"
                FROM pedidos_filtrados p
                LEFT JOIN dbeepl.MVariedad mv
                  ON UPPER(TRIM(mv.Variedad)) = UPPER(TRIM(p."VarCoop"))
                 AND UPPER(TRIM(mv.CULTIVO)) = UPPER(TRIM(p."Cultivo"))
                LEFT JOIN hecho h
                  ON h.Pedido = TRIM(p."IdPedidoLora")
                 AND h.Linea = CAST(p."Linea" AS TEXT)
                LEFT JOIN MConfecciones mc
                  ON CAST(mc.CODIGO AS TEXT) = CAST(p."Confeccion" AS TEXT)
            """
            query += """
                ORDER BY date(p."FechaSalida") ASC,
                         p."Cliente" ASC,
                         p."IdPedidoLora" ASC,
                         p."Linea" ASC
                LIMIT 500
            """
            logger.info("get_pedidos_pendientes: después de pedidos_filtrados (query construida)")
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
            logger.info("get_pedidos_pendientes: después de query final (%s filas)", len(rows))
            logger.info("get_pedidos_pendientes: tiempo total %.3fs", time.perf_counter() - t0_total)
            logger.info("Pedidos pendientes finales: %s", len(rows))
            if not rows:
                logger.warning("No se encontraron pedidos pendientes con los filtros aplicados.")
                return [], kpi_vacio

        pedidos_unicos = {str(r.get("IdPedidoLora") or "").strip() for r in rows if str(r.get("IdPedidoLora") or "").strip()}
        kpi = {
            "Kg pedido teórico total": sum(float(r.get("Kg pedido teórico", 0) or 0) for r in rows),
            "Kg hecho real total": sum(float(r.get("Kg hecho real", 0) or 0) for r in rows),
            "Kg pendiente total": sum(float(r.get("Kg pendiente", 0) or 0) for r in rows),
            "Merma kg total": sum(float(r.get("Merma kg", 0) or 0) for r in rows),
            "Nº pedidos": len(pedidos_unicos),
            "Nº líneas": len(rows),
            "Nº líneas sin datos": sum(1 for r in rows if str(r.get("Estado", "")).strip().lower() == "sin datos"),
            "Nº líneas parciales": sum(1 for r in rows if str(r.get("Estado", "")).strip().lower() == "parcial"),
        }
        pedido_total = float(kpi.get("Kg pedido teórico total", 0) or 0)
        kpi["% merma total"] = round((float(kpi.get("Merma kg total", 0) or 0) / pedido_total) * 100, 2) if pedido_total > 0 else 0.0
        return rows, kpi



    def get_balance_planificacion(self, filters: dict, policy: dict | None = None) -> list[dict]:
        policy_cfg = self._merge_policy(policy)
        detalle_rows = self.get_stock_almacen_detalle_palets(filters)
        pedidos_rows, _ = self.get_pedidos_pendientes(filters, modo_pedidos=str(filters.get("pedidos_modo") or "10_dias"))
        stock_campo_rows, _, _ = self.get_stock_campo(filters)

        commercial_map: dict[tuple, float] = {}
        industrial_stock_map: dict[tuple, float] = {}
        campo_map: dict[tuple, float] = {}
        campo_real_map: dict[tuple, float] = {}
        pedidos_map: dict[tuple, float] = {}

        for row in detalle_rows:
            campana_stock = row.get("Campaña", row.get("Campana", ""))
            common_key = (
                row.get("Cultivo", ""), campana_stock, row.get("GrupoVarietal", ""),
                row.get("Variedad", ""), row.get("Calibre", ""), row.get("Categoria", ""),
            )
            kg = float(row.get("Neto", 0) or 0)
            marca = row.get("Marca", "")
            id_confeccion = str(row.get("IdConfeccion", "") or "").strip()
            confe = str(row.get("Confeccion", "") or "").strip()
            tipo_stock = "omitido"
            if policy_cfg["usar_stock_industrial"] and self._is_stock_industrial(row.get("Pedido"), confe, id_confeccion):
                industrial_stock_map[common_key] = industrial_stock_map.get(common_key, 0.0) + kg
                tipo_stock = "industrial"
            elif policy_cfg["usar_stock_comercial"] and self._is_stock_sp_comercial(row.get("Pedido"), confe, id_confeccion):
                ckey = common_key + (marca, id_confeccion, confe)
                commercial_map[ckey] = commercial_map.get(ckey, 0.0) + kg
                tipo_stock = "comercial"
            if logger.isEnabledFor(logging.DEBUG):
                logger.info(
                    "Balance stock clasificado: pedido=%s id_conf=%s conf=%s tipo=%s kg=%s calibre=%s variedad=%s",
                    row.get("Pedido"), id_confeccion, confe, tipo_stock, kg, row.get("Calibre"), row.get("Variedad")
                )

        logger.info(
            "BALANCE DEBUG industrial_stock_map total claves=%s kg_total=%s",
            len(industrial_stock_map),
            sum(industrial_stock_map.values()),
        )
        for k, v in list(industrial_stock_map.items())[:20]:
            logger.info("BALANCE DEBUG INDUSTRIAL key=%s kg=%s", k, v)

        campo_tiene_desglose = False
        for row in stock_campo_rows:
            key = (
                row.get("Cultivo", ""), row.get("Campaña", ""), row.get("Grupo varietal", ""),
                row.get("Variedad", ""), "", "",
            )
            campo_map[key] = campo_map.get(key, 0.0) + float(row.get("Kg campo", 0) or 0)
        campo_real_rows, campo_sin_datos = (self._get_pesosfres_campo_disponibilidad_real(stock_campo_rows, filters) if policy_cfg["usar_entrada_estimada"] else ([], 0))
        campo_tiene_desglose = bool(campo_real_rows)
        for c_row in campo_real_rows:
            c_key = (
                c_row.get("Cultivo", ""), c_row.get("Campaña", ""), c_row.get("Grupo varietal", ""),
                c_row.get("Variedad", ""), c_row.get("Calibre", ""), c_row.get("Categoría", ""),
            )
            campo_real_map[c_key] = campo_real_map.get(c_key, 0.0) + float(c_row.get("Kg disponibles", 0) or 0)

        for row in pedidos_rows:
            id_confeccion = str(row.get("IdConfeccion", "") or "").strip()
            confeccion = str(row.get("Confección", "") or "").strip()
            key = (
                row.get("Cultivo", ""), row.get("Campaña", ""), row.get("Grupo varietal", ""),
                row.get("Variedad Coop", ""), row.get("Calibre", ""), row.get("Categoría", ""),
                row.get("Marca", ""), id_confeccion, confeccion,
            )
            pedidos_map[key] = pedidos_map.get(key, 0.0) + float(row.get("Kg pendiente", 0) or 0)

        keys = set(commercial_map.keys()) | set(pedidos_map.keys())
        calibre_map = self.get_mcalibres_map()
        logger.info(
            "BALANCE TEST calibres CAL 1/2 vs 0/1/2/3 = %s",
            self.comparar_calibres("CAL 1/2", "0/1/2/3", calibre_map=calibre_map),
        )
        data: list[dict] = []
        for key in sorted(keys, key=lambda k: tuple(str(x) for x in k)):
            cultivo, campana, grupo, variedad, calibre, categoria, marca, id_confeccion, confe = key
            common_key = (cultivo, campana, grupo, variedad, calibre, categoria)
            base_key = (cultivo, campana, grupo, variedad, "", "")
            kg_stock_comercial = round(commercial_map.get(key, 0.0), 2)
            kg_pendiente = round(pedidos_map.get(key, 0.0), 2)
            diff = round(kg_stock_comercial - kg_pendiente, 2)
            if kg_pendiente <= 0:
                estado_com = "Sobrante comercial" if diff > 0 else "Cubierto comercialmente"
            elif diff < 0:
                estado_com = "Faltante comercial"
            elif diff > 0:
                estado_com = "Sobrante comercial"
            else:
                estado_com = "Cubierto comercialmente"

            kg_industrial_stock = round(industrial_stock_map.get(common_key, 0.0), 2)
            kg_entrada_estimada_real = round(campo_real_map.get(common_key, 0.0), 2) if policy_cfg["usar_entrada_estimada"] else 0.0
            kg_entrada_estimada = kg_entrada_estimada_real
            kg_entrada_estimada_sin_datos = round(campo_map.get(base_key, 0.0), 2) if policy_cfg["usar_entrada_estimada"] else 0.0
            kg_base_total_estimada = round(kg_industrial_stock + kg_entrada_estimada, 2)
            necesita_cobertura = kg_pendiente > 0 and diff < 0

            kg_cobertura_exacta = 0.0
            kg_cobertura_agrupada = 0.0
            kg_cobertura_solape_parcial = 0.0
            variedades_stock_industrial: set[str] = set()
            coincidencia = "Sin cobertura"
            if necesita_cobertura:
                logger.info(
                    "BALANCE DEBUG pedido faltante cultivo=%s campana=%s grupo=%s variedad=%s calibre=%s categoria=%s faltante=%s",
                    cultivo, campana, grupo, variedad, calibre, categoria, abs(diff)
                )
                for ind_key, ind_kg in industrial_stock_map.items():
                    logger.info(
                        "BALANCE DEBUG compara pedido grupo=%s calibre=%s categoria=%s CON stock key=%s kg=%s",
                        grupo, calibre, categoria, ind_key, ind_kg
                    )
                    mismo_cultivo = str(ind_key[0]).strip().upper() == str(cultivo).strip().upper()
                    misma_campana = str(ind_key[1]).strip() == str(campana).strip()
                    mismo_grupo = str(ind_key[2]).strip().upper() == str(grupo).strip().upper()
                    grupo_ok = mismo_grupo or policy_cfg["permitir_grupo_varietal_alternativo"]
                    categoria_stock = str(ind_key[5]).strip().upper()
                    categoria_pedido = str(categoria).strip().upper()
                    misma_categoria = categoria_stock == categoria_pedido
                    cat_ok = misma_categoria or (policy_cfg["permitir_categoria_inferior"] and categoria_stock < categoria_pedido) or (policy_cfg["permitir_categoria_superior"] and categoria_stock > categoria_pedido)

                    if not (mismo_cultivo and misma_campana and grupo_ok and cat_ok):
                        if not mismo_cultivo:
                            logger.info("BALANCE DEBUG descarta: cultivo distinto")
                        elif not misma_campana:
                            logger.info("BALANCE DEBUG descarta: campaña distinta")
                        elif not grupo_ok:
                            logger.info("BALANCE DEBUG descarta: grupo distinto")
                        elif not misma_categoria:
                            logger.info("BALANCE DEBUG descarta: categoría distinta")
                        continue

                    if (not policy_cfg["permitir_variedad_alternativa"]) and str(ind_key[3]).strip().upper() != str(variedad).strip().upper():
                        continue
                    cmp_result = self.comparar_calibres_para_cobertura(calibre, ind_key[4], calibre_map=calibre_map)
                    if cmp_result["tipo"] == "SIN_COBERTURA":
                        logger.info("BALANCE DEBUG descarta: calibre sin cobertura")
                        continue

                    if cmp_result["tipo"] == "CALIBRE_ADMITIDO" and not policy_cfg["permitir_calibre_admitido"]:
                        continue
                    if cmp_result["tipo"] == "AGRUPADA" and not policy_cfg["permitir_calibre_agrupado"]:
                        continue
                    if cmp_result["tipo"] == "SOLAPE_PARCIAL" and not policy_cfg["permitir_solape_parcial"]:
                        continue
                    if logger.isEnabledFor(logging.INFO) and (mismo_grupo or (mismo_cultivo and misma_campana)):
                        logger.info(
                            "Cobertura industrial candidato: pedido_grupo=%s pedido_variedad=%s pedido_calibre=%s pedido_cat=%s | stock_grupo=%s stock_variedad=%s stock_calibre=%s stock_cat=%s kg=%s comparacion=%s",
                            grupo, variedad, calibre, categoria,
                            ind_key[2], ind_key[3], ind_key[4], ind_key[5],
                            ind_kg, cmp_result["tipo"]
                        )

                    variedades_stock_industrial.add(str(ind_key[3] or "").strip())
                    if cmp_result["tipo"] == "EXACTA":
                        kg_cobertura_exacta += ind_kg
                    elif cmp_result["tipo"] in {"AGRUPADA", "CALIBRE_ADMITIDO"}:
                        kg_cobertura_agrupada += ind_kg
                    elif cmp_result["tipo"] == "SOLAPE_PARCIAL":
                        kg_cobertura_solape_parcial += ind_kg

                kg_cobertura_exacta = round(kg_cobertura_exacta, 2)
                kg_cobertura_agrupada = round(kg_cobertura_agrupada, 2)
                kg_cobertura_solape_parcial = round(kg_cobertura_solape_parcial, 2)
                if kg_cobertura_exacta > 0:
                    coincidencia = "Exacta"
                elif kg_cobertura_agrupada > 0:
                    coincidencia = "Cobertura por calibre admitido"
                elif kg_cobertura_solape_parcial > 0:
                    coincidencia = "Cobertura por solape parcial"

                if policy_cfg["usar_stock_comercial"] and necesita_cobertura:
                    for ckey, ckg in commercial_map.items():
                        c_cultivo, c_campana, c_grupo, c_var, c_calibre, _cat, c_marca, c_id_conf, c_conf = ckey
                        if str(c_cultivo).strip().upper() != str(cultivo).strip().upper():
                            continue
                        if str(c_campana).strip() != str(campana).strip():
                            continue
                        if (not policy_cfg["permitir_grupo_varietal_alternativo"]) and str(c_grupo).strip().upper() != str(grupo).strip().upper():
                            continue
                        if (not policy_cfg["permitir_variedad_alternativa"]) and str(c_var).strip().upper() != str(variedad).strip().upper():
                            continue
                        if str(marca or "").strip() and str(c_marca or "").strip() and str(marca).strip().upper() != str(c_marca).strip().upper():
                            continue
                        cmp_result = self.comparar_calibres_para_cobertura(calibre, c_calibre, calibre_map=calibre_map)
                        if cmp_result["tipo"] == "SIN_COBERTURA":
                            continue
                        if cmp_result["tipo"] == "CALIBRE_ADMITIDO" and not policy_cfg["permitir_calibre_admitido"]:
                            continue
                        if cmp_result["tipo"] == "AGRUPADA" and not policy_cfg["permitir_calibre_agrupado"]:
                            continue
                        if cmp_result["tipo"] == "SOLAPE_PARCIAL" and not policy_cfg["permitir_solape_parcial"]:
                            continue
                        if cmp_result["tipo"] == "EXACTA":
                            kg_cobertura_exacta += ckg
                        elif cmp_result["tipo"] in {"AGRUPADA", "CALIBRE_ADMITIDO"}:
                            kg_cobertura_agrupada += ckg
                        elif cmp_result["tipo"] == "SOLAPE_PARCIAL":
                            kg_cobertura_solape_parcial += ckg

            kg_cobertura_potencial = round(kg_cobertura_exacta + kg_cobertura_agrupada + kg_cobertura_solape_parcial, 2) if necesita_cobertura else 0.0
            faltante = abs(diff) if necesita_cobertura else 0.0
            if necesita_cobertura:
                if kg_cobertura_potencial >= faltante and faltante > 0:
                    cobertura_posible = "Sí"
                elif 0 < kg_cobertura_potencial < faltante:
                    cobertura_posible = "Parcial"
                else:
                    cobertura_posible = "No"
            else:
                cobertura_posible = ""

            if (kg_cobertura_exacta + kg_cobertura_agrupada) > 0:
                estado_ind = "Disponible"
            else:
                estado_ind = "Sin base industrial"
            aviso = ""
            if kg_pendiente <= 0 and estado_com == "Sobrante comercial":
                aviso = "Disponible para venta"
            elif necesita_cobertura:
                if kg_cobertura_exacta > 0:
                    aviso = "Faltante con cobertura industrial exacta"
                elif kg_cobertura_agrupada > 0:
                    aviso = "Faltante con cobertura por calibre admitido"
                else:
                    aviso = "Faltante comercial sin base industrial"
                if kg_entrada_estimada > 0 and not campo_tiene_desglose and not calibre:
                    aviso = (aviso + " | " if aviso else "") + "Entrada estimada sin desglose por calibre"
            if kg_pendiente <= 0:
                tipo_linea = "Sobrante comercial" if diff > 0 else "Industrial disponible"
            else:
                tipo_linea = "Pedido"
            if tipo_linea == "Sobrante comercial":
                aviso = "Disponible para venta"
                cobertura_posible = ""
                kg_cobertura_exacta = 0.0
                kg_cobertura_agrupada = 0.0
                kg_cobertura_solape_parcial = 0.0
                kg_cobertura_potencial = 0.0
                coincidencia = "No aplica"

            score = 0
            flex = []
            if kg_cobertura_exacta > 0: score = 100
            elif kg_cobertura_agrupada > 0: score = 85 if "admitido" in coincidencia.lower() else 70
            elif kg_cobertura_solape_parcial > 0: score = 40
            if policy_cfg["usar_entrada_estimada"] and kg_entrada_estimada > 0: score -= 10
            if policy_cfg["usar_stock_comercial"] and kg_stock_comercial > 0: score -= 20
            if not (str(categoria).strip()): score -= 15
            explicacion = "Sin cobertura con la política actual" if (necesita_cobertura and kg_cobertura_potencial <= 0) else ("Stock compatible por calibre admitido" if kg_cobertura_agrupada > 0 else "Stock compatible por calibre exacto")
            data.append({
                "Cultivo": cultivo,
                "Campaña": campana,
                "Grupo varietal": grupo,
                "Variedad": variedad,
                "Calibre": calibre,
                "Categoría": categoria,
                "Marca": marca,
                "IdConfeccion": id_confeccion,
                "Confección": confe,
                "Kg stock comercial": kg_stock_comercial,
                "Kg pedidos pendientes": kg_pendiente,
                "Diferencia comercial": diff,
                "Tipo línea": tipo_linea,
                "Estado comercial": estado_com,
                "Kg stock industrial almacén": kg_industrial_stock,
                "Kg entrada estimada": kg_entrada_estimada,
                "Kg entrada estimada real": kg_entrada_estimada_real,
                "Kg entrada estimada sin datos": kg_entrada_estimada_sin_datos if campo_sin_datos > 0 else 0.0,
                "Kg base total estimada": kg_base_total_estimada,
                "Kg cobertura exacta": kg_cobertura_exacta,
                "Kg cobertura agrupada": kg_cobertura_agrupada,
                "Kg cobertura solape parcial": kg_cobertura_solape_parcial,
                "Kg cobertura potencial total": kg_cobertura_potencial,
                "Kg disponibilidad compatible": kg_cobertura_potencial,
                "Mejor cobertura": coincidencia,
                "Calibres coincidentes": "",
                "Flexibilidad aplicada": ", ".join(flex),
                "Score cobertura": score,
                "Explicación": explicacion,
                "Cobertura posible": cobertura_posible,
                "Coincidencia": coincidencia,
                "Estado industrial": estado_ind,
                "Agrupado": "Sí" if self._is_calibre_agrupado(calibre) else "No",
                "Aviso": aviso,
                "Variedad stock": " | ".join(sorted(v for v in variedades_stock_industrial if v)),
            })
        tipo_prioridad = {"Pedido": 0, "Sobrante comercial": 2, "Industrial disponible": 3}
        estado_pedido_prioridad = {"Faltante comercial": 0, "Ajustado": 1, "Cubierto comercialmente": 1, "Sobrante comercial": 1}
        data.sort(
            key=lambda r: (
                tipo_prioridad.get(str(r.get("Tipo línea", "")), 9),
                estado_pedido_prioridad.get(str(r.get("Estado comercial", "")), 9),
                tuple(str(r.get(k, "")) for k in ("Cultivo", "Campaña", "Grupo varietal", "Variedad", "Calibre", "Categoría", "Marca", "IdConfeccion", "Confección")),
            )
        )
        return data

    def get_balance_cobertura_detalle(self, filters: dict, balance_row: dict, policy: dict | None = None) -> list[dict]:
        policy_cfg = self._merge_policy(policy)
        detalle_rows = self.get_stock_almacen_detalle_palets(filters)
        stock_campo_rows, _, _ = self.get_stock_campo(filters)
        cultivo = str(balance_row.get("Cultivo", "") or "").strip()
        campana = str(balance_row.get("Campaña", "") or "").strip()
        grupo = str(balance_row.get("Grupo varietal", "") or "").strip()
        calibre_pedido = str(balance_row.get("Calibre", "") or "").strip()
        categoria = str(balance_row.get("Categoría", "") or "").strip()
        calibre_map = self.get_mcalibres_map()

        agrupado: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in detalle_rows:
            confe = str(row.get("Confeccion", "") or "").strip()
            id_confeccion = str(row.get("IdConfeccion", "") or "").strip()
            is_ind = self._is_stock_industrial(row.get("Pedido"), confe, id_confeccion)
            is_sp = self._is_stock_sp_comercial(row.get("Pedido"), confe, id_confeccion)
            if not ((policy_cfg["usar_stock_industrial"] and is_ind) or (policy_cfg["usar_stock_comercial"] and is_sp)):
                continue

            stock_cultivo = str(row.get("Cultivo", "") or "").strip()
            stock_campana = str(row.get("Campaña", row.get("Campana", "")) or "").strip()
            stock_grupo = str(row.get("GrupoVarietal", "") or "").strip()
            stock_categoria = str(row.get("Categoria", "") or "").strip()
            if stock_cultivo.upper() != cultivo.upper():
                continue
            if stock_campana != campana:
                continue
            if policy_cfg["mismo_grupo_varietal"] and (not policy_cfg["permitir_grupo_varietal_alternativo"]) and stock_grupo.upper() != grupo.upper():
                continue
            if stock_categoria.upper() != categoria.upper() and not policy_cfg["permitir_categoria_inferior"] and not policy_cfg["permitir_categoria_superior"]:
                continue

            cmp_result = self.comparar_calibres_para_cobertura(calibre_pedido, row.get("Calibre", ""), calibre_map=calibre_map)
            if cmp_result["tipo"] == "SIN_COBERTURA":
                continue
            if cmp_result["tipo"] == "CALIBRE_ADMITIDO" and not policy_cfg["permitir_calibre_admitido"]:
                continue
            if cmp_result["tipo"] == "AGRUPADA" and not policy_cfg["permitir_calibre_agrupado"]:
                continue
            if cmp_result["tipo"] == "SOLAPE_PARCIAL" and not policy_cfg["permitir_solape_parcial"]:
                continue

            is_sp = self._is_stock_sp_comercial(row.get("Pedido"), confe, id_confeccion)
            if cmp_result["tipo"] == "EXACTA":
                tipo = "Comercial S/P" if is_sp else "Industrial exacta"
                aviso = ""
                orden = 1
            elif len(self.normalizar_calibre_a_set(row.get("Calibre", ""), calibre_map=calibre_map)) > 1:
                tipo = "Comercial S/P" if is_sp else "Industrial agrupada"
                aviso = "Stock comercial S/P compatible por marca y calibre admitido" if is_sp else "Cobertura por calibre agrupado; puede requerir reparto"
                orden = 3
            else:
                tipo = "Comercial S/P" if is_sp else "Industrial por calibre admitido"
                aviso = "Stock comercial S/P compatible por marca y calibre admitido" if is_sp else "Cobertura por calibre admitido"
                orden = 2

            coincidencia_label = "Exacta" if cmp_result["tipo"] == "EXACTA" else ("Calibre agrupado" if len(self.normalizar_calibre_a_set(row.get("Calibre", ""), calibre_map=calibre_map)) > 1 else "Calibre admitido")
            calibre_stock = str(row.get("Calibre", "") or "").strip()
            coincidentes_txt = self.calibres_coincidentes(calibre_pedido, calibre_stock, calibre_map=calibre_map)
            key = (
                stock_cultivo, stock_campana, stock_grupo, str(row.get("Variedad", "") or "").strip(), calibre_stock,
                stock_categoria, id_confeccion, confe, tipo, coincidencia_label, coincidentes_txt, aviso, orden,
            )
            acc = agrupado.get(key)
            if not acc:
                acc = {
                    "__orden": orden,
                    "Tipo cobertura": tipo,
                    "Origen": "ALMACEN_COMERCIAL" if is_sp else "ALMACEN_INDUSTRIAL",
                    "Cultivo": stock_cultivo,
                    "Campaña": stock_campana,
                    "Grupo varietal": stock_grupo,
                    "Variedad stock": str(row.get("Variedad", "") or "").strip(),
                    "Calibre stock": calibre_stock,
                    "Calibres coincidentes": coincidentes_txt,
                    "Marca stock": str(row.get("Marca", "") or "").strip(),
                    "Categoría": stock_categoria,
                    "IdConfeccion stock": id_confeccion,
                    "Confección stock": confe,
                    "Palets": set(),
                    "Cajas": 0.0,
                    "Kg disponibles": 0.0,
                    "Coincidencia": coincidencia_label,
                    "Score": 95 if (is_sp and cmp_result["tipo"]=="EXACTA") else (80 if (is_sp and cmp_result["tipo"]=="CALIBRE_ADMITIDO") else (70 if (is_sp and cmp_result["tipo"]=="AGRUPADA") else (100 if cmp_result["tipo"]=="EXACTA" else (85 if cmp_result["tipo"]=="CALIBRE_ADMITIDO" else (70 if cmp_result["tipo"]=="AGRUPADA" else 40))))),
                    "Flexibilidad aplicada": cmp_result["tipo"],
                    "Explicación": aviso or "Stock compatible por política de simulación",
                    "Aviso": aviso,
                }
                agrupado[key] = acc
            id_palet = str(row.get("IdPalet", "") or "").strip()
            if id_palet:
                acc["Palets"].add(id_palet)
            acc["Cajas"] += float(row.get("Cajas", 0) or 0)
            acc["Kg disponibles"] += float(row.get("Neto", 0) or 0)

        if policy_cfg["usar_entrada_estimada"]:
            campo_real_rows, _ = self._get_pesosfres_campo_disponibilidad_real(stock_campo_rows, filters)
            for row in campo_real_rows:
                stock_cultivo = str(row.get("Cultivo", "") or "").strip()
                stock_campana = str(row.get("Campaña", "") or "").strip()
                stock_grupo = str(row.get("Grupo varietal", "") or "").strip()
                stock_categoria = str(row.get("Categoría", "") or "").strip()
                if stock_cultivo.upper() != cultivo.upper() or stock_campana != campana:
                    continue
                if policy_cfg["mismo_grupo_varietal"] and (not policy_cfg["permitir_grupo_varietal_alternativo"]) and stock_grupo.upper() != grupo.upper():
                    continue
                cmp_result = self.comparar_calibres_para_cobertura(calibre_pedido, row.get("Calibre", ""), calibre_map=calibre_map)
                if cmp_result["tipo"] == "SIN_COBERTURA":
                    continue
                aviso_base = str(row.get("Aviso", "") or "").strip()
                if not stock_categoria:
                    aviso_base = (aviso_base + " | " if aviso_base else "") + "Campo sin categoría; revisar"
                key = (
                    stock_cultivo, stock_campana, stock_grupo, str(row.get("Variedad", "") or "").strip(), str(row.get("Calibre", "") or "").strip(),
                    stock_categoria, str(row.get("Boleta", "") or "").strip(), str(row.get("Socio", "") or "").strip(), aviso_base,
                )
                acc = agrupado.get(key)
                if not acc:
                    acc = {
                        "__orden": 4,
                        "Tipo cobertura": "Entrada estimada real",
                        "Origen": "CAMPO_REAL_PESOSFRES",
                        "Cultivo": stock_cultivo,
                        "Campaña": stock_campana,
                        "Grupo varietal": stock_grupo,
                        "Variedad stock": str(row.get("Variedad", "") or "").strip(),
                        "Calibre stock": str(row.get("Calibre", "") or "").strip(),
                        "Calibres coincidentes": self.calibres_coincidentes(calibre_pedido, row.get("Calibre", ""), calibre_map=calibre_map),
                        "Marca stock": "",
                        "Categoría": stock_categoria,
                        "IdConfeccion stock": "",
                        "Confección stock": "",
                        "Boleta": str(row.get("Boleta", "") or "").strip(),
                        "Socio": str(row.get("Socio", "") or "").strip(),
                        "Fecha carga": str(row.get("Fecha carga", "") or "").strip(),
                        "Kg campo origen": float(row.get("Kg campo origen", 0) or 0),
                        "% aprovechamiento": float(row.get("% aprovechamiento", 0) or 0),
                        "Palets": 0,
                        "Cajas": 0.0,
                        "Kg disponibles": 0.0,
                        "Coincidencia": "Entrada campo estimada real",
                        "Score": 75,
                        "Flexibilidad aplicada": "CAMPO_REAL",
                        "Explicación": str(row.get("Explicación", "") or "").strip(),
                        "Aviso": aviso_base,
                    }
                    agrupado[key] = acc
                acc["Kg disponibles"] += float(row.get("Kg disponibles", 0) or 0)

        def _count_palets_safe(value: Any) -> int:
            if value is None:
                return 0
            if isinstance(value, (set, list, tuple)):
                return len(value)
            try:
                return int(value)
            except Exception:
                return 0

        out = list(agrupado.values())
        for row in out:
            row["Palets"] = _count_palets_safe(row.get("Palets"))
            row["Cajas"] = round(float(row.get("Cajas", 0) or 0), 2)
            row["Kg disponibles"] = round(float(row.get("Kg disponibles", 0) or 0), 2)
        out.sort(key=lambda r: (int(r.get("__orden", 9)), -float(r.get("Kg disponibles", 0) or 0)))
        for row in out:
            row.pop("__orden", None)
        return out

    @staticmethod
    def _ensure_planning_indexes(conn: sqlite3.Connection) -> None:
        conn.execute('CREATE INDEX IF NOT EXISTS bdloteado.idx_loteado_pedido_linea ON Loteado(Pedido, Linea)')
        conn.execute('CREATE INDEX IF NOT EXISTS bdloteado.idx_loteado_terminado ON Loteado(Terminado)')
        conn.execute('CREATE INDEX IF NOT EXISTS bdloteado.idx_lote_idpalet ON Lote(IdPalet)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_pedidos_fecha ON Pedidos(FechaSalida)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_pedidos_campana_cultivo ON Pedidos("Campaña", Cultivo)')
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
                db_eepl = self._db_path(DB_EEPPL)
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
