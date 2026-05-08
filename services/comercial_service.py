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
        rows_sorted = sorted(rows, key=lambda r: float(r.get("impacto_eur", 0) or 0), reverse=True)
        for idx, row in enumerate(rows_sorted, start=1):
            row["ranking_posicion"] = idx
            impacto = float(row.get("impacto_eur", 0) or 0)
            if impacto > 0:
                row["ranking_tipo"] = "BUENO"
            elif impacto < 0:
                row["ranking_tipo"] = "MALO"
            else:
                row["ranking_tipo"] = "NEUTRO"
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
            "top_buenos": [dict(r) for r in rows_sorted if float(r.get("impacto_eur", 0) or 0) > 0][:15],
            "top_malos": [dict(r) for r in sorted(rows_sorted, key=lambda r: float(r.get("impacto_eur", 0) or 0)) if float(r.get("impacto_eur", 0) or 0) < 0][:15],
            "kpis_forfait": kpis_forfait,
            "warnings": warnings,
        }
        self._desv_clientes_cache_key = key
        self._desv_clientes_cache_value = out
        return out

    @staticmethod
    def _build_forfait_kpis(rows: list[dict[str, Any]]) -> dict[str, float]:
        kg_total = sum(float(r.get("debug_kg_euroskg_valido") or 0) for r in rows)
        kg_forfait = sum(float(r.get("kg_forfait_validado") or 0) for r in rows)
        kg_sin = max(kg_total - kg_forfait, 0.0)
        coste_total = sum(float(r.get("coste_total_forfait_total_eur") or 0) for r in rows)
        impacto_ajustado = sum(
            float(r.get("impacto_ajustado_eur") or 0)
            for r in rows
            if r.get("impacto_ajustado_eur") is not None
        )
        return {
            "kg_con_forfait_validado": kg_forfait,
            "kg_sin_forfait": kg_sin,
            "pct_cobertura_forfait": (kg_forfait / kg_total * 100.0) if kg_total else 0.0,
            "coste_confeccion_estimado_total": coste_total,
            "impacto_ajustado_total": impacto_ajustado,
        }

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
