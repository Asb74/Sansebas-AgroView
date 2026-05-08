from typing import Any

from db.comercial_repository import ComercialRepository


class ComercialService:
    def __init__(self, repository: ComercialRepository | None = None) -> None:
        self.repository = repository or ComercialRepository()
        self._cache_key: tuple[tuple[str, str], ...] | None = None
        self._cache_value: dict[str, Any] | None = None
        self._precios_cache_key: tuple[tuple[str, str], ...] | None = None
        self._precios_cache_value: dict[str, Any] | None = None
        self._clientes_cache_key: tuple[tuple[str, str], ...] | None = None
        self._clientes_cache_value: dict[str, Any] | None = None
        self._reclam_cache_key: tuple[tuple[str, str], ...] | None = None
        self._reclam_cache_value: dict[str, Any] | None = None
        self._filter_options_cache: dict[tuple[tuple[tuple[str, str], ...], str], list[str]] = {}
        self._desv_clientes_cache_key: tuple[tuple[str, str], ...] | None = None
        self._desv_clientes_cache_value: dict[str, Any] | None = None

    def get_resumen_comercial(self, filters: dict[str, Any]) -> dict[str, Any]:
        key = tuple(sorted((k, str(v or "").strip()) for k, v in filters.items()))
        if self._cache_key == key and self._cache_value is not None:
            return self._cache_value

        payload = self.repository.get_resumen(filters)
        empresas_dict, empresa_warning = self.repository.load_empresas_dict()
        if empresa_warning:
            payload["warnings"].append(empresa_warning)

        kpis = self._enrich_metrics(payload.get("kpis", {}))

        grouped = payload.get("grouped", {})
        grouped_out: dict[str, list[dict[str, Any]]] = {}
        for key, rows in grouped.items():
            parsed_rows = [self._enrich_metrics(row) for row in rows]
            if key == "empresa":
                for row in parsed_rows:
                    rid = str(row.get("grupo", "")).strip()
                    if rid in empresas_dict and empresas_dict[rid]:
                        row["grupo"] = f"{rid} - {empresas_dict[rid]}"
            grouped_out[key] = parsed_rows

        out = {"kpis": kpis, "grouped": grouped_out, "warnings": payload.get("warnings", [])}
        self._cache_key = key
        self._cache_value = out
        return out

    def clear_cache(self) -> None:
        self._cache_key = None
        self._cache_value = None
        self._precios_cache_key = None
        self._precios_cache_value = None
        self._clientes_cache_key = None
        self._clientes_cache_value = None
        self._reclam_cache_key = None
        self._reclam_cache_value = None
        self._desv_clientes_cache_key = None
        self._desv_clientes_cache_value = None
        self._filter_options_cache = {}

    def get_analisis_precios(self, filters: dict[str, Any]) -> dict[str, Any]:
        key = tuple(sorted((k, str(v or "").strip()) for k, v in filters.items()))
        if self._precios_cache_key == key and self._precios_cache_value is not None:
            return self._precios_cache_value

        payload = self.repository.get_analisis_precios(filters)
        out = {
            "kpis_precios": self._enrich_metrics(payload.get("kpis_precios", {})),
            "evolucion_semanal": [self._enrich_metrics(row) for row in payload.get("evolucion_semanal", [])],
            "precios_por_variedad_calibre": [self._enrich_metrics(row) for row in payload.get("precios_por_variedad_calibre", [])],
            "warnings": payload.get("warnings", []),
        }
        self._precios_cache_key = key
        self._precios_cache_value = out
        return out

    def get_analisis_clientes(self, filters: dict[str, Any]) -> dict[str, Any]:
        key = tuple(sorted((k, str(v or "").strip()) for k, v in filters.items()))
        if self._clientes_cache_key == key and self._clientes_cache_value is not None:
            return self._clientes_cache_value

        payload = self.repository.get_analisis_clientes(filters)
        out = {
            "kpis": self._enrich_metrics(payload.get("kpis", {})),
            "ranking": [self._enrich_metrics(row) for row in payload.get("ranking", [])],
            "evolucion": [self._enrich_metrics(row) for row in payload.get("evolucion", [])],
            "grafica_clientes": [dict(row) for row in payload.get("grafica_clientes", [])],
            "warnings": payload.get("warnings", []),
        }
        self._clientes_cache_key = key
        self._clientes_cache_value = out
        return out

    def get_filter_options(self, filters: dict[str, Any], target_filter: str) -> list[str]:
        normalized_key = tuple(sorted((k, ",".join(sorted(self._as_list(v)))) for k, v in filters.items()))
        cache_key = (normalized_key, target_filter)
        if cache_key in self._filter_options_cache:
            return self._filter_options_cache[cache_key]
        options = self.repository.get_filter_options(filters, target_filter)
        self._filter_options_cache[cache_key] = options
        return options

    def get_analisis_reclamaciones(self, filters: dict[str, Any]) -> dict[str, Any]:
        key = tuple(sorted((k, str(v or "").strip()) for k, v in filters.items()))
        if self._reclam_cache_key == key and self._reclam_cache_value is not None:
            return self._reclam_cache_value

        payload = self.repository.get_analisis_reclamaciones(filters)
        resumen = dict(payload.get("resumen", {}))
        pedidos_reclamados = float(resumen.get("pedidos_reclamados") or 0)
        total_pedidos = float(resumen.get("total_pedidos_filtrados") or 0)
        importe_reclamado = float(resumen.get("importe_reclamado") or 0)
        total_importe_real = float(resumen.get("total_importe_real_filtrado") or 0)
        resumen["pct_pedidos_reclamados"] = (pedidos_reclamados / total_pedidos * 100.0) if total_pedidos else 0.0
        resumen["pct_importe_reclamado"] = (importe_reclamado / total_importe_real * 100.0) if total_importe_real else 0.0

        out = {
            "kpis": resumen,
            "resumen": resumen,
            "detalle": [dict(r) for r in payload.get("detalle", [])],
            "por_causa": [dict(r) for r in payload.get("por_causa", [])],
            "por_cliente": [dict(r) for r in payload.get("por_cliente", [])],
            "grafica_causas": [dict(r) for r in payload.get("grafica_causas", [])],
            "warnings": payload.get("warnings", []),
        }
        self._reclam_cache_key = key
        self._reclam_cache_value = out
        return out

    def get_desviacion_clientes(self, filters: dict[str, Any]) -> dict[str, Any]:
        key = tuple(sorted((k, str(v or "").strip()) for k, v in filters.items()))
        if self._desv_clientes_cache_key == key and self._desv_clientes_cache_value is not None:
            return self._desv_clientes_cache_value

        payload = self.repository.get_desviacion_clientes(filters)
        # Importante: no pasar por _enrich_metrics aquí para no sobrescribir
        # precio_medio_real/precio_referencia específicos de la desviación.
        rows = [dict(r) for r in payload.get("rows", [])]
        sort_key = str(filters.get("desv_sort_by") or "indice_cliente")
        for row in rows:
            row["cumplimiento_pct"] = (
                (float(row.get("precio_medio_real") or 0) / float(row.get("precio_referencia_ajustado") or 0) * 100.0)
                if float(row.get("precio_referencia_ajustado") or 0) > 0
                else 0.0
            )
            row["dif_precio_eurkg"] = float(row.get("desviacion_eurkg") or 0)
            row["coste_forfait_eurkg"] = float(row.get("coste_total_forfait_eurkg") or 0) if row.get("coste_total_forfait_eurkg") is not None else None
            row["margen_eurkg"] = float(row.get("margen_industrial_eurkg") or 0) if row.get("coste_total_forfait_eurkg") is not None else None
            row["margen_total_eur"] = float(row.get("margen_industrial_eurkg") or 0) * float(row.get("kg_forfait_validado") or 0) if row.get("coste_total_forfait_eurkg") is not None else 0.0
            row["cobertura_forfait_pct"] = float(row.get("pct_cobertura_forfait") or 0)
            row["n_reclamaciones"] = int(row.get("pedidos_reclamados") or 0)
            row["importe_reclamado_eur"] = float(row.get("importe_reclamado") or 0)
            kg_cliente = float(row.get("kg_cliente") or 0)
            pedidos_count = float(row.get("pedidos_count") or 0)
            importe_real = float(row.get("importe_real") or 0)
            row["reclamaciones_por_pedido"] = (row["n_reclamaciones"] / pedidos_count) if pedidos_count else 0.0
            row["reclamaciones_por_100k_kg"] = (row["n_reclamaciones"] / kg_cliente * 100000.0) if kg_cliente else 0.0
            row["reclamado_eurkg"] = (row["importe_reclamado_eur"] / kg_cliente) if kg_cliente else 0.0
            row["pct_reclamado_ventas"] = (row["importe_reclamado_eur"] / importe_real * 100.0) if importe_real else 0.0
            row["penalizacion_reclamaciones_eurkg"] = row["reclamado_eurkg"]
            row["margen_ajustado_eurkg"] = (float(row.get("margen_eurkg") or 0) - row["penalizacion_reclamaciones_eurkg"]) if row.get("margen_eurkg") is not None else -row["penalizacion_reclamaciones_eurkg"]
            row["margen_ajustado_total_eur"] = row["margen_ajustado_eurkg"] * kg_cliente
            row["estado"] = "REVISAR"
        max_kg = max((float(r.get("kg_cliente") or 0) for r in rows), default=0.0)
        penalizaciones = [float(r.get("penalizacion_reclamaciones_eurkg") or 0) for r in rows]
        max_pen = max(penalizaciones) if penalizaciones else 0.0
        min_pen = min(penalizaciones) if penalizaciones else 0.0
        max_margen_adj = max((float(r.get("margen_ajustado_eurkg") or 0) for r in rows), default=0.0)
        min_margen_adj = min((float(r.get("margen_ajustado_eurkg") or 0) for r in rows), default=0.0)
        margen_span = max(max_margen_adj - min_margen_adj, 0.0)
        pen_span = max(max_pen - min_pen, 0.0)
        for row in rows:
            margen_adj = float(row.get("margen_ajustado_eurkg") or 0)
            cumplimiento = float(row.get("cumplimiento_pct") or 0)
            kg_cliente = float(row.get("kg_cliente") or 0)
            penalizacion = float(row.get("penalizacion_reclamaciones_eurkg") or 0)
            indice_margen = ((margen_adj - min_margen_adj) / margen_span * 100.0) if margen_span > 0 else 100.0
            indice_cumplimiento = min(max(cumplimiento, 0.0), 120.0) / 120.0 * 100.0
            indice_volumen = (kg_cliente / max_kg * 100.0) if max_kg > 0 else 0.0
            indice_reclamaciones = 100.0 - (((penalizacion - min_pen) / pen_span * 100.0) if pen_span > 0 else 0.0)
            indice = (indice_margen * 0.50) + (indice_cumplimiento * 0.20) + (indice_volumen * 0.15) + (indice_reclamaciones * 0.15)
            row["indice_cliente"] = max(0.0, min(100.0, indice))
            row["estado"] = self._resolve_estado(row)

        rows_sorted = sorted(rows, key=lambda r: self._ranking_value(r, sort_key), reverse=True)
        for idx, row in enumerate(rows_sorted, start=1):
            row["ranking_posicion"] = idx
            row["ranking_tipo"] = row.get("estado", "REVISAR")
        ajustables = [
            row for row in rows_sorted
            if row.get("impacto_ajustado_eur") is not None and str(row.get("estado_forfait") or "") != "SIN_FORFAIT"
        ]
        ajustables.sort(key=lambda r: float(r.get("impacto_ajustado_eur") or 0), reverse=True)
        for idx, row in enumerate(ajustables, start=1):
            row["ranking_ajustado"] = idx
        kpis_forfait = self._build_forfait_kpis(rows_sorted)
        warnings = list(payload.get("warnings", []))
        if kpis_forfait["kg_sin_forfait"] > 0:
            warnings.append(
                f"Forfait sin cobertura: {kpis_forfait['kg_sin_forfait']:,.2f} kg sin coste importado por IdConfeccion."
            )
        out = {
            "rows": rows_sorted,
            "grafica": [dict(r) for r in rows_sorted[:15]],
            "top_buenos": [dict(r) for r in rows_sorted if float(r.get("margen_total_eur", 0) or 0) > 0][:15],
            "top_malos": [dict(r) for r in sorted(rows_sorted, key=lambda r: float(r.get("margen_total_eur", 0) or 0)) if float(r.get("margen_total_eur", 0) or 0) < 0][:15],
            "kpis_forfait": kpis_forfait,
            "warnings": warnings,
        }
        self._desv_clientes_cache_key = key
        self._desv_clientes_cache_value = out
        return out

    @staticmethod
    def _build_forfait_kpis(rows: list[dict[str, Any]]) -> dict[str, float]:
        kg_total = sum(float(r.get("kg_cliente") or 0) for r in rows)
        kg_forfait = sum(float(r.get("kg_forfait_validado") or 0) for r in rows)
        kg_sin = max(kg_total - kg_forfait, 0.0)
        coste_total = sum(float(r.get("coste_total_forfait_total_eur") or 0) for r in rows if r.get("coste_total_forfait_total_eur") is not None)
        importe_real_total = sum(float(r.get("importe_real") or 0) for r in rows)
        importe_orient_total = sum(float(r.get("precio_referencia_ajustado") or 0) * float(r.get("kg_cliente") or 0) for r in rows)
        margen_total = sum(float(r.get("margen_total_eur") or 0) for r in rows)
        n_reclamaciones = sum(int(r.get("n_reclamaciones") or 0) for r in rows)
        importe_reclamado_total = sum(float(r.get("importe_reclamado_eur") or 0) for r in rows)
        margen_ajustado_total = sum(float(r.get("margen_ajustado_total_eur") or 0) for r in rows)
        return {
            "kg_analizados": kg_total,
            "kg_con_forfait": kg_forfait,
            "kg_sin_forfait": kg_sin,
            "cobertura_forfait_pct": (kg_forfait / kg_total * 100.0) if kg_total else 0.0,
            "precio_real_medio_eurkg": (importe_real_total / kg_total) if kg_total else 0.0,
            "precio_orientativo_medio_eurkg": (importe_orient_total / kg_total) if kg_total else 0.0,
            "dif_media_eurkg": ((importe_real_total - importe_orient_total) / kg_total) if kg_total else 0.0,
            "coste_forfait_medio_eurkg": (coste_total / kg_forfait) if kg_forfait else 0.0,
            "margen_medio_eurkg": (margen_total / kg_forfait) if kg_forfait else 0.0,
            "margen_total_eur": margen_total,
            "n_reclamaciones": n_reclamaciones,
            "importe_reclamado_total_eur": importe_reclamado_total,
            "reclamaciones_por_100k_kg": (n_reclamaciones / kg_total * 100000.0) if kg_total else 0.0,
            "reclamado_medio_eurkg": (importe_reclamado_total / kg_total) if kg_total else 0.0,
            "margen_ajustado_total_eur": margen_ajustado_total,
        }

    @staticmethod
    def _ranking_value(row: dict[str, Any], sort_key: str) -> float:
        mapping = {
            "margen_total_eur": "margen_total_eur",
            "margen_eurkg": "margen_eurkg",
            "cumplimiento_pct": "cumplimiento_pct",
            "kg": "kg_cliente",
            "dif_precio_eurkg": "dif_precio_eurkg",
            "indice_cliente": "indice_cliente",
            "margen_ajustado_total": "margen_ajustado_total_eur",
            "margen_ajustado_eurkg": "margen_ajustado_eurkg",
            "reclamado_eurkg": "reclamado_eurkg",
            "n_reclamaciones": "n_reclamaciones",
        }
        return float(row.get(mapping.get(sort_key, "margen_total_eur")) or 0)

    @staticmethod
    def _resolve_estado(row: dict[str, Any]) -> str:
        kg_forfait = float(row.get("kg_forfait_validado") or 0)
        kg_sin = float(row.get("kg_sin_forfait") or 0)
        cobertura = float(row.get("pct_cobertura_forfait") or 0)
        margen_ajustado = float(row.get("margen_ajustado_eurkg") or 0)
        cumplimiento = float(row.get("cumplimiento_pct") or 0)
        precio_ref = float(row.get("precio_referencia_ajustado") or 0)
        recl_rate = float(row.get("reclamaciones_por_100k_kg") or 0)
        if kg_forfait <= 0:
            return "SIN_FORFAIT"
        if precio_ref <= 0:
            return "REVISAR"
        if cobertura < 100:
            return "PARCIAL"
        if margen_ajustado < 0 or cumplimiento < 95 or recl_rate >= 12:
            return "MALO"
        if margen_ajustado > 0 and cumplimiento >= 100 and cobertura >= 95 and recl_rate < 4:
            return "BUENO"
        if margen_ajustado > 0 and cumplimiento >= 95 and recl_rate < 12:
            return "ACEPTABLE"
        if kg_sin > 0:
            return "PARCIAL"
        return "REVISAR"

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        try:
            return [str(v) for v in value if str(v).strip()]
        except TypeError:
            return [str(value)]

    @staticmethod
    def _enrich_metrics(source: dict[str, Any]) -> dict[str, Any]:
        out = dict(source)
        kg_cliente = float(out.get("kg_cliente") or 0)
        kg_coop = float(out.get("kg_cooperativa") or 0)
        merma_kg = float(out.get("merma_kg") or (kg_cliente - kg_coop))
        cajas = float(out.get("cajas") or 0)
        has_weight_debug = "debug_suma_ponderada_euroskg" in out or "debug_importe_total" in out
        kg_precio_real = float(out.get("debug_kg_euroskg_valido") or out.get("debug_kg_precio_real") or 0)
        suma_ponderada_real = float(
            out.get("debug_suma_ponderada_euroskg")
            or out.get("debug_importe_total")
            or out.get("importe_real")
            or 0
        )
        precio_real = (suma_ponderada_real / kg_precio_real) if kg_precio_real else float(out.get("precio_medio_real") or 0)
        importe_real = suma_ponderada_real if has_weight_debug else float(out.get("importe_real") or 0)
        importe_orient = float(out.get("importe_orientativo") or 0)

        precio_orient = (importe_orient / kg_cliente) if kg_cliente else 0.0
        porcentaje_merma = (merma_kg / kg_cliente) if kg_cliente else 0.0

        out["kg_cliente"] = kg_cliente
        out["kg_cooperativa"] = kg_coop
        out["merma_kg"] = merma_kg
        out["pct_merma"] = porcentaje_merma
        out["cajas"] = cajas
        out["precio_medio_real"] = precio_real
        out["precio_medio_orientativo"] = precio_orient
        out["diferencia_media_eurkg"] = precio_real - precio_orient
        out["importe_real"] = importe_real
        out["importe_orientativo"] = importe_orient
        out["desviacion_total_eur"] = importe_real - importe_orient
        out["debug_kg_total"] = float(out.get("debug_kg_total") or kg_cliente or 0)
        out["debug_kg_euroskg_valido"] = kg_precio_real
        out["debug_kg_precio_real"] = kg_precio_real
        out["debug_suma_ponderada_euroskg"] = suma_ponderada_real
        out["debug_importe_total"] = suma_ponderada_real
        out["debug_precio_real_calculado"] = precio_real
        out["debug_precio_medio_real"] = precio_real
        out["pedidos_count"] = int(out.get("pedidos_count") or 0)
        out["pedidos_reclamados"] = int(out.get("pedidos_reclamados") or 0)
        out["importe_reclamado"] = float(out.get("importe_reclamado") or 0)
        out["pedidos_orientativo_original"] = int(out.get("pedidos_orientativo_original") or 0)
        out["pedidos_orientativo_estimado"] = int(out.get("pedidos_orientativo_estimado") or 0)
        out["pedidos_orientativo_sin_datos"] = int(out.get("pedidos_orientativo_sin_datos") or 0)
        out["pct_cobertura_orientativo"] = float(out.get("pct_cobertura_orientativo") or 0)
        out["originales"] = int(out.get("originales") or 0)
        out["estimados"] = int(out.get("estimados") or 0)
        out["sin_datos"] = int(out.get("sin_datos") or 0)
        return out
