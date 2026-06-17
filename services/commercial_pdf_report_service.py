from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence
import logging
import re
import unicodedata

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - fallback para entornos sin dependencias instaladas
    REPORTLAB_AVAILABLE = False


logger = logging.getLogger(__name__)


class CommercialPdfReportService:
    """Genera el informe comercial diario desde las filas ya filtradas en pantalla."""

    def default_filename(self, cultivos: Sequence[Any] | None = None, now: datetime | None = None) -> str:
        cultivo_slug = self._cultivo_filename_slug(cultivos)
        timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M")
        return f"Informe_comercial_{cultivo_slug}_{timestamp}.pdf"

    def _cultivo_filename_slug(self, cultivos: Sequence[Any] | None = None) -> str:
        valid_cultivos = [
            str(cultivo).strip()
            for cultivo in (cultivos or [])
            if str(cultivo or "").strip() and str(cultivo or "").strip().upper() != "TODOS"
        ]
        if len(valid_cultivos) != 1:
            return "TODOS"
        normalized = unicodedata.normalize("NFKD", valid_cultivos[0])
        ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
        ascii_text = ascii_text.replace("/", "_").replace("\\", "_")
        ascii_text = re.sub(r"\s+", "_", ascii_text.strip())
        ascii_text = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_text)
        ascii_text = re.sub(r"_+", "_", ascii_text).strip("_-")
        return ascii_text.upper() or "TODOS"

    def generate(
        self,
        target_path: str | Path,
        *,
        filters: dict[str, Any] | None = None,
        stock_campo_rows: list[dict] | None = None,
        stock_almacen_rows: list[dict] | None = None,
        pedidos_pendientes_rows: list[dict] | None = None,
        pedidos_previstos_rows: list[dict] | None = None,
        aprovechamiento_volcado: dict[str, Any] | None = None,
        generated_at: datetime | None = None,
    ) -> Path:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not REPORTLAB_AVAILABLE:
            self._generate_minimal_pdf(
                target,
                filters=filters or {},
                stock_campo_rows=list(stock_campo_rows or []),
                stock_almacen_rows=list(stock_almacen_rows or []),
                pedidos_pendientes_rows=list(pedidos_pendientes_rows or []),
                pedidos_previstos_rows=list(pedidos_previstos_rows or []),
                aprovechamiento_volcado=aprovechamiento_volcado or {},
                generated_at=generated_at or datetime.now(),
            )
            return target
        self._styles = getSampleStyleSheet()
        self._small = ParagraphStyle("Small", parent=self._styles["Normal"], fontSize=6.2, leading=7.2, alignment=TA_LEFT)
        self._normal = ParagraphStyle("NormalCompact", parent=self._styles["Normal"], fontSize=8, leading=9.5)
        self._section = ParagraphStyle("Section", parent=self._styles["Heading2"], fontSize=14, leading=16, spaceBefore=4, spaceAfter=7, textColor=colors.HexColor("#1F4E79"))
        self._title = ParagraphStyle("Title", parent=self._styles["Heading1"], fontSize=20, leading=23, alignment=TA_CENTER, textColor=colors.HexColor("#1F4E79"))
        self._kpi = ParagraphStyle("Kpi", parent=self._styles["Normal"], fontSize=10, leading=12, alignment=TA_CENTER)

        campo = list(stock_campo_rows or [])
        almacen = list(stock_almacen_rows or [])
        active_filters = filters or {}
        selected_cultivos = self._selected_filter_values(active_filters.get("cultivo"))
        pendientes = self._filter_pending_rows(list(pedidos_pendientes_rows or []), selected_cultivos)
        previstos = list(pedidos_previstos_rows or [])
        story: list[Any] = []
        self._add_header(story, active_filters, generated_at or datetime.now())
        self._add_summary(story, campo, almacen, pendientes, previstos)
        self._add_stock_campo(story, campo)
        self._add_aprovechamientos(story, campo)
        self._add_aprovechamiento_volcado(story, aprovechamiento_volcado or {})
        self._add_comparativa_aprovechamientos(story, campo, aprovechamiento_volcado or {})
        self._add_stock_almacen(story, almacen)
        self._add_pedidos(story, "PEDIDOS PENDIENTES", pendientes, kg_field="Kg pendiente", confeccion_field="Confección", previsto=False)
        self._add_pedidos(story, "PEDIDOS PREVISTOS / NO CONFIRMADOS", previstos, kg_field="Kg estimados", confeccion_field="Confección prevista", previsto=True)
        self._add_agenda(story, pendientes, selected_cultivos)
        self._add_alertas(story, campo, almacen, pendientes, previstos)
        self._add_capacidad(story)
        doc = SimpleDocTemplate(str(target), pagesize=landscape(A4), leftMargin=0.7*cm, rightMargin=0.7*cm, topMargin=0.7*cm, bottomMargin=0.7*cm)
        doc.build(story)
        return target

    def _p(self, value: Any) -> Paragraph:
        return Paragraph(str(value if value is not None else ""), self._small)

    def _num(self, value: Any, decimals: int = 2) -> str:
        try: return f"{float(str(value).replace(',', '.')):,.{decimals}f}"
        except Exception: return str(value or "")

    def _sum(self, rows: Iterable[dict], field: str) -> float:
        total = 0.0
        for r in rows:
            try: total += float(str(r.get(field, 0) or 0).replace(',', '.'))
            except Exception: pass
        return total

    def _filter_text(self, value: Any) -> str:
        if isinstance(value, list): return ", ".join(map(str, value)) if value else "TODOS"
        return str(value or "TODOS")

    def _selected_filter_values(self, value: Any) -> set[str]:
        values = value if isinstance(value, (list, tuple, set)) else [value]
        return {str(v or "").strip().upper() for v in values if str(v or "").strip() and str(v or "").strip().upper() != "TODOS"}

    def _filter_pending_rows(self, rows: list[dict], selected_cultivos: set[str] | None = None) -> list[dict]:
        filtered: list[dict] = []
        for row in rows:
            if self._sum([row], "Kg pendiente") <= 0:
                continue
            if selected_cultivos and str(self._value(row, "Cultivo") or "").strip().upper() not in selected_cultivos:
                continue
            filtered.append(row)
        return filtered

    def _add_header(self, story: list, filters: dict, generated_at: datetime) -> None:
        story.append(Paragraph("INFORME OPERATIVO DIARIO", self._title))
        data = [["Fecha/hora generación", generated_at.strftime("%Y-%m-%d %H:%M")], ["Campaña", self._filter_text(filters.get("campana"))], ["Cultivo", self._filter_text(filters.get("cultivo"))], ["Empresa", self._filter_text(filters.get("empresa"))], ["Semana", self._filter_text(filters.get("semana"))], ["Variedad Coop", self._filter_text(filters.get("var_coop"))], ["Grupo varietal", self._filter_text(filters.get("grupo_varietal"))], ["Marca", self._filter_text(filters.get("marca"))], ["Fecha desde / hasta", f"{filters.get('fecha_desde') or 'TODOS'} / {filters.get('fecha_hasta') or 'TODOS'}"], ["Modo pedidos", filters.get("pedidos_modo_label") or filters.get("pedidos_modo", "TODOS")]]
        story.append(self._table(data, repeat=0, header=False, col_widths=[4*cm, 21*cm]))
        story.append(Spacer(1, 6))

    def _add_summary(self, story: list, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict]) -> None:
        kg_campo = self._sum(campo, "Kg campo")
        kg_almacen = self._sum(almacen, "Kg stock")
        kg_pendientes = self._sum(pendientes, "Kg pendiente")
        kg_previstos = self._sum(previstos, "Kg estimados")
        story.append(Paragraph("RESUMEN EJECUTIVO", self._section))
        demanda_total = kg_pendientes + kg_previstos
        cobertura = ((kg_campo + kg_almacen) / demanda_total * 100) if demanda_total else 0
        estado = "VERDE" if cobertura >= 130 else "AMARILLO" if cobertura >= 100 else "ROJO"
        rows = [
            ["DISPONIBILIDAD", "DEMANDA", "COBERTURA"],
            [
                f"Kg stock campo\n{self._num(kg_campo)}\nKg stock almacén\n{self._num(kg_almacen)}\nTotal disponible\n{self._num(kg_campo + kg_almacen)}",
                f"Kg pedidos pendientes\n{self._num(kg_pendientes)}\nKg pedidos previstos\n{self._num(kg_previstos)}\nDemanda total\n{self._num(demanda_total)}",
                f"Dif. almacén vs pendientes\n{self._num(kg_almacen - kg_pendientes)}\nDif. total vs demanda\n{self._num(kg_campo + kg_almacen - demanda_total)}\nCobertura\n{cobertura:.0f}% ({estado})",
            ],
        ]
        story.append(self._table(rows, col_widths=[8.5*cm, 8.5*cm, 8.5*cm], row_styles=[(1, estado)]))
        max_value = max(kg_campo, kg_almacen, kg_pendientes, kg_previstos, 1)
        bars = [["Indicador", "Kg", "Barra"]]
        for label, value in [("Stock campo", kg_campo), ("Stock almacén", kg_almacen), ("Pedidos pendientes", kg_pendientes), ("Pedidos previstos", kg_previstos)]:
            bars.append([label, self._num(value), "█" * max(1, int(value / max_value * 28)) if value else ""])
        story.append(Spacer(1, 8))
        story.append(Paragraph("Comparativa visual stock / demanda", self._normal))
        story.append(self._table(bars, col_widths=[5*cm, 4*cm, 16*cm]))
        story.append(PageBreak())

    def _value(self, row: dict, column: str) -> Any:
        aliases = {
            "Tipo palet": ("Tipo palet", "TipoPalet", "Tipo Palet", "tipo_palet", "Tipo"),
            "Nombre palet": ("Nombre palet", "NombrePalet", "Nombre Palet", "nombre_palet", "Palet"),
            "Pedido": ("Pedido", "IdPedidoLora"),
        }
        for key in aliases.get(column, (column,)):
            if key in row:
                return row.get(key)
        return ""

    def _group_rows(self, rows: Sequence[dict], keys: list[str], sums: dict[str, str], count_label: str | None = None) -> list[dict]:
        grouped: dict[tuple[str, ...], dict[str, Any]] = {}
        for row in rows:
            key = tuple(str(self._value(row, k) or "") for k in keys)
            bucket = grouped.setdefault(key, {k: v for k, v in zip(keys, key)} | {label: 0.0 for label in sums})
            if count_label:
                bucket.setdefault("_ids", set()).add(self._value(row, "Pedido") or id(row))
            for label, field in sums.items():
                bucket[label] += self._sum([row], field)
        result = []
        for bucket in grouped.values():
            if count_label:
                bucket[count_label] = len(bucket.pop("_ids", set()))
            result.append(bucket)
        return sorted(result, key=lambda r: tuple(str(r.get(k, "")) for k in keys))

    def _add_group_summary(self, story: list, title: str, rows: list[dict], keys: list[str], sum_fields: dict[str, str], *, count_label: str | None = None, extra_fields: list[str] | None = None) -> None:
        grouped = self._group_rows(rows, keys, sum_fields, count_label=count_label)
        columns = keys + ([count_label] if count_label else []) + list(sum_fields) + list(extra_fields or [])
        data = [columns]
        for r in grouped:
            data.append([self._format_cell(r.get(c, ""), c) for c in columns])
        story.append(Paragraph(title, self._normal))
        story.append(self._table(data))
        story.append(Spacer(1, 6))

    def _add_stock_campo(self, story: list, rows: list[dict]) -> None:
        story.append(Paragraph("STOCK CAMPO", self._section))
        if not rows:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal)); story.append(PageBreak()); return
        columns = ["Fecha carga", "Semana", "Socio", "Variedad", "Grupo varietal", "Boleta", "Plataforma", "Empresa", "Color / restricciones", "Kg campo"]
        sorted_rows = sorted(rows, key=lambda r: (str(self._value(r, "Grupo varietal")), str(self._value(r, "Variedad")), str(self._value(r, "Socio")), str(self._value(r, "Boleta"))))
        data = [columns]
        styles = []
        current: dict[str, Any] = {"Grupo varietal": None, "Variedad": None, "Socio": None}
        buckets: dict[str, list[dict]] = {"Grupo varietal": [], "Variedad": [], "Socio": []}

        def subtotal(label: str, value: Any, level: str) -> None:
            data.append([label] + [""] * (len(columns) - 2) + [self._num(value)])
            styles.append((len(data) - 1, level))

        for row in sorted_rows:
            values = {k: self._value(row, k) or "Sin especificar" for k in ("Grupo varietal", "Variedad", "Socio")}
            if current["Grupo varietal"] is not None:
                if values["Grupo varietal"] != current["Grupo varietal"]:
                    subtotal(f"Subtotal socio: {current['Socio']}", self._sum(buckets["Socio"], "Kg campo"), "socio")
                    subtotal(f"Subtotal variedad: {current['Variedad']}", self._sum(buckets["Variedad"], "Kg campo"), "variedad")
                    subtotal(f"Total grupo varietal: {current['Grupo varietal']}", self._sum(buckets["Grupo varietal"], "Kg campo"), "cultivo")
                    buckets = {"Grupo varietal": [], "Variedad": [], "Socio": []}
                elif values["Variedad"] != current["Variedad"]:
                    subtotal(f"Subtotal socio: {current['Socio']}", self._sum(buckets["Socio"], "Kg campo"), "socio")
                    subtotal(f"Subtotal variedad: {current['Variedad']}", self._sum(buckets["Variedad"], "Kg campo"), "variedad")
                    buckets["Variedad"] = []; buckets["Socio"] = []
                elif values["Socio"] != current["Socio"]:
                    subtotal(f"Subtotal socio: {current['Socio']}", self._sum(buckets["Socio"], "Kg campo"), "socio")
                    buckets["Socio"] = []
            current = values
            for key in buckets: buckets[key].append(row)
            color = self._value(row, "Color") or self._value(row, "Restricciones / Color")
            data.append([self._format_cell(self._value(row, c), c) for c in columns[:-2]] + [self._format_cell(color, "Color"), self._format_cell(self._value(row, "Kg campo"), "Kg campo")])
            styles.append((len(data) - 1, str(color).upper()))
        if sorted_rows:
            subtotal(f"Subtotal socio: {current['Socio']}", self._sum(buckets["Socio"], "Kg campo"), "socio")
            subtotal(f"Subtotal variedad: {current['Variedad']}", self._sum(buckets["Variedad"], "Kg campo"), "variedad")
            subtotal(f"Total grupo varietal: {current['Grupo varietal']}", self._sum(buckets["Grupo varietal"], "Kg campo"), "cultivo")
        subtotal("TOTAL GENERAL STOCK CAMPO", self._sum(sorted_rows, "Kg campo"), "general")
        story.append(self._table(data, row_styles=styles))
        story.append(PageBreak())

    def _has_any_value(self, rows: Sequence[dict], column: str) -> bool:
        return any(str(self._value(row, column) or "").strip() for row in rows)

    def _add_stock_almacen(self, story: list, rows: list[dict]) -> None:
        story.append(Paragraph("STOCK ALMACÉN RESUMIDO", self._section))
        if not rows:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal)); story.append(PageBreak()); return
        keys = ["Grupo varietal", "Marca", "Confección", "Calibre", "Categoría"]
        optional = [c for c in ("Tipo palet", "Nombre palet") if self._has_any_value(rows, c)]
        sums = {"Palets": "Palets", "Cajas": "Cajas", "Kg stock": "Kg stock"}
        grouped = self._group_rows(rows, keys + optional, sums)
        data = [["Grupo varietal", "Marca", "Confección", "Calibre / categoría"] + optional + ["Palets", "Cajas", "Kg stock"]]
        last = {"Grupo varietal": None, "Marca": None, "Confección": None}
        buckets = {"Grupo varietal": [], "Marca": [], "Confección": []}

        def subtotal(label: str, value_rows: list[dict]) -> None:
            data.append([label, "", "", ""] + [""] * len(optional) + [self._format_cell(self._sum(value_rows, "Palets"), "Palets"), self._format_cell(self._sum(value_rows, "Cajas"), "Cajas"), self._num(self._sum(value_rows, "Kg stock"))])

        for r in grouped:
            vals = {k: r.get(k) or "Sin especificar" for k in last}
            if last["Grupo varietal"] is not None:
                if vals["Grupo varietal"] != last["Grupo varietal"]:
                    subtotal(f"Subtotal confección: {last['Confección']}", buckets["Confección"]); subtotal(f"Subtotal marca: {last['Marca']}", buckets["Marca"]); subtotal(f"Total grupo varietal: {last['Grupo varietal']}", buckets["Grupo varietal"])
                    buckets = {"Grupo varietal": [], "Marca": [], "Confección": []}
                elif vals["Marca"] != last["Marca"]:
                    subtotal(f"Subtotal confección: {last['Confección']}", buckets["Confección"]); subtotal(f"Subtotal marca: {last['Marca']}", buckets["Marca"])
                    buckets["Marca"] = []; buckets["Confección"] = []
                elif vals["Confección"] != last["Confección"]:
                    subtotal(f"Subtotal confección: {last['Confección']}", buckets["Confección"]); buckets["Confección"] = []
            last = vals
            for key in buckets: buckets[key].append(r)
            calib_cat = " / ".join(x for x in [str(r.get("Calibre") or ""), str(r.get("Categoría") or "")] if x)
            data.append([r.get("Grupo varietal", ""), r.get("Marca", ""), r.get("Confección", ""), calib_cat] + [r.get(c, "") for c in optional] + [self._format_cell(r.get("Palets"), "Palets"), self._format_cell(r.get("Cajas"), "Cajas"), self._num(r.get("Kg stock"))])
        if grouped:
            subtotal(f"Subtotal confección: {last['Confección']}", buckets["Confección"]); subtotal(f"Subtotal marca: {last['Marca']}", buckets["Marca"]); subtotal(f"Total grupo varietal: {last['Grupo varietal']}", buckets["Grupo varietal"])
        subtotal("TOTAL ALMACÉN", grouped)
        story.append(self._table(data))
        story.append(PageBreak())

    def _add_pedidos(self, story: list, title: str, rows: list[dict], *, kg_field: str, confeccion_field: str, previsto: bool) -> None:
        story.append(Paragraph(title, self._section))
        if not rows:
            msg = "Sin pedidos previstos para los filtros actuales." if previsto else "No hay pedidos pendientes para el cultivo seleccionado."
            story.append(Paragraph(msg, self._normal)); story.append(PageBreak()); return
        pedido_kg = "Kg estimados" if previsto else "Kg pedido teórico"
        palets = "Palets estimados" if previsto else "Palets pendientes"
        self._add_confeccion_mix(story, rows, kg_field, palets)
        self._add_timeline(story, rows, pedido_kg, kg_field, palets, previsto)
        self._add_pedidos_matrix(story, rows, pedido_kg, kg_field, palets)
        story.append(PageBreak())

    def _add_confeccion_mix(self, story: list, rows: list[dict], kg_field: str, palets_field: str) -> None:
        grouped = self._group_rows(rows, ["Grupo confección"], {"Palets": palets_field, "Kg pendiente": kg_field})
        total_palets = sum(r["Palets"] for r in grouped)
        data = [["Grupo confección", "% palets", "Palets", "Kg pendiente"]]
        for r in grouped:
            data.append([r.get("Grupo confección") or "DESCONOCIDO", f"{(r['Palets']/total_palets*100 if total_palets else 0):.0f}%", self._format_cell(r["Palets"], "Palets"), self._num(r["Kg pendiente"])])
        story.append(Paragraph("% pedidos por grupo confección", self._normal)); story.append(self._table(data, col_widths=[5*cm, 2.5*cm, 2.5*cm, 3*cm])); story.append(Spacer(1, 6))

    def _add_timeline(self, story: list, rows: list[dict], pedido_kg: str, kg_field: str, palets_field: str, previsto: bool) -> None:
        temporal = self._group_rows(rows, ["Fecha salida"], {"Kg teórico": pedido_kg, "Kg terminado": "Kg hecho real", "Kg pendiente": kg_field, "Palets pendientes": palets_field}, count_label="Nº pedidos")
        max_kg = max((r["Kg pendiente"] for r in temporal), default=0)
        data = [["Fecha salida", "Nº pedidos", "Palets pendientes", "Kg teórico", "Kg terminado", "Kg pendiente", "% pendiente", "Barra visual"]]
        for r in temporal:
            blocks = int(round((r["Kg pendiente"] / max_kg) * 14)) if max_kg else 0
            pct = (r["Kg pendiente"] / r["Kg teórico"] * 100) if r["Kg teórico"] else 0
            data.append([r["Fecha salida"], r["Nº pedidos"], self._format_cell(r["Palets pendientes"], "Palets"), self._num(r["Kg teórico"]), self._num(r["Kg terminado"]), self._num(r["Kg pendiente"]), f"{pct:.0f}%", "█" * blocks])
        story.append(Paragraph("LÍNEA TEMPORAL PEDIDOS" + (" PREVISTOS" if previsto else ""), self._normal)); story.append(self._table(data)); story.append(Spacer(1, 6))

    def _add_pedidos_matrix(self, story: list, rows: list[dict], pedido_kg: str, kg_field: str, palets_field: str) -> None:
        groups = sorted({str(self._value(r, "Grupo varietal") or "Sin grupo") for r in rows})
        matrix: dict[tuple[str, str, str, str], dict[str, dict[str, float]]] = {}
        for row in rows:
            key = (str(self._value(row, "Semana") or ""), str(self._value(row, "Fecha salida") or ""), str(self._value(row, "Cliente") or ""), str(self._value(row, "Pedido") or ""))
            gv = str(self._value(row, "Grupo varietal") or "Sin grupo")
            bucket = matrix.setdefault(key, {g: {"Palets": 0.0, "Kg teórico": 0.0, "Kg terminado": 0.0, "Kg pendiente": 0.0} for g in groups})[gv]
            bucket["Palets"] += self._sum([row], palets_field); bucket["Kg teórico"] += self._sum([row], pedido_kg); bucket["Kg terminado"] += self._sum([row], "Kg hecho real"); bucket["Kg pendiente"] += self._sum([row], kg_field)
        header = ["Semana", "Fecha salida", "Cliente", "Pedido"] + [f"{g} {m}" for g in groups for m in ("Palets", "Teórico", "Terminado", "Pendiente")] + [f"TOTAL {m}" for m in ("Palets", "Teórico", "Terminado", "Pendiente")]
        data = [header]
        for key in sorted(matrix):
            totals = {"Palets": 0.0, "Kg teórico": 0.0, "Kg terminado": 0.0, "Kg pendiente": 0.0}
            row = list(key)
            for g in groups:
                vals = matrix[key][g]
                for m in totals: totals[m] += vals[m]
                row += [self._format_cell(vals["Palets"], "Palets"), self._num(vals["Kg teórico"]), self._num(vals["Kg terminado"]), self._num(vals["Kg pendiente"])]
            row += [self._format_cell(totals["Palets"], "Palets"), self._num(totals["Kg teórico"]), self._num(totals["Kg terminado"]), self._num(totals["Kg pendiente"])]
            data.append(row)
        story.append(Paragraph("Matriz operativa por semana, fecha, cliente y grupo varietal", self._normal)); story.append(self._table(data))

    def _add_aprovechamientos(self, story: list, rows: list[dict]) -> None:
        story.append(Paragraph("APROVECHAMIENTO ESTIMADO", self._section))
        if not rows:
            story.append(Paragraph("Sin stock campo para analizar aprovechamientos.", self._normal)); story.append(PageBreak()); return
        total = self._sum(rows, "Kg campo")
        def estado(row: dict) -> str:
            txt = str(self._value(row, "Estado aprovechamiento") or self._value(row, "Origen aprovechamiento") or self._value(row, "Origen") or "").upper()
            if "PESOSFRES" in txt or ("REAL" in txt and "LOTEADO" not in txt): return "Real PesosFres"
            if "LOTEADO" in txt: return "Real Loteado"
            if "MANUAL" in txt or "ESTIMADO" in txt: return "Estimado manual"
            return "Sin aprovechamiento"
        blocks = [("Real PesosFres", []), ("Real Loteado", []), ("Estimado manual", []), ("Sin aprovechamiento", [])]
        by = {k: v for k, v in blocks}
        for r in rows: by[estado(r)].append(r)
        data = [["Bloque", "Nº partidas", "Kg campo afectado", "%"]]
        for label, part_rows in blocks:
            kg = self._sum(part_rows, "Kg campo")
            data.append([label, len(part_rows), self._num(kg), f"{(kg / total * 100 if total else 0):.1f}%"])
        story.append(self._table(data, col_widths=[8*cm, 4*cm, 5*cm, 3*cm]))
        story.append(PageBreak())

    def _add_aprovechamiento_volcado(self, story: list, volcado: dict[str, Any]) -> None:
        story.append(Paragraph("APROVECHAMIENTO DE VOLCADO", self._section))
        story.append(Paragraph(f"Periodo de volcado analizado: {volcado.get('periodo_texto') or 'Sin periodo disponible'}", self._normal))
        rows = list(volcado.get("rows") or [])
        summary = volcado.get("summary") or {}
        if not rows:
            story.append(Paragraph("Sin partidas volcadas o sin líneas de loteado para el periodo y filtros actuales.", self._normal)); story.append(PageBreak()); return
        sem = summary.get("semaforo", "Rojo")
        resumen = [["Nº partidas volcadas", "Líneas peso real", "Líneas estimadas", "Sin estimación", "Kg reales", "Kg estimados", "Cobertura líneas"], [summary.get("partidas", 0), summary.get("lineas_reales", 0), summary.get("lineas_estimadas", 0), summary.get("sin_estimacion", 0), self._num(summary.get("kg_real", 0)), self._num(summary.get("kg_estimado", 0)), f"{summary.get('cobertura_palets', 0):.1f}% ({sem})"]]
        story.append(self._table(resumen, row_styles=[(1, str(sem).upper())]))
        cols = ["Cultivo", "Grupo varietal", "Variedad", "Calibre", "Categoría", "Kg reales", "Kg estimados", "Kg total", "% sobre calculado"]
        story.append(self._table([cols] + [[self._format_cell(r.get(c, ""), c) for c in cols] for r in rows[:80]]))
        story.append(Spacer(1, 6))
        story.append(Paragraph("CALIDAD DE INFORMACIÓN DEL VOLCADO", self._normal))
        qcols = ["Tipo dato", "Palets/líneas", "Kg", "%"]
        story.append(self._table([qcols] + [[r.get(c, "") for c in qcols] for r in (volcado.get("quality") or [])], col_widths=[7*cm, 4*cm, 4*cm, 3*cm]))
        story.append(PageBreak())

    def _add_comparativa_aprovechamientos(self, story: list, campo: list[dict], volcado: dict[str, Any]) -> None:
        story.append(Paragraph("COMPARATIVA ESTIMADO VS VOLCADO", self._section))
        est: dict[str, float] = {}
        for r in campo:
            cal = str(self._value(r, "Calibre") or "").strip()
            if not cal: continue
            kg_est = self._sum([r], "Kg disponibles")
            if kg_est <= 0:
                kg_est = self._sum([r], "Kg estimados calculados") or self._sum([r], "Kg campo")
            est[cal] = est.get(cal, 0.0) + kg_est
        vol = {str(r.get("Calibre") or ""): float(r.get("Kg total") or 0) for r in (volcado.get("rows") or [])}
        total_est = sum(est.values()); total_vol = sum(vol.values())
        data = [["Calibre", "% estimado", "% volcado", "Diferencia p.p.", "Lectura"]]
        for cal in sorted(set(est) | set(vol)):
            pe = est.get(cal, 0) / total_est * 100 if total_est else 0
            pv = vol.get(cal, 0) / total_vol * 100 if total_vol else 0
            diff = pv - pe
            lectura = "Volcado superior" if diff > 5 else "Volcado inferior" if diff < -5 else "Similar"
            data.append([cal, f"{pe:.1f}%", f"{pv:.1f}%", f"{diff:+.1f}", lectura])
        logger.info("INFORME PDF comparativa calibres=%s", max(0, len(data) - 1))
        if len(data) == 1:
            story.append(Paragraph("Sin calibres suficientes para comparar estimado y volcado.", self._normal))
        else:
            story.append(self._table(data, col_widths=[4*cm, 4*cm, 4*cm, 4*cm, 6*cm]))
        story.append(PageBreak())

    def _add_agenda(self, story: list, rows: list[dict], selected_cultivos: set[str] | None = None) -> None:
        story.append(Paragraph("AGENDA DE PRODUCCIÓN", self._section))
        if not rows:
            story.append(Paragraph("Sin pedidos pendientes para agenda de producción.", self._normal)); story.append(PageBreak()); return
        columns = ["Fecha salida", "Cliente", "Pedido", "Cultivo", "Grupo confección", "Grupo varietal", "Kg pendiente", "Palets pendientes"]
        for optional in ("Prioridad", "Estado"):
            if self._has_any_value(rows, optional):
                columns.append(optional)
        data = [columns + ["Semáforo"]]
        today = datetime.now().date()
        styles = []
        for r in sorted(rows, key=lambda x: (str(self._value(x, "Fecha salida")), -self._sum([x], "Kg pendiente"))):
            kg = self._sum([r], "Kg pendiente")
            sem = "Verde" if kg <= 0 else "Rojo" if self._parse_date(self._value(r, "Fecha salida")) == today else "Amarillo" if self._parse_date(self._value(r, "Fecha salida")) == today + timedelta(days=1) else "Pendiente"
            data.append([self._format_cell(self._value(r, c), c) for c in columns] + [sem])
            if selected_cultivos and str(self._value(r, "Cultivo") or "").strip().upper() in selected_cultivos:
                styles.append((len(data) - 1, "DESTACADO"))
        story.append(self._table(data, row_styles=styles))
        story.append(PageBreak())

    def _add_alertas(self, story: list, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict]) -> None:
        story.append(Paragraph("RIESGOS / ALERTAS", self._section))
        alerts: list[list[Any]] = [["Nivel", "Área", "Mensaje", "Acción sugerida"]]
        today = datetime.now().date()
        for r in pendientes:
            if self._sum([r], "Kg pendiente") > 0 and self._parse_date(self._value(r, "Fecha salida")) == today:
                alerts.append(["Rojo", "Producción", f"Pedido {self._value(r, 'Pedido')} de {self._value(r, 'Cliente')} sale hoy con {self._num(self._value(r, 'Kg pendiente'))} kg pendientes.", "Priorizar fabricación/expedición hoy."])
        stock_gv = self._group_rows(almacen, ["Grupo varietal"], {"Kg stock": "Kg stock"})
        demanda_gv = self._group_rows(pendientes, ["Grupo varietal"], {"Kg pendiente": "Kg pendiente"})
        stock_map = {r["Grupo varietal"]: r["Kg stock"] for r in stock_gv}
        for d in demanda_gv:
            if d["Kg pendiente"] > stock_map.get(d["Grupo varietal"], 0):
                alerts.append(["Amarillo", "Almacén", f"Demanda de {d['Grupo varietal'] or 'Sin grupo'} supera stock almacén.", "Revisar stock campo y plan de confección."])
        if campo and not any(str(self._value(r, "Origen aprovechamiento") or self._value(r, "Origen") or "").strip() for r in campo):
            alerts.append(["Amarillo", "Campo", "Hay stock campo sin aprovechamiento informado en los datos disponibles.", "Completar aprovechamientos antes de cerrar planificación."])
        if len(alerts) == 1:
            alerts.append(["Verde", "General", "No se detectan alertas automáticas con los datos actuales.", "Mantener seguimiento operativo."])
        story.append(self._table(alerts, row_styles=[(i, row[0].upper()) for i, row in enumerate(alerts[1:], start=1)], col_widths=[2.5*cm, 3*cm, 14*cm, 8*cm]))
        story.append(PageBreak())

    def _add_capacidad(self, story: list) -> None:
        story.append(Paragraph("CAPACIDAD PRODUCTIVA", self._section))
        story.append(Paragraph("Capacidad productiva no incluida en esta versión del informe.", self._normal))
        story.append(PageBreak())

    def _parse_date(self, value: Any):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(str(value)[:10], fmt).date()
            except Exception:
                pass
        return None

    def _add_section(self, story: list, title: str, rows: list[dict], columns: list[str], groups: list[str], sort_keys: list[str], kg_field: str, *, page_break: bool = True) -> None:
        story.append(Paragraph(title, self._section))
        if not rows:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal)); story.append(PageBreak()); return
        sorted_rows = sorted(rows, key=lambda r: tuple(str(self._value(r, k)) for k in sort_keys))
        data = [columns]
        last = {g: None for g in groups}; buckets = {g: [] for g in groups}
        kg_idx = columns.index(kg_field) if kg_field in columns else len(columns) - 1
        subtotal_row = lambda label, value: [label] + [""] * (kg_idx - 1) + [self._num(value)] + [""] * (len(columns) - kg_idx - 1)
        for r in sorted_rows:
            for idx, g in enumerate(groups):
                v = self._value(r, g)
                if last[g] is not None and v != last[g]:
                    for sg in reversed(groups[idx:]):
                        if buckets[sg]: data.append(subtotal_row(f"Subtotal {sg}: {last[sg]}", self._sum(buckets[sg], kg_field))); buckets[sg]=[]
                    break
            for g in groups: last[g] = self._value(r, g); buckets[g].append(r)
            data.append([self._format_cell(self._value(r, c), c) for c in columns])
        for sg in reversed(groups):
            if buckets[sg]: data.append(subtotal_row(f"Subtotal {sg}: {last[sg]}", self._sum(buckets[sg], kg_field)))
        data.append(subtotal_row(f"Total {title.lower()}", self._sum(sorted_rows, kg_field)))
        story.append(self._table(data))
        if page_break: story.append(PageBreak())

    def _format_cell(self, value: Any, column: str) -> str:
        if "Kg" in column: return self._num(value)
        if any(x in column for x in ("Palets", "Cajas")): return self._num(value, 2).rstrip('0').rstrip('.') if str(value).strip() else ""
        return str(value or "")

    def _table(self, data: list[list[Any]], repeat: int = 1, header: bool = True, col_widths: list[float] | None = None, row_styles: list[tuple[int, str]] | None = None) -> Table:
        wrapped = [[self._p(c) for c in row] for row in data]
        t = Table(wrapped, repeatRows=repeat, colWidths=col_widths)
        style = [("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 2), ("RIGHTPADDING", (0,0), (-1,-1), 2)]
        if header: style += [("BACKGROUND", (0,0), (-1,0), colors.HexColor("#D9EAF7")), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold")]
        for i, row in enumerate(data):
            first = str(row[0]) if row else ""
            if first.startswith("Subtotal confección"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#F1F1F1"))]
            elif first.startswith("Subtotal marca"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#EAF3F8"))]
            elif first.startswith("Total grupo varietal"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#D9EAF7"))]
            elif first.startswith("TOTAL ALMACÉN"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#9DC3E6"))]
            elif first.startswith(("Subtotal", "Total", "TOTAL")):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#F1F1F1"))]
        color_map = {"VERDE": "#E2F0D9", "AMARILLO": "#FFF2CC", "ROJO": "#F4CCCC", "GRIS": "#E7E6E6"}
        for row_idx, marker in row_styles or []:
            marker_text = str(marker).upper()
            if marker_text in color_map:
                style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor(color_map[marker_text])))
            elif marker_text == "DESTACADO":
                style.append(("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Bold"))
                style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#EAF3F8")))
            elif marker_text in {"socio", "variedad", "cultivo", "general"}:
                style.append(("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Bold"))
                style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#F1F1F1")))
        t.setStyle(TableStyle(style)); return t

    def _generate_minimal_pdf(self, target: Path, **kwargs: Any) -> None:
        """Fallback PDF válido cuando ReportLab aún no está instalado en el entorno."""
        filters = kwargs.get("filters", {}) or {}
        lines = [
            "INFORME OPERATIVO DIARIO",
            f"Fecha/hora generación: {kwargs.get('generated_at').strftime('%Y-%m-%d %H:%M')}",
            f"Campaña: {self._filter_text(filters.get('campana'))}",
            f"Cultivo: {self._filter_text(filters.get('cultivo'))}",
            f"Empresa: {self._filter_text(filters.get('empresa'))}",
        ]
        selected_cultivos = self._selected_filter_values(filters.get("cultivo"))
        pending_rows = self._filter_pending_rows(kwargs.get("pedidos_pendientes_rows", []), selected_cultivos)
        sections = [
            ("RESUMEN EJECUTIVO", []),
            ("STOCK CAMPO", kwargs.get("stock_campo_rows", [])),
            ("STOCK ALMACÉN", kwargs.get("stock_almacen_rows", [])),
            ("PEDIDOS PENDIENTES", pending_rows),
            ("PEDIDOS PREVISTOS / NO CONFIRMADOS", kwargs.get("pedidos_previstos_rows", [])),
        ]
        for title, rows in sections:
            lines.append("")
            lines.append(title)
            if rows:
                for row in rows[:40]:
                    lines.append(" | ".join(f"{k}: {v}" for k, v in row.items() if not str(k).startswith("__"))[:150])
            else:
                lines.append("No hay pedidos pendientes para el cultivo seleccionado." if title == "PEDIDOS PENDIENTES" else "Sin datos para los filtros actuales.")
        content_lines = []
        y = 560
        for line in lines:
            safe = str(line).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content_lines.append(f"BT /F1 9 Tf 36 {y} Td ({safe}) Tj ET")
            y -= 12
            if y < 36:
                y = 560
        stream = "\n".join(content_lines).encode("latin-1", errors="replace")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        ]
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for idx, obj in enumerate(objects, 1):
            offsets.append(len(pdf))
            pdf.extend(f"{idx} 0 obj\n".encode() + obj + b"\nendobj\n")
        xref = len(pdf)
        pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
        for off in offsets[1:]:
            pdf.extend(f"{off:010d} 00000 n \n".encode())
        pdf.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        target.write_bytes(bytes(pdf))
