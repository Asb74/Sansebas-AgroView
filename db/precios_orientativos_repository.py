import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DB_DIR, DB_PEDIDOS
from db.agroview_calc_repository import AgroviewCalcRepository
from db.query_filters import build_pedidos_filters, build_pedidos_where, pedidos_base_where

logger = logging.getLogger(__name__)


class PreciosOrientativosRepository:
    TABLE_PEDIDOS = "Pedidos"
    TABLE_DPRECIO = "DPrecioO"
    TABLE_CONFECCIONES = "MConfecciones"
    TABLE_CALIBRE = "MCalibre"

    FILTER_MAP = {
        "campana": ("Campaña", "exact"),
        "cultivo": ("Cultivo", "like"),
        "empresa": ("EMPRESA", "exact"),
        "semana": ("Semana", "exact"),
        "cliente": ("Cliente", "like"),
        "var_coop": ("VarCoop", "like"),
        "grupo_varietal": ("GrupoVarietal", "like"),
        "estado_precio": ("EstadoPrecio", "exact"),
    }

    def __init__(self, db_path: Path | None = None, db_fruta_path: Path | None = None) -> None:
        self.db_path = db_path or (Path(DB_DIR) / DB_PEDIDOS)
        self.db_fruta_path = db_fruta_path or (Path(DB_DIR) / "DBfruta.sqlite")
        self.calc_repo = AgroviewCalcRepository()
        self.calc_repo.initialize()
        logger.info("Ruta DBPedidos.sqlite: %s", self.db_path)
        self._warned: set[str] = set()

    def ensure_columns(self) -> list[str]:
        # DBPedidos.sqlite es solo lectura en esta herramienta.
        return []

    def fetch_pending(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        logger.info("Modo usado: PENDIENTES")
        with self._connect() as conn:
            logger.info("Usando columna EMPRESA para filtro de empresa")
            cols = self._get_columns(conn, self.TABLE_PEDIDOS)
            where_sql, filter_params, warn, applied_filters = self._build_where(filters, cols)
            warnings.extend(warn)
            filtro_grupo_varietal = self._first_filter_value(filters.get("grupo_varietal")).lower()
            filtro_estado_precio = self._first_filter_value(filters.get("estado_precio")).upper()
            logger.info("Columnas detectadas en Pedidos: %s", ", ".join(sorted(cols)))
            logger.info("Filtros recibidos: %s", filters)
            logger.info("Filtros aplicados: %s", applied_filters)
            logger.info("Confirmado: usando Campaña/Cultivo/EMPRESA")

            orient_expr = self._num_expr("EurosOrientativos")
            pending_sql = f"({orient_expr} IS NULL OR {orient_expr} <= 0)"
            cancelado_sql, cancelado_params = self._cancelado_filter_for_pedidos(cols)

            selected: list[str] = []
            if "IdPedidoLora" in cols:
                selected.append('"IdPedidoLora"')
            if "Linea" in cols:
                selected.append('CAST("Linea" AS INTEGER) AS "Linea"')
            elif "Line" in cols:
                selected.append('CAST("Line" AS INTEGER) AS "Linea"')
            else:
                selected.append("0 AS Linea")

            for col in ["Campaña", "Semana", "FechaSalida", "Cultivo", "Cliente", "Confeccion", "Calibre", "VarCoop", "NetoCliente", "EurosKG", "EurosOrientativos"]:
                if col in cols:
                    selected.append(f'"{col}"')
            if "EMPRESA" in cols:
                selected.append('"EMPRESA" AS "Empresa"')
            query = f'SELECT {", ".join(selected)} FROM "{self.TABLE_PEDIDOS}" WHERE {pending_sql}'
            if cancelado_sql:
                query += f" AND {cancelado_sql}"
            if where_sql:
                query += f" AND {where_sql}"
            params = cancelado_params + filter_params
            query += ' ORDER BY CAST("Semana" AS INTEGER) DESC, "FechaSalida" DESC'
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

            keys = [(str(r.get("IdPedidoLora") or ""), self._to_int(r.get("Linea"), 0) or 0) for r in rows]
            calc_map = self.calc_repo.fetch_calc_map(keys)

            conf_map = self._load_confecciones(conn)
            cal_map = self._load_calibres(conn)
            empresa_map, empresa_warn = self._load_empresas_dict()
            grupo_var_map, grupo_var_warn = self._load_grupos_varietales()
            if empresa_warn:
                warnings.append(empresa_warn)
            if grupo_var_warn:
                warnings.append(grupo_var_warn)

            filtered_rows: list[dict[str, Any]] = []
            for row in rows:
                pid = str(row.get("IdPedidoLora") or "")
                linea = self._to_int(row.get("Linea"), 0) or 0
                calc = calc_map.get((pid, linea))
                has_valid_calc = self._to_float((calc or {}).get("EurosOrientativosCalc")) is not None and float((calc or {}).get("EurosOrientativosCalc") or 0) > 0
                if has_valid_calc:
                    continue

                conf = str(row.get("Confeccion", "")).strip()
                cult = str(row.get("Cultivo", "")).strip()
                cal = str(row.get("Calibre", "")).strip()
                emp = str(row.get("Empresa", "")).strip()

                row["GrupoConfeccion"] = conf_map.get(conf, "")
                row["CalibreU"] = cal_map.get((cal, cult), "")
                row["EmpresaNombre"] = empresa_map.get(emp, emp)
                row["GrupoVarietal"] = str(row.get("GrupoVarietal") or grupo_var_map.get((str(row.get("VarCoop", "")).strip(), cult), ""))
                if emp and emp not in empresa_map:
                    self._warn_once(f"No se pudo resolver nombre de empresa para IdEmpresa={emp}")

                row["EurosOrientativosCalc"] = (calc or {}).get("EurosOrientativosCalc")
                row["Metodo"] = str((calc or {}).get("Metodo") or "")
                row["Observaciones"] = str((calc or {}).get("Observaciones") or "")
                row["MuestrasUsadas"] = 0
                row["MediaGrupo"] = (calc or {}).get("MediaGrupo")
                row["MediaCalibre"] = (calc or {}).get("MediaCalibre")
                row["SemanaPrecioUsada"] = (calc or {}).get("SemanaPrecioUsada")
                row["CalibreUUsado"] = str((calc or {}).get("CalibreUUsado") or "")
                row["CampanaUsada"] = row.get("Campaña")
                row["CultivoUsado"] = row.get("Cultivo")
                row["EmpresaUsada"] = row.get("Empresa")
                row["IdsUsados"] = str((calc or {}).get("IdsUsados") or "")

                final_price, final_origin = self.get_precio_orientativo_final(row, calc)
                row["PrecioOrientativoFinal"] = final_price
                row["OrigenPrecioOrientativo"] = final_origin
                row["EstadoPrecio"] = self._estado_precio(row)
                if filtro_grupo_varietal and filtro_grupo_varietal not in str(row.get("GrupoVarietal", "")).lower():
                    continue
                if not self._match_estado_filter(filtro_estado_precio, row["EstadoPrecio"]):
                    continue
                filtered_rows.append(row)
            logger.info("Total filas cargadas (PENDIENTES): %s", len(filtered_rows))
            return filtered_rows, warnings

    def fetch_for_recalculation(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        logger.info("Modo usado: RECALCULO_TOTAL")
        with self._connect() as conn:
            params: list[Any] = []
            clauses: list[str] = []
            cols = self._get_columns(conn, self.TABLE_PEDIDOS)
            where_sql, filter_params, warn, applied_filters = self._build_where(filters, cols)
            warnings.extend(warn)
            filtro_grupo_varietal = self._first_filter_value(filters.get("grupo_varietal")).lower()
            filtro_estado_precio = self._first_filter_value(filters.get("estado_precio")).upper()
            cancelado_sql, cancelado_params = self._cancelado_filter_for_pedidos(cols)
            logger.info("Columnas detectadas en Pedidos: %s", ", ".join(sorted(cols)))
            logger.info("Filtros recibidos: %s", filters)
            logger.info("Filtros aplicados: %s", applied_filters)
            logger.info("Confirmado: usando Campaña/Cultivo/EMPRESA")

            selected: list[str] = []
            if "IdPedidoLora" in cols:
                selected.append('"IdPedidoLora"')
            if "Linea" in cols:
                selected.append('CAST("Linea" AS INTEGER) AS "Linea"')
            elif "Line" in cols:
                selected.append('CAST("Line" AS INTEGER) AS "Linea"')
            else:
                selected.append("0 AS Linea")

            for col in ["Campaña", "Semana", "FechaSalida", "Cultivo", "Cliente", "Confeccion", "Calibre", "VarCoop", "NetoCliente", "EurosKG", "EurosOrientativos"]:
                if col in cols:
                    selected.append(f'"{col}"')
            if "EMPRESA" in cols:
                selected.append('"EMPRESA" AS "Empresa"')
            query = f'SELECT {", ".join(selected)} FROM "{self.TABLE_PEDIDOS}"'
            if cancelado_sql:
                clauses.append(cancelado_sql)
                params.extend(cancelado_params)
            if where_sql:
                clauses.append(where_sql)
                params.extend(filter_params)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += ' ORDER BY CAST("Semana" AS INTEGER) DESC, "FechaSalida" DESC'
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]

            keys = [(str(r.get("IdPedidoLora") or ""), self._to_int(r.get("Linea"), 0) or 0) for r in rows]
            calc_map = self.calc_repo.fetch_calc_map(keys)
            conf_map = self._load_confecciones(conn)
            cal_map = self._load_calibres(conn)
            empresa_map, empresa_warn = self._load_empresas_dict()
            grupo_var_map, grupo_var_warn = self._load_grupos_varietales()
            if empresa_warn:
                warnings.append(empresa_warn)
            if grupo_var_warn:
                warnings.append(grupo_var_warn)

            out_rows: list[dict[str, Any]] = []
            for row in rows:
                pid = str(row.get("IdPedidoLora") or "")
                linea = self._to_int(row.get("Linea"), 0) or 0
                calc = calc_map.get((pid, linea))

                conf = str(row.get("Confeccion", "")).strip()
                cult = str(row.get("Cultivo", "")).strip()
                cal = str(row.get("Calibre", "")).strip()
                emp = str(row.get("Empresa", "")).strip()
                row["GrupoConfeccion"] = conf_map.get(conf, "")
                row["CalibreU"] = cal_map.get((cal, cult), "")
                row["EmpresaNombre"] = empresa_map.get(emp, emp)
                row["GrupoVarietal"] = str(row.get("GrupoVarietal") or grupo_var_map.get((str(row.get("VarCoop", "")).strip(), cult), ""))
                row["EurosOrientativosCalcAnterior"] = (calc or {}).get("EurosOrientativosCalc")

                row["EurosOrientativosCalc"] = None
                row["Metodo"] = ""
                row["Observaciones"] = ""
                row["MuestrasUsadas"] = 0
                row["MediaGrupo"] = None
                row["MediaCalibre"] = None
                row["SemanaPrecioUsada"] = None
                row["CalibreUUsado"] = ""
                row["CampanaUsada"] = row.get("Campaña")
                row["CultivoUsado"] = row.get("Cultivo")
                row["EmpresaUsada"] = row.get("Empresa")
                row["IdsUsados"] = ""

                final_price, final_origin = self.get_precio_orientativo_final(row, calc)
                row["PrecioOrientativoFinal"] = final_price
                row["OrigenPrecioOrientativo"] = final_origin
                row["EstadoPrecio"] = self._estado_precio(row)
                if filtro_grupo_varietal and filtro_grupo_varietal not in str(row.get("GrupoVarietal", "")).lower():
                    continue
                if not self._match_estado_filter(filtro_estado_precio, row["EstadoPrecio"]):
                    continue
                out_rows.append(row)
            logger.info("Total filas cargadas (RECALCULO_TOTAL): %s", len(out_rows))
            return out_rows, warnings

    def get_filter_options(self, filters: dict[str, Any], target_filter: str) -> list[str]:
        field_map = {
            "campana": "Campaña",
            "cultivo": "Cultivo",
            "empresa": "EMPRESA",
            "semana": "Semana",
            "cliente": "Cliente",
            "var_coop": "VarCoop",
        }
        if target_filter == "grupo_varietal":
            return self._get_grupo_varietal_options(filters)
        if target_filter not in field_map:
            return []
        target_col = field_map[target_filter]
        effective_filters = {k: v for k, v in filters.items() if k != target_filter}
        where_sql, params = build_pedidos_where(effective_filters, alias="p", include_base=True)
        order_sql = f'ORDER BY CAST(p."{target_col}" AS TEXT) ASC'
        if target_filter == "semana":
            order_sql = (
                'ORDER BY CASE WHEN CAST(p."Semana" AS INTEGER) >= 36 '
                'THEN CAST(p."Semana" AS INTEGER) - 35 ELSE CAST(p."Semana" AS INTEGER) + 17 END ASC'
            )
        elif target_filter == "empresa":
            order_sql = 'ORDER BY CAST(p."EMPRESA" AS INTEGER) ASC'
        query = f'''
            SELECT DISTINCT CAST(p."{target_col}" AS TEXT) AS value
            FROM "{self.TABLE_PEDIDOS}" p
            {where_sql}
              AND COALESCE(TRIM(CAST(p."{target_col}" AS TEXT)), '') <> ''
            {order_sql}
        '''
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [str(r["value"]).strip() for r in rows if str(r["value"] or "").strip()]

    def _get_grupo_varietal_options(self, filters: dict[str, Any]) -> list[str]:
        with self._connect() as conn:
            cols = self._get_columns(conn, self.TABLE_PEDIDOS)
            where_sql, params, _warn, _applied = self._build_where(filters, cols)
            query = f'SELECT "VarCoop", "Cultivo", "GrupoVarietal" FROM "{self.TABLE_PEDIDOS}"'
            if where_sql:
                query += f" WHERE {where_sql}"
            rows = [dict(r) for r in conn.execute(query, params).fetchall()]
        grupo_var_map, _ = self._load_grupos_varietales()
        grupos: set[str] = set()
        for row in rows:
            direct = str(row.get("GrupoVarietal") or "").strip()
            if direct:
                grupos.add(direct)
                continue
            vc = str(row.get("VarCoop") or "").strip()
            cult = str(row.get("Cultivo") or "").strip()
            mapped = str(grupo_var_map.get((vc, cult), "")).strip()
            if mapped:
                grupos.add(mapped)
        return sorted(grupos)

    @staticmethod
    def _match_estado_filter(selected: str, current: str) -> bool:
        selected = str(selected or "").strip().upper()
        if selected in {"", "TODOS"}:
            return True
        if selected == "CON_PRECIO":
            return current in {"CON_ORIGINAL", "ESTIMADO_GUARDADO"}
        if selected == "ESTIMADO":
            return current == "ESTIMADO_GUARDADO"
        if selected == "ORIGINAL":
            return current == "CON_ORIGINAL"
        return current == selected

    def calculate_estimations(self, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        warnings: list[str] = []
        with self._connect() as conn:
            conf_map = self._load_confecciones(conn)
            cal_map = self._load_calibres(conn)

            out: list[dict[str, Any]] = []
            for row in rows:
                updated = dict(row)
                pedido_id = row.get("IdPedidoLora")
                semana = self._to_int(row.get("Semana"))
                campana = str(row.get("Campaña", "")).strip()
                cultivo = str(row.get("Cultivo", "")).strip()
                empresa = str(row.get("Empresa", "")).strip()
                confeccion = str(row.get("Confeccion", "")).strip()
                calibre = str(row.get("Calibre", "")).strip()
                prefijo = self._extract_prefix(str(pedido_id or ""))
                euro_ori = self._to_float(row.get("EurosOrientativos"))

                grupo = conf_map.get(confeccion)
                if not grupo:
                    self._set_not_estimated(updated, "ERROR_MAESTRO_CONFECCION", "Confección sin grupo en MConfecciones")
                    out.append(updated)
                    continue

                calibre_u = cal_map.get((calibre, cultivo))
                if not calibre_u:
                    self._set_not_estimated(updated, "ERROR_MAESTRO_CALIBRE", "Calibre/Cultivo sin CalibreU en MCalibre")
                    out.append(updated)
                    continue

                updated["GrupoConfeccion"] = grupo
                updated["CalibreU"] = calibre_u

                if euro_ori is not None and euro_ori > 0:
                    updated["EurosOrientativosCalc"] = round(euro_ori, 4)
                    updated["Metodo"] = "ORIGINAL"
                    updated["MuestrasUsadas"] = 0
                    updated["MediaGrupo"] = None
                    updated["MediaCalibre"] = None
                    updated["SemanaPrecioUsada"] = semana
                    updated["CampanaUsada"] = campana
                    updated["CultivoUsado"] = cultivo
                    updated["EmpresaUsada"] = empresa
                    updated["IdsUsados"] = ""
                    updated["Observaciones"] = (
                        f"metodo=ORIGINAL; campana={campana}; cultivo={cultivo}; empresa={empresa}; "
                        f"semana={semana}; prefijo={prefijo}; gconf={grupo}; calibre_u={calibre_u}; muestras=0; ids="
                    )
                    out.append(updated)
                    continue

                result = self._estimate_price(
                    conn=conn,
                    pedido_id=pedido_id,
                    semana=semana,
                    campana=campana,
                    empresa=empresa,
                    cultivo=cultivo,
                    prefijo=prefijo,
                    grupo=grupo,
                    calibre_u=calibre_u,
                )

                if result["price"] is None:
                    self._set_not_estimated(updated, result["method"], result["obs"])
                    updated["MuestrasUsadas"] = result["samples"]
                    updated["MediaGrupo"] = result["media_grupo"]
                    updated["MediaCalibre"] = result["media_calibre"]
                    updated["SemanaPrecioUsada"] = result.get("week_label", result["week_ref"])
                    updated["CalibreUUsado"] = result.get("calibre_u_usado", "")
                    updated["CampanaUsada"] = campana
                    updated["CultivoUsado"] = cultivo
                    updated["EmpresaUsada"] = empresa
                    updated["IdsUsados"] = ",".join(result["sample_ids"])
                    warnings.append(f"Pedido {pedido_id}: {result['method']}")
                else:
                    updated["EurosOrientativosCalc"] = round(float(result["price"]), 4)
                    updated["Metodo"] = result["method"]
                    updated["EurosOrientativosSemanaRef"] = result["week_ref"]
                    updated["MuestrasUsadas"] = result["samples"]
                    updated["MediaGrupo"] = result["media_grupo"]
                    updated["MediaCalibre"] = result["media_calibre"]
                    updated["SemanaPrecioUsada"] = result.get("week_label", result["week_ref"])
                    updated["CalibreUUsado"] = result.get("calibre_u_usado", "")
                    updated["CampanaUsada"] = campana
                    updated["CultivoUsado"] = cultivo
                    updated["EmpresaUsada"] = empresa
                    updated["IdsUsados"] = ",".join(result["sample_ids"])
                    updated["Observaciones"] = result["obs"]
                out.append(updated)
        return out, warnings

    def save_estimations(self, rows: list[dict[str, Any]]) -> tuple[int, list[str]]:
        warnings: list[str] = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload: list[dict[str, Any]] = []
        for row in rows:
            method = str(row.get("Metodo", "") or "")
            calc = row.get("EurosOrientativosCalc")
            if method == "ORIGINAL":
                origen = "ORIGINAL"
            elif calc is not None and float(calc or 0) > 0:
                origen = "ESTIMADO"
            else:
                origen = "SIN_DATOS"
                calc = None
            record = dict(row)
            record["EurosOrientativosCalc"] = calc
            record["OrigenPrecioOrientativo"] = origen
            record["FechaCalculo"] = now
            record["UsuarioCalculo"] = "APP"
            payload.append(record)
        try:
            inserted, updated = self.calc_repo.upsert_calcs(payload)
            logger.info("Cálculos auxiliares insertados=%s actualizados=%s", inserted, updated)
            return inserted + updated, warnings
        except Exception as exc:
            logger.exception("Error guardando cálculos en DB auxiliar: %s", exc)
            warnings.append("Error de guardado en base auxiliar.")
            return 0, warnings

    def get_precio_orientativo_final(self, pedido: dict[str, Any], calc_row: dict[str, Any] | None = None) -> tuple[float | None, str]:
        original = self._to_float(pedido.get("EurosOrientativos"))
        if original is not None and original > 0:
            return original, "ORIGINAL"
        calc = self._to_float((calc_row or {}).get("EurosOrientativosCalc"))
        if calc is not None and calc > 0:
            return calc, "ESTIMADO"
        return None, "SIN_DATOS"

    def _estimate_price(
        self,
        conn: sqlite3.Connection,
        pedido_id: Any,
        semana: int | None,
        campana: str,
        empresa: str,
        cultivo: str,
        prefijo: str,
        grupo: str,
        calibre_u: str,
    ) -> dict[str, Any]:
        if semana is None or not campana or not cultivo or not empresa or not prefijo:
            return self._result_none(
                "SIN_DATOS",
                None,
                grupo,
                calibre_u,
                0,
                None,
                None,
                [],
                "faltan datos obligatorios de comparabilidad (campaña/cultivo/empresa/semana/prefijo)",
            )

        exact_methods = [
            (semana, "MISMA_SEMANA_GCONF_CALIBREU"),
            (semana - 1, "SEMANA_ANTERIOR_GCONF_CALIBREU"),
            (semana + 1, "SEMANA_POSTERIOR_GCONF_CALIBREU"),
        ]
        for week_ref, method in exact_methods:
            stat = self._exact_stat(conn, pedido_id, week_ref, campana, cultivo, empresa, prefijo, grupo, calibre_u)
            if stat["samples"] > 0 and stat["price"] is not None:
                self._debug_price_logs(pedido_id, method, week_ref, stat["samples"], stat["price"], stat["sample_ids"])
                return self._result_ok(
                    method, week_ref, campana, cultivo, empresa, grupo, calibre_u, stat["samples"], stat["price"], None, None, stat["sample_ids"]
                )

        fallback_methods = [
            (semana, "MISMA_SEMANA_PROMEDIO_GRUPO_Y_CALIBRE"),
            (semana - 1, "SEMANA_ANTERIOR_PROMEDIO_GRUPO_Y_CALIBRE"),
            (semana + 1, "SEMANA_POSTERIOR_PROMEDIO_GRUPO_Y_CALIBRE"),
        ]
        for week_ref, method in fallback_methods:
            grp = self._group_stat(conn, pedido_id, week_ref, campana, cultivo, empresa, prefijo, grupo)
            cal = self._calibre_stat(conn, pedido_id, week_ref, campana, cultivo, empresa, prefijo, calibre_u)
            if grp["samples"] > 0 and cal["samples"] > 0 and grp["price"] is not None and cal["price"] is not None:
                price = (grp["price"] + cal["price"]) / 2.0
                samples = grp["samples"] + cal["samples"]
                self._debug_price_logs(pedido_id, method, week_ref, samples, price, grp["sample_ids"] + cal["sample_ids"])
                return self._result_ok(
                    method,
                    week_ref,
                    campana,
                    cultivo,
                    empresa,
                    grupo,
                    calibre_u,
                    samples,
                    price,
                    grp["price"],
                    cal["price"],
                    grp["sample_ids"] + cal["sample_ids"],
                )
            if grp["samples"] > 0 or cal["samples"] > 0:
                return self._result_none(
                    "SIN_DATOS",
                    week_ref,
                    grupo,
                    calibre_u,
                    grp["samples"] + cal["samples"],
                    grp["price"],
                    cal["price"],
                    grp["sample_ids"] + cal["sample_ids"],
                    "faltan ambas medias (grupo y calibre) en la misma semana de fallback",
                )

        # Fallback flexible final (solo si fallan 1-6):
        # busca calibre y grupo por separado (misma, anterior, posterior) y combina si ambos existen.
        cal_pick = self._pick_first_calibre(conn, pedido_id, semana, campana, cultivo, empresa, prefijo, calibre_u)
        grp_pick = self._pick_first_group(conn, pedido_id, semana, campana, cultivo, empresa, prefijo, grupo)

        if cal_pick["price"] is not None and grp_pick["price"] is not None:
            final_price = (float(cal_pick["price"]) + float(grp_pick["price"])) / 2.0
            week_label = f"C:{cal_pick['week_ref']}/G:{grp_pick['week_ref']}"
            sample_ids = cal_pick["sample_ids"] + grp_pick["sample_ids"]
            obs = (
                "metodo=FALLBACK_FLEXIBLE_CALIBRE_Y_GRUPO; "
                f"precio_calibre={self._fmt(cal_pick['price'])}; semana_calibre={cal_pick['week_ref']}; "
                f"muestras_calibre={cal_pick['samples']}; ids_calibre={','.join(cal_pick['sample_ids'][:100])}; "
                f"precio_grupo={self._fmt(grp_pick['price'])}; semana_grupo={grp_pick['week_ref']}; "
                f"muestras_grupo={grp_pick['samples']}; ids_grupo={','.join(grp_pick['sample_ids'][:100])}; "
                f"precio_final={self._fmt(final_price)}"
            )
            return {
                "price": final_price,
                "method": "FALLBACK_FLEXIBLE_CALIBRE_Y_GRUPO",
                "week_ref": cal_pick["week_ref"],
                "week_label": week_label,
                "samples": int(cal_pick["samples"]) + int(grp_pick["samples"]),
                "media_grupo": grp_pick["price"],
                "media_calibre": cal_pick["price"],
                "sample_ids": sample_ids,
                "obs": obs,
            }

        if cal_pick["price"] is not None:
            obs = (
                "metodo=FALLBACK_FLEXIBLE_SOLO_CALIBREU; "
                f"precio_calibre={self._fmt(cal_pick['price'])}; semana_calibre={cal_pick['week_ref']}; "
                f"muestras_calibre={cal_pick['samples']}; ids_calibre={','.join(cal_pick['sample_ids'][:100])}; "
                "precio_grupo=; semana_grupo=; muestras_grupo=0; ids_grupo=; "
                f"precio_final={self._fmt(cal_pick['price'])}"
            )
            return {
                "price": cal_pick["price"],
                "method": "FALLBACK_FLEXIBLE_SOLO_CALIBREU",
                "week_ref": cal_pick["week_ref"],
                "week_label": str(cal_pick["week_ref"]),
                "samples": int(cal_pick["samples"]),
                "media_grupo": None,
                "media_calibre": cal_pick["price"],
                "sample_ids": cal_pick["sample_ids"],
                "obs": obs,
            }

        if grp_pick["price"] is not None:
            obs = (
                "metodo=FALLBACK_FLEXIBLE_SOLO_GRUPO; "
                "precio_calibre=; semana_calibre=; muestras_calibre=0; ids_calibre=; "
                f"precio_grupo={self._fmt(grp_pick['price'])}; semana_grupo={grp_pick['week_ref']}; "
                f"muestras_grupo={grp_pick['samples']}; ids_grupo={','.join(grp_pick['sample_ids'][:100])}; "
                f"precio_final={self._fmt(grp_pick['price'])}"
            )
            return {
                "price": grp_pick["price"],
                "method": "FALLBACK_FLEXIBLE_SOLO_GRUPO",
                "week_ref": grp_pick["week_ref"],
                "week_label": str(grp_pick["week_ref"]),
                "samples": int(grp_pick["samples"]),
                "media_grupo": grp_pick["price"],
                "media_calibre": None,
                "sample_ids": grp_pick["sample_ids"],
                "obs": obs,
            }

        # Último fallback: calibre cercano (menor primero, luego mayor), por semana actual/anterior/posterior.
        nearest = self._fallback_nearest_calibreu(
            conn=conn,
            pedido_id=pedido_id,
            semana=semana,
            campana=campana,
            cultivo=cultivo,
            empresa=empresa,
            prefijo=prefijo,
            calibre_u_objetivo=calibre_u,
        )
        if nearest is not None:
            return nearest

        return self._result_none("SIN_DATOS", None, grupo, calibre_u, 0, None, None, [], "sin muestras para todos los métodos")

    def _pick_first_calibre(
        self,
        conn: sqlite3.Connection,
        pedido_id: Any,
        semana: int,
        campana: str,
        cultivo: str,
        empresa: str,
        prefijo: str,
        calibre_u: str,
    ) -> dict[str, Any]:
        for week_ref in [semana, semana - 1, semana + 1]:
            stat = self._calibre_stat(conn, pedido_id, week_ref, campana, cultivo, empresa, prefijo, calibre_u)
            if stat["samples"] > 0 and stat["price"] is not None:
                return {"price": stat["price"], "week_ref": week_ref, "samples": stat["samples"], "sample_ids": stat["sample_ids"]}
        return {"price": None, "week_ref": None, "samples": 0, "sample_ids": []}

    def _pick_first_group(
        self,
        conn: sqlite3.Connection,
        pedido_id: Any,
        semana: int,
        campana: str,
        cultivo: str,
        empresa: str,
        prefijo: str,
        grupo: str,
    ) -> dict[str, Any]:
        for week_ref in [semana, semana - 1, semana + 1]:
            stat = self._group_stat(conn, pedido_id, week_ref, campana, cultivo, empresa, prefijo, grupo)
            if stat["samples"] > 0 and stat["price"] is not None:
                return {"price": stat["price"], "week_ref": week_ref, "samples": stat["samples"], "sample_ids": stat["sample_ids"]}
        return {"price": None, "week_ref": None, "samples": 0, "sample_ids": []}

    def _fallback_nearest_calibreu(
        self,
        conn: sqlite3.Connection,
        pedido_id: Any,
        semana: int,
        campana: str,
        cultivo: str,
        empresa: str,
        prefijo: str,
        calibre_u_objetivo: str,
    ) -> dict[str, Any] | None:
        objetivo_num = self._to_float(calibre_u_objetivo)
        if objetivo_num is None:
            return None

        week_steps = [
            (semana, "MISMA_SEMANA"),
            (semana - 1, "SEMANA_ANTERIOR"),
            (semana + 1, "SEMANA_POSTERIOR"),
        ]

        for week_ref, suffix in week_steps:
            candidates = self._candidate_calibreus_for_week(
                conn=conn,
                pedido_id=pedido_id,
                week_ref=week_ref,
                campana=campana,
                cultivo=cultivo,
                empresa=empresa,
                prefijo=prefijo,
            )

            lower = [c for c in candidates if c["num"] < objetivo_num]
            lower.sort(key=lambda c: objetivo_num - c["num"])
            if lower:
                picked = lower[0]
                stat = self._calibre_stat(conn, pedido_id, week_ref, campana, cultivo, empresa, prefijo, picked["raw"])
                if stat["samples"] > 0 and stat["price"] is not None:
                    method = f"FALLBACK_CALIBRE_MENOR_{suffix}"
                    obs = (
                        f"metodo={method}; calibre_u_objetivo={calibre_u_objetivo}; calibre_u_usado={picked['raw']}; "
                        f"semana={week_ref}; campana={campana}; cultivo={cultivo}; empresa={empresa}; prefijo={prefijo}; "
                        f"muestras={stat['samples']}; ids={','.join(stat['sample_ids'][:100])}; precio_final={self._fmt(stat['price'])}"
                    )
                    return {
                        "price": stat["price"],
                        "method": method,
                        "week_ref": week_ref,
                        "week_label": str(week_ref),
                        "samples": int(stat["samples"]),
                        "media_grupo": None,
                        "media_calibre": stat["price"],
                        "sample_ids": stat["sample_ids"],
                        "calibre_u_usado": picked["raw"],
                        "obs": obs,
                    }

            higher = [c for c in candidates if c["num"] > objetivo_num]
            higher.sort(key=lambda c: c["num"] - objetivo_num)
            if higher:
                picked = higher[0]
                stat = self._calibre_stat(conn, pedido_id, week_ref, campana, cultivo, empresa, prefijo, picked["raw"])
                if stat["samples"] > 0 and stat["price"] is not None:
                    method = f"FALLBACK_CALIBRE_MAYOR_{suffix}"
                    obs = (
                        f"metodo={method}; calibre_u_objetivo={calibre_u_objetivo}; calibre_u_usado={picked['raw']}; "
                        f"semana={week_ref}; campana={campana}; cultivo={cultivo}; empresa={empresa}; prefijo={prefijo}; "
                        f"muestras={stat['samples']}; ids={','.join(stat['sample_ids'][:100])}; precio_final={self._fmt(stat['price'])}"
                    )
                    return {
                        "price": stat["price"],
                        "method": method,
                        "week_ref": week_ref,
                        "week_label": str(week_ref),
                        "samples": int(stat["samples"]),
                        "media_grupo": None,
                        "media_calibre": stat["price"],
                        "sample_ids": stat["sample_ids"],
                        "calibre_u_usado": picked["raw"],
                        "obs": obs,
                    }
        return None

    def _candidate_calibreus_for_week(
        self,
        conn: sqlite3.Connection,
        pedido_id: Any,
        week_ref: int,
        campana: str,
        cultivo: str,
        empresa: str,
        prefijo: str,
    ) -> list[dict[str, Any]]:
        pcols = self._get_columns(conn, self.TABLE_PEDIDOS)
        cancelado_condition = ""
        cancelado_params: list[Any] = []
        if "Cancelado" in pcols:
            cancelado_condition = ' AND p."Cancelado" = ?'
            cancelado_params = [0]
            logger.info("Filtro Cancelado=0 aplicado")
        else:
            self._warn_once("Columna Cancelado no encontrada en Pedidos")

        query = f"""
            SELECT DISTINCT d."CalibreU" AS calibre_u
            FROM "{self.TABLE_DPRECIO}" d
            JOIN "{self.TABLE_PEDIDOS}" p ON d."IdPedido" = p."IdPedidoLora"
            WHERE CAST(p."Campaña" AS TEXT) = ?
              AND CAST(p."Cultivo" AS TEXT) = ?
              AND CAST(p."EMPRESA" AS TEXT) = ?
              AND CAST(p."Semana" AS INTEGER) = ?
              AND CAST(p."IdPedidoLora" AS TEXT) LIKE ?
              AND d."IdPedido" <> ?
              AND {self._num_expr('d."PrecioO"')} > 0
              {cancelado_condition}
        """
        params: list[Any] = [campana, cultivo, empresa, week_ref, f"{prefijo}%", pedido_id] + cancelado_params
        rows = conn.execute(query, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            raw = str(row["calibre_u"] or "").strip()
            num = self._to_float(raw)
            if num is None:
                continue
            out.append({"raw": raw, "num": num})
        return out

    def _exact_stat(
        self,
        conn: sqlite3.Connection,
        pedido_id: Any,
        semana: int,
        campana: str,
        cultivo: str,
        empresa: str,
        prefijo: str,
        grupo: str,
        calibre_u: str,
    ) -> dict[str, Any]:
        pcols = self._get_columns(conn, self.TABLE_PEDIDOS)
        cancelado_condition = ""
        cancelado_params: list[Any] = []
        if "Cancelado" in pcols:
            cancelado_condition = ' AND p."Cancelado" = ?'
            cancelado_params = [0]
            logger.info("Filtro Cancelado=0 aplicado")
        else:
            self._warn_once("Columna Cancelado no encontrada en Pedidos")

        query = f"""
            SELECT
                AVG({self._num_expr('d."PrecioO"')}) AS avg_price,
                COUNT(1) AS samples,
                GROUP_CONCAT(DISTINCT CAST(d."IdPedido" AS TEXT)) AS sample_ids
            FROM "{self.TABLE_DPRECIO}" d
            JOIN "{self.TABLE_PEDIDOS}" p ON d."IdPedido" = p."IdPedidoLora"
            WHERE d."GConfeccion" = ?
              AND d."CalibreU" = ?
              {cancelado_condition}
              AND CAST(p."Campaña" AS TEXT) = ?
              AND CAST(p."Cultivo" AS TEXT) = ?
              AND CAST(p."EMPRESA" AS TEXT) = ?
              AND CAST(p."Semana" AS INTEGER) = ?
              AND CAST(p."IdPedidoLora" AS TEXT) LIKE ?
              AND d."IdPedido" <> ?
              AND {self._num_expr('d."PrecioO"')} > 0
        """
        params: list[Any] = [grupo, calibre_u] + cancelado_params + [campana, cultivo, empresa, semana, f"{prefijo}%", pedido_id]
        row = conn.execute(query, params).fetchone()
        return self._row_stat(row)

    def _group_stat(
        self,
        conn: sqlite3.Connection,
        pedido_id: Any,
        semana: int,
        campana: str,
        cultivo: str,
        empresa: str,
        prefijo: str,
        grupo: str,
    ) -> dict[str, Any]:
        pcols = self._get_columns(conn, self.TABLE_PEDIDOS)
        cancelado_condition = ""
        cancelado_params: list[Any] = []
        if "Cancelado" in pcols:
            cancelado_condition = ' AND p."Cancelado" = ?'
            cancelado_params = [0]
            logger.info("Filtro Cancelado=0 aplicado")
        else:
            self._warn_once("Columna Cancelado no encontrada en Pedidos")

        query = f"""
            SELECT
                AVG({self._num_expr('d."PrecioO"')}) AS avg_price,
                COUNT(1) AS samples,
                GROUP_CONCAT(DISTINCT CAST(d."IdPedido" AS TEXT)) AS sample_ids
            FROM "{self.TABLE_DPRECIO}" d
            JOIN "{self.TABLE_PEDIDOS}" p ON d."IdPedido" = p."IdPedidoLora"
            WHERE d."GConfeccion" = ?
              {cancelado_condition}
              AND CAST(p."Campaña" AS TEXT) = ?
              AND CAST(p."Cultivo" AS TEXT) = ?
              AND CAST(p."EMPRESA" AS TEXT) = ?
              AND CAST(p."Semana" AS INTEGER) = ?
              AND CAST(p."IdPedidoLora" AS TEXT) LIKE ?
              AND d."IdPedido" <> ?
              AND {self._num_expr('d."PrecioO"')} > 0
        """
        params: list[Any] = [grupo] + cancelado_params + [campana, cultivo, empresa, semana, f"{prefijo}%", pedido_id]
        row = conn.execute(query, params).fetchone()
        return self._row_stat(row)

    def _calibre_stat(
        self,
        conn: sqlite3.Connection,
        pedido_id: Any,
        semana: int,
        campana: str,
        cultivo: str,
        empresa: str,
        prefijo: str,
        calibre_u: str,
    ) -> dict[str, Any]:
        pcols = self._get_columns(conn, self.TABLE_PEDIDOS)
        cancelado_condition = ""
        cancelado_params: list[Any] = []
        if "Cancelado" in pcols:
            cancelado_condition = ' AND p."Cancelado" = ?'
            cancelado_params = [0]
            logger.info("Filtro Cancelado=0 aplicado")
        else:
            self._warn_once("Columna Cancelado no encontrada en Pedidos")

        query = f"""
            SELECT
                AVG({self._num_expr('d."PrecioO"')}) AS avg_price,
                COUNT(1) AS samples,
                GROUP_CONCAT(DISTINCT CAST(d."IdPedido" AS TEXT)) AS sample_ids
            FROM "{self.TABLE_DPRECIO}" d
            JOIN "{self.TABLE_PEDIDOS}" p ON d."IdPedido" = p."IdPedidoLora"
            WHERE d."CalibreU" = ?
              {cancelado_condition}
              AND CAST(p."Campaña" AS TEXT) = ?
              AND CAST(p."Cultivo" AS TEXT) = ?
              AND CAST(p."EMPRESA" AS TEXT) = ?
              AND CAST(p."Semana" AS INTEGER) = ?
              AND CAST(p."IdPedidoLora" AS TEXT) LIKE ?
              AND d."IdPedido" <> ?
              AND {self._num_expr('d."PrecioO"')} > 0
        """
        params: list[Any] = [calibre_u] + cancelado_params + [campana, cultivo, empresa, semana, f"{prefijo}%", pedido_id]
        row = conn.execute(query, params).fetchone()
        return self._row_stat(row)

    @staticmethod
    def _row_stat(row: sqlite3.Row | None) -> dict[str, Any]:
        if not row:
            return {"price": None, "samples": 0, "sample_ids": []}
        sample_ids = str(row["sample_ids"] or "").strip()
        parsed_ids = [s for s in sample_ids.split(",") if s]
        price = PreciosOrientativosRepository._to_float(row["avg_price"])
        samples = int(row["samples"] or 0)
        return {"price": price, "samples": samples, "sample_ids": parsed_ids}

    def _result_ok(
        self,
        method: str,
        week_ref: int,
        campana: str,
        cultivo: str,
        empresa: str,
        grupo: str,
        calibre_u: str,
        samples: int,
        price: float,
        media_grupo: float | None,
        media_calibre: float | None,
        sample_ids: list[str],
    ) -> dict[str, Any]:
        obs = (
            f"metodo={method}; campana={campana}; cultivo={cultivo}; empresa={empresa}; semana={week_ref}; "
            f"gconf={grupo}; calibre_u={calibre_u}; muestras={samples}; media_grupo={self._fmt(media_grupo)}; "
            f"media_calibre={self._fmt(media_calibre)}; ids={','.join(sample_ids[:100])}"
        )
        return {
            "price": price,
            "method": method,
            "week_ref": week_ref,
            "samples": samples,
            "media_grupo": media_grupo,
            "media_calibre": media_calibre,
            "sample_ids": sample_ids,
            "obs": obs,
        }

    def _result_none(
        self,
        method: str,
        week_ref: int | None,
        grupo: str,
        calibre_u: str,
        samples: int,
        media_grupo: float | None,
        media_calibre: float | None,
        sample_ids: list[str],
        reason: str,
    ) -> dict[str, Any]:
        obs = (
            f"metodo={method}; semana={week_ref}; gconf={grupo}; calibre_u={calibre_u}; "
            f"muestras={samples}; media_grupo={self._fmt(media_grupo)}; media_calibre={self._fmt(media_calibre)}; "
            f"ids={','.join(sample_ids[:100])}; motivo={reason}"
        )
        return {
            "price": None,
            "method": method,
            "week_ref": week_ref,
            "samples": samples,
            "media_grupo": media_grupo,
            "media_calibre": media_calibre,
            "sample_ids": sample_ids,
            "obs": obs,
        }

    def _set_not_estimated(self, row: dict[str, Any], method: str, reason: str) -> None:
        row["EurosOrientativosCalc"] = None
        row["Metodo"] = method
        row["MuestrasUsadas"] = 0
        row["MediaGrupo"] = None
        row["MediaCalibre"] = None
        row["SemanaPrecioUsada"] = None
        row["CalibreUUsado"] = ""
        row["Observaciones"] = reason

    def _build_where(self, filters: dict[str, Any], cols: set[str]) -> tuple[str, list[Any], list[str], dict[str, str]]:
        clauses: list[str] = []
        params: list[Any] = []
        warnings: list[str] = []
        applied: dict[str, str] = {}

        built_where, built_params = build_pedidos_where(filters, alias="", include_base=False)
        mapped_clauses = []
        if built_where.startswith("WHERE "):
            mapped_clauses = built_where[6:].split(" AND ")
        mapped_params = built_params

        for raw_clause, param in zip(mapped_clauses, mapped_params):
            col = raw_clause.split('"')[1] if '"' in raw_clause else ""
            if col not in cols:
                warnings.append(f"Filtro no disponible: {col}")
                self._warn_once(f"Columna faltante para filtro: {col}")
                continue
            clauses.append(raw_clause.replace('."','"').replace('""','"'))
            params.append(param)
            applied[col] = str(param)
        return " AND ".join(clauses), params, warnings, applied

    def _load_confecciones(self, conn: sqlite3.Connection) -> dict[str, str]:
        cols = self._get_columns(conn, self.TABLE_CONFECCIONES)
        if not {"CODIGO", "GRUPO"}.issubset(cols):
            self._warn_once("MConfecciones sin CODIGO/GRUPO")
            return {}
        rows = conn.execute(f'SELECT "CODIGO", "GRUPO" FROM "{self.TABLE_CONFECCIONES}"').fetchall()
        return {str(r["CODIGO"]).strip(): str(r["GRUPO"]).strip() for r in rows}

    def _load_calibres(self, conn: sqlite3.Connection) -> dict[tuple[str, str], str]:
        cols = self._get_columns(conn, self.TABLE_CALIBRE)
        if not {"Calibre", "CULTIVO", "CalibreU"}.issubset(cols):
            self._warn_once("MCalibre sin Calibre/CULTIVO/CalibreU")
            return {}
        rows = conn.execute(f'SELECT "Calibre", "CULTIVO", "CalibreU" FROM "{self.TABLE_CALIBRE}"').fetchall()
        out: dict[tuple[str, str], str] = {}
        for r in rows:
            out[(str(r["Calibre"]).strip(), str(r["CULTIVO"]).strip())] = str(r["CalibreU"]).strip()
        return out

    def _load_empresas_dict(self) -> tuple[dict[str, str], str | None]:
        if not self.db_fruta_path.exists():
            msg = f"No se encontrÃ³ DBfruta.sqlite: {self.db_fruta_path}"
            logger.warning(msg)
            return {}, msg
        try:
            conn = sqlite3.connect(self.db_fruta_path)
            conn.row_factory = sqlite3.Row
            with conn:
                cols = self._get_columns(conn, "Empresa")
                if "IdEmpresa" not in cols:
                    return {}, "Tabla Empresa sin IdEmpresa."
                if "Nombre" not in cols:
                    return {}, "Tabla Empresa sin columna Nombre."
                rows = conn.execute('SELECT "IdEmpresa", "Nombre" AS nombre FROM "Empresa"').fetchall()
                return {str(r["IdEmpresa"]).strip(): str(r["nombre"] or "").strip() for r in rows}, None
        except Exception as exc:
            logger.exception("Error cargando empresas: %s", exc)
            return {}, "No se pudo cargar nombres de empresa."

    def _load_grupos_varietales(self) -> tuple[dict[tuple[str, str], str], str | None]:
        if not self.db_fruta_path.exists():
            return {}, "Filtro Grupo varietal no disponible"
        try:
            conn = sqlite3.connect(self.db_fruta_path)
            conn.row_factory = sqlite3.Row
            with conn:
                cols = self._get_columns(conn, "MVariedad")
                if not {"Variedad", "CULTIVO"}.issubset(cols):
                    return {}, "Filtro Grupo varietal no disponible"
                if "GRUPO" not in cols:
                    return {}, "Filtro Grupo varietal no disponible"
                has_subgrupo = "SUBGRUPO" in cols
                query = 'SELECT "Variedad", "CULTIVO", "GRUPO"'
                if has_subgrupo:
                    query += ', "SUBGRUPO"'
                query += ' FROM "MVariedad"'
                rows = conn.execute(query).fetchall()
                out: dict[tuple[str, str], str] = {}
                for r in rows:
                    grupo = str(r["GRUPO"] or "").strip()
                    if has_subgrupo:
                        sub = str(r["SUBGRUPO"] or "").strip()
                        grupo = f"{grupo} {sub}".strip()
                    out[(str(r["Variedad"] or "").strip(), str(r["CULTIVO"] or "").strip())] = grupo
                return out, None
        except Exception:
            return {}, "Filtro Grupo varietal no disponible"

    def _estado_precio(self, row: dict[str, Any]) -> str:
        metodo = str(row.get("Metodo") or "")
        original = self._to_float(row.get("EurosOrientativos"))
        calc = self._to_float(row.get("EurosOrientativosCalc"))
        if original is not None and original > 0:
            return "CON_ORIGINAL"
        if calc is not None and calc > 0:
            return "ESTIMADO_GUARDADO"
        if metodo.startswith("ERROR_"):
            return "ERROR_DATOS"
        if metodo == "SIN_DATOS":
            return "SIN_DATOS"
        return "SIN_PRECIO"

    @staticmethod
    def _num_expr(column_sql: str) -> str:
        return f'CAST(REPLACE(TRIM(COALESCE({column_sql}, "")), ",", ".") AS REAL)'

    @staticmethod
    def _extract_prefix(pedido_id: str) -> str:
        m = re.match(r"^([A-Za-z]+)", pedido_id.strip())
        return m.group(1) if m else ""

    def _debug_price_logs(self, pedido_id: Any, method: str, week: int, samples: int, price: float, sample_ids: list[str]) -> None:
        logger.info(
            "Estimacion pedido=%s metodo=%s semana=%s muestras=%s precio=%.4f ids=%s",
            pedido_id,
            method,
            week,
            samples,
            price,
            ",".join(sample_ids[:50]),
        )
        if abs(price - 1.26) < 0.001:
            logger.warning(
                "Caso 1.26 detectado pedido=%s metodo=%s semana=%s muestras=%s ids=%s",
                pedido_id,
                method,
                week,
                samples,
                ",".join(sample_ids[:100]),
            )

    @staticmethod
    def _fmt(value: float | None) -> str:
        return "" if value is None else f"{value:.4f}"

    def _warn_once(self, msg: str) -> None:
        if msg in self._warned:
            return
        self._warned.add(msg)
        logger.warning(msg)

    def _cancelado_filter_for_pedidos(self, cols: set[str]) -> tuple[str, list[Any]]:
        if "Cancelado" in cols:
            base, base_params = pedidos_base_where(alias="")
            logger.info("Filtro Cancelado=0 aplicado")
            return '"Cancelado" = ?', (base_params or [0])
        self._warn_once("Columna Cancelado no encontrada en Pedidos")
        return "", []


    @staticmethod
    def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        try:
            rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            return {str(r["name"]) for r in rows}
        except Exception:
            return set()

    def _connect(self) -> sqlite3.Connection:
        logger.info("Abriendo DBPedidos.sqlite sin URI: %s", self.db_path)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (float, int)):
            return float(value)
        try:
            return float(str(value).strip().replace(",", "."))
        except Exception:
            return None

    @staticmethod
    def _first_filter_value(raw: Any) -> str:
        if raw is None:
            return ""
        if isinstance(raw, list):
            for item in raw:
                val = str(item or "").strip()
                if val:
                    return val
            return ""
        return str(raw or "").strip()

    @staticmethod
    def _to_int(value: Any, default: int | None = None) -> int | None:
        try:
            return int(float(str(value).strip()))
        except Exception:
            return default
