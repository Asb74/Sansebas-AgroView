from typing import Any
from datetime import datetime
from pathlib import Path
import statistics

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
    ESTADOS_PRECIO = ["TODOS", "SIN_PRECIO", "CON_PRECIO", "ESTIMADO", "ORIGINAL"]

    def __init__(self, repository: PreciosOrientativosRepository | None = None) -> None:
        self.repository = repository or PreciosOrientativosRepository()

    def init_schema(self) -> list[str]:
        return self.repository.ensure_columns()

    def buscar_pendientes(self, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        return self.repository.fetch_pending(filters)

    def get_filter_options(self, filters: dict[str, Any], target_filter: str) -> list[str]:
        return self.repository.get_filter_options(filters, target_filter)

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
        con_original = 0
        estimadas_guardadas = 0
        sin_precio = 0
        errores_maestro = 0

        for row in rows:
            method = str(row.get("Metodo") or "SIN_DATOS")
            calc = self._to_float(row.get("EurosOrientativosCalc"))
            if method not in counts:
                counts[method] = 0
            counts[method] += 1

            estado = self.calcular_estado_precio(row)
            row["EstadoPrecio"] = estado
            if estado == "CON_ORIGINAL":
                con_precio += 1
                con_original += 1
            elif estado == "ESTIMADO_GUARDADO":
                con_precio += 1
                estimadas_guardadas += 1
            else:
                sin_precio += 1
            if str(method).startswith("ERROR_"):
                errores_maestro += 1

        resumen = []
        for method in self.METHOD_ORDER + [m for m in counts.keys() if m not in self.METHOD_ORDER]:
            qty = counts.get(method, 0)
            if qty == 0 and method not in self.METHOD_ORDER:
                continue
            pct = (qty / total * 100.0) if total else 0.0
            resumen.append({"metodo": method, "cantidad": qty, "porcentaje": pct})

        cobertura = (con_precio / total * 100.0) if total else 0.0
        return {
            "total": total,
            "con_precio": con_precio,
            "con_original": con_original,
            "estimadas_guardadas": estimadas_guardadas,
            "sin_precio": sin_precio,
            "errores_maestro": errores_maestro,
            "cobertura": cobertura,
            "resumen": resumen,
        }


    def calcular_estado_precio(self, row: dict[str, Any]) -> str:
        metodo = str(row.get("Metodo") or "").strip()
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

    def estado_matches(self, selected: str, estado_row: str) -> bool:
        if not selected or selected == "TODOS":
            return True
        if selected == "CON_PRECIO":
            return estado_row in {"CON_ORIGINAL", "ESTIMADO_GUARDADO"}
        if selected == "ORIGINAL":
            return estado_row == "CON_ORIGINAL"
        if selected == "ESTIMADO":
            return estado_row == "ESTIMADO_GUARDADO"
        return estado_row == selected

    def generar_resumen_semanal(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        agg: dict[str, dict[str, Any]] = {}
        for row in rows:
            semana = str(row.get("Semana") or "")
            estado = self.calcular_estado_precio(row)
            grupo = str(row.get("GrupoVarietal") or "").strip()
            reg = agg.setdefault(semana, {"Semana": semana, "Total líneas": 0, "Con precio": 0, "Estimadas": 0, "Sin precio": 0, "Kg": 0.0, "Importe afectado": 0.0, "_grupos": {}})
            reg["Total líneas"] += 1
            kg = self._to_float(row.get("NetoCliente")) or 0.0
            reg["Kg"] += kg
            if estado == "CON_ORIGINAL":
                reg["Con precio"] += 1
            elif estado == "ESTIMADO_GUARDADO":
                reg["Estimadas"] += 1
            else:
                reg["Sin precio"] += 1
                precio_ref = self._to_float(row.get("EurosKG")) or 0.0
                reg["Importe afectado"] += kg * precio_ref
            if grupo:
                reg["_grupos"][grupo] = reg["_grupos"].get(grupo, 0) + 1
        out=[]
        for reg in sorted(agg.values(), key=lambda r: int(r["Semana"]) if str(r["Semana"]).isdigit() else -1, reverse=True):
            total=reg["Total líneas"]
            con_precio=reg["Con precio"]+reg["Estimadas"]
            principal=max(reg["_grupos"].items(), key=lambda x:x[1])[0] if reg["_grupos"] else ""
            out.append({"Semana": reg["Semana"], "Total líneas": total, "Con precio": reg["Con precio"], "Estimadas": reg["Estimadas"], "Sin precio": reg["Sin precio"], "Cobertura %": round((con_precio/total*100.0) if total else 0.0,2), "Grupo varietal principal": principal, "Kg": round(reg["Kg"], 2), "Importe afectado": round(reg["Importe afectado"], 2)})
        return out

    def preparar_propuesta_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        propuesta = []
        for row in rows:
            original = self._to_float(row.get("EurosOrientativos"))
            if original is not None and original > 0:
                continue
            calc = self._to_float(row.get("EurosOrientativosCalc"))
            propuesta.append(
                {
                    "IdPedidoLora": row.get("IdPedidoLora", ""),
                    "Línea": row.get("Linea", ""),
                    "Semana": row.get("Semana", ""),
                    "FechaSalida": row.get("FechaSalida", ""),
                    "Cliente": row.get("Cliente", ""),
                    "Variedad Coop": row.get("VarCoop", ""),
                    "Calibre": row.get("Calibre", ""),
                    "Confección": row.get("Confeccion", ""),
                    "GrupoConfección": row.get("GrupoConfeccion", ""),
                    "NetoCliente": self._to_float(row.get("NetoCliente")) or 0.0,
                    "EurosOrientativos actual": original if original is not None else "",
                    "EurosOrientativosCalc": calc if calc is not None else "",
                    "€/kg propuesto": calc if calc is not None and calc > 0 else "",
                    "Método": row.get("Metodo", ""),
                    "Observaciones": row.get("Observaciones", ""),
                    "Campaña": row.get("Campaña", ""),
                    "Cultivo": row.get("Cultivo", ""),
                    "Empresa": row.get("Empresa", ""),
                }
            )
        return propuesta

    def generar_pdf_propuesta(self, propuesta_rows: list[dict[str, Any]], filters: dict[str, Any]) -> tuple[Path | None, str | None]:
        export_dir = Path("exports") / "precios_orientativos"
        export_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        semanas = sorted({str(r.get("Semana") or "").strip() for r in propuesta_rows if str(r.get("Semana") or "").strip()}, key=lambda s: int(s) if s.isdigit() else s)
        if len(semanas) == 1:
            filename = f"propuesta_precios_orientativos_semana_{semanas[0]}_{ts}.pdf"
        elif len(semanas) > 1:
            filename = f"propuesta_precios_orientativos_semanas_{semanas[0]}-{semanas[-1]}_{ts}.pdf"
        else:
            filename = f"propuesta_precios_orientativos_{ts}.pdf"
        out_path = export_dir / filename
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except Exception:
            return None, "No se pudo generar PDF: falta dependencia 'reportlab'."

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(out_path), pagesize=landscape(A4))

        propuesta_vals = [self._to_float(r.get("€/kg propuesto")) for r in propuesta_rows]
        propuesta_vals = [v for v in propuesta_vals if v is not None]
        neto_total = sum(self._to_float(r.get("NetoCliente")) or 0.0 for r in propuesta_rows)
        with_calc = sum(1 for r in propuesta_rows if (self._to_float(r.get("EurosOrientativosCalc")) or 0) > 0)
        sin_prop = sum(1 for r in propuesta_rows if self._to_float(r.get("€/kg propuesto")) is None)

        header_lines = [
            f"Fecha generación: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            f"Campaña: {', '.join(filters.get('campana') or ['Todas'])}",
            f"Semana/s: {', '.join(filters.get('semana') or ['Todas'])}",
            f"Cultivo: {', '.join(filters.get('cultivo') or ['Todos'])}",
            f"Empresa: {', '.join(filters.get('empresa') or ['Todas'])}",
            f"Cliente: {', '.join(filters.get('cliente') or ['Todos'])}",
            "Usuario: APP",
        ]
        summary_lines = [
            f"Nº líneas propuestas: {len(propuesta_rows)}",
            f"Nº líneas con propuesta calculada: {with_calc}",
            f"Nº líneas sin propuesta: {sin_prop}",
            f"NetoCliente total: {neto_total:.2f} kg",
            f"Precio medio propuesto: {statistics.mean(propuesta_vals):.4f} €/kg" if propuesta_vals else "Precio medio propuesto: N/D",
        ]

        elements = [Paragraph("Propuesta de precios orientativos pendientes", styles["Title"]), Spacer(1, 8)]
        for line in header_lines:
            elements.append(Paragraph(line, styles["Normal"]))
        elements.append(Spacer(1, 8))
        for line in summary_lines:
            elements.append(Paragraph(line, styles["Normal"]))
        elements.append(Spacer(1, 10))

        data = [["Pedido", "Línea", "Semana", "Fecha salida", "Cliente", "Variedad", "Calibre", "Confección", "Grupo confección", "NetoCliente", "Precio calculado", "€/kg propuesto", "Método"]]
        for r in propuesta_rows:
            data.append([
                r.get("IdPedidoLora", ""), r.get("Línea", ""), r.get("Semana", ""), r.get("FechaSalida", ""),
                r.get("Cliente", ""), r.get("Variedad Coop", ""), r.get("Calibre", ""), r.get("Confección", ""),
                r.get("GrupoConfección", ""), f"{(self._to_float(r.get('NetoCliente')) or 0.0):.2f}",
                "" if self._to_float(r.get("EurosOrientativosCalc")) is None else f"{self._to_float(r.get('EurosOrientativosCalc')):.4f}",
                "" if self._to_float(r.get("€/kg propuesto")) is None else f"{self._to_float(r.get('€/kg propuesto')):.4f}",
                r.get("Método", ""),
            ])
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("Documento informativo para revisión administrativa. No modifica automáticamente los precios reales.", styles["Italic"]))

        doc.build(elements)
        return out_path, None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).strip().replace(",", "."))
        except Exception:
            return None
