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

def normalizar_espacios(valor: Any) -> str:
    return " ".join(normalizar_texto(valor).split())

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

def normalizar_categoria_operativa(valor: Any) -> str:
    txt = str(valor or "").strip().upper()
    txt = txt.replace("ª", "").replace("º", "")
    if txt in {"I", "1", "PRIMERA", "PRIMERA CATEGORIA", "CAT I", "CATEGORIA I"}:
        return "PRIMERA"
    if txt in {"II", "2", "SEGUNDA", "SEGUNDA CATEGORIA", "CAT II", "CATEGORIA II"}:
        return "SEGUNDA"
    if txt in {"NORMAL", "", "MIXTO"}:
        return "MIXTO"
    return txt

def normalizar_codigo_confeccion(valor: Any) -> str:
    txt = normalizar_texto(valor)
    if not txt:
        return ""
    try:
        num = float(txt.replace(",", "."))
        if num.is_integer():
            return str(int(num))
    except Exception:
        pass
    return txt

def detectar_perfil_confeccion_desde_grupo(grupo_confeccion: Any) -> str:
    grupo = normalizar_texto(grupo_confeccion).upper()
    if any(t in grupo for t in ("MALLA", "MALLAS", "RED", "BOLSA")):
        return "MALLA"
    if any(t in grupo for t in ("ENCAJADO", "ENCAJAR", "GRANEL", "ALVEOLO", "ALVÉOLO", "ALVEOLADO", "CAJA", "CAJAS")):
        return "EXIGENTE"
    return "DESCONOCIDO"

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
    def cargar_mconfecciones(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        try:
            rows = conn.execute(
                'SELECT "CODIGO","NOMBRE","GRUPO","MERMA","NETO","ARTICULO","CODCAJA","DESCRIPCORTA" FROM "MConfecciones"'
            ).fetchall()
        except Exception:
            return out
        for row in rows:
            item = dict(row)
            key = normalizar_codigo_confeccion(item.get("CODIGO"))
            if key:
                out[key] = item
        return out

    @staticmethod
    def enriquecer_pedido_con_confeccion(pedido: dict[str, Any], mconfecciones: dict[str, dict[str, Any]]) -> dict[str, Any]:
        codigo_raw = (
            pedido.get("Confeccion")
            or pedido.get("confeccion")
            or pedido.get("IdConfeccion")
            or pedido.get("id_confeccion")
            or ""
        )
        id_confeccion = normalizar_codigo_confeccion(codigo_raw)
        mconf = mconfecciones.get(id_confeccion)

        nombre_confeccion = normalizar_texto(pedido.get("Confección") or pedido.get("nombre_confeccion") or codigo_raw)
        grupo_confeccion = normalizar_texto(
            pedido.get("grupo_confeccion")
            or pedido.get("GrupoConfeccion")
            or pedido.get("GRUPO")
            or pedido.get("grupo")
        )
        perfil_confeccion = normalizar_texto(pedido.get("perfil_confeccion"))
        if mconf:
            nombre_confeccion = normalizar_texto(mconf.get("NOMBRE")) or nombre_confeccion
            grupo_confeccion = normalizar_texto(mconf.get("GRUPO")) or grupo_confeccion
            pedido["merma_confeccion"] = mconf.get("MERMA")
            pedido["neto_confeccion"] = mconf.get("NETO")
            pedido["articulo_confeccion"] = normalizar_texto(mconf.get("ARTICULO"))
            pedido["codcaja_confeccion"] = normalizar_texto(mconf.get("CODCAJA"))
            pedido["descripcion_corta_confeccion"] = normalizar_texto(mconf.get("DESCRIPCORTA"))
        else:
            pedido.setdefault("merma_confeccion", None)
            pedido.setdefault("neto_confeccion", None)
            pedido.setdefault("articulo_confeccion", "")
            pedido.setdefault("codcaja_confeccion", "")
            pedido.setdefault("descripcion_corta_confeccion", "")
            if id_confeccion:
                logger.debug("Confección %s no encontrada en MConfecciones para pedido pendiente.", id_confeccion)
        if not grupo_confeccion:
            grupo_confeccion = "DESCONOCIDO"
        if not perfil_confeccion:
            perfil_confeccion = detectar_perfil_confeccion_desde_grupo(grupo_confeccion)
        if perfil_confeccion == "DESCONOCIDO":
            texto_fallback = " ".join(
                normalizar_texto(pedido.get(c))
                for c in ("Confeccion", "Confección", "nombre_confeccion", "descripcion_corta_confeccion", "articulo_confeccion", "producto", "descripcion")
            ).upper()
            if any(t in texto_fallback for t in ("MALLA", "MALLAS", "RED", "BOLSA")):
                perfil_confeccion = "MALLA"
            elif any(t in texto_fallback for t in ("ENCAJADO", "CAJA", "CAJAS", "GRANEL", "ALVEOLO", "ALVÉOLO", "ALVEOLADO")):
                perfil_confeccion = "EXIGENTE"
        if not perfil_confeccion:
            perfil_confeccion = "DESCONOCIDO"

        pedido["id_confeccion"] = id_confeccion
        pedido["nombre_confeccion"] = nombre_confeccion or id_confeccion
        pedido["grupo_confeccion"] = grupo_confeccion
        pedido["perfil_confeccion"] = perfil_confeccion
        pedido["Grupo confección"] = grupo_confeccion
        pedido["Perfil confección"] = perfil_confeccion
        return pedido

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

        if "-" in text:
            resultado: set[str] = set()
            for bloque in re.split(r"\s*-\s*", text):
                bloque = bloque.strip()
                if not bloque:
                    continue
                resultado.update(PlanningRepository.normalizar_calibre_a_set(bloque, calibre_map=calibre_map))
            if resultado:
                logger.info("CALIBRE normalizado compuesto original=%s set=%s", calibre_texto, sorted(resultado))
                return resultado

        if "/" in text:
            nums = [n for n in re.split(r"\s*/\s*", text) if re.fullmatch(r"\d+", n)]
            if len(nums) >= 3:
                return set(nums)
            if len(nums) == 2:
                a, b = nums
                if len(b) >= 2 and int(b) >= 10:
                    return {a}
                return {a, b}
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
            "permitir_solape_parcial": True,
            "usar_factor_calibre_agrupado": True,
            "usar_stock_completo_en_calibre_admitido": False,
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

    @staticmethod
    def calcular_factor_cobertura_calibre(
        calibre_pedido: Any,
        calibre_stock: Any,
        calibre_map: dict[str, str] | None = None,
        usar_stock_completo_en_calibre_admitido: bool = False,
    ) -> tuple[float, str, list[str]]:
        pedido_set = PlanningRepository.normalizar_calibre_a_set(calibre_pedido, calibre_map)
        stock_set = PlanningRepository.normalizar_calibre_a_set(calibre_stock, calibre_map)
        if not pedido_set or not stock_set:
            return 0.0, "SIN_COBERTURA", []
        coincidentes = sorted(pedido_set.intersection(stock_set), key=lambda x: int(x) if x.isdigit() else 9999)
        if not coincidentes:
            return 0.0, "SIN_COBERTURA", []
        if pedido_set == stock_set:
            return 1.0, "EXACTA", coincidentes
        if stock_set.issubset(pedido_set):
            if usar_stock_completo_en_calibre_admitido:
                return 1.0, "CALIBRE_ADMITIDO", coincidentes
            factor = len(coincidentes) / max(len(stock_set), 1)
            return factor, "CALIBRE_ADMITIDO", coincidentes
        if pedido_set.issubset(stock_set):
            factor = len(coincidentes) / max(len(stock_set), 1)
            return factor, "AGRUPADA_PARCIAL", coincidentes
        factor = len(coincidentes) / max(len(stock_set), 1)
        return factor, "SOLAPE_PARCIAL", coincidentes

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

    def _categoria_compatible(self, categoria_pedido: Any, categoria_stock: Any, policy_cfg: dict[str, bool]) -> tuple[bool, str]:
        pedido_norm = normalizar_categoria_operativa(categoria_pedido)
        stock_norm = normalizar_categoria_operativa(categoria_stock)
        if pedido_norm == "MIXTO":
            return True, ""
        if pedido_norm == "PRIMERA":
            if stock_norm == "PRIMERA":
                return True, ""
            if stock_norm == "SEGUNDA" and policy_cfg["permitir_categoria_inferior"]:
                return True, "Categoría inferior"
            return False, "categoría incompatible"
        if pedido_norm == "SEGUNDA":
            if stock_norm in {"SEGUNDA", "PRIMERA"}:
                if stock_norm == "PRIMERA" and policy_cfg["permitir_categoria_superior"]:
                    return True, "Categoría superior"
                if stock_norm == "PRIMERA" and not policy_cfg["permitir_categoria_superior"]:
                    return True, ""
                return True, ""
            return False, "categoría incompatible"
        return (pedido_norm == stock_norm), ("categoría incompatible" if pedido_norm != stock_norm else "")

    def _calcular_stock_compatible_industrial(
        self,
        industrial_stock_map: dict[tuple, float],
        cultivo: Any,
        campana: Any,
        grupo: Any,
        variedad: Any,
        calibre: Any,
        categoria: Any,
        policy_cfg: dict[str, bool],
        calibre_map: dict[str, str],
    ) -> dict[str, Any]:
        kg_exacta = 0.0
        kg_agrupada = 0.0
        kg_solape = 0.0
        variedades_stock: set[str] = set()
        calibres_coincidentes: set[str] = set()
        flex_aplicada: set[str] = set()

        for ind_key, ind_kg in industrial_stock_map.items():
            ind_cultivo, ind_campana, ind_grupo, ind_variedad, ind_calibre, ind_categoria = ind_key
            mismo_cultivo = str(ind_cultivo).strip().upper() == str(cultivo).strip().upper()
            if not mismo_cultivo:
                continue
            misma_campana = str(ind_campana).strip() == str(campana).strip()
            if not misma_campana:
                continue
            mismo_grupo = str(ind_grupo).strip().upper() == str(grupo).strip().upper()
            grupo_ok = mismo_grupo or policy_cfg["permitir_grupo_varietal_alternativo"]
            if not grupo_ok:
                logger.info(
                    "MATCH DESCARTA motivo=%s pedido_calibre=%s stock_calibre=%s pedido_cat=%s stock_cat=%s",
                    "grupo distinto", calibre, ind_calibre, categoria, ind_categoria
                )
                continue
            if (not policy_cfg["permitir_variedad_alternativa"]) and str(ind_variedad).strip().upper() != str(variedad).strip().upper():
                logger.info(
                    "MATCH DESCARTA motivo=%s pedido_calibre=%s stock_calibre=%s pedido_cat=%s stock_cat=%s",
                    "variedad distinta", calibre, ind_calibre, categoria, ind_categoria
                )
                continue
            categoria_ok, flex_cat = self._categoria_compatible(categoria, ind_categoria, policy_cfg)
            if not categoria_ok:
                logger.info(
                    "MATCH DESCARTA motivo=%s pedido_calibre=%s stock_calibre=%s pedido_cat=%s stock_cat=%s",
                    "categoria distinta", calibre, ind_calibre, categoria, ind_categoria
                )
                continue

            cmp_result = self.comparar_calibres_para_cobertura(calibre, ind_calibre, calibre_map=calibre_map)
            if cmp_result["tipo"] == "SIN_COBERTURA":
                logger.info(
                    "MATCH DESCARTA motivo=%s pedido_calibre=%s stock_calibre=%s pedido_cat=%s stock_cat=%s",
                    "calibre sin cobertura", calibre, ind_calibre, categoria, ind_categoria
                )
                continue
            if cmp_result["tipo"] == "CALIBRE_ADMITIDO" and not policy_cfg["permitir_calibre_admitido"]:
                continue
            if cmp_result["tipo"] == "AGRUPADA" and not policy_cfg["permitir_calibre_agrupado"]:
                continue
            if cmp_result["tipo"] == "SOLAPE_PARCIAL" and not policy_cfg["permitir_solape_parcial"]:
                continue
            factor_calibre, tipo_factor, coincidentes = self.calcular_factor_cobertura_calibre(
                calibre,
                ind_calibre,
                calibre_map=calibre_map,
                usar_stock_completo_en_calibre_admitido=policy_cfg.get("usar_stock_completo_en_calibre_admitido", False),
            )
            if factor_calibre <= 0:
                continue
            kg_util = ind_kg * (factor_calibre if policy_cfg.get("usar_factor_calibre_agrupado", True) else 1.0)

            logger.info(
                "MATCH CALIBRE pedido=%s stock=%s pedido_set=%s stock_set=%s coincidentes=%s tipo=%s factor=%s kg_stock=%s kg_util=%s",
                calibre,
                ind_calibre,
                sorted(cmp_result.get("pedido_set") or []),
                sorted(cmp_result.get("stock_set") or []),
                coincidentes,
                tipo_factor,
                factor_calibre,
                ind_kg,
                round(kg_util, 2),
            )
            if flex_cat:
                flex_aplicada.add(flex_cat)
            variedades_stock.add(str(ind_variedad or "").strip())
            calibres_coincidentes.update(coincidentes or [])
            if cmp_result["tipo"] == "EXACTA":
                kg_exacta += kg_util
            elif cmp_result["tipo"] in {"AGRUPADA", "CALIBRE_ADMITIDO"}:
                kg_agrupada += kg_util
            elif cmp_result["tipo"] == "SOLAPE_PARCIAL":
                kg_solape += kg_util

        kg_exacta = round(kg_exacta, 2)
        kg_agrupada = round(kg_agrupada, 2)
        kg_solape = round(kg_solape, 2)
        coincidencia = "Sin cobertura"
        if kg_exacta > 0:
            coincidencia = "Exacta"
        elif kg_agrupada > 0:
            coincidencia = "Cobertura por calibre admitido"
        elif kg_solape > 0:
            coincidencia = "Cobertura por solape parcial"
        return {
            "kg_exacta": kg_exacta,
            "kg_agrupada": kg_agrupada,
            "kg_solape": kg_solape,
            "kg_total": round(kg_exacta + kg_agrupada + kg_solape, 2),
            "variedades_stock": variedades_stock,
            "coincidencia": coincidencia,
            "calibres_coincidentes": ",".join(sorted(calibres_coincidentes, key=lambda x: int(x) if str(x).isdigit() else 9999)),
            "flex_aplicada": sorted(flex_aplicada),
        }

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


    def build_aprovechamiento_stock_campo(self, stock_campo_rows: list[dict[str, Any]], filters: dict) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        real_rows, _ = self._get_pesosfres_campo_disponibilidad_real(stock_campo_rows, filters)
        by_boleta: dict[str, list[dict[str, Any]]] = {}
        for row in real_rows:
            boleta = str(row.get("Boleta", "") or "").strip()
            by_boleta.setdefault(boleta, []).append(row)

        resumen: dict[str, dict[str, Any]] = {}
        detalle: dict[str, list[dict[str, Any]]] = {}
        for partida in stock_campo_rows:
            boleta = str(partida.get("Boleta", "") or "").strip()
            rows = by_boleta.get(boleta, [])
            if rows:
                estado = "Real PesosFres"
                n_cal = len({str(r.get("Calibre", "")) for r in rows if str(r.get("Calibre", "")).strip()})
                kg_est = round(sum(float(r.get("Kg disponibles", 0) or 0) for r in rows), 2)
            else:
                estado = "Sin aprovechamiento"
                n_cal = 0
                kg_est = 0.0
            logger.info("APROVECHAMIENTO partida boleta=%s estado=%s calibres=%s kg_estimados=%s", boleta, estado, n_cal, kg_est)
            resumen[boleta] = {"Estado aprovechamiento": estado, "Nº calibres aprovechamiento": n_cal, "Kg estimados calculados": kg_est}
            detalle[boleta] = rows
        return resumen, detalle

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
            mconfecciones = self.cargar_mconfecciones(conn)
            rows = [self.enriquecer_pedido_con_confeccion(row, mconfecciones) for row in rows]

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

        resumen_aprov, _ = self.build_aprovechamiento_stock_campo(data, filters)
        for row in data:
            boleta = str(row.get("Boleta", "") or "").strip()
            row.update(resumen_aprov.get(boleta, {"Estado aprovechamiento": "Sin aprovechamiento", "Nº calibres aprovechamiento": 0, "Kg estimados calculados": 0.0}))

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
            """
            logger.info("get_pedidos_pendientes: después de pedidos_filtrados (query construida)")
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
            mconfecciones = self.cargar_mconfecciones(conn)
            rows = [
                self.enriquecer_pedido_con_confeccion(r, mconfecciones)
                for r in rows
            ]
            logger.info(
                "Pedidos pendientes enriquecidos con MConfecciones: %s filas, con grupo: %s",
                len(rows),
                sum(
                    1
                    for r in rows
                    if str(r.get("Grupo confección", "")).strip()
                    and str(r.get("Grupo confección", "")).strip() != "DESCONOCIDO"
                ),
            )
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
        mconfecciones: dict[str, dict[str, Any]] = {}
        try:
            with sqlite3.connect(self._db_path(DB_PEDIDOS).as_posix()) as conn_ped:
                conn_ped.row_factory = sqlite3.Row
                mconfecciones = self.cargar_mconfecciones(conn_ped)
        except Exception:
            logger.exception("No se pudo cargar MConfecciones para enriquecer balance.")

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
            id_confeccion = normalizar_codigo_confeccion(row.get("IdConfeccion", row.get("Confeccion", "")))
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
            mconf = mconfecciones.get(normalizar_codigo_confeccion(id_confeccion))
            if mconf:
                grupo_confeccion = normalizar_texto(mconf.get("GRUPO"))
                nombre_confeccion = normalizar_texto(mconf.get("NOMBRE")) or confe
                merma_confeccion = mconf.get("MERMA")
                neto_confeccion = mconf.get("NETO")
                articulo_confeccion = normalizar_texto(mconf.get("ARTICULO"))
                codcaja_confeccion = normalizar_texto(mconf.get("CODCAJA"))
                descripcion_corta_confeccion = normalizar_texto(mconf.get("DESCRIPCORTA"))
            else:
                grupo_confeccion = "DESCONOCIDO"
                nombre_confeccion = confe or str(id_confeccion)
                merma_confeccion = None
                neto_confeccion = None
                articulo_confeccion = ""
                codcaja_confeccion = ""
                descripcion_corta_confeccion = ""
                if id_confeccion:
                    logger.warning("Confección %s no encontrada en MConfecciones; usando fallback.", id_confeccion)
            perfil_confeccion = detectar_perfil_confeccion_desde_grupo(grupo_confeccion)
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

            kg_industrial_stock = 0.0
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
            flex: list[str] = []
            compat: dict[str, Any] = {}
            if necesita_cobertura:
                logger.info(
                    "MATCH pedido cultivo=%s campana=%s grupo=%s variedad=%s calibre=%s categoria=%s faltante=%s",
                    cultivo, campana, grupo, variedad, calibre, categoria, abs(diff)
                )
                compat = self._calcular_stock_compatible_industrial(
                    industrial_stock_map=industrial_stock_map,
                    cultivo=cultivo,
                    campana=campana,
                    grupo=grupo,
                    variedad=variedad,
                    calibre=calibre,
                    categoria=categoria,
                    policy_cfg=policy_cfg,
                    calibre_map=calibre_map,
                )
                kg_industrial_stock = compat["kg_total"]
                kg_cobertura_exacta = compat["kg_exacta"]
                kg_cobertura_agrupada = compat["kg_agrupada"]
                kg_cobertura_solape_parcial = compat["kg_solape"]
                coincidencia = compat["coincidencia"]
                variedades_stock_industrial = compat["variedades_stock"]
                flex.extend(compat.get("flex_aplicada", []))

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
            kg_base_total_estimada = round(kg_industrial_stock + kg_entrada_estimada, 2)

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
                "id_confeccion": normalizar_codigo_confeccion(id_confeccion),
                "nombre_confeccion": nombre_confeccion,
                "grupo_confeccion": grupo_confeccion,
                "merma_confeccion": merma_confeccion,
                "neto_confeccion": neto_confeccion,
                "articulo_confeccion": articulo_confeccion,
                "codcaja_confeccion": codcaja_confeccion,
                "descripcion_corta_confeccion": descripcion_corta_confeccion,
                "perfil_confeccion": perfil_confeccion,
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
                "Calibres coincidentes": compat["calibres_coincidentes"] if necesita_cobertura else "",
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


    def get_candidatos_compatibles_para_pedido(self, filters: dict, pedido: dict, policy_cfg: dict | None = None) -> list[dict]:
        """Fuente única de candidatos compatibles para Balance y Simulación."""
        pedido_normalizado = dict(pedido)
        cultivo = str(pedido_normalizado.get("Cultivo", pedido_normalizado.get("cultivo", "")) or "").strip()
        campana = str(pedido_normalizado.get("Campaña", pedido_normalizado.get("Campana", pedido_normalizado.get("campana", ""))) or "").strip()
        if not cultivo:
            cultivos = filters.get("cultivo", []) if isinstance(filters, dict) else []
            cultivos_validos = [str(c or "").strip() for c in cultivos if str(c or "").strip() and str(c or "").strip().upper() != "TODOS"]
            if len(cultivos_validos) == 1:
                cultivo = cultivos_validos[0]
                pedido_normalizado.setdefault("Cultivo", cultivo)
                pedido_normalizado.setdefault("cultivo", cultivo)
        if not campana:
            campanas = filters.get("campana", []) if isinstance(filters, dict) else []
            campanas_validas = [str(c or "").strip() for c in campanas if str(c or "").strip() and str(c or "").strip().upper() != "TODOS"]
            if len(campanas_validas) == 1:
                campana = campanas_validas[0]
                pedido_normalizado.setdefault("Campaña", campana)
                pedido_normalizado.setdefault("Campana", campana)
                pedido_normalizado.setdefault("campana", campana)
        variedad = str(pedido_normalizado.get("Variedad", pedido_normalizado.get("Variedad Coop", "")) or "").strip()
        grupo_varietal = str(pedido_normalizado.get("Grupo varietal", pedido_normalizado.get("grupo_varietal", "")) or "").strip()
        calibre = str(pedido_normalizado.get("Calibre", pedido_normalizado.get("calibre", "")) or "").strip()
        categoria = str(pedido_normalizado.get("Categoría", pedido_normalizado.get("Categoria", pedido_normalizado.get("categoria", ""))) or "").strip()
        logger.info(
            "Candidatos pedido filtro cultivo=%s campana=%s variedad=%s grupo=%s calibre=%s categoria=%s",
            cultivo,
            campana,
            variedad,
            grupo_varietal,
            calibre,
            categoria,
        )
        candidatos = self.get_balance_cobertura_detalle(filters, pedido_normalizado, policy=policy_cfg)
        out: list[dict] = []
        for row in candidatos:
            cand = dict(row)
            cand.setdefault("Grupo varietal stock", cand.get("Grupo varietal", ""))
            cand.setdefault("compatibilidad_calibre", cand.get("Coincidencia", cand.get("Flexibilidad aplicada", "")))
            cand.setdefault("compatibilidad_categoria", "COMPATIBLE")
            cand.setdefault("compatibilidad_varietal", "COMPATIBLE")
            cand.setdefault("coincidencia", cand.get("Flexibilidad aplicada", cand.get("Coincidencia", "")))
            kg_disp = float(cand.get("Kg disponibles", 0) or 0)
            cand.setdefault("kg_fisicos", kg_disp)
            cand.setdefault("kg_utiles_estimados", kg_disp)
            cand.setdefault("kg_primera_estimado", kg_disp)
            cand.setdefault("kg_segunda_estimado", 0.0)
            out.append(cand)
        return out

    def get_inventario_operativo_global(self, filters: dict, policy: dict | None = None) -> list[dict]:
        policy_cfg = self._merge_policy(policy)
        detalle_rows = self.get_stock_almacen_detalle_palets(filters)
        stock_campo_rows, _, _ = self.get_stock_campo(filters)

        pools: list[dict] = []
        for row in detalle_rows:
            confe = str(row.get("Confeccion", "") or "").strip()
            id_confeccion = str(row.get("IdConfeccion", "") or "").strip()
            is_ind = self._is_stock_industrial(row.get("Pedido"), confe, id_confeccion)
            is_sp = self._is_stock_sp_comercial(row.get("Pedido"), confe, id_confeccion)
            if not ((policy_cfg["usar_stock_industrial"] and is_ind) or (policy_cfg["usar_stock_comercial"] and is_sp)):
                continue
            kg_fisicos = float(row.get("Neto", 0) or 0)
            if kg_fisicos <= 0:
                continue
            origen = "ALMACEN_COMERCIAL" if is_sp else "ALMACEN_INDUSTRIAL"
            calibre = str(row.get("Calibre", "") or "").strip()
            categoria = str(row.get("Categoria", "") or "").strip()
            pools.append({
                "pool_id": f"{origen}|{row.get('Cultivo','')}|{row.get('Campana','')}|{row.get('GrupoVarietal','')}|{row.get('Variedad','')}|{calibre}|{categoria}|{id_confeccion}|{row.get('IdPalet','')}",
                "origen": origen,
                "tipo_stock": "COMERCIAL" if is_sp else "INDUSTRIAL",
                "variedad": str(row.get("Variedad", "") or "").strip(),
                "grupo_varietal": str(row.get("GrupoVarietal", "") or "").strip(),
                "calibre": calibre,
                "categoria": categoria,
                "kg_utiles_finales": round(kg_fisicos, 2),
                "kg_restante_simulado": round(kg_fisicos, 2),
                "destrio_pct": 0.0,
                "coef_primera": 1.0,
                "Origen": origen,
                "Cultivo": str(row.get("Cultivo", "") or "").strip(),
                "Campaña": str(row.get("Campana", "") or "").strip(),
                "Grupo varietal": str(row.get("GrupoVarietal", "") or "").strip(),
                "Variedad stock": str(row.get("Variedad", "") or "").strip(),
                "Calibre stock": calibre,
                "Categoría": categoria,
                "Marca stock": str(row.get("Marca", "") or "").strip(),
                "IdConfeccion stock": id_confeccion,
                "Confección stock": str(row.get("Confeccion", "") or "").strip(),
                "Kg disponibles": round(kg_fisicos, 2),
                "kg_fisicos": round(kg_fisicos, 2),
                "kg_utiles_estimados": round(kg_fisicos, 2),
                "kg_primera_estimado": round(kg_fisicos, 2),
                "kg_segunda_estimado": 0.0,
            })

        if policy_cfg["usar_entrada_estimada"]:
            campo_real_rows, _ = self._get_pesosfres_campo_disponibilidad_real(stock_campo_rows, filters)
            for row in campo_real_rows:
                kg_fisicos = float(row.get("Kg disponibles", 0) or 0)
                if kg_fisicos <= 0:
                    continue
                calibre = str(row.get("Calibre", "") or "").strip()
                categoria = str(row.get("Categoría", "") or "").strip()
                pools.append({
                    "pool_id": f"CAMPO_REAL|{row.get('Cultivo','')}|{row.get('Campaña','')}|{row.get('Grupo varietal','')}|{row.get('Variedad','')}|{calibre}|{categoria}|{row.get('Boleta','')}",
                    "origen": "CAMPO_REAL",
                    "tipo_stock": "CAMPO",
                    "variedad": str(row.get("Variedad", "") or "").strip(),
                    "grupo_varietal": str(row.get("Grupo varietal", "") or "").strip(),
                    "calibre": calibre,
                    "categoria": categoria,
                    "kg_utiles_finales": round(kg_fisicos, 2),
                    "kg_restante_simulado": round(kg_fisicos, 2),
                    "destrio_pct": 0.0,
                    "coef_primera": 1.0,
                    "Origen": "CAMPO_REAL",
                    "Cultivo": str(row.get("Cultivo", "") or "").strip(),
                    "Campaña": str(row.get("Campaña", "") or "").strip(),
                    "Grupo varietal": str(row.get("Grupo varietal", "") or "").strip(),
                    "Variedad stock": str(row.get("Variedad", "") or "").strip(),
                    "Calibre stock": calibre,
                    "Categoría": categoria,
                    "Marca stock": "",
                    "IdConfeccion stock": "",
                    "Confección stock": "",
                    "Kg disponibles": round(kg_fisicos, 2),
                    "kg_fisicos": round(kg_fisicos, 2),
                    "kg_utiles_estimados": round(kg_fisicos, 2),
                    "kg_primera_estimado": round(kg_fisicos, 2),
                    "kg_segunda_estimado": 0.0,
                })
        return pools

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
        if key in {"campana", "cultivo", "semana", "empresa", "var_coop", "grupo_varietal", "marca"}:
            return self.get_filter_options_contextual(key, {})
        return []

    def get_filter_options_contextual(self, key: str, filters: dict) -> list[str]:
        pedidos_path = self._db_path(DB_PEDIDOS)
        if not pedidos_path.exists():
            return []

        key_map = {
            "campana": 'p."Campaña"',
            "cultivo": 'p."Cultivo"',
            "semana": 'p."Semana"',
            "empresa": 'p."EMPRESA"',
            "var_coop": 'p."VarCoop"',
            "marca": 'p."Marca"',
            "grupo_varietal": "TRIM(COALESCE(mv.GRUPO,'') || ' ' || COALESCE(mv.SUBGRUPO,''))",
        }
        target_col = key_map.get(key)
        if not target_col:
            return []

        try:
            if key in {"campana", "cultivo"}:
                return self._get_campaign_crop_options_from_all_sources(key, filters)
            with sqlite3.connect(pedidos_path) as conn:
                conn.row_factory = sqlite3.Row
                db_eepl = self._db_path(DB_EEPPL)
                conn.execute(f"ATTACH DATABASE '{db_eepl.as_posix()}' AS dbeepl")
                query = f"""
                    SELECT DISTINCT {target_col} AS val
                    FROM "Pedidos" p
                    LEFT JOIN "MConfecciones" mc
                      ON CAST(mc."CODIGO" AS TEXT) = CAST(p."Confeccion" AS TEXT)
                    LEFT JOIN dbeepl."MVariedad" mv
                      ON UPPER(TRIM(mv."Variedad")) = UPPER(TRIM(p."VarCoop"))
                     AND UPPER(TRIM(mv."CULTIVO")) = UPPER(TRIM(p."Cultivo"))
                    WHERE COALESCE(p."Cancelado", 0) = 0
                """
                params: list[Any] = []
                for field, col in (("campana", 'p."Campaña"'), ("cultivo", 'p."Cultivo"'), ("semana", 'p."Semana"'), ("empresa", 'p."EMPRESA"'), ("var_coop", 'p."VarCoop"'), ("marca", 'p."Marca"')):
                    if field == key:
                        continue
                    values = self._normalize_filter_values(filters.get(field))
                    if values:
                        placeholders = ",".join(["UPPER(TRIM(?))"] * len(values))
                        query += f" AND UPPER(TRIM(COALESCE({col}, ''))) IN ({placeholders})"
                        params.extend(values)

                if key != "grupo_varietal":
                    gv_values = self._normalize_filter_values(filters.get("grupo_varietal"))
                    if gv_values:
                        placeholders = ",".join(["UPPER(TRIM(?))"] * len(gv_values))
                        query += " AND UPPER(TRIM(COALESCE(TRIM(COALESCE(mv.GRUPO,'') || ' ' || COALESCE(mv.SUBGRUPO,'')), ''))) IN (" + placeholders + ")"
                        params.extend(gv_values)

                pedidos_modo = str(filters.get("pedidos_modo") or "").strip()
                if pedidos_modo == "10_dias":
                    query += " AND date(p.\"FechaSalida\") BETWEEN date('now') AND date('now', '+10 days')"
                elif pedidos_modo == "todos_futuros":
                    query += " AND date(p.\"FechaSalida\") >= date('now')"
                elif pedidos_modo == "rango":
                    fecha_desde = str(filters.get("fecha_desde") or "").strip()
                    fecha_hasta = str(filters.get("fecha_hasta") or "").strip()
                    if fecha_desde:
                        query += " AND date(p.\"FechaSalida\") >= date(?)"
                        params.append(fecha_desde)
                    if fecha_hasta:
                        query += " AND date(p.\"FechaSalida\") <= date(?)"
                        params.append(fecha_hasta)

                rows = conn.execute(query, params).fetchall()

            values = [str(r["val"]).strip() for r in rows if str(r["val"] or "").strip()]
            if key == "semana":
                try:
                    values = sorted(set(values), key=lambda x: int(float(x)))
                except Exception:
                    values = sorted(set(values))
            else:
                values = sorted(set(values))
            logger.info("Opciones filtro %s con filtros %s: %s", key, filters, values)
            return values
        except Exception:
            logger.exception("Error obteniendo opciones contextuales de filtro %s con filtros %s", key, filters)
            raise

    def _get_campaign_crop_options_from_all_sources(self, key: str, filters: dict) -> list[str]:
        pedidos_path = self._db_path(DB_PEDIDOS)
        eepl_path = self._db_path(DB_EEPPL)
        if not pedidos_path.exists():
            return []

        def _clean(v: Any) -> str:
            return str(v or "").strip()

        def _norm(v: Any) -> str:
            return _clean(v).upper()

        selected_campanas = set(self._normalize_filter_values(filters.get("campana")))
        selected_cultivos = set(self._normalize_filter_values(filters.get("cultivo")))
        pairs: dict[tuple[str, str], set[str]] = {}

        def _add(campana: Any, cultivo: Any, origin: str) -> None:
            campana_txt = _clean(campana)
            cultivo_txt = _clean(cultivo)
            if not campana_txt or not cultivo_txt:
                return
            pair_key = (_norm(campana_txt), _norm(cultivo_txt))
            existing = pairs.get(pair_key)
            if not existing:
                pairs[pair_key] = {origin, f"val:{campana_txt}|{cultivo_txt}"}
            else:
                existing.add(origin)

        with sqlite3.connect(pedidos_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(f"ATTACH DATABASE '{eepl_path.as_posix()}' AS dbeepl")

            for row in conn.execute('SELECT DISTINCT p."Campaña" AS Campana, p."Cultivo" AS Cultivo FROM "Pedidos" p WHERE COALESCE(p."Cancelado", 0) = 0').fetchall():
                _add(row["Campana"], row["Cultivo"], "pedidos")

            rows_campo = self.fetch_stock_campo(filters)
            for row in rows_campo:
                _add(row.get("Campaña"), row.get("Cultivo"), "stock_campo")

            rows_loteado = self.fetch_stock_almacen(filters)
            for row in rows_loteado:
                _add(row.get("Campaña"), row.get("Cultivo"), "loteado")

            master_table = self._find_table(conn, ["CAMPAÑA", "CAMPA\u00d1A", "Campaña", "campaña"])
            if master_table:
                cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{master_table}")').fetchall()]
                camp_col = self._find_column(cols, ["CAMPAÑA", "CAMPA\u00d1A", "Campaña", "CAMPANA", "Campana"])
                cultivo_col = self._find_column(cols, ["CULTIVO", "Cultivo", "cultivo"])
                if camp_col and cultivo_col:
                    for row in conn.execute(f'SELECT DISTINCT "{camp_col}" AS Campana, "{cultivo_col}" AS Cultivo FROM "{master_table}"').fetchall():
                        _add(row["Campana"], row["Cultivo"], "maestro_campaña")

        filtered_pairs: list[tuple[str, str, set[str], str, str]] = []
        for (camp_norm, cult_norm), meta in pairs.items():
            val = next((m for m in meta if m.startswith("val:")), "val:|")
            raw_camp, raw_cult = val.removeprefix("val:").split("|", 1)
            if selected_campanas and camp_norm not in selected_campanas:
                continue
            if selected_cultivos and cult_norm not in selected_cultivos:
                continue
            filtered_pairs.append((camp_norm, cult_norm, {m for m in meta if not m.startswith("val:")}, raw_camp, raw_cult))

        for camp_norm, cult_norm, origins, raw_camp, raw_cult in sorted(filtered_pairs):
            logger.info(
                "Filtro inteligente campaña/cultivo origenes=%s campana=%s cultivo=%s",
                sorted(origins),
                raw_camp,
                raw_cult,
            )

        if key == "campana":
            values = sorted({raw_camp for _, _, _, raw_camp, _ in filtered_pairs}, key=lambda x: x.upper())
        else:
            values = sorted({raw_cult for _, _, _, _, raw_cult in filtered_pairs}, key=lambda x: x.upper())
        return values

    def cargar_catalogos_pedidos_previstos(self, cultivo: str) -> dict[str, Any]:
        cultivo_norm = str(cultivo or "").strip()
        out: dict[str, Any] = {"variedades": [], "variedad_meta": {}, "calibres": [], "categorias": [], "grupos_confeccion": [], "clientes": []}
        pedidos_path = self._db_path(DB_PEDIDOS)
        eepl_path = self._db_path(DB_EEPPL)
        if not pedidos_path.exists() or not eepl_path.exists():
            return out
        try:
            with sqlite3.connect(eepl_path) as conn_eepl:
                conn_eepl.row_factory = sqlite3.Row
                try:
                    rows_var = conn_eepl.execute(
                        """
                        SELECT DISTINCT "Variedad" AS variedad, "GRUPO" AS grupo, "SUBGRUPO" AS subgrupo, "PRODUCTO" AS producto
                        FROM "MVariedad"
                        WHERE UPPER(TRIM("CULTIVO")) = UPPER(TRIM(?))
                          AND "Variedad" IS NOT NULL
                          AND TRIM("Variedad") <> ''
                        ORDER BY "Variedad"
                        """,
                        (cultivo_norm,),
                    ).fetchall()
                    for r in rows_var:
                        variedad = str(r["variedad"] or "").strip()
                        if not variedad:
                            continue
                        out["variedades"].append(variedad)
                        grupo = normalizar_texto(r["grupo"])
                        subgrupo = normalizar_texto(r["subgrupo"])
                        producto = normalizar_texto(r["producto"])
                        grupo_varietal = normalizar_espacios(f"{grupo} {subgrupo}") if grupo else "DESCONOCIDO"
                        out["variedad_meta"][variedad] = {
                            "grupo": grupo,
                            "subgrupo": subgrupo,
                            "producto": producto,
                            "grupo_varietal": grupo_varietal,
                        }
                except Exception as exc:
                    logger.warning("No se pudieron cargar maestros de %s para cultivo=%s: %s", "variedades", cultivo_norm, exc)

            with sqlite3.connect(pedidos_path) as conn_ped:
                conn_ped.row_factory = sqlite3.Row
                try:
                    out["calibres"] = [
                        str(r["calibre"]).strip()
                        for r in conn_ped.execute(
                            """
                            SELECT DISTINCT "Calibre" AS calibre
                            FROM "MCalibre"
                            WHERE UPPER(TRIM("CULTIVO")) = UPPER(TRIM(?))
                              AND "Calibre" IS NOT NULL
                              AND TRIM("Calibre") <> ''
                            ORDER BY "Calibre"
                            """,
                            (cultivo_norm,),
                        ).fetchall()
                        if str(r["calibre"] or "").strip()
                    ]
                except Exception as exc:
                    logger.warning("No se pudieron cargar maestros de %s para cultivo=%s: %s", "calibres", cultivo_norm, exc)
                try:
                    out["categorias"] = [
                        str(r["categoria"]).strip()
                        for r in conn_ped.execute(
                            """
                            SELECT DISTINCT "UNIFICADO" AS categoria
                            FROM "MCategoria"
                            WHERE UPPER(TRIM("CULTIVO")) = UPPER(TRIM(?))
                              AND "UNIFICADO" IS NOT NULL
                              AND TRIM("UNIFICADO") <> ''
                            ORDER BY "UNIFICADO"
                            """,
                            (cultivo_norm,),
                        ).fetchall()
                        if str(r["categoria"] or "").strip()
                    ]
                except Exception as exc:
                    logger.warning("No se pudieron cargar maestros de %s para cultivo=%s: %s", "categorias", cultivo_norm, exc)
                try:
                    out["grupos_confeccion"] = [
                        str(r["grupo"]).strip()
                        for r in conn_ped.execute(
                            """
                            SELECT DISTINCT "GRUPO" AS grupo
                            FROM "MGrupoConfeccion"
                            WHERE "GRUPO" IS NOT NULL AND TRIM("GRUPO") <> ''
                            ORDER BY "GRUPO"
                            """
                        ).fetchall()
                        if str(r["grupo"] or "").strip()
                    ]
                except Exception as exc:
                    logger.warning("No se pudieron cargar maestros de %s para cultivo=%s: %s", "grupos_confeccion", cultivo_norm, exc)
                try:
                    out["clientes"] = [
                        str(r["cliente"]).strip()
                        for r in conn_ped.execute(
                            """
                            SELECT DISTINCT "Cliente" AS cliente
                            FROM [MCliente/Pais]
                            WHERE UPPER(TRIM("Activo")) = 'S'
                              AND "Cliente" IS NOT NULL
                              AND TRIM("Cliente") <> ''
                            ORDER BY "Cliente"
                            """
                        ).fetchall()
                        if str(r["cliente"] or "").strip()
                    ]
                except Exception as exc:
                    logger.warning("No se pudieron cargar maestros de %s para cultivo=%s: %s", "clientes", cultivo_norm, exc)
        except Exception:
            logger.exception("No se pudieron cargar catálogos de pedidos previstos para cultivo=%s", cultivo_norm)
        return out
