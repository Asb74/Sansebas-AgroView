import logging
import sqlite3
from pathlib import Path
from typing import Any

from config import DB_DIR, DB_PEDIDOS
from db.query_filters import build_pedidos_filters, build_pedidos_where, pedidos_base_where

logger = logging.getLogger(__name__)


class ComercialRepository:
    TABLE_PEDIDOS = "Pedidos"
    TABLE_RECLAMACIONES = "DReclamacion"

    def __init__(self, db_pedidos: str | None = None, db_fruta: str | None = None) -> None:
        self.db_pedidos = Path(db_pedidos or (Path(DB_DIR) / DB_PEDIDOS))
        self.db_fruta = Path(db_fruta or (Path(DB_DIR) / "DBfruta.sqlite"))
        self.db_calc = Path(DB_DIR) / "DBAgroViewCalc.sqlite"
        self._warned_missing_columns: set[str] = set()
        self._calc_price_col: str | None = None
        self._calc_cols: set[str] = set()
        self._has_forfait_equiv = False

    def load_empresas_dict(self) -> tuple[dict[str, str], str | None]:
        if not self.db_fruta.exists():
            return {}, f"No se encontró DBfruta.sqlite: {self.db_fruta}"

        try:
            conn = sqlite3.connect(str(self.db_fruta))
            conn.row_factory = sqlite3.Row
            with conn:
                cols = self._get_columns(conn, "Empresa")
                if "IdEmpresa" not in cols or "Nombre" not in cols:
                    return {}, "Tabla Empresa sin IdEmpresa o Nombre"

                rows = conn.execute('SELECT "IdEmpresa", "Nombre" FROM "Empresa"').fetchall()
                return {
                    str(r["IdEmpresa"]).strip(): str(r["Nombre"] or "").strip()
                    for r in rows
                }, None
        except Exception as exc:
            logger.exception("Error cargando empresas: %s", exc)
            return {}, "No se pudo cargar Empresa desde DBfruta.sqlite"

    def get_resumen(self, filters: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        with self._connect_pedidos() as conn:
            pedidos_cols = self._get_columns(conn, self.TABLE_PEDIDOS)
            recl_cols = self._get_columns(conn, self.TABLE_RECLAMACIONES)
            has_calc = self._attach_calcdb(conn)
            line_field = "Linea" if "Linea" in pedidos_cols else ("Line" if "Line" in pedidos_cols else None)

            where_sql, params, missing_filters = self._build_where(filters, pedidos_cols)
            warnings.extend(missing_filters)

            kpis = self._query_kpis(conn, where_sql, params, pedidos_cols, has_calc, line_field)
            grouped = {
                "clientes": self._query_grouped(conn, "Cliente", where_sql, params, pedidos_cols, has_calc, line_field),
                "variedad_coop": self._query_grouped(conn, "VarCoop", where_sql, params, pedidos_cols, has_calc, line_field),
                "pais": self._query_grouped(conn, "Pais", where_sql, params, pedidos_cols, has_calc, line_field),
                "semana": self._query_grouped(conn, "Semana", where_sql, params, pedidos_cols, has_calc, line_field),
                "empresa": self._query_grouped(conn, "EMPRESA", where_sql, params, pedidos_cols, has_calc, line_field),
            }

            recl_amount = self._query_reclamado_importe(conn, where_sql, params, pedidos_cols, recl_cols)
            if recl_amount is None:
                warnings.append("No se pudo calcular el importe reclamado.")
            else:
                kpis["importe_reclamado"] = recl_amount

        return {"kpis": kpis, "grouped": grouped, "warnings": warnings}

    def get_analisis_precios(self, filters: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        with self._connect_pedidos() as conn:
            pedidos_cols = self._get_columns(conn, self.TABLE_PEDIDOS)
            has_calc = self._attach_calcdb(conn)
            line_field = "Linea" if "Linea" in pedidos_cols else ("Line" if "Line" in pedidos_cols else None)

            where_sql, params, missing_filters = self._build_where(filters, pedidos_cols)
            warnings.extend(missing_filters)

            return {
                "kpis_precios": self._query_kpis_precios(conn, where_sql, params, pedidos_cols, has_calc, line_field),
                "evolucion_semanal": self._query_precios_por_semana(conn, where_sql, params, pedidos_cols, has_calc, line_field),
                "precios_por_variedad_calibre": self._query_precios_por_variedad_calibre(
                    conn, where_sql, params, pedidos_cols, has_calc, line_field
                ),
                "warnings": warnings,
            }

    def get_desviacion_clientes(self, filters: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        with self._connect_pedidos() as conn:
            cols = self._get_columns(conn, self.TABLE_PEDIDOS)
            recl_cols = self._get_columns(conn, self.TABLE_RECLAMACIONES)
            has_calc = self._attach_calcdb(conn)
            line_field = "Linea" if "Linea" in cols else ("Line" if "Line" in cols else None)
            where_sql, params, missing_filters = self._build_where(filters, cols)
            warnings.extend(missing_filters)
            result = self._query_desviacion_clientes(conn, where_sql, params, cols, recl_cols, has_calc, line_field)
            return {
                "rows": result,
                "grafica": result[:15],
                "warnings": warnings,
            }

    def get_analisis_clientes(self, filters: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        with self._connect_pedidos() as conn:
            pedidos_cols = self._get_columns(conn, self.TABLE_PEDIDOS)
            recl_cols = self._get_columns(conn, self.TABLE_RECLAMACIONES)
            has_calc = self._attach_calcdb(conn)
            line_field = "Linea" if "Linea" in pedidos_cols else ("Line" if "Line" in pedidos_cols else None)

            where_sql, params, missing_filters = self._build_where(filters, pedidos_cols)
            warnings.extend(missing_filters)
            cte_sql = self._clientes_base_cte(where_sql, pedidos_cols, has_calc, line_field)

            return {
                "kpis": self._query_clientes_kpis(conn, cte_sql, params, recl_cols),
                "ranking": self._query_clientes_ranking(conn, cte_sql, params, recl_cols),
                "evolucion": self._query_clientes_evolucion(conn, cte_sql, params),
                "grafica_clientes": self._query_clientes_top(conn, cte_sql, params),
                "warnings": warnings,
            }

    def get_filter_options(self, filters: dict[str, Any], target_filter: str) -> list[str]:
        field_map = {
            "campana": "Campaña",
            "cultivo": "Cultivo",
            "empresa": "EMPRESA",
            "semana": "Semana",
            "cliente": "Cliente",
            "pais": "Pais",
            "calibre": "Calibre",
            "categoria": "Categoria",
            "var_cliente": "VarCliente",
            "var_coop": "VarCoop",
            "marca": "Marca",
        }
        if target_filter not in field_map:
            return []
        target_col = field_map[target_filter]
        effective_filters = {k: v for k, v in filters.items() if k != target_filter}
        where_sql, params = build_pedidos_where(effective_filters, alias="p", include_base=True)
        order_sql = 'ORDER BY CAST(p."Semana" AS INTEGER) ASC'
        if target_filter == "semana":
            order_sql = (
                'ORDER BY CASE WHEN CAST(p."Semana" AS INTEGER) >= 36 '
                'THEN CAST(p."Semana" AS INTEGER) - 35 ELSE CAST(p."Semana" AS INTEGER) + 17 END ASC'
            )
        elif target_filter == "empresa":
            order_sql = f'ORDER BY CAST(p."{target_col}" AS INTEGER) ASC'
        else:
            order_sql = f'ORDER BY CAST(p."{target_col}" AS TEXT) ASC'

        query = f"""
            SELECT DISTINCT CAST(p."{target_col}" AS TEXT) AS value
            FROM "{self.TABLE_PEDIDOS}" p
            {where_sql}
              AND COALESCE(TRIM(CAST(p."{target_col}" AS TEXT)), '') <> ''
            {order_sql}
        """
        with self._connect_pedidos() as conn:
            rows = conn.execute(query, params).fetchall()
        return [str(r["value"]).strip() for r in rows if str(r["value"] or "").strip()]

    def get_analisis_reclamaciones(self, filters: dict[str, Any]) -> dict[str, Any]:
        warnings: list[str] = []
        with self._connect_pedidos() as conn:
            pedidos_cols = self._get_columns(conn, self.TABLE_PEDIDOS)
            recl_cols = self._get_columns(conn, self.TABLE_RECLAMACIONES)
            where_sql, params, missing_filters = self._build_where(filters, pedidos_cols)
            warnings.extend(missing_filters)

            if not recl_cols:
                warnings.append("Tabla DReclamacion no disponible.")
                return {
                    "resumen": {},
                    "detalle": [],
                    "por_causa": [],
                    "por_cliente": [],
                    "grafica": [],
                    "warnings": warnings,
                }

            base_cte = self._reclamaciones_base_cte(where_sql, pedidos_cols, recl_cols)
            por_causa = self._query_reclam_por_causa(conn, base_cte, params)
            grafica_causas = self._query_reclam_grafica(conn, base_cte, params)
            logger.info("Reclamaciones por_causa filas: %s", len(por_causa))
            logger.info("Reclamaciones grafica_causas filas: %s", len(grafica_causas))
            return {
                "resumen": self._query_reclam_resumen(conn, base_cte, params),
                "detalle": self._query_reclam_detalle(conn, base_cte, params),
                "por_causa": por_causa,
                "por_cliente": self._query_reclam_por_cliente(conn, base_cte, params),
                "grafica_causas": grafica_causas,
                "warnings": warnings,
            }

    def _attach_calcdb(self, conn: sqlite3.Connection) -> bool:
        self._calc_price_col = None
        self._calc_cols = set()
        self._has_forfait_equiv = False
        if not self.db_calc.exists():
            logger.warning("DBAgroViewCalc.sqlite no existe: %s", self.db_calc)
            return False
        try:
            conn.execute("ATTACH DATABASE ? AS calcdb", [str(self.db_calc)])
            logger.info("Tabla auxiliar encontrada: sí")
            row = conn.execute(
                "SELECT name FROM calcdb.sqlite_master WHERE type='table' AND name='PreciosOrientativosCalc'"
            ).fetchone()
            if not row:
                logger.warning("No existe calcdb.PreciosOrientativosCalc")
                return False
            cols_rows = conn.execute('PRAGMA calcdb.table_info("PreciosOrientativosCalc")').fetchall()
            self._calc_cols = {str(r["name"]) for r in cols_rows}
            logger.info("Columnas PreciosOrientativosCalc: %s", sorted(self._calc_cols))
            candidates = [
                "EurosOrientativosCalc",
                "EurosOrientativoCalc",
                "PrecioOrientativoCalc",
                "PrecioOCalc",
                "PrecioCalc",
            ]
            for candidate in candidates:
                if candidate in self._calc_cols:
                    self._calc_price_col = candidate
                    break
            if self._calc_price_col:
                logger.info("Columna usada para precio calculado: %s", self._calc_price_col)
            else:
                logger.warning("No existe columna de precio orientativo calculado en PreciosOrientativosCalc")
            forfait_row = conn.execute(
                "SELECT name FROM calcdb.sqlite_master WHERE type='table' AND name='EquivalenciaForfaitConfeccion'"
            ).fetchone()
            self._has_forfait_equiv = bool(forfait_row)
            related_row = conn.execute(
                "SELECT name FROM calcdb.sqlite_master WHERE type='table' AND name='ForfaitConfeccionRelacionada'"
            ).fetchone()
            self._has_related_forfait = bool(related_row)
            logger.info("Tabla equivalencias forfait encontrada: %s", "sí" if self._has_forfait_equiv else "no")
            return True
        except Exception as exc:
            logger.warning("No se pudo ATTACH de DB auxiliar: %s", exc)
            return False

    def _calc_join_sql(self, has_calc: bool, line_field: str | None) -> str:
        if not has_calc:
            return ""
        if line_field:
            return (
                'LEFT JOIN calcdb."PreciosOrientativosCalc" poc '
                f'ON poc."IdPedidoLora" = p."IdPedidoLora" AND COALESCE(poc."Linea", 0) = COALESCE(p."{line_field}", 0)'
            )
        return 'LEFT JOIN calcdb."PreciosOrientativosCalc" poc ON poc."IdPedidoLora" = p."IdPedidoLora" AND COALESCE(poc."Linea", 0) = 0'

    def _forfait_join_sql(self, has_calc: bool, cols: set[str]) -> str:
        if not has_calc:
            return ""
        required = {"Cultivo", "Campaña", "Confeccion"}
        if not required.issubset(cols):
            return ""
        if self._has_related_forfait:
            return (
                'LEFT JOIN calcdb."ForfaitConfeccionRelacionada" ef ON ef.Id = ('
                'SELECT fr.Id FROM calcdb."ForfaitConfeccionRelacionada" fr '
                'WHERE fr."Campaña" = CAST(p."Campaña" AS TEXT) '
                'AND fr."Cultivo" = CAST(p."Cultivo" AS TEXT) '
                'AND fr."IdConfeccion" = CAST(p."Confeccion" AS TEXT) '
                'LIMIT 1)'
            )
        if not self._has_forfait_equiv:
            return ""
        return (
            'LEFT JOIN calcdb."EquivalenciaForfaitConfeccion" ef '
            'ON ef."Cultivo" = CAST(p."Cultivo" AS TEXT) '
            'AND ef."Campaña" = CAST(p."Campaña" AS TEXT) '
            'AND ef."ConfeccionPedido" = CAST(p."Confeccion" AS TEXT) '
            'AND ef."Estado" = \'VALIDADO\''
        )

    @staticmethod
    def _num_expr(expr: str) -> str:
        return f'CAST(REPLACE(TRIM(COALESCE({expr}, "")), ",", ".") AS REAL)'

    @staticmethod
    def _real_price_line_exprs(kg_expr: str, euros_kg_expr: str) -> tuple[str, str, str]:
        valid = f"({euros_kg_expr} > 0 AND {kg_expr} > 0)"
        kg_total = f"CASE WHEN {kg_expr} > 0 THEN {kg_expr} ELSE 0 END"
        kg_valid = f"CASE WHEN {valid} THEN {kg_expr} ELSE 0 END"
        weighted = f"CASE WHEN {valid} THEN {kg_expr} * {euros_kg_expr} ELSE 0 END"
        return kg_total, kg_valid, weighted

    @staticmethod
    def _safe_div(numerator: str, denominator: str) -> str:
        return f"COALESCE(({numerator}) / NULLIF(({denominator}), 0), 0)"

    def _real_price_aggregate_selects(self, kg_expr: str, euros_kg_expr: str) -> str:
        kg_total_line, kg_valid_line, weighted_line = self._real_price_line_exprs(kg_expr, euros_kg_expr)
        kg_total = f"SUM({kg_total_line})"
        kg_valid = f"SUM({kg_valid_line})"
        weighted = f"SUM({weighted_line})"
        price = self._safe_div(weighted, kg_valid)
        return f"""
                COALESCE({weighted}, 0) AS importe_real,
                {price} AS precio_medio_real,
                COALESCE({kg_total}, 0) AS debug_kg_total,
                COALESCE({kg_valid}, 0) AS debug_kg_euroskg_valido,
                COALESCE({weighted}, 0) AS debug_suma_ponderada_euroskg,
                {price} AS debug_precio_real_calculado
        """

    def _get_calc_price_expr(self, has_calc: bool, calc_price_col: str | None) -> str:
        if has_calc and calc_price_col:
            return self._num_expr(f'poc."{calc_price_col}"')
        if has_calc and not calc_price_col:
            logger.warning(
                "No existe columna de precio orientativo calculado en PreciosOrientativosCalc"
            )
        return "0"

    def _orient_final_expr(self, has_calc: bool, calc_price_col: str | None) -> str:
        original = self._num_expr('p."EurosOrientativos"')
        calc = self._get_calc_price_expr(has_calc, calc_price_col)
        if has_calc:
            return (
                f"CASE WHEN {original} > 0 THEN {original} "
                f"WHEN {calc} > 0 THEN {calc} ELSE 0 END"
            )
        return f"CASE WHEN {original} > 0 THEN {original} ELSE 0 END"

    def _orient_origin_expr(self, has_calc: bool, calc_price_col: str | None) -> str:
        original = self._num_expr('p."EurosOrientativos"')
        calc = self._get_calc_price_expr(has_calc, calc_price_col)
        if has_calc:
            return (
                f"CASE WHEN {original} > 0 THEN 'ORIGINAL' "
                f"WHEN {calc} > 0 THEN 'ESTIMADO' ELSE 'SIN_DATOS' END"
            )
        return f"CASE WHEN {original} > 0 THEN 'ORIGINAL' ELSE 'SIN_DATOS' END"

    def _query_kpis(
        self,
        conn: sqlite3.Connection,
        where_sql: str,
        params: list[Any],
        cols: set[str],
        has_calc: bool,
        line_field: str | None,
    ) -> dict[str, float]:
        neto_cliente = self._real_expr("NetoCliente", cols, alias="p")
        neto_coop = self._real_expr("NetoCoop", cols, alias="p")
        cajas = self._real_expr("Cajas", cols, alias="p")
        euros_kg = self._real_expr("EurosKG", cols, alias="p")
        real_price_selects = self._real_price_aggregate_selects(neto_cliente, euros_kg)
        orient_final = self._orient_final_expr(has_calc, self._calc_price_col)
        orient_origin = self._orient_origin_expr(has_calc, self._calc_price_col)

        reclaimed_count = "0"
        if "Reclamado" in cols:
            reclaimed_count = 'SUM(CASE WHEN UPPER(COALESCE(p."Reclamado", "")) = \'S\' THEN 1 ELSE 0 END)'

        query = f"""
            SELECT
                SUM({neto_cliente}) AS kg_cliente,
                SUM({neto_coop}) AS kg_cooperativa,
                SUM({neto_cliente} - {neto_coop}) AS merma_kg,
                SUM({cajas}) AS cajas,
                {real_price_selects},
                SUM({neto_cliente} * ({orient_final})) AS importe_orientativo,
                COUNT(1) AS pedidos_count,
                {reclaimed_count} AS pedidos_reclamados,
                SUM(CASE WHEN ({orient_origin}) = 'ORIGINAL' THEN 1 ELSE 0 END) AS pedidos_orientativo_original,
                SUM(CASE WHEN ({orient_origin}) = 'ESTIMADO' THEN 1 ELSE 0 END) AS pedidos_orientativo_estimado,
                SUM(CASE WHEN ({orient_origin}) = 'SIN_DATOS' THEN 1 ELSE 0 END) AS pedidos_orientativo_sin_datos
            FROM "{self.TABLE_PEDIDOS}" p
            {self._calc_join_sql(has_calc, line_field)}
            {where_sql}
        """
        logger.debug("SQL KPIS: %s", query)
        logger.debug("PARAMS KPIS: %s", params)
        row = conn.execute(query, params).fetchone()
        if not row:
            return {}
        data = dict(row)
        total = float(data.get("pedidos_count") or 0)
        con_precio = float(data.get("pedidos_orientativo_original") or 0) + float(data.get("pedidos_orientativo_estimado") or 0)
        data["pct_cobertura_orientativo"] = (con_precio / total * 100.0) if total else 0.0
        return data

    def _query_grouped(
        self,
        conn: sqlite3.Connection,
        group_col: str,
        where_sql: str,
        params: list[Any],
        cols: set[str],
        has_calc: bool,
        line_field: str | None,
    ) -> list[dict[str, Any]]:
        if group_col not in cols:
            self._warn_missing_column(group_col)
            return []

        neto_cliente = self._real_expr("NetoCliente", cols, alias="p")
        neto_coop = self._real_expr("NetoCoop", cols, alias="p")
        cajas = self._real_expr("Cajas", cols, alias="p")
        euros_kg = self._real_expr("EurosKG", cols, alias="p")
        real_price_selects = self._real_price_aggregate_selects(neto_cliente, euros_kg)
        orient_final = self._orient_final_expr(has_calc, self._calc_price_col)
        orient_origin = self._orient_origin_expr(has_calc, self._calc_price_col)

        query = f"""
            SELECT
                COALESCE(CAST(p."{group_col}" AS TEXT), '(Sin dato)') AS grupo,
                SUM({neto_cliente}) AS kg_cliente,
                SUM({neto_coop}) AS kg_cooperativa,
                SUM({neto_cliente} - {neto_coop}) AS merma_kg,
                SUM({cajas}) AS cajas,
                {real_price_selects},
                SUM({neto_cliente} * ({orient_final})) AS importe_orientativo,
                COUNT(1) AS pedidos_count,
                SUM(CASE WHEN ({orient_origin}) = 'ORIGINAL' THEN 1 ELSE 0 END) AS originales,
                SUM(CASE WHEN ({orient_origin}) = 'ESTIMADO' THEN 1 ELSE 0 END) AS estimados,
                SUM(CASE WHEN ({orient_origin}) = 'SIN_DATOS' THEN 1 ELSE 0 END) AS sin_datos
            FROM "{self.TABLE_PEDIDOS}" p
            {self._calc_join_sql(has_calc, line_field)}
            {where_sql}
            GROUP BY p."{group_col}"
            ORDER BY kg_cliente DESC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _agri_week_order_expr(alias: str = "p") -> str:
        return (
            f'CASE WHEN CAST({alias}."Semana" AS INTEGER) >= 36 '
            f'THEN CAST({alias}."Semana" AS INTEGER) - 35 '
            f'ELSE CAST({alias}."Semana" AS INTEGER) + 17 END'
        )

    def _query_kpis_precios(
        self,
        conn: sqlite3.Connection,
        where_sql: str,
        params: list[Any],
        cols: set[str],
        has_calc: bool,
        line_field: str | None,
    ) -> dict[str, Any]:
        neto_cliente = self._real_expr("NetoCliente", cols, alias="p")
        euros_kg = self._real_expr("EurosKG", cols, alias="p")
        real_price_selects = self._real_price_aggregate_selects(neto_cliente, euros_kg)
        orient_final = self._orient_final_expr(has_calc, self._calc_price_col)
        orient_origin = self._orient_origin_expr(has_calc, self._calc_price_col)
        query = f"""
            SELECT
                SUM({neto_cliente}) AS kg_cliente,
                {real_price_selects},
                SUM({neto_cliente} * ({orient_final})) AS importe_orientativo,
                SUM(CASE WHEN ({orient_origin}) IN ('ORIGINAL', 'ESTIMADO') THEN {neto_cliente} ELSE 0 END) AS kg_con_precio_orientativo,
                SUM(CASE WHEN ({orient_origin}) = 'SIN_DATOS' THEN {neto_cliente} ELSE 0 END) AS kg_sin_precio_orientativo,
                COUNT(1) AS pedidos_count
            FROM "{self.TABLE_PEDIDOS}" p
            {self._calc_join_sql(has_calc, line_field)}
            {where_sql}
        """
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else {}

    def _query_precios_por_semana(
        self,
        conn: sqlite3.Connection,
        where_sql: str,
        params: list[Any],
        cols: set[str],
        has_calc: bool,
        line_field: str | None,
    ) -> list[dict[str, Any]]:
        if "Semana" not in cols:
            return []
        neto_cliente = self._real_expr("NetoCliente", cols, alias="p")
        euros_kg = self._real_expr("EurosKG", cols, alias="p")
        real_price_selects = self._real_price_aggregate_selects(neto_cliente, euros_kg)
        orient_final = self._orient_final_expr(has_calc, self._calc_price_col)
        orient_origin = self._orient_origin_expr(has_calc, self._calc_price_col)
        week_order = self._agri_week_order_expr(alias="p")
        query = f"""
            SELECT
                COALESCE(CAST(p."Semana" AS TEXT), '(Sin dato)') AS grupo,
                SUM({neto_cliente}) AS kg_cliente,
                {real_price_selects},
                SUM({neto_cliente} * ({orient_final})) AS importe_orientativo,
                COUNT(1) AS pedidos_count,
                SUM(CASE WHEN ({orient_origin}) = 'ORIGINAL' THEN 1 ELSE 0 END) AS originales,
                SUM(CASE WHEN ({orient_origin}) = 'ESTIMADO' THEN 1 ELSE 0 END) AS estimados,
                SUM(CASE WHEN ({orient_origin}) = 'SIN_DATOS' THEN 1 ELSE 0 END) AS sin_datos,
                {week_order} AS semana_orden
            FROM "{self.TABLE_PEDIDOS}" p
            {self._calc_join_sql(has_calc, line_field)}
            {where_sql}
            GROUP BY p."Semana"
            ORDER BY semana_orden ASC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _query_precios_por_variedad_calibre(
        self,
        conn: sqlite3.Connection,
        where_sql: str,
        params: list[Any],
        cols: set[str],
        has_calc: bool,
        line_field: str | None,
    ) -> list[dict[str, Any]]:
        if "VarCoop" not in cols or "Calibre" not in cols:
            return []
        neto_cliente = self._real_expr("NetoCliente", cols, alias="p")
        euros_kg = self._real_expr("EurosKG", cols, alias="p")
        real_price_selects = self._real_price_aggregate_selects(neto_cliente, euros_kg)
        orient_final = self._orient_final_expr(has_calc, self._calc_price_col)
        query = f"""
            SELECT
                COALESCE(CAST(p."VarCoop" AS TEXT), '(Sin dato)') AS var_coop,
                COALESCE(CAST(p."Calibre" AS TEXT), '(Sin dato)') AS calibre,
                SUM({neto_cliente}) AS kg_cliente,
                {real_price_selects},
                SUM({neto_cliente} * ({orient_final})) AS importe_orientativo,
                COUNT(1) AS pedidos_count
            FROM "{self.TABLE_PEDIDOS}" p
            {self._calc_join_sql(has_calc, line_field)}
            {where_sql}
            GROUP BY p."VarCoop", p."Calibre"
            ORDER BY kg_cliente DESC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _clientes_base_cte(
        self,
        where_sql: str,
        cols: set[str],
        has_calc: bool,
        line_field: str | None,
    ) -> str:
        neto_cliente = self._real_expr("NetoCliente", cols, alias="p")
        neto_coop = self._real_expr("NetoCoop", cols, alias="p")
        cajas = self._real_expr("Cajas", cols, alias="p")
        euros_kg = self._real_expr("EurosKG", cols, alias="p")
        kg_total_line, kg_valid_line, weighted_line = self._real_price_line_exprs(neto_cliente, euros_kg)
        orient_final = self._orient_final_expr(has_calc, self._calc_price_col)
        orient_origin = self._orient_origin_expr(has_calc, self._calc_price_col)
        semana_orden = self._agri_week_order_expr(alias="p")
        cliente_expr = 'COALESCE(CAST(p."Cliente" AS TEXT), "(Sin dato)")'
        pais_expr = 'COALESCE(CAST(p."Pais" AS TEXT), "(Sin dato)")'
        id_expr = 'COALESCE(CAST(p."IdPedidoLora" AS TEXT), "")'
        week_expr = 'COALESCE(CAST(p."Semana" AS INTEGER), 0)'
        reclamado_expr = 'CASE WHEN UPPER(COALESCE(p."Reclamado", "")) = \'S\' THEN 1 ELSE 0 END' if "Reclamado" in cols else "0"
        line_expr = f'COALESCE(CAST(p."{line_field}" AS INTEGER), 0)' if line_field else "0"
        return f"""
            WITH base AS (
                SELECT
                    {cliente_expr} AS cliente,
                    {pais_expr} AS pais,
                    {id_expr} AS id_pedido,
                    {line_expr} AS linea,
                    {week_expr} AS semana,
                    {semana_orden} AS semana_orden,
                    {neto_cliente} AS kg_cliente,
                    {neto_coop} AS kg_cooperativa,
                    {cajas} AS cajas,
                    {kg_total_line} AS kg_total_line,
                    {kg_valid_line} AS kg_euroskg_valido_line,
                    {weighted_line} AS suma_ponderada_euroskg_line,
                    {weighted_line} AS importe_real_line,
                    ({neto_cliente} * ({orient_final})) AS importe_orientativo_line,
                    ({orient_origin}) AS orient_origen,
                    {reclamado_expr} AS pedido_reclamado
                FROM "{self.TABLE_PEDIDOS}" p
                {self._calc_join_sql(has_calc, line_field)}
                {where_sql}
            )
        """

    @staticmethod
    def _reclamaciones_agg_cte(recl_cols: set[str]) -> tuple[str, str, str]:
        if not recl_cols or "IdPedido" not in recl_cols or "Importe" not in recl_cols:
            return "", "0", ""
        line_col = 'COALESCE(CAST("Linea" AS INTEGER), 0) AS linea,' if "Linea" in recl_cols else "0 AS linea,"
        return (
            f""",
            recl AS (
                SELECT
                    COALESCE(CAST("IdPedido" AS TEXT), "") AS id_pedido,
                    {line_col}
                    SUM(COALESCE(CAST("Importe" AS REAL), 0)) AS importe_reclamado
                FROM "DReclamacion"
                GROUP BY COALESCE(CAST("IdPedido" AS TEXT), ""), linea
            )
            """,
            "COALESCE(r.importe_reclamado, 0)",
            "LEFT JOIN recl r ON r.id_pedido = b.id_pedido AND r.linea = b.linea",
        )

    def _query_clientes_kpis(self, conn: sqlite3.Connection, cte_sql: str, params: list[Any], recl_cols: set[str]) -> dict[str, Any]:
        recl_cte, recl_expr, recl_join = self._reclamaciones_agg_cte(recl_cols)
        precio_real = self._safe_div("SUM(b.suma_ponderada_euroskg_line)", "SUM(b.kg_euroskg_valido_line)")
        query = f"""
            {cte_sql}
            {recl_cte}
            SELECT
                COUNT(DISTINCT b.cliente) AS clientes_count,
                SUM(b.kg_cliente) AS kg_cliente,
                SUM(b.cajas) AS cajas,
                SUM(b.importe_real_line) AS importe_real,
                {precio_real} AS precio_medio_real,
                SUM(b.kg_total_line) AS debug_kg_total,
                SUM(b.kg_euroskg_valido_line) AS debug_kg_euroskg_valido,
                SUM(b.suma_ponderada_euroskg_line) AS debug_suma_ponderada_euroskg,
                {precio_real} AS debug_precio_real_calculado,
                SUM(b.importe_orientativo_line) AS importe_orientativo,
                COUNT(1) AS pedidos_count,
                SUM(b.pedido_reclamado) AS pedidos_reclamados,
                SUM({recl_expr}) AS importe_reclamado
            FROM base b
            {recl_join}
        """
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else {}

    def _query_clientes_ranking(self, conn: sqlite3.Connection, cte_sql: str, params: list[Any], recl_cols: set[str]) -> list[dict[str, Any]]:
        recl_cte, recl_expr, recl_join = self._reclamaciones_agg_cte(recl_cols)
        precio_real = self._safe_div("SUM(b.suma_ponderada_euroskg_line)", "SUM(b.kg_euroskg_valido_line)")
        query = f"""
            {cte_sql}
            {recl_cte}
            , pais_rank AS (
                SELECT
                    cliente,
                    pais,
                    COUNT(1) AS cnt,
                    ROW_NUMBER() OVER (PARTITION BY cliente ORDER BY COUNT(1) DESC, pais ASC) AS rn
                FROM base
                GROUP BY cliente, pais
            )
            SELECT
                b.cliente AS grupo,
                COALESCE(pr.pais, '(Sin dato)') AS pais_principal,
                SUM(b.kg_cliente) AS kg_cliente,
                SUM(b.kg_cooperativa) AS kg_cooperativa,
                SUM(b.kg_cliente - b.kg_cooperativa) AS merma_kg,
                SUM(b.cajas) AS cajas,
                SUM(b.importe_real_line) AS importe_real,
                {precio_real} AS precio_medio_real,
                SUM(b.kg_total_line) AS debug_kg_total,
                SUM(b.kg_euroskg_valido_line) AS debug_kg_euroskg_valido,
                SUM(b.suma_ponderada_euroskg_line) AS debug_suma_ponderada_euroskg,
                {precio_real} AS debug_precio_real_calculado,
                SUM(b.importe_orientativo_line) AS importe_orientativo,
                COUNT(1) AS pedidos_count,
                SUM(b.pedido_reclamado) AS reclamaciones,
                SUM({recl_expr}) AS importe_reclamado,
                SUM(CASE WHEN b.orient_origen = 'ORIGINAL' THEN 1 ELSE 0 END) AS originales,
                SUM(CASE WHEN b.orient_origen = 'ESTIMADO' THEN 1 ELSE 0 END) AS estimados,
                SUM(CASE WHEN b.orient_origen = 'SIN_DATOS' THEN 1 ELSE 0 END) AS sin_datos
            FROM base b
            LEFT JOIN pais_rank pr ON pr.cliente = b.cliente AND pr.rn = 1
            {recl_join}
            GROUP BY b.cliente, pr.pais
            ORDER BY importe_real DESC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _query_clientes_evolucion(self, conn: sqlite3.Connection, cte_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        precio_real = self._safe_div("SUM(b.suma_ponderada_euroskg_line)", "SUM(b.kg_euroskg_valido_line)")
        query = f"""
            {cte_sql}
            SELECT
                b.cliente,
                b.semana AS semana,
                b.semana_orden,
                SUM(b.kg_cliente) AS kg_cliente,
                SUM(b.importe_real_line) AS importe_real,
                {precio_real} AS precio_medio_real,
                SUM(b.kg_total_line) AS debug_kg_total,
                SUM(b.kg_euroskg_valido_line) AS debug_kg_euroskg_valido,
                SUM(b.suma_ponderada_euroskg_line) AS debug_suma_ponderada_euroskg,
                {precio_real} AS debug_precio_real_calculado,
                SUM(b.importe_orientativo_line) AS importe_orientativo,
                COUNT(1) AS pedidos_count
            FROM base b
            GROUP BY b.cliente, b.semana, b.semana_orden
            ORDER BY b.cliente ASC, b.semana_orden ASC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _query_clientes_top(self, conn: sqlite3.Connection, cte_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        query = f"""
            {cte_sql}
            SELECT
                b.cliente,
                SUM(b.kg_cliente) AS kg_cliente,
                SUM(b.importe_real_line) AS importe_real
            FROM base b
            GROUP BY b.cliente
            ORDER BY importe_real DESC
            LIMIT 15
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _reclamaciones_base_cte(self, where_sql: str, pedidos_cols: set[str], recl_cols: set[str]) -> str:
        line_field = "Linea" if "Linea" in pedidos_cols else ("Line" if "Line" in pedidos_cols else None)
        join_line = ""
        if line_field and "Linea" in recl_cols:
            join_line = f' AND COALESCE(CAST(dr."Linea" AS INTEGER), 0) = COALESCE(CAST(p."{line_field}" AS INTEGER), 0)'

        neto_cliente = self._real_expr("NetoCliente", pedidos_cols, alias="p")
        neto_coop = self._real_expr("NetoCoop", pedidos_cols, alias="p")
        cajas = self._real_expr("Cajas", pedidos_cols, alias="p")
        euros_kg = self._real_expr("EurosKG", pedidos_cols, alias="p")
        _, _, weighted_line = self._real_price_line_exprs(neto_cliente, euros_kg)

        return f"""
            WITH filtered AS (
                SELECT
                    p.*,
                    {weighted_line} AS importe_real_line
                FROM "{self.TABLE_PEDIDOS}" p
                {where_sql}
            ),
            recl_base AS (
                SELECT
                    COALESCE(CAST(p."IdPedidoLora" AS TEXT), "") AS id_pedido,
                    {"COALESCE(CAST(p.\"%s\" AS INTEGER), 0)" % line_field if line_field else "0"} AS linea,
                    COALESCE(CAST(p."FechaSalida" AS TEXT), "") AS fecha_salida,
                    COALESCE(CAST(p."Campaña" AS TEXT), "") AS campana,
                    COALESCE(CAST(p."Cultivo" AS TEXT), "") AS cultivo,
                    COALESCE(CAST(p."EMPRESA" AS TEXT), "") AS empresa,
                    COALESCE(CAST(p."Semana" AS TEXT), "") AS semana,
                    COALESCE(CAST(p."Cliente" AS TEXT), "") AS cliente,
                    COALESCE(CAST(p."Pais" AS TEXT), "") AS pais,
                    COALESCE(CAST(p."VarCoop" AS TEXT), "") AS var_coop,
                    COALESCE(CAST(p."VarCliente" AS TEXT), "") AS var_cliente,
                    COALESCE(CAST(p."Calibre" AS TEXT), "") AS calibre,
                    COALESCE(CAST(p."Categoria" AS TEXT), "") AS categoria,
                    COALESCE(CAST(p."Marca" AS TEXT), "") AS marca,
                    {neto_cliente} AS kg_cliente,
                    {neto_coop} AS kg_cooperativa,
                    {cajas} AS cajas,
                    p."importe_real_line" AS importe_real_line,
                    COALESCE(CAST(dr."Causa" AS TEXT), "") AS causa,
                    COALESCE(CAST(dr."Neto" AS REAL), 0) AS neto_reclamado,
                    COALESCE(CAST(dr."Importe" AS REAL), 0) AS importe_reclamado,
                    COALESCE(CAST(dr."Fecha" AS TEXT), "") AS fecha_reclamacion,
                    COALESCE(CAST(dr."Medida" AS TEXT), "") AS medida,
                    COALESCE(CAST(dr."Observaciones" AS TEXT), "") AS observaciones,
                    CASE WHEN dr."IdPedido" IS NOT NULL THEN 1 ELSE 0 END AS tiene_registro_reclamacion,
                    CASE WHEN UPPER(COALESCE(p."Reclamado", "")) = 'S' THEN 1 ELSE 0 END AS marcado_reclamado
                FROM filtered p
                LEFT JOIN "{self.TABLE_RECLAMACIONES}" dr
                  ON COALESCE(CAST(dr."IdPedido" AS TEXT), "") = COALESCE(CAST(p."IdPedidoLora" AS TEXT), "")
                  {join_line}
            ),
            recl_filtered AS (
                SELECT *
                FROM recl_base
                WHERE marcado_reclamado = 1 OR tiene_registro_reclamacion = 1
            ),
            totals AS (
                SELECT
                    COUNT(1) AS total_pedidos_filtrados,
                    COALESCE(SUM(importe_real_line), 0) AS total_importe_real_filtrado
                FROM filtered
            )
        """

    def _query_reclam_resumen(self, conn: sqlite3.Connection, cte_sql: str, params: list[Any]) -> dict[str, Any]:
        query = f"""
            {cte_sql}
            , top_cliente AS (
                SELECT cliente, SUM(importe_reclamado) AS total_imp
                FROM recl_filtered
                GROUP BY cliente
                ORDER BY total_imp DESC
                LIMIT 1
            ),
            top_causa AS (
                SELECT causa, SUM(importe_reclamado) AS total_imp
                FROM recl_filtered
                GROUP BY causa
                ORDER BY total_imp DESC
                LIMIT 1
            )
            SELECT
                COUNT(DISTINCT id_pedido) AS pedidos_reclamados,
                COUNT(1) AS lineas_reclamadas,
                COALESCE(SUM(importe_reclamado), 0) AS importe_reclamado,
                COALESCE(SUM(neto_reclamado), 0) AS kg_reclamados,
                COALESCE((SELECT total_pedidos_filtrados FROM totals), 0) AS total_pedidos_filtrados,
                COALESCE((SELECT total_importe_real_filtrado FROM totals), 0) AS total_importe_real_filtrado,
                COALESCE((SELECT cliente FROM top_cliente), '') AS cliente_top_reclamacion,
                COALESCE((SELECT causa FROM top_causa), '') AS causa_principal
            FROM recl_filtered
        """
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else {}

    def _query_reclam_detalle(self, conn: sqlite3.Connection, cte_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        query = f"""
            {cte_sql}
            SELECT
                id_pedido,
                linea,
                fecha_salida,
                fecha_reclamacion,
                campana,
                cultivo,
                empresa,
                semana,
                cliente,
                pais,
                var_coop,
                var_cliente,
                calibre,
                categoria,
                marca,
                causa,
                neto_reclamado,
                importe_reclamado,
                medida,
                observaciones
            FROM recl_filtered
            ORDER BY fecha_salida DESC, id_pedido DESC, linea DESC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _query_reclam_por_causa(self, conn: sqlite3.Connection, cte_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        query = f"""
            {cte_sql}
            SELECT
                COALESCE(NULLIF(causa, ''), '(Sin causa)') AS causa,
                COUNT(1) AS reclamaciones_count,
                COALESCE(SUM(importe_reclamado), 0) AS importe_reclamado,
                COALESCE(SUM(neto_reclamado), 0) AS neto_reclamado,
                COUNT(DISTINCT cliente) AS clientes_count,
                COUNT(DISTINCT id_pedido) AS pedidos_count
            FROM recl_filtered
            GROUP BY COALESCE(NULLIF(causa, ''), '(Sin causa)')
            ORDER BY importe_reclamado DESC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _query_reclam_por_cliente(self, conn: sqlite3.Connection, cte_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        query = f"""
            {cte_sql}
            , causas_cliente AS (
                SELECT
                    cliente,
                    COALESCE(NULLIF(causa, ''), '(Sin causa)') AS causa,
                    SUM(importe_reclamado) AS importe_causa,
                    ROW_NUMBER() OVER (
                        PARTITION BY cliente
                        ORDER BY SUM(importe_reclamado) DESC, COALESCE(NULLIF(causa, ''), '(Sin causa)') ASC
                    ) AS rn
                FROM recl_filtered
                GROUP BY cliente, COALESCE(NULLIF(causa, ''), '(Sin causa)')
            ),
            pais_cliente AS (
                SELECT
                    cliente,
                    pais,
                    COUNT(1) AS cnt,
                    ROW_NUMBER() OVER (
                        PARTITION BY cliente
                        ORDER BY COUNT(1) DESC, pais ASC
                    ) AS rn
                FROM recl_filtered
                GROUP BY cliente, pais
            )
            SELECT
                rf.cliente,
                COALESCE(pc.pais, '') AS pais,
                COUNT(1) AS reclamaciones_count,
                COALESCE(SUM(rf.importe_reclamado), 0) AS importe_reclamado,
                COALESCE(SUM(rf.neto_reclamado), 0) AS neto_reclamado,
                COUNT(DISTINCT rf.id_pedido) AS pedidos_reclamados,
                COALESCE(cc.causa, '') AS causa_principal
            FROM recl_filtered rf
            LEFT JOIN pais_cliente pc ON pc.cliente = rf.cliente AND pc.rn = 1
            LEFT JOIN causas_cliente cc ON cc.cliente = rf.cliente AND cc.rn = 1
            GROUP BY rf.cliente, pc.pais, cc.causa
            ORDER BY importe_reclamado DESC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _query_reclam_grafica(self, conn: sqlite3.Connection, cte_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        query = f"""
            {cte_sql}
            SELECT
                COALESCE(NULLIF(causa, ''), '(Sin causa)') AS causa,
                COALESCE(SUM(importe_reclamado), 0) AS importe_reclamado
            FROM recl_filtered
            GROUP BY COALESCE(NULLIF(causa, ''), '(Sin causa)')
            ORDER BY importe_reclamado DESC
            LIMIT 10
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _query_desviacion_clientes(
        self,
        conn: sqlite3.Connection,
        where_sql: str,
        params: list[Any],
        cols: set[str],
        recl_cols: set[str],
        has_calc: bool,
        line_field: str | None,
    ) -> list[dict[str, Any]]:
        neto_cliente = self._real_expr("NetoCliente", cols, alias="p")
        euros_kg = self._real_expr("EurosKG", cols, alias="p")
        kg_total_line, kg_valid_line, weighted_line = self._real_price_line_exprs(neto_cliente, euros_kg)
        orient_final = self._orient_final_expr(has_calc, self._calc_price_col)
        var_col = 'COALESCE(CAST(p."VarCoop" AS TEXT), "")' if "VarCoop" in cols else "''"
        cat_col = 'COALESCE(CAST(p."Categoria" AS TEXT), "")' if "Categoria" in cols else "''"
        cal_col = 'COALESCE(CAST(p."Calibre" AS TEXT), "")' if "Calibre" in cols else "''"
        sem_col = 'COALESCE(CAST(p."Semana" AS TEXT), "")' if "Semana" in cols else "''"
        cli_col = 'COALESCE(CAST(p."Cliente" AS TEXT), "")' if "Cliente" in cols else "''"
        pais_col = 'COALESCE(CAST(p."Pais" AS TEXT), "")' if "Pais" in cols else "''"
        id_col = 'COALESCE(CAST(p."IdPedidoLora" AS TEXT), "")' if "IdPedidoLora" in cols else "''"
        line_col = 'COALESCE(CAST(p."Linea" AS INTEGER), 0)' if "Linea" in cols else ('COALESCE(CAST(p."Line" AS INTEGER), 0)' if "Line" in cols else "0")
        reclamado_col = 'CASE WHEN UPPER(COALESCE(p."Reclamado", "")) = \'S\' THEN 1 ELSE 0 END' if "Reclamado" in cols else "0"

        recl_cte = ""
        recl_join = ""
        recl_amount_expr = "0"
        if recl_cols and "IdPedido" in recl_cols and "Importe" in recl_cols:
            recl_line = 'COALESCE(CAST("Linea" AS INTEGER), 0)' if "Linea" in recl_cols else "0"
            recl_cte = f"""
            , recl AS (
                SELECT
                    COALESCE(CAST("IdPedido" AS TEXT), "") AS id_pedido,
                    {recl_line} AS linea,
                    SUM(COALESCE(CAST("Importe" AS REAL), 0)) AS importe_reclamado
                FROM "{self.TABLE_RECLAMACIONES}"
                GROUP BY COALESCE(CAST("IdPedido" AS TEXT), ""), {recl_line}
            )
            """
            recl_join = "LEFT JOIN recl r ON r.id_pedido = cc.id_pedido AND r.linea = cc.linea"
            recl_amount_expr = "COALESCE(r.importe_reclamado, 0)"

        real_weight = "SUM(cc.suma_ponderada_euroskg)"
        real_kg = "SUM(cc.kg_euroskg_valido)"
        ref_weight = "SUM(cc.kg_euroskg_valido * cc.precio_ref)"
        precio_real = self._safe_div(real_weight, real_kg)
        precio_ref = self._safe_div(ref_weight, real_kg)
        desviacion = f"(({precio_real}) - ({precio_ref}))"
        forfait_join = self._forfait_join_sql(has_calc, cols)
        if forfait_join:
            coste_conf_line = 'ef."CosteConfeccionEurKg"'
            coste_total_line = 'ef."CosteTotalEurKg"'
            estado_forfait_line = 'ef."Estado"'
        else:
            coste_conf_line = "NULL"
            coste_total_line = "NULL"
            estado_forfait_line = "'SIN_COSTE_FORFAIT'"
        kg_forfait_line = (
            "CASE WHEN cc.coste_confeccion_eurkg IS NOT NULL AND cc.kg_euroskg_valido > 0 "
            "THEN cc.kg_euroskg_valido ELSE 0 END"
        )
        kg_forfait = f"SUM({kg_forfait_line})"
        coste_conf_total = f"SUM(({kg_forfait_line}) * COALESCE(cc.coste_confeccion_eurkg, 0))"
        coste_total_forfait = f"SUM(({kg_forfait_line}) * COALESCE(cc.coste_total_forfait_eurkg, 0))"
        precio_real_forfait = self._safe_div(
            "SUM(CASE WHEN cc.coste_confeccion_eurkg IS NOT NULL THEN cc.suma_ponderada_euroskg ELSE 0 END)",
            kg_forfait,
        )
        precio_ref_forfait = self._safe_div(
            "SUM(CASE WHEN cc.coste_confeccion_eurkg IS NOT NULL THEN cc.kg_euroskg_valido * cc.precio_ref ELSE 0 END)",
            kg_forfait,
        )
        coste_conf_avg = self._safe_div(coste_conf_total, kg_forfait)
        coste_total_avg = self._safe_div(coste_total_forfait, kg_forfait)
        margen_ajustado = f"(({precio_real_forfait}) - ({precio_ref_forfait}) - ({coste_conf_avg}))"
        impacto_ajustado = f"CASE WHEN ({kg_forfait}) > 0 THEN ({margen_ajustado}) * ({kg_forfait}) ELSE NULL END"
        estado_forfait = (
            f"CASE WHEN ({kg_forfait}) <= 0 THEN 'SIN_COSTE_FORFAIT' "
            f"WHEN ({kg_forfait}) < COALESCE({real_kg}, 0) THEN 'PARCIAL' "
            "ELSE 'VALIDADO' END"
        )

        query = f"""
            WITH filtered AS (
                SELECT
                    p.*,
                    ({orient_final}) AS precio_orientativo_final,
                    {coste_conf_line} AS coste_confeccion_eurkg,
                    {coste_total_line} AS coste_total_forfait_eurkg,
                    {estado_forfait_line} AS estado_forfait_line
                FROM "{self.TABLE_PEDIDOS}" p
                {self._calc_join_sql(has_calc, line_field)}
                {forfait_join}
                {where_sql}
            ),
            comparable AS (
                SELECT
                    {cli_col} AS cliente,
                    {pais_col} AS pais,
                    {id_col} AS id_pedido,
                    {line_col} AS linea,
                    {sem_col} AS semana,
                    {var_col} AS var_coop,
                    {cat_col} AS categoria,
                    {cal_col} AS calibre,
                    {neto_cliente} AS kg_cliente,
                    {euros_kg} AS euros_kg,
                    {kg_total_line} AS kg_total_line,
                    {kg_valid_line} AS kg_euroskg_valido,
                    {weighted_line} AS suma_ponderada_euroskg,
                    p."precio_orientativo_final" AS precio_orientativo_final,
                    p."coste_confeccion_eurkg" AS coste_confeccion_eurkg,
                    p."coste_total_forfait_eurkg" AS coste_total_forfait_eurkg,
                    p."estado_forfait_line" AS estado_forfait_line,
                    {reclamado_col} AS pedido_reclamado
                FROM filtered p
                WHERE {neto_cliente} > 0
            ),
            refs AS (
                SELECT
                    semana,
                    var_coop,
                    categoria,
                    calibre,
                    SUM(precio_orientativo_final * kg_cliente) / NULLIF(SUM(kg_cliente), 0) AS precio_ref
                FROM comparable
                WHERE kg_cliente > 0
                GROUP BY semana, var_coop, categoria, calibre
            ),
            client_calc AS (
                SELECT
                    c.cliente,
                    c.pais,
                    c.id_pedido,
                    c.linea,
                    c.var_coop,
                    c.categoria,
                    c.calibre,
                    c.kg_cliente,
                    c.euros_kg,
                    c.kg_total_line,
                    c.kg_euroskg_valido,
                    c.suma_ponderada_euroskg,
                    c.coste_confeccion_eurkg,
                    c.coste_total_forfait_eurkg,
                    c.estado_forfait_line,
                    c.pedido_reclamado,
                    COALESCE(r.precio_ref, 0) AS precio_ref
                FROM comparable c
                LEFT JOIN refs r
                  ON r.semana = c.semana
                 AND r.var_coop = c.var_coop
                 AND r.categoria = c.categoria
                 AND r.calibre = c.calibre
            )
            {recl_cte}
            SELECT
                cc.cliente AS cliente,
                MAX(cc.pais) AS pais,
                SUM(cc.kg_cliente) AS kg_cliente,
                COUNT(1) AS pedidos_count,
                COALESCE({real_weight}, 0) AS importe_real,
                {precio_real} AS precio_medio_real,
                {precio_ref} AS precio_referencia_ajustado,
                {desviacion} AS desviacion_eurkg,
                ({desviacion} * COALESCE({real_kg}, 0)) AS impacto_eur,
                {coste_conf_avg} AS coste_confeccion_eurkg,
                {coste_conf_total} AS coste_confeccion_total_eur,
                {coste_total_avg} AS coste_total_forfait_eurkg,
                {margen_ajustado} AS margen_ajustado_eurkg,
                {impacto_ajustado} AS impacto_ajustado_eur,
                {kg_forfait} AS kg_forfait_validado,
                (COALESCE({real_kg}, 0) - COALESCE({kg_forfait}, 0)) AS kg_sin_forfait,
                {estado_forfait} AS estado_forfait,
                GROUP_CONCAT(DISTINCT NULLIF(cc.var_coop, '')) AS variedades_principales,
                GROUP_CONCAT(DISTINCT NULLIF(cc.categoria, '')) AS categorias_principales,
                GROUP_CONCAT(DISTINCT NULLIF(cc.calibre, '')) AS calibres_principales,
                SUM(cc.pedido_reclamado) AS pedidos_reclamados,
                SUM({recl_amount_expr}) AS importe_reclamado,
                SUM(cc.kg_total_line) AS debug_kg_total,
                COALESCE({real_kg}, 0) AS debug_kg_euroskg_valido,
                COALESCE({real_weight}, 0) AS debug_suma_ponderada_euroskg,
                {precio_real} AS debug_precio_real_calculado,
                COALESCE({real_kg}, 0) AS debug_kg_precio_real,
                COALESCE({real_weight}, 0) AS debug_importe_total,
                {precio_real} AS debug_precio_medio_real,
                {precio_ref} AS debug_precio_referencia
            FROM client_calc cc
            {recl_join}
            GROUP BY cc.cliente
            ORDER BY impacto_eur DESC
        """
        logger.debug("SQL DESVIACION CLIENTES:\n%s", query)
        rows = conn.execute(query, params).fetchall()
        out = [dict(r) for r in rows]
        for idx, row in enumerate(out, start=1):
            row["ranking_posicion"] = idx
        sum_kg = sum(float(r.get("debug_kg_total") or 0) for r in out)
        sum_imp = sum(float(r.get("debug_importe_total") or 0) for r in out)
        precio_calc = (sum_imp / sum_kg) if sum_kg else 0.0
        logger.info(
            "Desviacion clientes: filas=%s, kg_total=%.4f, importe_total=%.4f, precio_medio_calc=%.6f",
            len(out),
            sum_kg,
            sum_imp,
            precio_calc,
        )
        if out:
            logger.info(
                "Desviacion clientes referencia (primera fila): cliente=%s precio_real=%.6f precio_ref=%.6f",
                out[0].get("cliente", ""),
                float(out[0].get("precio_medio_real") or 0),
                float(out[0].get("precio_referencia_ajustado") or 0),
            )
        return out

    def _query_reclamado_importe(
        self,
        conn: sqlite3.Connection,
        where_sql: str,
        params: list[Any],
        pedidos_cols: set[str],
        recl_cols: set[str],
    ) -> float | None:
        if not recl_cols:
            logger.warning("Tabla DReclamacion no disponible.")
            return None
        if "IdPedidoLora" not in pedidos_cols or "IdPedido" not in recl_cols or "Importe" not in recl_cols:
            logger.warning("No se pudo preparar join de reclamaciones por falta de columnas.")
            return None

        join_cond = 'dr."IdPedido" = p."IdPedidoLora"'
        select_cols = ['p."IdPedidoLora"']
        if "Linea" in recl_cols and "Linea" in pedidos_cols:
            select_cols.append('p."Linea"')
            join_cond += ' AND dr."Linea" = p."Linea"'
        elif "Linea" in recl_cols and "Line" in pedidos_cols:
            select_cols.append('p."Line"')
            join_cond += ' AND dr."Linea" = p."Line"'

        query = f"""
            SELECT COALESCE(SUM(COALESCE(CAST(dr."Importe" AS REAL), 0)), 0) AS importe_reclamado
            FROM (
                SELECT {", ".join(select_cols)}
                FROM "{self.TABLE_PEDIDOS}" p
                {where_sql}
            ) p
            LEFT JOIN "{self.TABLE_RECLAMACIONES}" dr ON {join_cond}
        """
        row = conn.execute(query, params).fetchone()
        return float(row["importe_reclamado"] or 0) if row else 0.0

    def _build_where(self, filters: dict[str, Any], cols: set[str]) -> tuple[str, list[Any], list[str]]:
        warnings: list[str] = []
        where_sql, params = build_pedidos_where(filters, alias="p", include_base=True)
        logger.info("Filtro Cancelado=0 aplicado")
        if str(filters.get("semana", "")).strip():
            logger.info("Filtro Semana aplicado")
        logger.info("Filtros recibidos: %s", filters)
        logger.info("WHERE generado: %s", where_sql)
        logger.info("PARAMS generados: %s", params)

        if "Cancelado" not in cols and "Cancelado" not in self._warned_missing_columns:
            logger.warning("Columna Cancelado no encontrada en Pedidos")
            self._warned_missing_columns.add("Cancelado")

        # Validar columnas realmente existentes para evitar romper consultas.
        mapped_clauses, _, _ = build_pedidos_filters(filters, alias="p")
        for raw_clause in mapped_clauses:
            column = raw_clause.split('"')[1] if '"' in raw_clause else ""
            if column and column not in cols:
                if column not in self._warned_missing_columns:
                    logger.warning("Columna de filtro no disponible en Pedidos: %s", column)
                    self._warned_missing_columns.add(column)
                warnings.append(f"Filtro no disponible: {column}")
        return where_sql, params, warnings

    def _real_expr(self, column: str, cols: set[str], alias: str = "p") -> str:
        if column not in cols:
            self._warn_missing_column(column)
            return "0"
        return self._num_expr(f'{alias}."{column}"')

    def _warn_missing_column(self, column: str) -> None:
        if column in self._warned_missing_columns:
            return
        logger.warning("Columna esperada no disponible en %s: %s", self.TABLE_PEDIDOS, column)
        self._warned_missing_columns.add(column)

    @staticmethod
    def _get_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
        try:
            rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            return {str(r["name"]) for r in rows}
        except Exception:
            return set()

    def _connect_pedidos(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_pedidos))
        conn.row_factory = sqlite3.Row
        return conn
