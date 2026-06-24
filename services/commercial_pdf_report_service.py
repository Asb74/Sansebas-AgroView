from __future__ import annotations

from datetime import date, datetime, time, timedelta
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
    from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - fallback para entornos sin dependencias instaladas
    REPORTLAB_AVAILABLE = False


logger = logging.getLogger(__name__)


if REPORTLAB_AVAILABLE:
    class PdfBookmark(Flowable):
        def __init__(self, key: str, title: str | None = None, level: int = 0) -> None:
            super().__init__()
            self.key = key
            self.title = title
            self.level = level
            self.width = 0
            self.height = 0

        def draw(self) -> None:
            self.canv.bookmarkPage(self.key)
            if self.title:
                self.canv.addOutlineEntry(self.title, self.key, level=self.level, closed=False)
else:  # pragma: no cover
    PdfBookmark = None


class CommercialPdfReportService:
    """Genera el informe comercial diario desde las filas ya filtradas en pantalla."""

    COLOR_PRIMARY = "#1F4E79"
    COLOR_HEADER_BG = "#D9EAF7"
    COLOR_LIGHT_BG = "#F5F7FA"
    COLOR_GREEN = "#C8E6C9"
    COLOR_YELLOW = "#FFF3CD"
    COLOR_RED = "#F8D7DA"
    COLOR_GREY = "#E0E0E0"


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
        prevision_recoleccion_rows: list[dict] | None = None,
        pedidos_pendientes_rows: list[dict] | None = None,
        pedidos_previstos_rows: list[dict] | None = None,
        aprovechamiento_volcado: dict[str, Any] | None = None,
        aprovechamiento_campo_detalle: dict[str, list[dict]] | None = None,
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
                prevision_recoleccion_rows=list(prevision_recoleccion_rows or []),
                pedidos_pendientes_rows=list(pedidos_pendientes_rows or []),
                pedidos_previstos_rows=list(pedidos_previstos_rows or []),
                aprovechamiento_volcado=aprovechamiento_volcado or {},
                aprovechamiento_campo_detalle=aprovechamiento_campo_detalle or {},
                generated_at=generated_at or datetime.now(),
            )
            return target
        self._styles = getSampleStyleSheet()
        self._small = ParagraphStyle("Small", parent=self._styles["Normal"], fontSize=6.2, leading=7.2, alignment=TA_LEFT)
        self._normal = ParagraphStyle("NormalCompact", parent=self._styles["Normal"], fontSize=8, leading=9.5)
        self._section = ParagraphStyle("Section", parent=self._styles["Heading2"], fontSize=14, leading=16, spaceBefore=4, spaceAfter=7, textColor=colors.HexColor(self.COLOR_PRIMARY))
        self._title = ParagraphStyle("Title", parent=self._styles["Heading1"], fontSize=20, leading=23, alignment=TA_CENTER, textColor=colors.HexColor(self.COLOR_PRIMARY))
        self._kpi = ParagraphStyle("Kpi", parent=self._styles["Normal"], fontSize=10, leading=12, alignment=TA_CENTER)

        campo = list(stock_campo_rows or [])
        almacen = list(stock_almacen_rows or [])
        prevision = list(prevision_recoleccion_rows or [])
        active_filters = filters or {}
        selected_cultivos = self._selected_filter_values(active_filters.get("cultivo"))
        pendientes = self._filter_pending_rows(list(pedidos_pendientes_rows or []), selected_cultivos)
        previstos = list(pedidos_previstos_rows or [])
        story: list[Any] = []
        self._add_index(story)
        self._add_header(story, active_filters, generated_at or datetime.now())
        self._add_summary(story, campo, almacen, pendientes, previstos)
        self._add_stock_campo(story, campo)
        self._add_prevision_recoleccion(story, prevision, active_filters)
        self._add_aprovechamientos(story, campo)
        self._add_aprovechamiento_detalle_partida(story, campo, aprovechamiento_campo_detalle or {})
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

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value if value is not None else "").strip()
        if not text:
            return default
        try:
            if "," in text and "." in text:
                text = text.replace(".", "").replace(",", ".")
            elif "," in text:
                text = text.replace(",", ".")
            return float(text)
        except Exception:
            return default

    def _format_number(self, value: Any, decimals: int = 0) -> str:
        try:
            text = f"{float(value or 0):,.{decimals}f}"
            return text.replace(",", "_").replace(".", ",").replace("_", ".")
        except Exception:
            return str(value or "")

    def _format_kg(self, value: Any) -> str:
        return f"{self._format_number(self._to_float(value), 0)} kg"

    def _format_t(self, value: Any) -> str:
        return f"{self._format_number(self._to_float(value) / 1000, 1)} t"

    def _format_pct(self, value: Any, *, blank: str = "-") -> str:
        if value is None:
            return blank
        return f"{self._format_number(self._to_float(value), 1)} %"

    def _num(self, value: Any, decimals: int = 2) -> str:
        return self._format_number(self._to_float(value), decimals)

    def _format_toneladas(self, value: Any) -> str:
        return self._format_t(value)

    def _format_toneladas_cifra(self, value: Any) -> str:
        return self._format_number(self._to_float(value) / 1000, 1)

    def _format_pct_1(self, value: Any, *, blank: str = "-") -> str:
        return self._format_pct(value, blank=blank).replace(" %", "") if value is not None else blank

    def _traffic_label(self, value: Any, green_min: float, yellow_min: float) -> str:
        if value is None:
            return "GRIS"
        numeric = self._to_float(value)
        if numeric >= green_min:
            return "VERDE"
        if numeric >= yellow_min:
            return "AMARILLO"
        return "ROJO"

    def _traffic_color(self, label: str):
        palette = {"VERDE": self.COLOR_GREEN, "AMARILLO": self.COLOR_YELLOW, "ROJO": self.COLOR_RED, "GRIS": self.COLOR_GREY}
        return colors.HexColor(palette.get(str(label).upper(), self.COLOR_GREY)) if REPORTLAB_AVAILABLE else None

    def _risk_label(self, cobertura: float | None = None, *, sin_aprovechamiento_pct: float | None = None) -> str:
        if sin_aprovechamiento_pct is not None:
            if sin_aprovechamiento_pct <= 5:
                return "VERDE"
            if sin_aprovechamiento_pct <= 15:
                return "AMARILLO"
            return "ROJO"
        if cobertura is None:
            return "GRIS"
        return self._traffic_label(cobertura, 130, 100)

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
            if selected_cultivos and str(self._value(row, "Cultivo") or "").strip().upper() not in selected_cultivos:
                continue
            filtered.append(row)
        return filtered

    def _add_index(self, story: list) -> None:
        story.append(PdfBookmark("indice", "ÍNDICE"))
        story.append(Paragraph('<a name="indice"/>ÍNDICE', self._title))
        sections = [
            ("1. Resumen ejecutivo", "resumen_ejecutivo"),
            ("2. Stock campo", "stock_campo"),
            ("3. Previsión de recolección", "prevision_recoleccion"),
            ("4. Stock almacén", "stock_almacen"),
            ("5. Pedidos pendientes", "pedidos_pendientes"),
            ("6. Balance comercial", "balance_comercial"),
            ("7. Aprovechamiento estimado", "aprovechamiento_estimado"),
            ("8. Aprovechamiento de volcado", "aprovechamiento_volcado"),
            ("9. Capacidad productiva", "capacidad_productiva"),
        ]
        for label, anchor in sections:
            story.append(Paragraph(f'<link href="#{anchor}" color="blue">{label}</link>', self._normal))
            story.append(Spacer(1, 3))
        story.append(PageBreak())

    def _section_title(self, story: list, title: str, anchor: str) -> None:
        story.append(PdfBookmark(anchor, title))
        story.append(Paragraph(f'<a name="{anchor}"/>{title} <font size="6"><link href="#indice" color="blue">Volver al índice</link></font>', self._section))

    def _add_header(self, story: list, filters: dict, generated_at: datetime) -> None:
        story.append(Paragraph("INFORME OPERATIVO DIARIO", self._title))
        data = [["Fecha/hora generación", generated_at.strftime("%Y-%m-%d %H:%M")], ["Campaña", self._filter_text(filters.get("campana"))], ["Cultivo", self._filter_text(filters.get("cultivo"))], ["Empresa", self._filter_text(filters.get("empresa"))], ["Semana", self._filter_text(filters.get("semana"))], ["Variedad Coop", self._filter_text(filters.get("var_coop"))], ["Grupo varietal", self._filter_text(filters.get("grupo_varietal"))], ["Marca", self._filter_text(filters.get("marca"))], ["Fecha desde / hasta", f"{filters.get('fecha_desde') or 'TODOS'} / {filters.get('fecha_hasta') or 'TODOS'}"], ["Modo pedidos", filters.get("pedidos_modo_label") or filters.get("pedidos_modo", "TODOS")]]
        story.append(self._table(data, repeat=0, header=False, col_widths=[4*cm, 21*cm]))
        story.append(Spacer(1, 6))

    def _kpi_cards(self, cards: list[dict[str, Any]], *, columns: int = 4, width: float = 6.4*cm) -> Table:
        rows: list[list[Any]] = []
        for i in range(0, len(cards), columns):
            chunk = cards[i:i + columns]
            rows.append([
                Paragraph(f"<b>{card['label']}</b><br/><font size='14'><b>{card['value']}</b></font><br/><font size='7'>{card.get('unit', '')}</font>", self._kpi)
                for card in chunk
            ] + [""] * (columns - len(chunk)))
        table = Table(rows, colWidths=[width] * columns)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(self.COLOR_HEADER_BG)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]
        for idx, card in enumerate(cards):
            row, col = divmod(idx, columns)
            bg = self._traffic_color(card.get("status", "GRIS")) if card.get("status") else colors.HexColor(self.COLOR_LIGHT_BG)
            style.append(("BACKGROUND", (col, row), (col, row), bg))
        table.setStyle(TableStyle(style))
        return table

    def _add_summary(self, story: list, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict]) -> None:
        kg_campo = self._sum(campo, "Kg campo")
        kg_almacen = self._sum(almacen, "Kg stock")
        kg_pendientes = self._sum(pendientes, "Kg pendiente")
        kg_previstos = self._sum(previstos, "Kg estimados")
        demanda_total = kg_pendientes + kg_previstos
        total_disponible = kg_campo + kg_almacen
        cobertura = (total_disponible / demanda_total * 100) if demanda_total else None
        diferencia_total = total_disponible - demanda_total
        diferencia_almacen = kg_almacen - kg_pendientes
        estado = self._risk_label(cobertura)

        self._section_title(story, "RESUMEN EJECUTIVO", "resumen_ejecutivo")
        cards = [
            {"label": "STOCK CAMPO", "value": self._format_t(kg_campo), "unit": self._format_kg(kg_campo)},
            {"label": "STOCK ALMACÉN", "value": self._format_t(kg_almacen), "unit": self._format_kg(kg_almacen), "status": "VERDE" if kg_almacen >= kg_pendientes and kg_pendientes else None},
            {"label": "TOTAL DISPONIBLE", "value": self._format_t(total_disponible), "unit": self._format_kg(total_disponible)},
            {"label": "PEDIDOS PENDIENTES", "value": self._format_t(kg_pendientes), "unit": self._format_kg(kg_pendientes), "status": "AMARILLO" if kg_pendientes > 0 else "VERDE"},
            {"label": "PEDIDOS PREVISTOS", "value": self._format_t(kg_previstos), "unit": self._format_kg(kg_previstos), "status": "AMARILLO" if kg_previstos > 0 else "VERDE"},
            {"label": "COBERTURA GLOBAL", "value": self._format_pct(cobertura) if cobertura is not None else "Sin demanda", "unit": estado, "status": estado},
            {"label": "DIFERENCIA", "value": self._format_t(diferencia_total), "unit": "Disponible vs demanda", "status": "VERDE" if diferencia_total >= 0 else "ROJO"},
            {"label": "ESTADO GENERAL", "value": estado, "unit": "Semáforo operativo", "status": estado},
        ]
        story.append(self._kpi_cards(cards, columns=4, width=6.4*cm))
        story.append(Spacer(1, 8))

        lectura = []
        if demanda_total:
            if cobertura is not None and cobertura >= 130:
                lectura.append("Cobertura global suficiente para la demanda actual.")
            elif cobertura is not None and cobertura >= 100:
                lectura.append("Cobertura global ajustada: conviene revisar disponibilidad por variedad y confección.")
            else:
                lectura.append("Cobertura global insuficiente para la demanda actual.")
            if diferencia_total >= 0:
                lectura.append(f"El stock total supera la demanda en {self._format_t(diferencia_total)}.")
            else:
                lectura.append(f"La demanda supera el stock total en {self._format_t(abs(diferencia_total))}.")
        else:
            lectura.append("No hay demanda pendiente o prevista en los datos actuales.")
        lectura.append("El stock de almacén cubre por sí solo los pedidos pendientes." if diferencia_almacen >= 0 else "El stock de almacén no cubre por sí solo los pedidos pendientes.")
        lectura.append("Existen pedidos pendientes para revisar." if kg_pendientes > 0 else "No hay pedidos pendientes para revisar.")
        lectura.append("Existen pedidos previstos no confirmados." if kg_previstos > 0 else "No hay pedidos previstos no confirmados.")
        lectura.append("Revisar partidas sin aprovechamiento si existen en el informe.")
        story.append(Paragraph("LECTURA RÁPIDA", self._normal))
        story.append(self._table([["Lectura operativa"]] + [[text] for text in lectura], col_widths=[25.6*cm]))
        story.append(Spacer(1, 8))

        alerts = [["Nivel", "Alerta", "Lectura"]]
        alerts.append([estado, "Cobertura global", "Sin demanda actual." if cobertura is None else f"Cobertura {self._format_pct(cobertura)}."])
        if kg_almacen < kg_pendientes:
            alerts.append(["AMARILLO", "Stock almacén", "Almacén inferior a pedidos pendientes; revisar campo y confección."])
        if kg_previstos > 0:
            alerts.append(["AMARILLO", "Pedidos previstos", "Hay demanda prevista no confirmada que puede consumir disponibilidad."])
        if len(alerts) == 2 and estado == "VERDE":
            alerts.append(["VERDE", "General", "No se detectan alertas globales con los datos del resumen."])
        story.append(Paragraph("ALERTAS DEL INFORME", self._normal))
        story.append(self._table(alerts, row_styles=[(i, r[0]) for i, r in enumerate(alerts[1:], start=1)], col_widths=[3*cm, 5*cm, 17.6*cm]))
        story.append(PageBreak())

    def _value(self, row: dict, column: str) -> Any:
        aliases = {
            "Tipo palet": ("Tipo palet", "TipoPalet", "Tipo Palet", "tipo_palet", "Tipo"),
            "Nombre palet": ("Nombre palet", "NombrePalet", "Nombre Palet", "nombre_palet", "Palet"),
            "Pedido": ("Pedido", "IdPedidoLora"),
            "IdPartida": ("IdPartida", "AlbaranDef"),
            "IdSocio": ("IdSocio",),
            "Nombre socio": ("Nombre socio", "Socio"),
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


    def _top_by(self, rows: Sequence[dict], group_field: str, sum_field: str, *, limit: int = 8) -> list[tuple[str, float]]:
        totals: dict[str, float] = {}
        for row in rows:
            key = str(self._value(row, group_field) or row.get(group_field) or "Sin especificar").strip() or "Sin especificar"
            totals[key] = totals.get(key, 0.0) + self._sum([row], sum_field)
        return sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]

    def _ranking_table(self, ranking: list[tuple[str, float]], total: float, kg_label: str) -> Table:
        data = [["Posición", "Variedad / grupo", kg_label, "% sobre total"]]
        for pos, (label, kg) in enumerate(ranking, start=1):
            pct = (kg / total * 100) if total else 0
            data.append([pos, label, self._format_kg(kg), self._format_pct(pct)])
        return self._table(data, col_widths=[2.5*cm, 11*cm, 6*cm, 4*cm], right_cols=[2, 3], center_cols=[0])

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
        self._section_title(story, "STOCK CAMPO", "stock_campo")
        if not rows:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal)); story.append(PageBreak()); return
        total_kg = self._sum(rows, "Kg campo")
        variedades_set = {str(self._value(r, "Variedad") or "").strip() for r in rows if str(self._value(r, "Variedad") or "").strip()}
        socios_set = {str(self._value(r, "Socio") or self._value(r, "IdSocio") or "").strip() for r in rows if str(self._value(r, "Socio") or self._value(r, "IdSocio") or "").strip()}
        boletas_set = {str(self._value(r, "Boleta") or "").strip() for r in rows if str(self._value(r, "Boleta") or "").strip()}
        grupos_set = {str(self._value(r, "Grupo varietal") or "").strip() for r in rows if str(self._value(r, "Grupo varietal") or "").strip()}
        story.append(Paragraph("STOCK CAMPO - RESUMEN", self._normal))
        story.append(self._kpi_cards([
            {"label": "TOTAL KG CAMPO", "value": self._format_t(total_kg), "unit": self._format_kg(total_kg)},
            {"label": "Nº VARIEDADES", "value": len(variedades_set), "unit": "variedades"},
            {"label": "Nº SOCIOS", "value": len(socios_set), "unit": "socios"},
            {"label": "Nº BOLETAS", "value": len(boletas_set), "unit": "boletas"},
            {"label": "Nº GRUPOS", "value": len(grupos_set), "unit": "grupos varietales"},
        ], columns=5, width=5.1*cm))
        top = self._top_by(rows, "Variedad", "Kg campo", limit=8)
        if top:
            story.append(Spacer(1, 6))
            story.append(Paragraph("TOP VARIEDADES EN CAMPO", self._normal))
            story.append(self._ranking_table(top, total_kg, "Kg campo"))
            story.append(Spacer(1, 8))
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


    def _weekday_es(self, iso_date: Any, upper: bool = False) -> str:
        names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        dt = self._parse_date(iso_date)
        name = names[dt.weekday()] if dt else ""
        return name.upper() if upper else name

    def _fmt_t(self, kg: Any) -> str:
        return self._format_t(kg)

    def _prevision_fecha(self, row: dict) -> Any:
        return row.get("Fecha_date") or row.get("Fecha") or row.get("FechaR_date") or row.get("FechaR")

    def _prevision_operational_detail_date(self, now: datetime | None = None) -> date:
        current = now or datetime.now()
        detail_date = current.date()
        if current.time() >= time(16, 0):
            detail_date += timedelta(days=1)
        return detail_date

    def _add_prevision_recoleccion(self, story: list, rows: list[dict], filters: dict[str, Any] | None = None) -> None:
        self._section_title(story, "PREVISIÓN DE RECOLECCIÓN", "prevision_recoleccion")
        if not rows:
            story.append(Paragraph("Sin previsión de recolección desde hoy para los filtros actuales.", self._normal))
            story.append(PageBreak())
            return
        total_kg = self._sum(rows, "KgAprox")
        socios = {str(self._value(r, "IdSocio") or r.get("Socio") or "").strip() for r in rows if str(self._value(r, "IdSocio") or r.get("Socio") or "").strip()}
        boletas = {str(r.get("Boleta") or "").strip() for r in rows if str(r.get("Boleta") or "").strip()}
        variedades = {str(r.get("Variedad") or "").strip() for r in rows if str(r.get("Variedad") or "").strip()}
        dias = sorted({str(self._prevision_fecha(r) or "") for r in rows if str(self._prevision_fecha(r) or "")})
        story.append(self._table([
            ["Kg previstos", "Nº socios", "Nº boletas", "Nº variedades", "Nº días"],
            [self._fmt_t(total_kg), len(socios), len(boletas), len(variedades), len(dias)],
        ], col_widths=[5*cm, 4*cm, 4*cm, 4*cm, 4*cm]))
        story.append(Spacer(1, 6))
        top_previstas = self._top_by(rows, "Variedad", "KgAprox", limit=8)
        if top_previstas:
            story.append(Paragraph("TOP VARIEDADES PREVISTAS", self._normal))
            story.append(self._ranking_table(top_previstas, total_kg, "Kg previstos"))
            story.append(Spacer(1, 8))

        self._add_prevision_weekly_matrix(story, rows, filters or {})

        by_day: dict[str, list[dict]] = {}
        for r in rows:
            by_day.setdefault(str(self._prevision_fecha(r)), []).append(r)
        day_summary = [["Día", "Fecha", "Kg previstos", "Nº socios", "Nº boletas"]]
        for day in sorted(by_day):
            day_rows = by_day[day]
            day_summary.append([self._weekday_es(day), self._parse_date(day).strftime("%d/%m/%Y") if self._parse_date(day) else day, self._fmt_t(self._sum(day_rows, "KgAprox")), len({str(r.get("IdSocio") or r.get("Socio") or "").strip() for r in day_rows if str(r.get("IdSocio") or r.get("Socio") or "").strip()}), len({str(r.get("Boleta") or "").strip() for r in day_rows if str(r.get("Boleta") or "").strip()})])
        story.append(Paragraph("Resumen por día", self._normal))
        story.append(self._table(day_summary, col_widths=[4*cm, 4*cm, 4*cm, 4*cm, 4*cm]))
        story.append(Spacer(1, 8))

        detail_cols = ["IdSocio", "Socio", "Boleta", "Variedad", "Manijero", "Matrícula", "Destino", "Cajas", "Kg aprox (t)", "Hora"]
        operational_date = self._prevision_operational_detail_date()
        operational_iso = operational_date.isoformat()
        story.append(Paragraph(f"Detalle operativo mostrado: {operational_date.strftime('%d/%m/%Y')}", self._normal))
        if operational_iso in by_day:
            day_rows = sorted(by_day[operational_iso], key=lambda r: (str(r.get("Variedad") or ""), str(r.get("Socio") or ""), str(r.get("Boleta") or "")))
            date_text = operational_date.strftime("%d/%m/%Y")
            story.append(Paragraph(f"{self._weekday_es(operational_iso, upper=True)} {date_text}", self._normal))
            data = [detail_cols]
            for r in day_rows:
                data.append([r.get("IdSocio", ""), r.get("Socio", ""), r.get("Boleta", ""), r.get("Variedad", ""), r.get("Manijero", ""), r.get("Matricula", r.get("Matricual", "")), r.get("Destino", ""), self._format_cell(r.get("Cajas", ""), "Cajas"), self._fmt_t(r.get("KgAprox")), r.get("Hora", "")])
            for label, key in (("Subtotal variedad", "Variedad"), ("Subtotal socio", "Socio")):
                totals: dict[str, float] = {}
                for r in day_rows:
                    name = str(r.get(key) or "Sin especificar")
                    totals[name] = totals.get(name, 0.0) + float(r.get("KgAprox") or 0)
                for name, kg in sorted(totals.items()):
                    data.append([f"{label}: {name}"] + [""] * 7 + [self._fmt_t(kg), ""])
            data.append(["TOTAL DÍA"] + [""] * 7 + [self._fmt_t(self._sum(day_rows, "KgAprox")), ""])
            story.append(self._table(data))
        else:
            story.append(Paragraph("Sin previsión para el día operativo seleccionado.", self._normal))
        story.append(Spacer(1, 6))

        final: dict[str, list[dict]] = {}
        for r in rows:
            final.setdefault(str(r.get("Variedad") or "Sin especificar"), []).append(r)
        final_rows = [["Variedad", "Kg previstos", "Nº socios", "Nº boletas"]]
        for variedad, vrows in sorted(final.items(), key=lambda item: self._sum(item[1], "KgAprox"), reverse=True):
            final_rows.append([variedad, self._fmt_t(self._sum(vrows, "KgAprox")), len({str(r.get("IdSocio") or r.get("Socio") or "").strip() for r in vrows if str(r.get("IdSocio") or r.get("Socio") or "").strip()}), len({str(r.get("Boleta") or "").strip() for r in vrows if str(r.get("Boleta") or "").strip()})])
        story.append(Paragraph("Resumen final por variedad", self._normal))
        story.append(self._table(final_rows, col_widths=[8*cm, 5*cm, 4*cm, 4*cm]))
        story.append(PageBreak())


    def _single_selected_cultivo(self, filters: dict[str, Any]) -> str:
        selected = sorted(self._selected_filter_values((filters or {}).get("cultivo")))
        return selected[0] if len(selected) == 1 else ""

    def _cultivo_for_prevision_row(self, row: dict, filters: dict[str, Any]) -> str:
        cultivo = str(row.get("Cultivo") or row.get("CULTIVO") or "").strip()
        if cultivo:
            return cultivo
        return self._single_selected_cultivo(filters)

    def _cultivo_abbrev(self, cultivo: Any) -> str:
        text = str(cultivo or "").strip().upper()
        mapping = {"SANDIA": "SA", "SANDÍA": "SA", "CITRICOS": "CI", "CÍTRICOS": "CI"}
        return mapping.get(text, text[:2]) if text else ""

    def _weekly_day_labels(self, rows: list[dict]) -> list[tuple[str, str]]:
        parsed_dates = [self._parse_date(self._prevision_fecha(r)) for r in rows]
        parsed_dates = [d for d in parsed_dates if d]
        start = min(parsed_dates) if parsed_dates else datetime.now().date()
        days = [start + timedelta(days=i) for i in range(7)]
        return [(d.isoformat(), f"{self._weekday_es(d.isoformat()).lower()}-{d.day:02d}") for d in days]

    def _format_weekly_tons(self, kg: float) -> str:
        return f"{kg / 1000:.1f}" if kg else "-"

    def _add_prevision_weekly_matrix(self, story: list, rows: list[dict], filters: dict[str, Any]) -> None:
        days = self._weekly_day_labels(rows)
        grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            day = self._parse_date(self._prevision_fecha(row))
            if not day:
                continue
            iso = day.isoformat()
            if iso not in {d[0] for d in days}:
                continue
            socio = str(row.get("Socio") or self._value(row, "Nombre socio") or "").strip()
            cultivo = self._cultivo_for_prevision_row(row, filters)
            variedad = str(row.get("Variedad") or "").strip()
            key = (socio, cultivo, variedad)
            bucket = grouped.setdefault(key, {"Socio": socio, "Cult.": self._cultivo_abbrev(cultivo), "Variedad": variedad, "days": {d[0]: 0.0 for d in days}})
            bucket["days"][iso] += self._sum([row], "KgAprox")

        header = ["Socio", "Cult.", "Variedad"] + [label for _, label in days] + ["Total"]
        data = [header]
        day_totals = {d[0]: 0.0 for d in days}
        for key in sorted(grouped):
            bucket = grouped[key]
            values = [bucket["days"][d[0]] for d in days]
            for iso, kg in zip([d[0] for d in days], values):
                day_totals[iso] += kg
            data.append([bucket["Socio"], bucket["Cult."], bucket["Variedad"]] + [self._format_weekly_tons(kg) for kg in values] + [self._format_weekly_tons(sum(values))])
        data.append(["TOTAL", "", ""] + [self._format_weekly_tons(day_totals[d[0]]) for d in days] + [self._format_weekly_tons(sum(day_totals.values()))])
        story.append(Paragraph("RESUMEN SEMANAL DE RECOLECCIÓN PREVISTA", self._normal))
        story.append(self._table(data, col_widths=[4.2*cm, 1.2*cm, 4.2*cm] + [1.9*cm] * 8, right_cols=list(range(3, 11)), center_cols=list(range(1, 11))))
        story.append(Spacer(1, 8))

    def _has_any_value(self, rows: Sequence[dict], column: str) -> bool:
        return any(str(self._value(row, column) or "").strip() for row in rows)

    def _add_stock_almacen(self, story: list, rows: list[dict]) -> None:
        self._section_title(story, "STOCK ALMACÉN RESUMIDO", "stock_almacen")
        if not rows:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal)); story.append(PageBreak()); return
        total_kg = self._sum(rows, "Kg stock")
        total_palets = self._sum(rows, "Palets")
        total_cajas = self._sum(rows, "Cajas")
        confecciones = {str(self._value(r, "Confección") or "").strip() for r in rows if str(self._value(r, "Confección") or "").strip()}
        calibres = {str(self._value(r, "Calibre") or "").strip() for r in rows if str(self._value(r, "Calibre") or "").strip()}
        story.append(Paragraph("STOCK ALMACÉN - RESUMEN", self._normal))
        story.append(self._kpi_cards([
            {"label": "KG STOCK TOTAL", "value": self._format_t(total_kg), "unit": self._format_kg(total_kg)},
            {"label": "PALETS TOTALES", "value": self._format_number(total_palets, 0), "unit": "palets"},
            {"label": "CAJAS TOTALES", "value": self._format_number(total_cajas, 0), "unit": "cajas"},
            {"label": "Nº CONFECCIONES", "value": len(confecciones), "unit": "confecciones"},
            {"label": "Nº CALIBRES", "value": len(calibres), "unit": "calibres"},
        ], columns=5, width=5.1*cm))
        top_confecciones = self._top_by(rows, "Confección", "Kg stock", limit=8)
        if top_confecciones:
            story.append(Spacer(1, 6))
            story.append(Paragraph("TOP CONFECCIONES EN ALMACÉN", self._normal))
            story.append(self._ranking_table(top_confecciones, total_kg, "Kg stock"))
            story.append(Spacer(1, 8))
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
        anchor = "pedidos_pendientes" if not previsto else "balance_comercial"
        self._section_title(story, title, anchor)
        if not rows:
            msg = "Sin pedidos previstos para los filtros actuales." if previsto else "No hay pedidos pendientes para el cultivo seleccionado."
            story.append(Paragraph(msg, self._normal)); story.append(PageBreak()); return
        pedido_kg = "Kg estimados" if previsto else "Kg pedido teórico"
        palets = "Palets estimados" if previsto else "Palets pendientes"
        if not previsto:
            self._add_pedidos_resumen_operativo(story, rows)
        self._add_confeccion_mix(story, rows, kg_field, palets)
        self._add_timeline(story, rows, pedido_kg, kg_field, palets, previsto)
        if not previsto:
            self._add_pedidos_detail(story, rows)
        self._add_pedidos_matrix(story, rows, pedido_kg, kg_field, palets)
        story.append(PageBreak())

    def _add_pedidos_resumen_operativo(self, story: list, rows: list[dict]) -> None:
        pedidos = {str(self._value(r, "Pedido") or "").strip() for r in rows if str(self._value(r, "Pedido") or "").strip()}
        terminados = [r for r in rows if str(self._value(r, "Estado") or "").strip().upper() in {"TERMINADO", "COMPLETO"}]
        pedidos_terminados = {str(self._value(r, "Pedido") or "").strip() for r in terminados if str(self._value(r, "Pedido") or "").strip()}
        estimadas = [r for r in rows if str(self._value(r, "Origen cálculo") or "").strip().upper() == "ESTIMADO_SIN_CONFECCION"]
        data = [
            ["Kg pedido teórico total", "Kg hecho real total", "Kg pendiente total", "Kg terminado/completo total"],
            [self._num(self._sum(rows, "Kg pedido teórico")), self._num(self._sum(rows, "Kg hecho real")), self._num(self._sum(rows, "Kg pendiente")), self._num(self._sum(terminados, "Kg pedido teórico"))],
            ["Nº pedidos total", "Nº pedidos pendientes", "Nº pedidos terminados", "Nº líneas sin confección estimadas"],
            [len(pedidos), len(pedidos - pedidos_terminados), len(pedidos_terminados), len(estimadas)],
        ]
        story.append(Paragraph("Resumen pedidos pendientes", self._normal))
        story.append(self._table(data, repeat=0, header=False, col_widths=[6*cm, 6*cm, 6*cm, 7*cm]))
        story.append(Spacer(1, 6))

    def _add_pedidos_detail(self, story: list, rows: list[dict]) -> None:
        columns = [
            "Pedido", "Cliente", "Fecha salida", "Cultivo", "Variedad Coop", "Grupo varietal",
            "Calibre", "Categoría", "Marca", "Confección", "Grupo confección", "Palets pedido",
            "Kg pedido teórico", "Kg estimado", "Kg hecho real", "Kg pendiente", "Estado", "Observación",
        ]
        data = [columns]
        styles = []
        for r in sorted(rows, key=lambda x: (str(self._value(x, "Fecha salida")), str(self._value(x, "Cliente")), str(self._value(x, "Pedido"))))[:120]:
            data.append([self._format_cell(self._value(r, c), c) for c in columns])
            estado = str(self._value(r, "Estado") or "").upper()
            if estado in {"TERMINADO", "COMPLETO"}:
                styles.append((len(data) - 1, "VERDE"))
            elif str(self._value(r, "Origen cálculo") or "").upper() == "ESTIMADO_SIN_CONFECCION":
                styles.append((len(data) - 1, "AMARILLO"))
        story.append(Paragraph("Detalle pedidos pendientes (incluye terminados/completos)", self._normal))
        story.append(self._table(data, row_styles=styles))
        story.append(Spacer(1, 6))

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
        self._section_title(story, "APROVECHAMIENTO ESTIMADO", "aprovechamiento_estimado")
        if not rows:
            story.append(Paragraph("Sin stock campo para analizar aprovechamientos.", self._normal)); story.append(PageBreak()); return
        total = self._sum(rows, "Kg campo")
        def estado(row: dict) -> str:
            txt = str(self._value(row, "Estado aprovechamiento") or self._value(row, "Origen aprovechamiento") or self._value(row, "Origen") or "").upper()
            if "PESOSFRES" in txt or ("REAL" in txt and "LOTEADO" not in txt): return "Real PesosFres"
            if "LOTEADO" in txt: return "Real Loteado"
            if "HARVESTSYNC" in txt: return "HarvestSync"
            if "MANUAL" in txt or "ESTIMADO" in txt: return "Estimado manual"
            return "Sin aprovechamiento"
        blocks = [("Real PesosFres", []), ("Real Loteado", []), ("HarvestSync", []), ("Estimado manual", []), ("Sin aprovechamiento", [])]
        by = {k: v for k, v in blocks}
        for r in rows: by[estado(r)].append(r)
        data = [["Origen", "Nº partidas", "Kg campo afectado", "%", "Estado"]]
        row_styles = []
        for label, part_rows in blocks:
            kg = self._sum(part_rows, "Kg campo")
            pct = (kg / total * 100 if total else 0)
            sem = self._risk_label(sin_aprovechamiento_pct=pct) if label == "Sin aprovechamiento" else "VERDE"
            data.append([label, len(part_rows), self._format_kg(kg), self._format_pct(pct), sem])
            if label == "Sin aprovechamiento":
                row_styles.append((len(data) - 1, sem))
        story.append(Paragraph("Resumen visual por origen", self._normal))
        story.append(self._table(data, row_styles=row_styles, col_widths=[8*cm, 4*cm, 5*cm, 3*cm, 3*cm]))
        story.append(PageBreak())

    def _add_aprovechamiento_detalle_partida(self, story: list, stock_rows: list[dict], detalle_map: dict[str, list[dict]]) -> None:
        story.append(Paragraph("DETALLE APROVECHAMIENTO ESTIMADO POR PARTIDA", self._section))
        if not stock_rows:
            story.append(Paragraph("Sin stock campo para detallar aprovechamientos.", self._normal)); story.append(PageBreak()); return

        cal_cols = [f"CAL {i} %" for i in range(11)]
        columns = [
            "IdPartida", "Boleta", "IdSocio", "Nombre socio", "Fecha carga", "T entregadas",
            "T comerciales", "Origen", "Destrío %", "Industria %",
        ] + cal_cols + ["% comercial total"]
        groups: dict[str, list[dict[str, Any]]] = {}
        total_general = self._empty_aprovechamiento_totals()
        seen: set[tuple[str, str, str, str]] = set()

        for partida in sorted(stock_rows, key=lambda r: (self._grupo_varietal_partida(r).upper(), str(self._value(r, "Fecha carga")), str(self._value(r, "Boleta")), str(self._value(r, "IdPartida")))):
            unique_key = (
                str(self._value(partida, "IdPartida") or ""),
                str(self._value(partida, "Boleta") or ""),
                str(self._value(partida, "Fecha carga") or ""),
                str(self._value(partida, "Kg campo") or ""),
            )
            if unique_key in seen:
                continue
            seen.add(unique_key)
            detail = self._aprovechamiento_partida_detail(partida, detalle_map)
            groups.setdefault(detail["grupo_varietal"], []).append(detail)
            self._accumulate_aprovechamiento_totals(total_general, detail)

        data: list[list[Any]] = [columns]
        styles: list[tuple[int, str]] = []
        for grupo in sorted(groups, key=lambda g: g.upper()):
            details = groups[grupo]
            data.append([f"GRUPO VARIETAL: {grupo}"] + [""] * (len(columns) - 1))
            styles.append((len(data) - 1, "GRUPO_APROVECHAMIENTO"))
            group_totals = self._empty_aprovechamiento_totals()
            for detail in details:
                self._accumulate_aprovechamiento_totals(group_totals, detail)
                data.append(detail["row"])
                styles.append((len(data) - 1, detail["origen"]))
            data.append(self._aprovechamiento_totals_row(f"SUBTOTAL {grupo}", group_totals, columns))
            styles.append((len(data) - 1, "SUBTOTAL_APROVECHAMIENTO"))
        data.append(self._aprovechamiento_totals_row("TOTAL GENERAL", total_general, columns))
        styles.append((len(data) - 1, "TOTAL_APROVECHAMIENTO"))
        story.append(self._table(data, row_styles=styles, col_widths=[
            1.25*cm, 1.05*cm, 1.05*cm, 2.0*cm, 1.4*cm, 1.25*cm, 1.25*cm, 1.7*cm, 1.0*cm, 1.0*cm,
            *([0.72*cm] * 11), 1.15*cm,
        ]))
        story.append(PageBreak())

    def _empty_aprovechamiento_totals(self) -> dict[str, Any]:
        return {"partidas": 0, "kg_entregado": 0.0, "kg_estimado": 0.0, "calibres": {str(i): 0.0 for i in range(11)}, "destrio_kg": 0.0, "industria_kg": 0.0}

    def _accumulate_aprovechamiento_totals(self, totals: dict[str, Any], detail: dict[str, Any]) -> None:
        totals["partidas"] += 1
        totals["kg_entregado"] += detail["kg_entregado"]
        totals["kg_estimado"] += detail["kg_estimado"]
        for cal, kg in detail["kg_by_cal"].items():
            totals["calibres"][cal] += kg
        if detail.get("destrio_pct") is not None:
            totals["destrio_kg"] += detail["kg_entregado"] * detail["destrio_pct"] / 100
        if detail.get("industria_pct") is not None:
            totals["industria_kg"] += detail["kg_entregado"] * detail["industria_pct"] / 100

    def _aprovechamiento_resumen_table(self, title: str, totals: dict[str, Any]) -> Table:
        resumen = [
            [title, "", "", ""],
            ["Nº partidas", "Kg entregados", "Kg estimados", ""],
            [totals["partidas"], self._format_toneladas(totals["kg_entregado"]), self._format_toneladas(totals["kg_estimado"]), ""],
            ["Calibre", "Toneladas", "Calibre", "Toneladas"],
        ]
        for i in range(0, 11, 2):
            resumen.append([
                f"CAL{i}", self._format_toneladas(totals["calibres"][str(i)]),
                f"CAL{i + 1}" if i + 1 <= 10 else "", self._format_toneladas(totals["calibres"][str(i + 1)]) if i + 1 <= 10 else "",
            ])
        return self._table(resumen, row_styles=[(0, "SUBTOTAL_APROVECHAMIENTO")], col_widths=[5*cm, 4*cm, 5*cm, 4*cm])

    def _weighted_pct(self, kg: float, total_kg: float) -> float | None:
        return (kg / total_kg * 100) if total_kg else None

    def _aprovechamiento_totals_row(self, label: str, totals: dict[str, Any], columns: list[str]) -> list[str]:
        row = [""] * len(columns)
        row[0] = label
        row[1] = str(totals["partidas"])
        row[5] = self._format_toneladas_cifra(totals["kg_entregado"])
        row[6] = self._format_toneladas_cifra(totals["kg_estimado"])
        row[8] = self._format_pct_1(self._weighted_pct(totals.get("destrio_kg", 0.0), totals["kg_entregado"]))
        row[9] = self._format_pct_1(self._weighted_pct(totals.get("industria_kg", 0.0), totals["kg_entregado"]))
        for i in range(11):
            row[columns.index(f"CAL {i} %")] = self._format_pct_1(self._weighted_pct(totals["calibres"][str(i)], totals["kg_entregado"]), blank="0,0")
        row[columns.index("% comercial total")] = self._format_pct_1(self._weighted_pct(totals["kg_estimado"], totals["kg_entregado"]), blank="0,0")
        return row

    def _row_float(self, row: dict, *fields: str) -> float | None:
        for field in fields:
            if field in row and str(row.get(field) or "").strip() != "":
                try:
                    return float(str(row.get(field)).replace(",", "."))
                except Exception:
                    pass
        return None

    def _aprovechamiento_pct_from_rows(self, rows: list[dict], pct_fields: tuple[str, ...], kg_fields: tuple[str, ...], denominator_fields: tuple[str, ...], fallback_kg: float) -> float | None:
        vals = [self._row_float(r, *pct_fields) for r in rows]
        vals = [v for v in vals if v is not None]
        if vals:
            return sum(vals) / len(vals)
        num = sum((self._row_float(r, *kg_fields) or 0.0) for r in rows)
        den = sum((self._row_float(r, *denominator_fields) or 0.0) for r in rows) or fallback_kg
        return (num / den * 100) if num and den else None

    def _aprovechamiento_partida_detail(self, partida: dict, detalle_map: dict[str, list[dict]]) -> dict[str, Any]:
        boleta = str(self._value(partida, "Boleta") or "").strip()
        rows = list(detalle_map.get(self._detalle_partida_key(partida)) or detalle_map.get(boleta) or [])
        origen = self._aprovechamiento_origen(rows)
        kg_by_cal = {str(i): 0.0 for i in range(11)}
        for row in rows:
            cal = self._pure_calibre(row.get("Calibre"))
            if cal in kg_by_cal:
                kg_by_cal[cal] += self._sum([row], "Kg disponibles")
        kg_entregado = self._sum([partida], "Kg campo")
        kg_estimado = sum(kg_by_cal.values()) if rows else 0.0
        destrio_pct = self._aprovechamiento_pct_from_rows(rows, ("Destrío %", "Destrio %"), ("Podrido",), ("NetoPartida", "Neto"), kg_entregado)
        industria_pct = self._aprovechamiento_pct_from_rows(rows, ("Industria %",), ("Destrios", "Destríos"), ("NetoPartida", "Neto"), kg_entregado)
        cal_pcts = [self._format_pct_1((kg_by_cal[str(i)] / kg_entregado * 100) if kg_entregado else 0.0, blank="0,0") for i in range(11)]
        row = [
            self._format_cell(self._value(partida, "IdPartida"), "IdPartida"),
            self._format_cell(self._value(partida, "Boleta"), "Boleta"),
            self._format_cell(self._value(partida, "IdSocio"), "IdSocio"),
            self._format_cell(self._value(partida, "Nombre socio") or self._value(partida, "Socio"), "Nombre socio"),
            self._format_cell(self._value(partida, "Fecha carga"), "Fecha carga"),
            "", "", origen, self._format_pct_1(destrio_pct), self._format_pct_1(industria_pct),
        ] + cal_pcts + [self._format_pct_1((kg_estimado / kg_entregado * 100) if kg_entregado else 0.0, blank="0,0")]
        return {"grupo_varietal": self._grupo_varietal_partida(partida), "origen": origen, "kg_by_cal": kg_by_cal, "kg_entregado": kg_entregado, "kg_estimado": kg_estimado, "destrio_pct": destrio_pct, "industria_pct": industria_pct, "row": row}

    def _grupo_varietal_partida(self, row: dict) -> str:
        grupo = self._value(row, "Grupo varietal") or self._value(row, "GrupoVarietal") or self._value(row, "grupo_varietal")
        return str(grupo or "SIN GRUPO VARIETAL").strip() or "SIN GRUPO VARIETAL"

    def _aprovechamiento_origen(self, rows: list[dict]) -> str:
        if not rows:
            return "SIN_APROVECHAMIENTO"
        txt = " ".join(str(r.get("Origen aprovechamiento", r.get("Origen", "")) or "").upper() for r in rows)
        if "HARVESTSYNC" in txt:
            return "HARVESTSYNC"
        if "LOTEADO" in txt:
            return "LOTEADO"
        if "PESOSFRES" in txt or "REAL" in txt:
            return "REAL_PESOSFRES"
        return str(rows[0].get("Origen aprovechamiento") or rows[0].get("Origen") or "SIN_APROVECHAMIENTO").upper()

    def _detalle_partida_key(self, row: dict) -> str:
        kg_campo = self._sum([row], "Kg campo")
        return "PARTIDA|" + "|".join([
            str(self._value(row, "Boleta") or "").strip(),
            str(self._value(row, "Fecha carga") or "").strip(),
            str(self._value(row, "Socio") or "").strip(),
            str(self._value(row, "Variedad") or "").strip(),
            str(self._value(row, "Grupo varietal") or "").strip(),
            str(float(kg_campo)),
        ])

    def _pure_calibre(self, value: Any) -> str:
        text = str(value or "").strip().upper().replace("CAL", "").strip()
        return text if text.isdigit() and 0 <= int(text) <= 10 else ""

    def _add_aprovechamiento_volcado(self, story: list, volcado: dict[str, Any]) -> None:
        self._section_title(story, "APROVECHAMIENTO DE VOLCADO", "aprovechamiento_volcado")
        story.append(Paragraph(f"Periodo de volcado analizado: {volcado.get('periodo_texto') or 'Sin periodo disponible'}", self._normal))
        rows = list(volcado.get("rows") or [])
        summary = volcado.get("summary") or {}
        if not rows:
            story.append(Paragraph("Sin partidas volcadas o sin líneas de loteado para el periodo y filtros actuales.", self._normal)); story.append(PageBreak()); return
        sem = summary.get("semaforo", "Rojo")
        resumen = [["Nº partidas volcadas", "Líneas peso real", "Líneas estimadas", "Sin estimación", "Kg reales", "Kg estimados", "Cobertura líneas"], [summary.get("partidas", 0), summary.get("lineas_reales", 0), summary.get("lineas_estimadas", 0), summary.get("sin_estimacion", 0), self._num(summary.get("kg_real", 0)), self._num(summary.get("kg_estimado", 0)), f"{summary.get('cobertura_palets', 0):.1f}% ({sem})"]]
        story.append(self._table(resumen, row_styles=[(1, str(sem).upper())]))
        partida_summary = list(volcado.get("partida_summary") or [])
        if partida_summary:
            story.append(Paragraph("RESUMEN DESTRÍO Y MERMA POR PARTIDA VOLCADA", self._normal))
            pcols = ["Partida principal", "Boleta", "Socio", "Nombre socio", "Neto partidas", "Neto comercial", "Destrío", "Merma", "% comercial", "% destrío", "% merma"]
            pct_cols = {"% comercial", "% destrío", "% merma"}
            kg_cols = {"Neto partidas", "Neto comercial", "Destrío", "Merma"}
            pdata = [pcols]
            for r in partida_summary[:80]:
                pdata.append([
                    f"{float(r.get(c) or 0):.1f}%" if c in pct_cols else self._fmt_t(r.get(c, 0)) if c in kg_cols else r.get(c, "")
                    for c in pcols
                ])
            story.append(self._table(pdata, col_widths=[2.5*cm, 1.6*cm, 1.6*cm, 4.2*cm, 2.1*cm, 2.1*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.8*cm]))
            story.append(Spacer(1, 6))
        cols = ["Cultivo", "Grupo varietal", "Variedad", "Calibre", "Categoría", "Kg reales", "Kg estimados", "Kg total", "% sobre calculado"]
        story.append(self._table([cols] + [[self._format_cell(r.get(c, ""), c) for c in cols] for r in rows[:80]]))
        story.append(Spacer(1, 6))
        grouped_rows = list(volcado.get("grouped_partidas") or [])
        grouped_summary = volcado.get("grouped_summary") or {}
        story.append(Paragraph("PARTIDAS AGRUPADAS EN VOLCADO", self._normal))
        grouped_resume = [
            ["Nº partidas principales volcadas", "Nº partidas incluidas totales", "Nº partidas agrupadas adicionales", "Kg total agrupado según Partidas.kgP"],
            [
                grouped_summary.get("principales", 0),
                grouped_summary.get("incluidas", 0),
                grouped_summary.get("adicionales", 0),
                self._num(grouped_summary.get("kg_total", 0)),
            ],
        ]
        story.append(self._table(grouped_resume))
        if grouped_rows:
            grouped_cols = ["Partida principal", "Partida incluida", "Boleta", "Socio", "Nombre socio", "Fecha carga", "Semana", "Kg asociado", "Tipo"]
            table_rows = [grouped_cols] + [[self._format_cell(r.get(c, ""), c) for c in grouped_cols] for r in grouped_rows[:120]]
            row_styles = [(idx, "DESTACADO") for idx, r in enumerate(grouped_rows[:120], start=1) if str(r.get("Tipo", "")).startswith("Principal")]
            story.append(self._table(
                table_rows,
                col_widths=[3.0*cm, 3.0*cm, 1.8*cm, 1.8*cm, 4.6*cm, 2.2*cm, 1.5*cm, 2.1*cm, 2.3*cm],
                row_styles=row_styles,
            ))
        else:
            story.append(Paragraph("Sin trazabilidad de partidas agrupadas para el periodo y filtros actuales.", self._normal))
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
        logger.debug("INFORME PDF comparativa calibres=%s", max(0, len(data) - 1))
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
        self._section_title(story, "CAPACIDAD PRODUCTIVA", "capacidad_productiva")
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
        if any(x in column for x in ("Palets", "Cajas")):
            return self._format_number(self._to_float(value), 0) if str(value).strip() else ""
        return str(value or "")

    def _table(self, data: list[list[Any]], repeat: int = 1, header: bool = True, col_widths: list[float] | None = None, row_styles: list[tuple[int, str]] | None = None, right_cols: Sequence[int] | None = None, center_cols: Sequence[int] | None = None) -> Table:
        wrapped = [[self._p(c) for c in row] for row in data]
        t = Table(wrapped, repeatRows=repeat, colWidths=col_widths)
        style = [("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 2), ("RIGHTPADDING", (0,0), (-1,-1), 2)]
        if header: style += [("BACKGROUND", (0,0), (-1,0), colors.HexColor(self.COLOR_HEADER_BG)), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold")]
        for col in center_cols or []:
            style.append(("ALIGN", (col, 0), (col, -1), "CENTER"))
        for col in right_cols or []:
            style.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
        for i, row in enumerate(data):
            first = str(row[0]) if row else ""
            if first.startswith("Subtotal confección"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor(self.COLOR_LIGHT_BG))]
            elif first.startswith("Subtotal marca"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#EAF3F8"))]
            elif first.startswith("Total grupo varietal"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor(self.COLOR_HEADER_BG))]
            elif first.startswith("TOTAL ALMACÉN"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#9DC3E6"))]
            elif first.startswith("SUBTOTAL GRUPO VARIETAL"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#D9D9D9"))]
            elif first.startswith("GRUPO VARIETAL:"):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor(self.COLOR_HEADER_BG)), ("SPAN", (0,i), (-1,i))]
            elif first.startswith("SUBTOTAL "):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#EAF3F8"))]
            elif first.startswith(("Subtotal", "Total", "TOTAL")):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor(self.COLOR_LIGHT_BG))]
        color_map = {
            "VERDE": self.COLOR_GREEN, "AMARILLO": self.COLOR_YELLOW, "ROJO": self.COLOR_RED, "GRIS": self.COLOR_GREY,
            "HARVESTSYNC": "#D9EAF7", "REAL_PESOSFRES": "#E2F0D9", "LOTEADO": "#E7E6E6",
            "MANUAL": "#FFF2CC", "ESTIMADO_MANUAL": "#FFF2CC", "SIN_APROVECHAMIENTO": "#F4CCCC",
            "GRUPO_APROVECHAMIENTO": "#D9EAF7", "SUBTOTAL_APROVECHAMIENTO": "#EAF3F8", "TOTAL_APROVECHAMIENTO": "#D9D9D9",
        }
        for row_idx, marker in row_styles or []:
            marker_text = str(marker).upper()
            if marker_text in color_map:
                style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor(color_map[marker_text])))
                if marker_text in {"GRUPO_APROVECHAMIENTO", "SUBTOTAL_APROVECHAMIENTO", "TOTAL_APROVECHAMIENTO"}:
                    style.append(("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Bold"))
                if marker_text == "GRUPO_APROVECHAMIENTO":
                    style.append(("SPAN", (0, row_idx), (-1, row_idx)))
            elif marker_text == "DESTACADO":
                style.append(("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Bold"))
                style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#EAF3F8")))
            elif marker_text in {"socio", "variedad", "cultivo", "general"}:
                style.append(("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Bold"))
                style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor(self.COLOR_LIGHT_BG)))
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
            ("PREVISIÓN DE RECOLECCIÓN", kwargs.get("prevision_recoleccion_rows", [])),
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
