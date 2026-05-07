from typing import Any

from db.precios_orientativos_repository import PreciosOrientativosRepository


class PreciosOrientativosService:
    METHOD_ORDER = [
        "ORIGINAL",
        "MISMA_SEMANA_GCONF_CALIBREU",
        "SEMANA_ANTERIOR_GCONF_CALIBREU",
        "SEMANA_POSTERIOR_GCONF_CALIBREU",
        "MISMA_SEMANA_PROMEDIO_GRUPO_Y_CALIBRE",
        "SEMANA_ANTERIOR_PROMEDIO_GRUPO_Y_CALIBRE",
        "SEMANA_POSTERIOR_PROMEDIO_GRUPO_Y_CALIBRE",
        "FALLBACK_FLEXIBLE_CALIBRE_Y_GRUPO",
        "FALLBACK_FLEXIBLE_SOLO_CALIBREU",
        "FALLBACK_FLEXIBLE_SOLO_GRUPO",
        "FALLBACK_CALIBRE_MENOR_MISMA_SEMANA",
        "FALLBACK_CALIBRE_MENOR_SEMANA_ANTERIOR",
        "FALLBACK_CALIBRE_MENOR_SEMANA_POSTERIOR",
        "FALLBACK_CALIBRE_MAYOR_MISMA_SEMANA",
        "FALLBACK_CALIBRE_MAYOR_SEMANA_ANTERIOR",
        "FALLBACK_CALIBRE_MAYOR_SEMANA_POSTERIOR",
        "SIN_DATOS",
        "ERROR_MAESTRO_CONFECCION",
        "ERROR_MAESTRO_CALIBRE",
    ]
    NO_DATA_METHODS = {"SIN_DATOS", "SIN_DATOS_COMPLETOS", "ERROR_MAESTRO_CONFECCION", "ERROR_MAESTRO_CALIBRE"}

    def __init__(self, repository: PreciosOrientativosRepository | None = None) -> None:
        self.repository = repository or PreciosOrientativosRepository()

    def init_schema(self) -> list[str]:
        return self.repository.ensure_columns()

    def buscar_pendientes(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        return self.repository.fetch_pending(filters)

    def buscar_para_recalculo(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        return self.repository.fetch_for_recalculation(filters)

    def calcular_estimaciones(self, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        return self.repository.calculate_estimations(rows)

    def guardar_estimaciones(self, rows: list[dict[str, Any]]) -> tuple[int, list[str]]:
        return self.repository.save_estimations(rows)

    def eliminar_calculos_guardados(self, filters: dict[str, Any]) -> int:
        return self.repository.calc_repo.delete_calculations_by_filters(filters)

    def generar_resumen_estimaciones(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        counts = {m: 0 for m in self.METHOD_ORDER}
        con_precio = 0

        for row in rows:
            method = str(row.get("Metodo") or "SIN_DATOS")
            calc = self._to_float(row.get("EurosOrientativosCalc"))
            if method not in counts:
                counts[method] = 0
            counts[method] += 1

            if method == "ORIGINAL":
                con_precio += 1
            elif method not in self.NO_DATA_METHODS and calc is not None and calc > 0:
                con_precio += 1

        resumen = []
        for method in self.METHOD_ORDER + [m for m in counts.keys() if m not in self.METHOD_ORDER]:
            qty = counts.get(method, 0)
            if qty == 0 and method not in self.METHOD_ORDER:
                continue
            pct = (qty / total * 100.0) if total else 0.0
            resumen.append({"metodo": method, "cantidad": qty, "porcentaje": pct})

        cobertura = (con_precio / total * 100.0) if total else 0.0
        return {"total": total, "con_precio": con_precio, "cobertura": cobertura, "resumen": resumen}

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).strip().replace(",", "."))
        except Exception:
            return None
