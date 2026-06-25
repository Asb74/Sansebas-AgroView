from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence
import logging
import re
import unicodedata

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
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


    def default_filename(self, cultivos: Sequence[Any] | None = None, now: datetime | None = None, report_mode: str | None = None) -> str:
        cultivo_slug = self._cultivo_filename_slug(cultivos)
        timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M")
        if report_mode is None:
            return f"Informe_comercial_{cultivo_slug}_{timestamp}.pdf"
        mode = self._normalize_report_mode(report_mode)
        return f"Informe_{mode}_{cultivo_slug}_{timestamp}.pdf"

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
        report_mode: str = "operativo",
    ) -> Path:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = self._normalize_report_mode(report_mode)
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
                report_mode=mode,
            )
            return target
        self._styles = getSampleStyleSheet()
        self._small = ParagraphStyle("Small", parent=self._styles["Normal"], fontSize=5.8, leading=6.7, alignment=TA_LEFT)
        self._small_right = ParagraphStyle("SmallRight", parent=self._small, alignment=TA_RIGHT)
        self._small_center = ParagraphStyle("SmallCenter", parent=self._small, alignment=TA_CENTER)
        self._normal = ParagraphStyle("NormalCompact", parent=self._styles["Normal"], fontSize=8, leading=9.5)
        self._section = ParagraphStyle("Section", parent=self._styles["Heading2"], fontSize=14, leading=16, spaceBefore=4, spaceAfter=7, textColor=colors.HexColor(self.COLOR_PRIMARY))
        self._title = ParagraphStyle("Title", parent=self._styles["Heading1"], fontSize=20, leading=23, alignment=TA_CENTER, textColor=colors.HexColor(self.COLOR_PRIMARY))
        self._kpi = ParagraphStyle("Kpi", parent=self._styles["Normal"], fontSize=10, leading=12, alignment=TA_CENTER)
        self._cell_small = ParagraphStyle("CellSmall", parent=self._styles["Normal"], fontSize=7, leading=8.4, alignment=TA_LEFT)
        self._cell_tiny = ParagraphStyle("CellTiny", parent=self._styles["Normal"], fontSize=5.2, leading=6.3, alignment=TA_LEFT)
        self._cell_wrap = ParagraphStyle("CellWrap", parent=self._styles["Normal"], fontSize=6.5, leading=7.8, alignment=TA_LEFT)
        self._header_small = ParagraphStyle("HeaderSmall", parent=self._cell_small, fontName="Helvetica-Bold", alignment=TA_CENTER)
        self._header_tiny = ParagraphStyle("HeaderTiny", parent=self._cell_tiny, fontName="Helvetica-Bold", alignment=TA_CENTER)
        self._kpi_title = ParagraphStyle("KpiTitle", parent=self._kpi, fontSize=8, leading=9.5)
        self._kpi_value = ParagraphStyle("KpiValue", parent=self._kpi, fontSize=14, leading=16)
        self._kpi_subtext = ParagraphStyle("KpiSubtext", parent=self._kpi, fontSize=7, leading=8.5)
        self._alert_cell = ParagraphStyle("AlertCell", parent=self._cell_wrap, fontSize=7, leading=8.5)
        self._current_report_mode = mode
        self._generated_at = generated_at or datetime.now()

        campo = list(stock_campo_rows or [])
        almacen = list(stock_almacen_rows or [])
        prevision = list(prevision_recoleccion_rows or [])
        active_filters = filters or {}
        presentation_warnings = self._run_pdf_presentation_checks({
            "stock_campo_rows": campo,
            "stock_almacen_rows": almacen,
            "prevision_recoleccion_rows": prevision,
            "pedidos_pendientes_rows": list(pedidos_pendientes_rows or []),
            "pedidos_previstos_rows": list(pedidos_previstos_rows or []),
            "aprovechamiento_volcado": aprovechamiento_volcado or {},
        })
        for warning in presentation_warnings:
            logger.warning("PDF presentation check: %s", warning)
        selected_cultivos = self._selected_filter_values(active_filters.get("cultivo"))
        pendientes = self._filter_pending_rows(list(pedidos_pendientes_rows or []), selected_cultivos)
        previstos = list(pedidos_previstos_rows or [])
        if mode == "direccion":
            self._generate_direction_report(
                target,
                filters=active_filters,
                campo=campo,
                almacen=almacen,
                prevision=prevision,
                pendientes=pendientes,
                previstos=previstos,
                aprovechamiento_volcado=aprovechamiento_volcado or {},
                aprovechamiento_campo_detalle=aprovechamiento_campo_detalle or {},
                generated_at=generated_at or datetime.now(),
            )
            return target

        story: list[Any] = []
        self._add_index(story)
        self._add_header(story, active_filters, generated_at or datetime.now())
        self._add_summary(story, campo, almacen, pendientes, previstos)
        self._add_vision_comercial(story, pendientes)
        self._add_vision_produccion(story, pendientes, prevision)
        self._add_vision_calidad(story, campo, aprovechamiento_campo_detalle or {}, aprovechamiento_volcado or {})
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
        doc = SimpleDocTemplate(str(target), pagesize=landscape(A4), leftMargin=0.7*cm, rightMargin=0.7*cm, topMargin=0.7*cm, bottomMargin=1.0*cm)
        doc.build(story, onFirstPage=self._draw_footer, onLaterPages=self._draw_footer)
        return target


    def _normalize_report_mode(self, report_mode: str | None) -> str:
        mode = str(report_mode or "operativo").strip().lower()
        if mode not in {"operativo", "direccion"}:
            raise ValueError("report_mode debe ser 'operativo' o 'direccion'")
        return mode

    def _generate_direction_report(
        self,
        target: Path,
        *,
        filters: dict[str, Any],
        campo: list[dict],
        almacen: list[dict],
        prevision: list[dict],
        pendientes: list[dict],
        previstos: list[dict],
        aprovechamiento_volcado: dict[str, Any],
        aprovechamiento_campo_detalle: dict[str, list[dict]],
        generated_at: datetime,
    ) -> None:
        story: list[Any] = []
        self._add_direction_index(story)
        self._add_direction_cover(story, filters, campo, almacen, pendientes, previstos, generated_at)
        self._add_direction_commercial(story, pendientes)
        self._add_direction_production(story, pendientes, prevision)
        self._add_direction_quality(story, campo, aprovechamiento_volcado)
        self._add_direction_alerts_recommendations(story, campo, almacen, pendientes, previstos)
        self._current_report_mode = "direccion"
        self._generated_at = generated_at
        doc = SimpleDocTemplate(str(target), pagesize=landscape(A4), leftMargin=0.7*cm, rightMargin=0.7*cm, topMargin=0.7*cm, bottomMargin=1.0*cm)
        doc.build(story, onFirstPage=self._draw_footer, onLaterPages=self._draw_footer)

    def _add_direction_index(self, story: list) -> None:
        story.append(PdfBookmark("indice", "ÍNDICE DIRECCIÓN"))
        story.append(Paragraph('<a name="indice"/>ÍNDICE DIRECCIÓN', self._title))
        for label, anchor in [
            ("1. Resumen dirección", "resumen_direccion"),
            ("2. Visión comercial", "direccion_comercial"),
            ("3. Visión producción", "direccion_produccion"),
            ("4. Visión calidad", "direccion_calidad"),
            ("5. Alertas y recomendaciones", "direccion_alertas"),
        ]:
            story.append(Paragraph(f'<link href="#{anchor}" color="blue">{label}</link>', self._normal))
            story.append(Spacer(1, 3))
        story.append(Spacer(1, 10))

    def _direction_metrics(self, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict]) -> dict[str, Any]:
        kg_campo = self._sum(campo, "Kg campo")
        kg_almacen = self._sum(almacen, "Kg stock")
        kg_pendientes = self._sum(pendientes, "Kg pendiente")
        kg_previstos = self._sum(previstos, "Kg estimados")
        demanda_total = kg_pendientes + kg_previstos
        total_disponible = kg_campo + kg_almacen
        cobertura = (total_disponible / demanda_total * 100) if demanda_total else None
        today = datetime.now().date()
        kg_hoy = self._sum([r for r in pendientes if self._safe_date(self._value(r, "Fecha salida")) and self._safe_date(self._value(r, "Fecha salida")) <= today], "Kg pendiente")
        kg_manana = self._sum([r for r in pendientes if self._safe_date(self._value(r, "Fecha salida")) == today + timedelta(days=1)], "Kg pendiente")
        sin_rows = [r for r in campo if self._aprovechamiento_estado_row(r) == "Sin aprovechamiento"]
        sin_kg = self._sum(sin_rows, "Kg campo")
        return {"kg_campo": kg_campo, "kg_almacen": kg_almacen, "kg_pendientes": kg_pendientes, "kg_previstos": kg_previstos, "demanda_total": demanda_total, "total_disponible": total_disponible, "cobertura": cobertura, "diferencia": total_disponible - demanda_total, "kg_hoy": kg_hoy, "kg_manana": kg_manana, "sin_kg": sin_kg, "sin_pct": (sin_kg / kg_campo * 100) if kg_campo else 0}

    def _add_direction_cover(self, story: list, filters: dict, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict], generated_at: datetime) -> None:
        self._section_title(story, "SANSEBAS AGROVIEW - INFORME DIRECCIÓN", "resumen_direccion")
        metrics = self._direction_metrics(campo, almacen, pendientes, previstos)
        estado = self._risk_label(metrics["cobertura"])
        story.append(self._table([
            ["Fecha generación", generated_at.strftime("%d/%m/%Y %H:%M"), "Cultivo", self._filter_text(filters.get("cultivo"))],
            ["Campaña", self._filter_text(filters.get("campana")), "Modo pedidos", filters.get("pedidos_modo_label") or filters.get("pedidos_modo", "TODOS")],
            ["Estado general", estado, "Empresa", self._filter_text(filters.get("empresa"))],
        ], repeat=0, header=False, col_widths=[4*cm, 9*cm, 4*cm, 9*cm]))
        story.append(Spacer(1, 8))
        self._add_general_status_panel(story, estado, metrics["cobertura"], metrics["diferencia"])
        self._add_kpi_cards(story, [
            {"label": "STOCK TOTAL DISPONIBLE", "value": self._format_t(metrics["total_disponible"]), "unit": self._format_kg(metrics["total_disponible"])},
            {"label": "PEDIDOS PENDIENTES", "value": self._format_t(metrics["kg_pendientes"]), "unit": self._format_kg(metrics["kg_pendientes"]), "status": "AMARILLO" if metrics["kg_pendientes"] else "VERDE"},
            {"label": "COBERTURA GLOBAL", "value": self._format_pct(metrics["cobertura"]) if metrics["cobertura"] is not None else "Sin demanda", "unit": estado, "status": estado},
            {"label": "DIFERENCIA DISP. VS DEM.", "value": self._format_t(metrics["diferencia"]), "unit": self._format_kg(metrics["diferencia"]), "status": "VERDE" if metrics["diferencia"] >= 0 else "ROJO"},
            {"label": "KG PENDIENTES HOY", "value": self._format_t(metrics["kg_hoy"]), "unit": self._format_kg(metrics["kg_hoy"]), "status": "ROJO" if metrics["kg_hoy"] else "VERDE"},
            {"label": "SIN APROVECHAMIENTO", "value": self._format_t(metrics["sin_kg"]), "unit": self._format_pct(metrics["sin_pct"]), "status": self._risk_label(sin_aprovechamiento_pct=metrics["sin_pct"])},
        ], columns=3, width=8.5*cm)
        recommendations = self._build_direction_recommendations(campo, almacen, pendientes, previstos)
        self._add_section_summary(story, "CONCLUSIÓN OPERATIVA", recommendations[:5] or ["Sin conclusiones automáticas con los datos disponibles."])
        story.append(PageBreak())

    def _short_text(self, value: Any, max_len: int = 35) -> str:
        text = re.sub(r"\s+", " ", str(value or "").replace(" 00:00:00", "")).strip()
        return text if len(text) <= max_len else text[: max(0, max_len - 1)].rstrip() + "…"

    def _clean_client_name(self, value: Any, max_len: int | None = 35) -> str:
        text = re.sub(r"\s+", " ", str(value or "").replace("ANECOOP//", "")).strip()
        for suffix in (" S.L.", " SL", " S.A.", " SA"):
            if text.upper().endswith(suffix.strip()):
                text = text[: -len(suffix)].strip()
        return self._short_text(text, max_len) if max_len else text

    def _safe_paragraph(self, value: Any, style_name: str = "CellSmall") -> Paragraph:
        styles = {
            "CellSmall": getattr(self, "_cell_small", self._small),
            "CellTiny": getattr(self, "_cell_tiny", self._small),
            "CellWrap": getattr(self, "_cell_wrap", self._small),
            "HeaderSmall": getattr(self, "_header_small", self._small_center),
            "HeaderTiny": getattr(self, "_header_tiny", self._small_center),
            "AlertCell": getattr(self, "_alert_cell", self._small),
        }
        return Paragraph(str(value if value is not None else ""), styles.get(style_name, self._small))

    def _p(self, value: Any, style: Any | None = None) -> Paragraph:
        return Paragraph(str(value if value is not None else ""), style or self._small)

    def _wrap_columns(self, data: list[list[Any]], col_indexes: Sequence[int]) -> list[list[Any]]:
        wrap_set = set(col_indexes)
        return [[self._safe_paragraph(cell, "CellWrap") if i in wrap_set else cell for i, cell in enumerate(row)] for row in data]

    def _truncate_columns(self, data: list[list[Any]], col_indexes: Sequence[int], max_len: int) -> list[list[Any]]:
        trunc_set = set(col_indexes)
        return [[self._short_text(cell, max_len) if i in trunc_set and row_idx > 0 else cell for i, cell in enumerate(row)] for row_idx, row in enumerate(data)]

    def _right_align_numeric_columns(self, table_style: list, col_indexes: Sequence[int]) -> None:
        for col in col_indexes:
            table_style.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))

    def _center_columns(self, table_style: list, col_indexes: Sequence[int]) -> None:
        for col in col_indexes:
            table_style.append(("ALIGN", (col, 0), (col, -1), "CENTER"))

    def _apply_common_table_style(self, table: Table, header: bool = True, zebra: bool = False) -> None:
        style = [
            ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(self.COLOR_HEADER_BG)), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        if zebra:
            for row in range(1, len(getattr(table, "_cellvalues", [])), 2):
                style.append(("BACKGROUND", (0, row), (-1, row), colors.HexColor("#FAFBFC")))
        table.setStyle(TableStyle(style))

    def _make_table(self, data: list[list[Any]], col_widths: list[float] | None = None, repeat_rows: int = 1, style: list | None = None, font_size: float = 7) -> Table:
        style_name = "CellTiny" if font_size <= 5.5 else "CellSmall"
        header_name = "HeaderTiny" if font_size <= 5.5 else "HeaderSmall"
        wrapped = [[self._safe_paragraph(c, header_name if r == 0 and repeat_rows else style_name) for c in row] for r, row in enumerate(data)]
        table = Table(wrapped, colWidths=col_widths, repeatRows=repeat_rows)
        self._apply_common_table_style(table, header=bool(repeat_rows), zebra=False)
        if style:
            table.setStyle(TableStyle(style))
        return table

    def _draw_footer(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        y = 0.45 * cm
        width = doc.pagesize[0]
        mode = "Informe Dirección" if getattr(self, "_current_report_mode", "operativo") == "direccion" else "Informe Operativo"
        generated = getattr(self, "_generated_at", None)
        gen_text = f"Generado: {generated.strftime('%d/%m/%Y %H:%M')}" if isinstance(generated, datetime) else ""
        canvas.drawString(doc.leftMargin, y, f"Sansebas AgroView  {gen_text}".strip())
        canvas.drawCentredString(width / 2, y, mode)
        canvas.drawRightString(width - doc.rightMargin, y, f"Página {doc.page}")
        canvas.restoreState()

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value if value is not None else "").strip().replace("%", "")
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
        return self._format_pct(value, blank=blank) if value is not None else blank

    def _format_pct_value(self, value: Any, *, blank: str = "-") -> str:
        return self._format_number(self._to_float(value), 1) if value is not None else blank

    def _validate_pdf_totals(self, rows: list[dict], weekly_total_kg: float | None = None) -> list[str]:
        if not rows:
            return []
        base_total = self._sum(rows, "KgAprox")
        totals = {
            "cabecera": base_total,
            "top_variedades": sum(v for _, v in self._top_by(rows, "Variedad", "KgAprox", limit=len(rows))),
            "resumen_dia": sum(self._sum(day_rows, "KgAprox") for day_rows in self._group_lists_by_date(rows).values()),
        }
        if weekly_total_kg is not None:
            totals["semanal"] = weekly_total_kg
        warnings = []
        for name, value in totals.items():
            if abs(value - base_total) > 1:
                warnings.append(f"Total previsión incoherente en {name}: {value:.0f} kg vs {base_total:.0f} kg")
        return warnings

    def _group_lists_by_date(self, rows: list[dict]) -> dict[str, list[dict]]:
        by_day: dict[str, list[dict]] = {}
        for r in rows:
            by_day.setdefault(str(self._prevision_fecha(r) or ""), []).append(r)
        return by_day

    def _run_pdf_presentation_checks(self, data: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        text = str(data)
        if "00:00:00" in text:
            warnings.append("Se detectaron fechas con hora residual 00:00:00 en datos de entrada.")
        if "t t" in text:
            warnings.append("Se detectó texto con unidad duplicada 't t'.")
        if "..." in text or "…" in text:
            warnings.append("Se detectaron cadenas con puntos suspensivos en datos de entrada.")
        campo = list(data.get("stock_campo_rows") or [])
        total_campo = self._sum(campo, "Kg campo")
        if total_campo > 100000:
            by_origen: dict[str, float] = {}
            for row in campo:
                by_origen[self._aprovechamiento_estado_row(row)] = by_origen.get(self._aprovechamiento_estado_row(row), 0.0) + self._sum([row], "Kg campo")
            if any(0 < kg < 1000 for kg in by_origen.values()):
                warnings.append("Kg de aprovechamiento sospechosamente bajos frente al stock campo total.")
        warnings.extend(self._validate_pdf_totals(list(data.get("prevision_recoleccion_rows") or [])))
        return warnings

    def _format_date_es(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y")
        if isinstance(value, date):
            return value.strftime("%d/%m/%Y")
        text = str(value or "").strip()
        if not text:
            return ""
        parsed = self._parse_date(text)
        return parsed.strftime("%d/%m/%Y") if parsed else text.replace(" 00:00:00", "")

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
            ("2. Visión comercial", "vision_comercial"),
            ("3. Visión producción", "vision_produccion"),
            ("4. Visión calidad / aprovechamientos", "vision_calidad_aprovechamientos"),
            ("5. Stock campo", "stock_campo"),
            ("6. Previsión de recolección", "prevision_recoleccion"),
            ("7. Aprovechamiento estimado", "aprovechamiento_estimado"),
            ("8. Aprovechamiento de volcado", "aprovechamiento_volcado"),
            ("9. Stock almacén", "stock_almacen"),
            ("10. Pedidos pendientes", "pedidos_pendientes"),
            ("11. Pedidos previstos / no confirmados", "balance_comercial"),
            ("12. Agenda de producción", "agenda_produccion"),
            ("13. Riesgos / alertas", "riesgos_alertas"),
            ("14. Capacidad productiva", "capacidad_productiva"),
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
                Paragraph(
                    f"<b>{card['label']}</b><br/><font size='{12 if len(str(card.get('value', ''))) > 12 else 14}'><b>{card['value']}</b></font><br/><font size='7'>{card.get('unit', '')}</font>",
                    self._kpi,
                )
                for card in chunk
            ] + [""] * (columns - len(chunk)))
        table = Table(rows, colWidths=[width] * columns)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(self.COLOR_HEADER_BG)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
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
        self._add_general_status_panel(story, estado, cobertura, diferencia_total)
        self._add_disponibilidad_demanda_dashboard(story, kg_campo, kg_almacen, kg_pendientes, kg_previstos)
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
        story.append(Spacer(1, 6))

        conclusion = []
        if estado:
            conclusion.append(f"Estado general: {estado.lower()}.")
        if cobertura is not None:
            conclusion.append(f"Cobertura global: {self._format_pct(cobertura)} sobre demanda pendiente y prevista.")
        kg_hoy = self._sum([r for r in pendientes if self._safe_date(self._value(r, "Fecha salida")) and self._safe_date(self._value(r, "Fecha salida")) <= datetime.now().date()], "Kg pendiente")
        if kg_hoy > 0:
            conclusion.append(f"Pendiente para hoy: {self._format_kg(kg_hoy)}.")
        if campo:
            sin_rows = [r for r in campo if self._aprovechamiento_estado_row(r) == "Sin aprovechamiento"]
            sin_kg = self._sum(sin_rows, "Kg campo")
            if sin_kg > 0:
                conclusion.append(f"Sin aprovechamiento informado: {self._format_kg(sin_kg)} de stock campo.")
        foco = self._main_value(pendientes, "Grupo confección") or self._main_value(pendientes, "Grupo varietal")
        if foco:
            conclusion.append(f"Principal foco de producción: {foco}.")
        if conclusion:
            story.append(Paragraph("CONCLUSIÓN OPERATIVA", self._normal))
            story.append(self._table([["Conclusión"]] + [[text] for text in conclusion[:5]], col_widths=[25.6*cm]))
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


    def _add_general_status_panel(self, story: list, estado: str, cobertura: float | None, diferencia_kg: float) -> None:
        lectura = "Sin demanda actual para calcular cobertura."
        if cobertura is not None:
            if estado == "VERDE":
                lectura = "Cobertura suficiente: la disponibilidad supera con margen la demanda pendiente y prevista."
            elif estado == "AMARILLO":
                lectura = "Cobertura ajustada: revisar variedades, confecciones y fechas críticas antes de comprometer salidas."
            elif estado == "ROJO":
                lectura = "Cobertura insuficiente: priorizar pedidos críticos y contrastar disponibilidad real."
        diff_text = ("superávit" if diferencia_kg >= 0 else "déficit") + f" de {self._format_t(abs(diferencia_kg))}"
        data = [[
            Paragraph(f"<b>ESTADO GENERAL</b><br/><font size='18'><b>{estado}</b></font>", self._kpi),
            Paragraph(f"<b>Cobertura</b><br/><font size='14'>{self._format_pct(cobertura) if cobertura is not None else 'Sin demanda'}</font>", self._kpi),
            Paragraph(f"<b>Diferencia</b><br/><font size='14'>{diff_text}</font>", self._kpi),
            Paragraph(f"<b>Lectura</b><br/>{lectura}", self._normal),
        ]]
        table = Table(data, colWidths=[4.2*cm, 4.2*cm, 4.2*cm, 13.0*cm])
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(self.COLOR_HEADER_BG)),
            ("BACKGROUND", (0, 0), (-1, -1), self._traffic_color(estado)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (2, 0), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(table)
        story.append(Spacer(1, 8))

    def _add_bar_table(self, story: list, title: str, rows: Sequence[Any], label_col: str | int, value_col: str | int, total: float | None = None, max_rows: int = 8, *, extra_cols: list[str] | None = None, status_col: str | None = None) -> None:
        story.append(Paragraph(title, self._normal))
        normalized: list[dict[str, Any]] = []
        for item in rows[:max_rows] if isinstance(rows, list) else list(rows)[:max_rows]:
            if isinstance(item, dict):
                label = item.get(label_col, "") if isinstance(label_col, str) else ""
                value = self._to_float(item.get(value_col, 0) if isinstance(value_col, str) else 0)
                label_text = self._format_date_es(label) if isinstance(label_col, str) and "Fecha" in label_col else str(label or "Sin especificar").replace(" 00:00:00", "")
                normalized.append({"label": label_text, "value": value, "source": item})
            elif isinstance(item, (tuple, list)):
                label = item[label_col] if isinstance(label_col, int) and len(item) > label_col else item[0] if item else ""
                value = self._to_float(item[value_col] if isinstance(value_col, int) and len(item) > value_col else item[1] if len(item) > 1 else 0)
                normalized.append({"label": str(label or "Sin especificar").replace(" 00:00:00", ""), "value": value, "source": {}})
        if not normalized:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal))
            story.append(Spacer(1, 6))
            return
        max_value = max((r["value"] for r in normalized), default=0)
        total_value = total if total is not None else sum(r["value"] for r in normalized)
        extra_cols = extra_cols or []
        bar_segments = 10
        headers = ["Etiqueta", "Valor", "%"] + extra_cols + ["Barra visual"] + [""] * (bar_segments - 1)
        data: list[list[Any]] = [headers]
        styles: list[tuple[int, str]] = []
        for idx, r in enumerate(normalized, start=1):
            pct = (r["value"] / total_value * 100) if total_value else 0
            source = r["source"] if isinstance(r["source"], dict) else {}
            extras = [self._format_cell(source.get(c, ""), c) for c in extra_cols]
            data.append([r["label"], self._format_kg(r["value"]), self._format_pct(pct), *extras, *([""] * bar_segments)])
            if status_col and source.get(status_col):
                styles.append((idx, str(source.get(status_col))))
        bar_start = 3 + len(extra_cols)
        col_widths = [8*cm, 4*cm, 3*cm] + [2.8*cm]*len(extra_cols) + [0.75*cm]*bar_segments
        table = self._table(data, row_styles=styles, col_widths=col_widths, right_cols=[1, 2], center_cols=list(range(3, 3 + len(extra_cols))))
        style = [("SPAN", (bar_start, 0), (bar_start + bar_segments - 1, 0))]
        for idx, r in enumerate(normalized, start=1):
            width = int(round((r["value"] / max_value) * bar_segments)) if max_value else 0
            for col in range(bar_start, bar_start + width):
                style.append(("BACKGROUND", (col, idx), (col, idx), colors.HexColor(self.COLOR_PRIMARY)))
            for col in range(bar_start + width, bar_start + bar_segments):
                style.append(("BACKGROUND", (col, idx), (col, idx), colors.HexColor(self.COLOR_LIGHT_BG)))
        table.setStyle(TableStyle(style))
        story.append(table)
        story.append(Spacer(1, 6))

    def _add_disponibilidad_demanda_dashboard(self, story: list, kg_campo: float, kg_almacen: float, kg_pendientes: float, kg_previstos: float) -> None:
        rows = [
            {"Concepto": "Stock campo", "Kg": kg_campo},
            {"Concepto": "Stock almacén", "Kg": kg_almacen},
            {"Concepto": "Total disponible", "Kg": kg_campo + kg_almacen},
            {"Concepto": "Pedidos pendientes", "Kg": kg_pendientes},
            {"Concepto": "Pedidos previstos", "Kg": kg_previstos},
        ]
        self._add_bar_table(story, "DISPONIBILIDAD VS DEMANDA", rows, "Concepto", "Kg", total=max(sum(r["Kg"] for r in rows), 1), max_rows=5)

    def _production_attack_lines(self, rows: list[dict]) -> list[str]:
        if not rows:
            return ["Sin pedidos pendientes para definir plan de ataque producción."]
        today = datetime.now().date()
        kg_hoy = self._sum([r for r in rows if self._safe_date(self._value(r, "Fecha salida")) and self._safe_date(self._value(r, "Fecha salida")) <= today], "Kg pendiente")
        kg_manana = self._sum([r for r in rows if self._safe_date(self._value(r, "Fecha salida")) == today + timedelta(days=1)], "Kg pendiente")
        grupo_conf = self._main_value(rows, "Grupo confección")
        grupo_var = self._main_value(rows, "Grupo varietal")
        dates = sorted([d for d in (self._safe_date(self._value(r, "Fecha salida")) for r in rows) if d and d > today])
        lines = []
        if kg_hoy > 0:
            lines.append(f"Priorizar pedidos con salida hoy: {self._format_kg(kg_hoy)}.")
        else:
            lines.append("Sin pedidos vencidos o con salida hoy en los filtros actuales.")
        if grupo_conf:
            lines.append(f"Principal carga de trabajo: {grupo_conf}.")
        if grupo_var:
            lines.append(f"Grupo varietal más demandado: {grupo_var}.")
        if kg_manana > 0:
            lines.append(f"Preparar mañana: {self._format_kg(kg_manana)} pendientes.")
        elif dates:
            lines.append(f"Siguiente fecha crítica: {dates[0].strftime('%d/%m/%Y')}.")
        return lines[:5]

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


    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        return self._to_float(value, default)

    def _safe_date(self, value: Any):
        return self._parse_date(value)

    def _date_status_label(self, value: Any, today: date | None = None) -> str:
        day = self._safe_date(value)
        today = today or datetime.now().date()
        if not day:
            return "FUTURO"
        if day <= today:
            return "HOY"
        if day == today + timedelta(days=1):
            return "MAÑANA"
        return "FUTURO"

    def _main_value(self, rows: Sequence[dict], group_field: str, kg_field: str = "Kg pendiente") -> str:
        ranking = self._top_by(rows, group_field, kg_field, limit=1)
        return ranking[0][0] if ranking else ""

    def _group_sum(self, rows: Sequence[dict], keys: list[str], sums: dict[str, str], count_label: str | None = None) -> list[dict]:
        return self._group_rows(rows, keys, sums, count_label=count_label)

    def _add_kpi_cards(self, story: list, cards: list[dict[str, Any]], *, columns: int = 4, width: float = 6.4*cm) -> None:
        story.append(self._kpi_cards(cards, columns=columns, width=width))
        story.append(Spacer(1, 8))

    def _add_top_ranking(self, story: list, title: str, rows: list[list[Any]], col_widths: list[float] | None = None) -> None:
        story.append(Paragraph(title, self._normal))
        story.append(self._table(rows, col_widths=col_widths))
        story.append(Spacer(1, 6))

    def _add_section_summary(self, story: list, title: str, texts: list[str]) -> None:
        story.append(Paragraph(title, self._normal))
        story.append(self._table([["Lectura"]] + [[t] for t in texts], col_widths=[25.6*cm]))
        story.append(Spacer(1, 8))

    def _add_vision_comercial(self, story: list, rows: list[dict]) -> None:
        self._section_title(story, "VISIÓN COMERCIAL", "vision_comercial")
        if not rows:
            story.append(Paragraph("Sin pedidos pendientes para construir la visión comercial.", self._normal)); story.append(PageBreak()); return
        total = self._sum(rows, "Kg pendiente")
        pedidos = {str(self._value(r, "Pedido") or "").strip() for r in rows if str(self._value(r, "Pedido") or "").strip()}
        clientes = {str(self._value(r, "Cliente") or "").strip() for r in rows if str(self._value(r, "Cliente") or "").strip()}
        top_fecha = self._main_value(rows, "Fecha salida")
        top_grupo = self._main_value(rows, "Grupo varietal")
        self._add_kpi_cards(story, [
            {"label": "KG PENDIENTE TOTAL", "value": self._format_t(total), "unit": self._format_kg(total), "status": "AMARILLO" if total else "VERDE"},
            {"label": "Nº PEDIDOS PENDIENTES", "value": len(pedidos), "unit": "pedidos"},
            {"label": "Nº CLIENTES", "value": len(clientes), "unit": "clientes"},
            {"label": "FECHA MÁS CARGADA", "value": self._format_date_es(top_fecha) or "-", "unit": "por kg pendiente"},
            {"label": "GRUPO MÁS CARGADO", "value": top_grupo or "-", "unit": "por kg pendiente"},
        ], columns=5, width=5.1*cm)
        client_rows = [["Posición", "Cliente", "Kg pendiente", "% sobre total", "Nº pedidos"]]
        grouped_clients = self._group_sum(rows, ["Cliente"], {"Kg pendiente": "Kg pendiente"}, count_label="Nº pedidos")
        for pos, r in enumerate(sorted(grouped_clients, key=lambda x: x["Kg pendiente"], reverse=True)[:8], 1):
            client_rows.append([pos, r.get("Cliente") or "Sin cliente", self._format_kg(r["Kg pendiente"]), self._format_pct(r["Kg pendiente"] / total * 100 if total else 0), r.get("Nº pedidos", 0)])
        self._add_bar_table(story, "TOP CLIENTES POR KG PENDIENTE", sorted(grouped_clients, key=lambda x: x["Kg pendiente"], reverse=True), "Cliente", "Kg pendiente", total=total, max_rows=8, extra_cols=["Nº pedidos"])
        today = datetime.now().date()
        by_date = self._group_sum(rows, ["Fecha salida"], {"Kg pendiente": "Kg pendiente", "Palets pendientes": "Palets pendientes"}, count_label="Nº pedidos")
        date_data = [["Fecha salida", "Kg pendiente", "Palets pendientes", "Nº pedidos", "Semáforo"]]
        styles = []
        for r in sorted(by_date, key=lambda x: str(x.get("Fecha salida") or "")):
            status = self._date_status_label(r.get("Fecha salida"), today)
            sem = "ROJO" if status == "HOY" else "AMARILLO" if status == "MAÑANA" else "VERDE"
            date_data.append([self._format_date_es(r.get("Fecha salida", "")), self._format_kg(r["Kg pendiente"]), self._format_number(r["Palets pendientes"], 0), r.get("Nº pedidos", 0), sem])
            styles.append((len(date_data)-1, sem))
        self._add_bar_table(story, "DEMANDA POR FECHA DE SALIDA", sorted(by_date, key=lambda x: str(x.get("Fecha salida") or "")), "Fecha salida", "Kg pendiente", total=total, max_rows=10, extra_cols=["Palets pendientes", "Nº pedidos"], )
        gv = self._group_sum(rows, ["Grupo varietal"], {"Kg pendiente": "Kg pendiente"}, count_label="Nº pedidos")
        gv_data = [["Grupo varietal", "Kg pendiente", "% sobre total", "Nº pedidos"]]
        for r in sorted(gv, key=lambda x: x["Kg pendiente"], reverse=True):
            gv_data.append([r.get("Grupo varietal") or "Sin grupo", self._format_kg(r["Kg pendiente"]), self._format_pct(r["Kg pendiente"] / total * 100 if total else 0), r.get("Nº pedidos", 0)])
        self._add_bar_table(story, "DEMANDA POR GRUPO VARIETAL", sorted(gv, key=lambda x: x["Kg pendiente"], reverse=True), "Grupo varietal", "Kg pendiente", total=total, max_rows=8, extra_cols=["Nº pedidos"])
        story.append(PageBreak())

    def _add_vision_produccion(self, story: list, rows: list[dict], prevision: list[dict]) -> None:
        self._section_title(story, "VISIÓN PRODUCCIÓN", "vision_produccion")
        if not rows and not prevision:
            story.append(Paragraph("Sin pedidos pendientes ni previsión de entradas para producción.", self._normal)); story.append(PageBreak()); return
        self._add_section_summary(story, "PLAN DE ATAQUE PRODUCCIÓN", self._production_attack_lines(rows))
        today = datetime.now().date()
        if rows:
            carga = self._group_sum(rows, ["Fecha salida"], {"Kg pendiente": "Kg pendiente", "Palets pendientes": "Palets pendientes"}, count_label="Nº pedidos")
            data = [["Fecha", "Kg pendiente", "Palets pendientes", "Nº pedidos", "Estado temporal"]]
            for r in sorted(carga, key=lambda x: str(x.get("Fecha salida") or "")):
                data.append([self._format_date_es(r.get("Fecha salida", "")), self._format_kg(r["Kg pendiente"]), self._format_number(r["Palets pendientes"],0), r.get("Nº pedidos",0), self._date_status_label(r.get("Fecha salida"), today)])
            story.append(Paragraph("CARGA POR FECHA", self._normal)); story.append(self._table(data)); story.append(Spacer(1,6))
            total = self._sum(rows, "Kg pendiente")
            confe = self._group_sum(rows, ["Grupo confección"], {"Kg pendiente": "Kg pendiente", "Palets pendientes": "Palets pendientes"})
            data = [["Grupo confección", "Kg pendiente", "Palets pendientes", "% sobre total"]]
            for r in sorted(confe, key=lambda x: x["Kg pendiente"], reverse=True):
                data.append([r.get("Grupo confección") or "Sin grupo", self._format_kg(r["Kg pendiente"]), self._format_number(r["Palets pendientes"],0), self._format_pct(r["Kg pendiente"] / total * 100 if total else 0)])
            story.append(Paragraph("CARGA POR GRUPO CONFECCIÓN", self._normal)); story.append(self._table(data)); story.append(Spacer(1,6))
            prio = [["Fecha salida","Cliente","Pedido","Grupo confección","Grupo varietal","Kg pendiente","Palets pendientes","Prioridad"]]
            styles=[]
            for r in sorted(rows, key=lambda x: (str(self._value(x,"Fecha salida")), -self._sum([x],"Kg pendiente")))[:12]:
                status = self._date_status_label(self._value(r,"Fecha salida"), today) if self._sum([r],"Kg pendiente") > 0 else "FUTURO"
                sem = "ROJO" if status == "HOY" else "AMARILLO" if status == "MAÑANA" else "VERDE"
                prio.append([self._format_cell(self._value(r, c), c) for c in ["Fecha salida", "Cliente", "Pedido", "Grupo confección", "Grupo varietal"]] + [self._format_kg(self._sum([r], "Kg pendiente")), self._format_number(self._sum([r], "Palets pendientes"), 0), sem])
                styles.append((len(prio)-1, sem))
            story.append(Paragraph("PRIORIDAD PRODUCCIÓN", self._normal)); story.append(self._table(prio, row_styles=styles)); story.append(Spacer(1,6))
        if prevision:
            by_day: dict[str, list[dict]] = {}
            for r in prevision:
                by_day.setdefault(str(self._prevision_fecha(r) or ""), []).append(r)
            data = [["Fecha", "Kg previstos", "Nº socios", "Nº boletas", "Variedad principal"]]
            for day, day_rows in sorted(by_day.items()):
                socios = {str(r.get("IdSocio") or r.get("Socio") or "").strip() for r in day_rows if str(r.get("IdSocio") or r.get("Socio") or "").strip()}
                boletas = {str(r.get("Boleta") or "").strip() for r in day_rows if str(r.get("Boleta") or "").strip()}
                data.append([self._format_date_es(day), self._format_kg(self._sum(day_rows, "KgAprox")), len(socios), len(boletas), self._main_value(day_rows, "Variedad", "KgAprox")])
            story.append(Paragraph("PREVISIÓN ENTRADAS CAMPO", self._normal)); story.append(self._table(data))
        story.append(PageBreak())

    def _aprovechamiento_estado_row(self, row: dict) -> str:
        txt = str(self._value(row, "Estado aprovechamiento") or self._value(row, "Origen aprovechamiento") or self._value(row, "Origen") or "").upper()
        if "PESOSFRES" in txt or ("REAL" in txt and "LOTEADO" not in txt): return "Real PesosFres"
        if "LOTEADO" in txt: return "Real Loteado"
        if "HARVESTSYNC" in txt: return "HarvestSync"
        if "MANUAL" in txt or "ESTIMADO" in txt: return "Estimado manual"
        return "Sin aprovechamiento"

    def _add_vision_calidad(self, story: list, campo: list[dict], detalle_map: dict[str, list[dict]], volcado: dict[str, Any]) -> None:
        self._section_title(story, "VISIÓN CALIDAD / APROVECHAMIENTOS", "vision_calidad_aprovechamientos")
        if not campo:
            story.append(Paragraph("Sin stock campo para construir la visión de calidad.", self._normal)); story.append(PageBreak()); return
        total = self._sum(campo, "Kg campo")
        labels = ["Real PesosFres", "Real Loteado", "HarvestSync", "Estimado manual", "Sin aprovechamiento"]
        data = [["Origen", "Kg", "%", "Estado"]]
        by = {label: [] for label in labels}
        for r in campo:
            by[self._aprovechamiento_estado_row(r)].append(r)
        sin_pct = 0.0
        for label in labels:
            kg = self._sum(by[label], "Kg campo")
            pct = kg / total * 100 if total else 0
            if label == "Sin aprovechamiento": sin_pct = pct
            estado = self._risk_label(sin_aprovechamiento_pct=pct) if label == "Sin aprovechamiento" else ("VERDE" if kg else "GRIS")
            data.append([label, self._format_kg(kg), self._format_pct(pct), estado])
        bar_rows = []
        for label in labels:
            kg = self._sum(by[label], "Kg campo")
            pct = kg / total * 100 if total else 0
            estado = self._risk_label(sin_aprovechamiento_pct=pct) if label == "Sin aprovechamiento" else ("VERDE" if kg else "GRIS")
            bar_rows.append({"Origen": label, "Kg": kg, "Estado": estado})
        self._add_bar_table(story, "RESUMEN APROVECHAMIENTO CAMPO", bar_rows, "Origen", "Kg", total=total, max_rows=5, status_col="Estado")
        sin_rows = by["Sin aprovechamiento"]
        if sin_rows:
            grouped = self._group_sum(sin_rows, ["Variedad"], {"Kg campo afectado": "Kg campo"}, count_label="Nº partidas")
            top = [["Variedad / grupo", "Kg campo afectado", "Nº partidas", "Estado"]]
            for r in sorted(grouped, key=lambda x: x["Kg campo afectado"], reverse=True)[:8]:
                label = r.get("Variedad") or self._main_value(sin_rows, "Grupo varietal", "Kg campo") or "Sin especificar"
                top.append([label, self._format_kg(r["Kg campo afectado"]), r.get("Nº partidas",0), self._risk_label(sin_aprovechamiento_pct=sin_pct)])
            self._add_bar_table(story, "TOP VARIEDADES SIN APROVECHAMIENTO", sorted(grouped, key=lambda x: x["Kg campo afectado"], reverse=True), "Variedad", "Kg campo afectado", total=self._sum(sin_rows, "Kg campo"), max_rows=8, extra_cols=["Nº partidas"])
        else:
            story.append(Paragraph("No se dispone de detalle suficiente para agrupar sin aprovechamiento por variedad.", self._normal)); story.append(Spacer(1,6))
        dominant = max(((label, self._sum(rows, "Kg campo")) for label, rows in by.items()), key=lambda x: x[1])[0]
        lectura = [f"El {self._format_pct(sin_pct)} del stock campo está sin aprovechamiento informado."]
        if sin_pct > 0:
            lectura.append("Priorizar revisión de grupos con aprovechamiento pendiente antes de cerrar planificación.")
        lectura.append(f"La mayor parte del aprovechamiento procede de {dominant}.")
        if volcado.get("summary"):
            lectura.append("Existe resumen de aprovechamiento de volcado disponible para contrastar calidad real del periodo.")
        self._add_section_summary(story, "LECTURA CALIDAD", lectura)
        story.append(PageBreak())

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
            self._add_bar_table(story, "TOP VARIEDADES EN CAMPO", top, 0, 1, total=total_kg, max_rows=8)
        columns = ["Fecha carga", "Semana", "Socio", "Variedad", "Grupo varietal", "Boleta", "Plataforma", "Empresa", "Color / restricciones", "Kg campo"]
        sorted_rows = sorted(rows, key=lambda r: (str(self._value(r, "Grupo varietal")), str(self._value(r, "Variedad")), str(self._value(r, "Socio")), str(self._value(r, "Boleta"))))
        data = [columns]
        styles = []
        current: dict[str, Any] = {"Grupo varietal": None, "Variedad": None, "Socio": None}
        buckets: dict[str, list[dict]] = {"Grupo varietal": [], "Variedad": [], "Socio": []}

        def subtotal(label: str, value: Any, level: str) -> None:
            data.append([label] + [""] * (len(columns) - 2) + [self._format_kg(value)])
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
        story.append(self._table(data, row_styles=styles, right_cols=[9], center_cols=[0,1,5,7], font_size=6.2))
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
            self._add_bar_table(story, "TOP VARIEDADES PREVISTAS", top_previstas, 0, 1, total=total_kg, max_rows=8)

        total_warnings = self._validate_pdf_totals(rows)
        if total_warnings:
            for warning in total_warnings:
                logger.warning("PDF totals validation: %s", warning)
            story.append(Paragraph("Nota: existen diferencias entre resumen semanal y total previsto mostrado; revisar origen de datos.", self._normal))

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
        weekly_total = sum(day_totals.values())
        for warning in self._validate_pdf_totals(rows, weekly_total):
            logger.warning("PDF totals validation: %s", warning)
            story.append(Paragraph("Nota: existen diferencias entre resumen semanal y total previsto mostrado; revisar origen de datos.", self._normal))
            break
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
            self._add_bar_table(story, "TOP CONFECCIONES EN ALMACÉN", top_confecciones, 0, 1, total=total_kg, max_rows=8)
        keys = ["Grupo varietal", "Marca", "Confección", "Calibre", "Categoría"]
        optional = [c for c in ("Tipo palet", "Nombre palet") if self._has_any_value(rows, c)]
        sums = {"Palets": "Palets", "Cajas": "Cajas", "Kg stock": "Kg stock"}
        grouped = self._group_rows(rows, keys + optional, sums)
        data = [["Grupo varietal", "Marca", "Confección", "Calibre / categoría"] + optional + ["Palets", "Cajas", "Kg stock"]]
        last = {"Grupo varietal": None, "Marca": None, "Confección": None}
        buckets = {"Grupo varietal": [], "Marca": [], "Confección": []}

        def subtotal(label: str, value_rows: list[dict]) -> None:
            data.append([label, "", "", ""] + [""] * len(optional) + [self._format_cell(self._sum(value_rows, "Palets"), "Palets"), self._format_cell(self._sum(value_rows, "Cajas"), "Cajas"), self._format_kg(self._sum(value_rows, "Kg stock"))])

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
            data.append([r.get("Grupo varietal", ""), r.get("Marca", ""), r.get("Confección", ""), calib_cat] + [r.get(c, "") for c in optional] + [self._format_cell(r.get("Palets"), "Palets"), self._format_cell(r.get("Cajas"), "Cajas"), self._format_kg(r.get("Kg stock"))])
        if grouped:
            subtotal(f"Subtotal confección: {last['Confección']}", buckets["Confección"]); subtotal(f"Subtotal marca: {last['Marca']}", buckets["Marca"]); subtotal(f"Total grupo varietal: {last['Grupo varietal']}", buckets["Grupo varietal"])
        subtotal("TOTAL ALMACÉN", grouped)
        story.append(self._table(data, right_cols=list(range(len(data[0]) - 3, len(data[0]))), font_size=6.0))
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
            self._add_pedidos_criticos(story, rows)
        self._add_confeccion_mix(story, rows, kg_field, palets)
        self._add_timeline(story, rows, pedido_kg, kg_field, palets, previsto)
        if not previsto:
            self._add_pedidos_detail(story, rows)
        self._add_pedidos_matrix_summary(story, rows, kg_field, palets)
        self._add_pedidos_matrix(story, rows, pedido_kg, kg_field, palets)
        story.append(PageBreak())

    def _add_pedidos_resumen_operativo(self, story: list, rows: list[dict]) -> None:
        pedidos = {str(self._value(r, "Pedido") or "").strip() for r in rows if str(self._value(r, "Pedido") or "").strip()}
        terminados = [r for r in rows if str(self._value(r, "Estado") or "").strip().upper() in {"TERMINADO", "COMPLETO"}]
        pedidos_terminados = {str(self._value(r, "Pedido") or "").strip() for r in terminados if str(self._value(r, "Pedido") or "").strip()}
        estimadas = [r for r in rows if str(self._value(r, "Origen cálculo") or "").strip().upper() == "ESTIMADO_SIN_CONFECCION"]
        data = [
            ["Kg pedido teórico total", "Kg hecho real total", "Kg pendiente total", "Kg terminado/completo total"],
            [self._format_kg(self._sum(rows, "Kg pedido teórico")), self._format_kg(self._sum(rows, "Kg hecho real")), self._format_kg(self._sum(rows, "Kg pendiente")), self._format_kg(self._sum(terminados, "Kg pedido teórico"))],
            ["Nº pedidos total", "Nº pedidos pendientes", "Nº pedidos terminados", "Nº líneas sin confección estimadas"],
            [len(pedidos), len(pedidos - pedidos_terminados), len(pedidos_terminados), len(estimadas)],
        ]
        story.append(Paragraph("Resumen pedidos pendientes", self._normal))
        story.append(self._table(data, repeat=0, header=False, col_widths=[6*cm, 6*cm, 6*cm, 7*cm]))
        story.append(Spacer(1, 6))


    def _add_pedidos_criticos(self, story: list, rows: list[dict]) -> None:
        pending = [r for r in rows if self._sum([r], "Kg pendiente") > 0]
        grouped = self._group_rows(pending, ["Pedido", "Cliente", "Fecha salida"], {"Kg pendiente": "Kg pendiente", "Palets pendientes": "Palets pendientes"})
        data = [["Fecha", "Cliente", "Pedido", "Kg pendiente", "Palets pendientes", "Grupo principal", "Estado prioridad"]]
        styles = []
        today = datetime.now().date()
        for g in sorted(grouped, key=lambda r: (self._safe_date(r.get("Fecha salida")) or date.max, -r.get("Kg pendiente", 0)))[:15]:
            group_rows = [r for r in pending if str(self._value(r, "Pedido") or "") == str(g.get("Pedido") or "") and str(self._value(r, "Cliente") or "") == str(g.get("Cliente") or "") and str(self._value(r, "Fecha salida") or "") == str(g.get("Fecha salida") or "")]
            status = self._date_status_label(g.get("Fecha salida"), today)
            sem = "ROJO" if status == "HOY" else "AMARILLO" if status == "MAÑANA" else "VERDE"
            data.append([self._format_date_es(g.get("Fecha salida")), g.get("Cliente") or "-", g.get("Pedido") or "-", self._format_kg(g["Kg pendiente"]), self._format_number(g["Palets pendientes"], 0), self._main_value(group_rows, "Grupo varietal") or "-", sem])
            styles.append((len(data) - 1, sem))
        story.append(Paragraph("PEDIDOS CRÍTICOS", self._normal))
        story.append(self._table(data, row_styles=styles, col_widths=[2.5*cm, 6*cm, 3.2*cm, 3.2*cm, 2.8*cm, 4.5*cm, 3*cm], right_cols=[3,4], center_cols=[6]))
        story.append(Spacer(1, 6))

    def _estado_priority(self, row: dict) -> int:
        estado = str(self._value(row, "Estado") or "").strip().upper()
        if estado == "PENDIENTE":
            return 0
        if estado in {"PARCIAL", "EN CURSO"}:
            return 1
        if estado in {"TERMINADO", "COMPLETO"}:
            return 2
        return 3

    def _compact_confeccion(self, row: dict, max_len: int = 18) -> str:
        value = self._value(row, "Grupo confección") or self._value(row, "Confección")
        return self._short_text(value or "-", max_len)

    def _add_pedidos_detail(self, story: list, rows: list[dict]) -> None:
        columns = ["Fecha", "Cliente", "Pedido", "Variedad", "Grupo", "Calibre", "Conf.", "Palets", "Kg pend.", "Estado", "Obs."]
        data = [columns]
        styles = []
        ordered = sorted(
            rows,
            key=lambda x: (
                self._safe_date(self._value(x, "Fecha salida")) or date.max,
                self._estado_priority(x),
                -self._sum([x], "Kg pendiente"),
            ),
        )
        previous_date = None
        for r in ordered[:120]:
            row_date = self._safe_date(self._value(r, "Fecha salida"))
            sin_conf = str(self._value(r, "Origen cálculo") or "").strip().upper() == "ESTIMADO_SIN_CONFECCION"
            data.append([
                self._format_date_es(self._value(r, "Fecha salida")),
                self._clean_client_name(self._value(r, "Cliente"), 28) or "-",
                self._short_text(self._value(r, "Pedido"), 16) or "-",
                self._short_text(self._value(r, "Variedad Coop") or self._value(r, "Variedad"), 20) or "-",
                self._short_text(self._value(r, "Grupo varietal"), 18) or "-",
                self._short_text(self._value(r, "Calibre"), 10) or "-",
                self._compact_confeccion(r),
                self._format_cell(self._value(r, "Palets pendientes") or self._value(r, "Palets pedido"), "Palets"),
                self._format_kg(self._sum([r], "Kg pendiente")),
                self._short_text(self._value(r, "Estado"), 14) or "-",
                "Sin conf." if sin_conf else "",
            ])
            row_idx = len(data) - 1
            estado = str(self._value(r, "Estado") or "").strip().upper()
            if previous_date is not None and row_date != previous_date:
                styles.append((row_idx, "PEDIDO_DAY_BREAK"))
            if estado in {"PARCIAL", "EN CURSO"}:
                styles.append((row_idx, "PEDIDO_PARCIAL"))
            elif estado in {"TERMINADO", "COMPLETO"}:
                styles.append((row_idx, "PEDIDO_TERMINADO"))
            previous_date = row_date
        story.append(Paragraph("DETALLE OPERATIVO DE PEDIDOS", self._normal))
        story.append(Paragraph("Detalle operativo resumido. Para auditoría completa usar exportación Excel.", self._normal))
        story.append(self._table(data, row_styles=styles, col_widths=[2.0*cm, 4.2*cm, 2.4*cm, 3.4*cm, 3.0*cm, 1.7*cm, 3.0*cm, 1.8*cm, 2.4*cm, 2.1*cm, 2.0*cm], right_cols=[7, 8], center_cols=[0, 9], font_size=6.5))
        story.append(Spacer(1, 6))

    def _add_confeccion_mix(self, story: list, rows: list[dict], kg_field: str, palets_field: str) -> None:
        grouped = self._group_rows(rows, ["Grupo confección"], {"Palets": palets_field, "Kg pendiente": kg_field})
        total_palets = sum(r["Palets"] for r in grouped)
        data = [["Grupo confección", "% palets", "Palets", "Kg pendiente"]]
        for r in grouped:
            data.append([r.get("Grupo confección") or "DESCONOCIDO", self._format_pct(r['Palets']/total_palets*100 if total_palets else 0), self._format_cell(r["Palets"], "Palets"), self._format_kg(r["Kg pendiente"])])
        story.append(Paragraph("% pedidos por grupo confección", self._normal)); story.append(self._table(data, col_widths=[5*cm, 2.5*cm, 2.5*cm, 3*cm])); story.append(Spacer(1, 6))

    def _add_timeline(self, story: list, rows: list[dict], pedido_kg: str, kg_field: str, palets_field: str, previsto: bool) -> None:
        temporal = self._group_rows(rows, ["Fecha salida"], {"Kg teórico": pedido_kg, "Kg terminado": "Kg hecho real", "Kg pendiente": kg_field, "Palets pendientes": palets_field}, count_label="Nº pedidos")
        max_kg = max((r["Kg pendiente"] for r in temporal), default=0)
        data = [["Fecha salida", "Nº pedidos", "Palets pendientes", "Kg teórico", "Kg terminado", "Kg pendiente", "% pendiente", "Barra visual"]]
        for r in temporal:
            blocks = int(round((r["Kg pendiente"] / max_kg) * 14)) if max_kg else 0
            pct = (r["Kg pendiente"] / r["Kg teórico"] * 100) if r["Kg teórico"] else 0
            data.append([self._format_date_es(r["Fecha salida"]), r["Nº pedidos"], self._format_cell(r["Palets pendientes"], "Palets"), self._format_kg(r["Kg teórico"]), self._format_kg(r["Kg terminado"]), self._format_kg(r["Kg pendiente"]), self._format_pct(pct), "█" * blocks])
        story.append(Paragraph("LÍNEA TEMPORAL PEDIDOS" + (" PREVISTOS" if previsto else ""), self._normal)); story.append(self._table(data)); story.append(Spacer(1, 6))


    def _add_pedidos_matrix_summary(self, story: list, rows: list[dict], kg_field: str, palets_field: str) -> None:
        grouped = self._group_rows(rows, ["Fecha salida", "Cliente"], {"Kg pendiente": kg_field, "Palets pendientes": palets_field}, count_label="Nº pedidos")
        data = [["Fecha", "Cliente", "Kg pendiente", "Palets pendientes", "Nº pedidos", "Grupo principal"]]
        for g in sorted(grouped, key=lambda r: (self._safe_date(r.get("Fecha salida")) or date.max, str(r.get("Cliente") or ""))):
            group_rows = [r for r in rows if str(self._value(r, "Fecha salida") or "") == str(g.get("Fecha salida") or "") and str(self._value(r, "Cliente") or "") == str(g.get("Cliente") or "")]
            data.append([self._format_date_es(g.get("Fecha salida")), g.get("Cliente") or "-", self._format_kg(g["Kg pendiente"]), self._format_number(g["Palets pendientes"], 0), g.get("Nº pedidos", 0), self._main_value(group_rows, "Grupo varietal") or "-"])
        story.append(Paragraph("MATRIZ RESUMIDA POR CLIENTE Y FECHA", self._normal))
        story.append(self._table(data, col_widths=[2.8*cm, 8*cm, 4*cm, 3.2*cm, 2.5*cm, 5*cm], right_cols=[2,3,4]))
        story.append(Spacer(1, 6))

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
            row = [key[0], self._format_date_es(key[1]), key[2], key[3]]
            for g in groups:
                vals = matrix[key][g]
                for m in totals: totals[m] += vals[m]
                row += [self._format_cell(vals["Palets"], "Palets"), self._format_kg(vals["Kg teórico"]), self._format_kg(vals["Kg terminado"]), self._format_kg(vals["Kg pendiente"])]
            row += [self._format_cell(totals["Palets"], "Palets"), self._format_kg(totals["Kg teórico"]), self._format_kg(totals["Kg terminado"]), self._format_kg(totals["Kg pendiente"])]
            data.append(row)
        summary_data = self._build_pedidos_matrix_summary_data(rows, pedido_kg, kg_field, palets_field)
        story.append(Paragraph("Detalle técnico para auditoría y revisión operativa avanzada.", self._normal))
        self._render_or_summarize_table(
            story,
            "Detalle técnico: matriz operativa por semana, fecha, cliente y grupo varietal",
            data,
            summary_data,
            full_columns=header,
            summary_columns=summary_data[0],
            full_note="Matriz técnica completa incluida porque cabe en PDF.",
            summary_note="Matriz técnica completa no incluida en PDF por anchura. Consultar exportación Excel para detalle por grupo/calibre. Disponible en exportación Excel.",
            full_font_size=6.5,
            summary_font_size=6.5,
            summary_widths=[1.8*cm, 2.0*cm, 4.2*cm, 2.4*cm, 3.8*cm, 2.0*cm, 2.6*cm, 2.6*cm, 2.6*cm, 2.3*cm],
            right_cols=[5, 6, 7, 8],
            center_cols=[0, 1, 9],
        )

    def _build_pedidos_matrix_summary_data(self, rows: list[dict], pedido_kg: str, kg_field: str, palets_field: str) -> list[list[Any]]:
        grouped = self._group_rows(rows, ["Semana", "Fecha salida", "Cliente", "Pedido"], {"Palets total": palets_field, "Kg teórico": pedido_kg, "Kg terminado": "Kg hecho real", "Kg pendiente": kg_field})
        data: list[list[Any]] = [["Semana", "Fecha", "Cliente", "Pedido", "Grupo principal", "Palets total", "Kg teórico", "Kg terminado", "Kg pendiente", "Estado"]]
        for g in sorted(grouped, key=lambda r: (str(r.get("Semana") or ""), self._safe_date(r.get("Fecha salida")) or date.max, str(r.get("Cliente") or ""), str(r.get("Pedido") or "")))[:80]:
            group_rows = [r for r in rows if str(self._value(r, "Semana") or "") == str(g.get("Semana") or "") and str(self._value(r, "Fecha salida") or "") == str(g.get("Fecha salida") or "") and str(self._value(r, "Cliente") or "") == str(g.get("Cliente") or "") and str(self._value(r, "Pedido") or "") == str(g.get("Pedido") or "")]
            estado = self._short_text(self._main_value(group_rows, "Estado"), 14) or "-"
            data.append([
                g.get("Semana") or "-",
                self._format_date_es(g.get("Fecha salida")),
                self._clean_client_name(g.get("Cliente"), 28) or "-",
                self._short_text(g.get("Pedido"), 16) or "-",
                self._short_text(self._main_value(group_rows, "Grupo varietal"), 22) or "-",
                self._format_cell(g.get("Palets total"), "Palets"),
                self._format_kg(g.get("Kg teórico")),
                self._format_kg(g.get("Kg terminado")),
                self._format_kg(g.get("Kg pendiente")),
                estado,
            ])
        return data

    def _available_table_width(self) -> float:
        return landscape(A4)[0] - (1.4 * cm)

    def _should_render_full_table(self, num_cols: int, min_col_width: float = 35, available_width: float | None = None) -> bool:
        available = available_width if available_width is not None else self._available_table_width()
        return num_cols <= 14 and (num_cols * min_col_width) <= available

    def _render_or_summarize_table(
        self,
        story: list,
        title: str,
        full_data: list[list[Any]],
        summary_data: list[list[Any]],
        full_columns: Sequence[Any],
        summary_columns: Sequence[Any],
        *,
        full_note: str = "",
        summary_note: str = "Tabla completa no incluida en PDF por anchura. Consultar exportación Excel.",
        full_font_size: float = 6.5,
        summary_font_size: float = 6.5,
        summary_widths: list[float] | None = None,
        right_cols: Sequence[int] | None = None,
        center_cols: Sequence[int] | None = None,
    ) -> None:
        render_full = self._should_render_full_table(len(full_columns), available_width=self._available_table_width())
        if render_full:
            story.append(Paragraph(title, self._normal))
            if full_note:
                story.append(Paragraph(full_note, self._normal))
            story.append(self._table(full_data, font_size=max(full_font_size, 6.5), right_cols=right_cols, center_cols=center_cols))
            return
        story.append(Paragraph("MATRIZ OPERATIVA RESUMIDA", self._normal))
        story.append(Paragraph(summary_note, self._normal))
        story.append(self._table(summary_data, col_widths=summary_widths, font_size=max(summary_font_size, 6.5), right_cols=right_cols, center_cols=center_cols))

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
        row[8] = self._format_pct_value(self._weighted_pct(totals.get("destrio_kg", 0.0), totals["kg_entregado"]))
        row[9] = self._format_pct_value(self._weighted_pct(totals.get("industria_kg", 0.0), totals["kg_entregado"]))
        for i in range(11):
            row[columns.index(f"CAL {i} %")] = self._format_pct_value(self._weighted_pct(totals["calibres"][str(i)], totals["kg_entregado"]), blank="0,0")
        row[columns.index("% comercial total")] = self._format_pct_value(self._weighted_pct(totals["kg_estimado"], totals["kg_entregado"]), blank="0,0")
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
        cal_pcts = [self._format_pct_value((kg_by_cal[str(i)] / kg_entregado * 100) if kg_entregado else 0.0, blank="0,0") for i in range(11)]
        row = [
            self._format_cell(self._value(partida, "IdPartida"), "IdPartida"),
            self._format_cell(self._value(partida, "Boleta"), "Boleta"),
            self._format_cell(self._value(partida, "IdSocio"), "IdSocio"),
            self._format_cell(self._value(partida, "Nombre socio") or self._value(partida, "Socio"), "Nombre socio"),
            self._format_cell(self._value(partida, "Fecha carga"), "Fecha carga"),
            "", "", origen, self._format_pct_value(destrio_pct), self._format_pct_value(industria_pct),
        ] + cal_pcts + [self._format_pct_value((kg_estimado / kg_entregado * 100) if kg_entregado else 0.0, blank="0,0")]
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
        resumen = [["Nº partidas volcadas", "Líneas peso real", "Líneas estimadas", "Sin estimación", "Kg reales", "Kg estimados", "Cobertura líneas"], [summary.get("partidas", 0), summary.get("lineas_reales", 0), summary.get("lineas_estimadas", 0), summary.get("sin_estimacion", 0), self._format_kg(summary.get("kg_real", 0)), self._format_kg(summary.get("kg_estimado", 0)), f"{self._format_pct(summary.get('cobertura_palets', 0))} ({sem})"]]
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
                    self._format_pct(r.get(c, 0)) if c in pct_cols else self._fmt_t(r.get(c, 0)) if c in kg_cols else r.get(c, "")
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
                self._format_kg(grouped_summary.get("kg_total", 0)),
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
        story.append(self._table([qcols] + [[self._format_cell(r.get(c, ""), c) for c in qcols] for r in (volcado.get("quality") or [])], col_widths=[7*cm, 4*cm, 4*cm, 3*cm]))
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
            data.append([cal, self._format_pct(pe), self._format_pct(pv), self._format_number(diff, 1), lectura])
        logger.debug("INFORME PDF comparativa calibres=%s", max(0, len(data) - 1))
        if len(data) == 1:
            story.append(Paragraph("Sin calibres suficientes para comparar estimado y volcado.", self._normal))
        else:
            story.append(self._table(data, col_widths=[4*cm, 4*cm, 4*cm, 4*cm, 6*cm]))
        story.append(PageBreak())

    def _add_agenda(self, story: list, rows: list[dict], selected_cultivos: set[str] | None = None) -> None:
        self._section_title(story, "AGENDA DE PRODUCCIÓN", "agenda_produccion")
        if not rows:
            story.append(Paragraph("Sin pedidos pendientes para agenda de producción.", self._normal)); story.append(PageBreak()); return
        today = datetime.now().date()
        today_rows = [r for r in rows if self._safe_date(self._value(r, "Fecha salida")) and self._safe_date(self._value(r, "Fecha salida")) <= today]
        tomorrow_rows = [r for r in rows if self._safe_date(self._value(r, "Fecha salida")) == today + timedelta(days=1)]
        future_rows = [r for r in rows if (self._safe_date(self._value(r, "Fecha salida")) or today + timedelta(days=2)) > today + timedelta(days=1)]
        self._add_kpi_cards(story, [
            {"label": "KG PENDIENTES HOY", "value": self._format_t(self._sum(today_rows, "Kg pendiente")), "unit": self._format_kg(self._sum(today_rows, "Kg pendiente")), "status": "ROJO" if today_rows else "VERDE"},
            {"label": "KG PENDIENTES MAÑANA", "value": self._format_t(self._sum(tomorrow_rows, "Kg pendiente")), "unit": self._format_kg(self._sum(tomorrow_rows, "Kg pendiente")), "status": "AMARILLO" if tomorrow_rows else "VERDE"},
            {"label": "KG PRÓXIMOS DÍAS", "value": self._format_t(self._sum(future_rows, "Kg pendiente")), "unit": self._format_kg(self._sum(future_rows, "Kg pendiente"))},
            {"label": "Nº PEDIDOS HOY", "value": len({self._value(r, "Pedido") for r in today_rows}), "unit": "pedidos", "status": "ROJO" if today_rows else "VERDE"},
            {"label": "Nº PEDIDOS MAÑANA", "value": len({self._value(r, "Pedido") for r in tomorrow_rows}), "unit": "pedidos", "status": "AMARILLO" if tomorrow_rows else "VERDE"},
        ], columns=5, width=5.1*cm)
        agenda_rows = [r for r in rows if self._sum([r], "Kg pendiente") > 0]
        story.append(Paragraph("Agenda priorizada: se muestran líneas con pendiente > 0.", self._normal))
        grouped = self._group_sum(agenda_rows, ["Fecha salida"], {"Kg pendiente": "Kg pendiente", "Palets pendientes": "Palets pendientes"}, count_label="Nº pedidos")
        summary = [["Fecha", "Estado temporal", "Kg pendiente", "Palets pendientes", "Nº pedidos", "Principal cliente", "Principal grupo varietal"]]
        for g in sorted(grouped, key=lambda x: str(x.get("Fecha salida") or "")):
            day_rows = [r for r in agenda_rows if str(self._value(r, "Fecha salida") or "") == str(g.get("Fecha salida") or "")]
            summary.append([self._format_date_es(g.get("Fecha salida", "")), self._date_status_label(g.get("Fecha salida"), today), self._format_kg(g["Kg pendiente"]), self._format_number(g["Palets pendientes"],0), g.get("Nº pedidos",0), self._main_value(day_rows,"Cliente"), self._main_value(day_rows,"Grupo varietal")])
        story.append(Paragraph("AGRUPACIÓN POR DÍA", self._normal)); story.append(self._table(summary)); story.append(Spacer(1,8))
        columns = ["Fecha salida", "Cliente", "Pedido", "Cultivo", "Grupo confección", "Grupo varietal", "Kg pendiente", "Palets pendientes"]
        for optional in ("Prioridad", "Estado"):
            if self._has_any_value(agenda_rows, optional): columns.append(optional)
        data = [columns + ["Semáforo"]]
        styles = []
        for r in sorted(agenda_rows, key=lambda x: (str(self._value(x, "Fecha salida")), -self._sum([x], "Kg pendiente")))[:120]:
            kg = self._sum([r], "Kg pendiente")
            status = self._date_status_label(self._value(r, "Fecha salida"), today) if kg > 0 else "FUTURO"
            sem = "ROJO" if status == "HOY" else "AMARILLO" if status == "MAÑANA" else "VERDE"
            data.append([self._format_cell(self._value(r, c), c) for c in columns] + [sem])
            styles.append((len(data) - 1, sem if not selected_cultivos or str(self._value(r, "Cultivo") or "").strip().upper() not in selected_cultivos else "DESTACADO"))
        story.append(Paragraph("Detalle agenda de producción", self._normal))
        story.append(self._table(data, row_styles=styles))
        story.append(PageBreak())


    def _build_direction_recommendations(self, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict]) -> list[str]:
        metrics = self._direction_metrics(campo, almacen, pendientes, previstos)
        recommendations: list[str] = []
        if metrics["demanda_total"]:
            if metrics["cobertura"] is not None and metrics["cobertura"] >= 130:
                recommendations.append("Cobertura global suficiente para la demanda actual.")
            elif metrics["cobertura"] is not None and metrics["cobertura"] >= 100:
                recommendations.append("Cobertura global ajustada; revisar disponibilidad por variedad y confección.")
            else:
                recommendations.append("Cobertura global insuficiente para la demanda actual.")
        if metrics["kg_hoy"] > 0:
            recommendations.append("Priorizar fabricación de pedidos con salida hoy.")
        if metrics["sin_kg"] > 0:
            recommendations.append("Revisar stock campo sin aprovechamiento antes del cierre de planificación.")
        if metrics["kg_almacen"] < metrics["kg_pendientes"]:
            recommendations.append("El almacén no cubre por sí solo la demanda pendiente; dependerá de campo y confección.")
        elif metrics["kg_pendientes"] > 0:
            recommendations.append("El stock de almacén cubre por sí solo los pedidos pendientes.")
        foco = self._main_value(pendientes, "Grupo confección") or self._main_value(pendientes, "Grupo varietal")
        if foco:
            recommendations.append(f"Principal foco de producción: {foco}.")
        if self._sum(previstos, "Kg estimados") > 0:
            recommendations.append("Validar pedidos previstos porque pueden consumir disponibilidad adicional.")
        return recommendations

    def _add_direction_commercial(self, story: list, rows: list[dict]) -> None:
        self._section_title(story, "VISIÓN COMERCIAL RESUMIDA", "direccion_comercial")
        if not rows:
            story.append(Paragraph("Sin pedidos pendientes para construir la visión comercial.", self._normal)); story.append(PageBreak()); return
        total = self._sum(rows, "Kg pendiente")
        pedidos = {str(self._value(r, "Pedido") or "").strip() for r in rows if str(self._value(r, "Pedido") or "").strip()}
        clientes = {str(self._value(r, "Cliente") or "").strip() for r in rows if str(self._value(r, "Cliente") or "").strip()}
        self._add_kpi_cards(story, [
            {"label": "KG PENDIENTE", "value": self._format_t(total), "unit": self._format_kg(total), "status": "AMARILLO" if total else "VERDE"},
            {"label": "PEDIDOS", "value": len(pedidos), "unit": "pendientes"},
            {"label": "CLIENTES", "value": len(clientes), "unit": "con demanda"},
            {"label": "FECHA CRÍTICA", "value": self._format_date_es(self._main_value(rows, "Fecha salida")) or "-", "unit": "por kg pendiente"},
        ], columns=4, width=6.4*cm)
        client_rows = [["Cliente", "Kg pendiente", "%", "Nº pedidos"]]
        grouped_clients = self._group_sum(rows, ["Cliente"], {"Kg pendiente": "Kg pendiente"}, count_label="Nº pedidos")
        for r in sorted(grouped_clients, key=lambda x: x["Kg pendiente"], reverse=True)[:8]:
            client_rows.append([self._clean_client_name(r.get("Cliente") or "Sin cliente", 30), self._format_kg(r["Kg pendiente"]), self._format_pct(r["Kg pendiente"] / total * 100 if total else 0), r.get("Nº pedidos", 0)])
        compact_clients = [{**r, "Cliente": self._clean_client_name(r.get("Cliente") or "Sin cliente", 30)} for r in sorted(grouped_clients, key=lambda x: x["Kg pendiente"], reverse=True)]
        self._add_bar_table(story, "TOP CLIENTES POR KG PENDIENTE", compact_clients, "Cliente", "Kg pendiente", total=total, max_rows=8, extra_cols=["Nº pedidos"])
        by_date = self._group_sum(rows, ["Fecha salida"], {"Kg pendiente": "Kg pendiente"}, count_label="Nº pedidos")
        date_data = [["Fecha salida", "Kg pendiente", "Nº pedidos", "Semáforo"]]
        styles=[]
        today = datetime.now().date()
        for r in sorted(by_date, key=lambda x: str(x.get("Fecha salida") or ""))[:10]:
            status = self._date_status_label(r.get("Fecha salida"), today)
            sem = "ROJO" if status == "HOY" else "AMARILLO" if status == "MAÑANA" else "VERDE"
            date_data.append([self._format_date_es(r.get("Fecha salida")), self._format_kg(r["Kg pendiente"]), r.get("Nº pedidos", 0), sem]); styles.append((len(date_data)-1, sem))
        self._add_bar_table(story, "DEMANDA POR FECHA", sorted(by_date, key=lambda x: str(x.get("Fecha salida") or "")), "Fecha salida", "Kg pendiente", total=total, max_rows=8, extra_cols=["Nº pedidos"])
        risks = []
        if any(s[1] == "ROJO" for s in styles): risks.append("Hay demanda con salida hoy pendiente de fabricación/expedición.")
        if total > 0 and grouped_clients and sorted(grouped_clients, key=lambda x: x["Kg pendiente"], reverse=True)[0]["Kg pendiente"] / total > 0.4:
            risks.append("Demanda concentrada en un cliente principal.")
        self._add_section_summary(story, "RIESGOS COMERCIALES PRINCIPALES", risks or ["Sin riesgos comerciales automáticos relevantes."])
        story.append(PageBreak())

    def _add_direction_production(self, story: list, rows: list[dict], prevision: list[dict]) -> None:
        self._section_title(story, "VISIÓN PRODUCCIÓN RESUMIDA", "direccion_produccion")
        metrics = self._direction_metrics([], [], rows, [])
        self._add_kpi_cards(story, [
            {"label": "KG PENDIENTES HOY", "value": self._format_t(metrics["kg_hoy"]), "unit": self._format_kg(metrics["kg_hoy"]), "status": "ROJO" if metrics["kg_hoy"] else "VERDE"},
            {"label": "KG PENDIENTES MAÑANA", "value": self._format_t(metrics["kg_manana"]), "unit": self._format_kg(metrics["kg_manana"]), "status": "AMARILLO" if metrics["kg_manana"] else "VERDE"},
        ], columns=2, width=8*cm)
        self._add_section_summary(story, "PLAN DE ATAQUE PRODUCCIÓN", self._production_attack_lines(rows))
        today = datetime.now().date()
        prio = [["Fecha", "Cliente", "Pedido", "Confección", "Kg pendiente", "Prioridad"]]; styles=[]
        for r in sorted(rows, key=lambda x: (self._safe_date(self._value(x, "Fecha salida")) or date.max, -self._sum([x], "Kg pendiente")))[:10]:
            status = self._date_status_label(self._value(r, "Fecha salida"), today)
            sem = "ROJO" if status == "HOY" else "AMARILLO" if status == "MAÑANA" else "VERDE"
            kg_text = f"<b>{self._format_kg(self._sum([r], 'Kg pendiente'))}</b>"
            prio.append([self._format_date_es(self._value(r,"Fecha salida")), self._clean_client_name(self._value(r,"Cliente"), 24), self._value(r,"Pedido"), self._short_text(self._value(r,"Grupo confección"), 22), kg_text, sem]); styles.append((len(prio)-1, sem))
        story.append(Paragraph("PRIORIDAD PRODUCCIÓN TOP 10", self._normal)); story.append(self._table(prio, row_styles=styles, col_widths=[3*cm, 5.5*cm, 3.5*cm, 5.5*cm, 4.5*cm, 3*cm])); story.append(Spacer(1, 6))
        by_day: dict[str, list[dict]] = {}
        for r in prevision:
            by_day.setdefault(self._format_date_es(self._prevision_fecha(r) or ""), []).append(r)
        data = [["Fecha", "Kg previstos", "Variedad principal"]]
        for day, day_rows in list(sorted(by_day.items()))[:8]:
            data.append([day, self._format_kg(self._sum(day_rows, "KgAprox")), self._main_value(day_rows, "Variedad", "KgAprox")])
        story.append(Paragraph("PREVISIÓN ENTRADA CAMPO RESUMIDA", self._normal)); story.append(self._table(data if len(data)>1 else data + [["-", "0 kg", "-"]], col_widths=[5*cm, 6*cm, 10*cm])); story.append(PageBreak())

    def _add_direction_quality(self, story: list, campo: list[dict], volcado: dict[str, Any]) -> None:
        self._section_title(story, "VISIÓN CALIDAD / APROVECHAMIENTOS", "direccion_calidad")
        if not campo:
            story.append(Paragraph("Sin stock campo para construir la visión de calidad.", self._normal)); story.append(PageBreak()); return
        metrics = self._direction_metrics(campo, [], [], [])
        self._add_kpi_cards(story, [{"label": "SIN APROVECHAMIENTO", "value": self._format_t(metrics["sin_kg"]), "unit": self._format_pct(metrics["sin_pct"]), "status": self._risk_label(sin_aprovechamiento_pct=metrics["sin_pct"])}], columns=1, width=8*cm)
        total_campo = self._sum(campo, "Kg campo")
        quality_labels = ["Real Loteado", "Real PesosFres", "HarvestSync", "Sin aprovechamiento"]
        quality_rows = []
        for label in quality_labels:
            kg = self._sum([r for r in campo if self._aprovechamiento_estado_row(r) == label], "Kg campo")
            quality_rows.append({
                "Origen": label,
                "Kg": kg,
                "%": self._format_pct((kg / total_campo * 100) if total_campo else 0),
                "Estado": self._risk_label(sin_aprovechamiento_pct=(kg / total_campo * 100) if total_campo else 0) if label == "Sin aprovechamiento" else ("VERDE" if kg else "GRIS"),
            })
        self._add_bar_table(story, "RESUMEN VISUAL DE APROVECHAMIENTO", quality_rows, "Origen", "Kg", total=total_campo or 1, max_rows=4, extra_cols=["%"], status_col="Estado")
        sin_rows = [r for r in campo if self._aprovechamiento_estado_row(r) == "Sin aprovechamiento"]
        grouped = self._group_sum(sin_rows, ["Variedad"], {"Kg campo": "Kg campo"}, count_label="Nº partidas") if sin_rows else []
        top = [["Variedad", "Kg sin aprovechamiento", "Nº partidas", "Estado"]]
        for r in sorted(grouped, key=lambda x: x["Kg campo"], reverse=True)[:8]:
            top.append([r.get("Variedad") or "Sin especificar", self._format_kg(r["Kg campo"]), r.get("Nº partidas",0), self._risk_label(sin_aprovechamiento_pct=metrics["sin_pct"])])
        if grouped:
            self._add_bar_table(story, "TOP VARIEDADES SIN APROVECHAMIENTO", sorted(grouped, key=lambda x: x["Kg campo"], reverse=True), "Variedad", "Kg campo", total=metrics["sin_kg"] or 1, max_rows=8, extra_cols=["Nº partidas"])
        else:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal)); story.append(Spacer(1, 6))
        summary = volcado.get("summary") if isinstance(volcado, dict) else None
        volcado_text = "Aprovechamiento de volcado disponible para contraste." if summary else "Sin resumen de aprovechamiento de volcado disponible."
        self._add_section_summary(story, "ESTADO APROVECHAMIENTO DE VOLCADO", [volcado_text])
        story.append(PageBreak())


    def _add_risk_panel(self, story: list, alert_items: list[dict[str, Any]]) -> None:
        counts = {level: sum(1 for a in alert_items if a.get("nivel") == level) for level in ("ROJO", "AMARILLO", "VERDE")}
        area_counts: dict[str, int] = {}
        for item in alert_items:
            area = str(item.get("area") or "General")
            area_counts[area] = area_counts.get(area, 0) + 1
        main_area = max(area_counts.items(), key=lambda x: x[1])[0] if area_counts else "Sin alertas"
        main_action = next((str(a.get("accion") or "") for a in alert_items if a.get("nivel") == "ROJO"), "Mantener seguimiento")
        self._add_kpi_cards(story, [
            {"label": "ALERTAS ROJAS", "value": counts["ROJO"], "unit": "críticas", "status": "ROJO" if counts["ROJO"] else "VERDE"},
            {"label": "ALERTAS AMARILLAS", "value": counts["AMARILLO"], "unit": "riesgo", "status": "AMARILLO" if counts["AMARILLO"] else "VERDE"},
            {"label": "ÁREA AFECTADA", "value": main_area, "unit": "principal"},
            {"label": "ACCIÓN SUGERIDA", "value": self._compact_text(main_action, 24), "unit": "prioridad"},
        ], columns=4, width=6.4*cm)

    def _build_alert_items(self, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict]) -> list[dict[str, Any]]:
        today = datetime.now().date()
        alert_items: list[dict[str, Any]] = []
        grouped: dict[tuple[str, str, str], list[dict]] = {}
        for r in pendientes:
            if self._sum([r], "Kg pendiente") <= 0: continue
            key = (str(self._value(r, "Pedido") or ""), str(self._value(r, "Cliente") or ""), str(self._value(r, "Fecha salida") or ""))
            grouped.setdefault(key, []).append(r)
        for (pedido, cliente, fecha), grows in grouped.items():
            status = self._date_status_label(fecha, today)
            if status not in {"HOY", "MAÑANA"}: continue
            kg = self._sum(grows, "Kg pendiente")
            nivel = "ROJO" if status == "HOY" else "AMARILLO"
            alert_items.append({"nivel": nivel, "area": "Producción", "kg": kg, "mensaje": f"{pedido or '-'}: {self._format_kg(kg)} pendientes {'hoy' if nivel == 'ROJO' else 'mañana'}", "accion": "Priorizar fabricación" if nivel == "ROJO" else "Planificar fabricación"})
        stock_map = {r["Grupo varietal"]: r["Kg stock"] for r in self._group_rows(almacen, ["Grupo varietal"], {"Kg stock": "Kg stock"})}
        for d in self._group_rows(pendientes, ["Grupo varietal"], {"Kg pendiente": "Kg pendiente"}):
            deficit = d["Kg pendiente"] - stock_map.get(d["Grupo varietal"], 0)
            if deficit > 0: alert_items.append({"nivel": "AMARILLO", "area": "Almacén", "kg": deficit, "mensaje": f"{d['Grupo varietal'] or 'Sin grupo'}: déficit {self._format_kg(deficit)}", "accion": "Revisar campo y confección"})
        if campo:
            sin = [r for r in campo if self._aprovechamiento_estado_row(r) == "Sin aprovechamiento"]
            sin_pct = self._sum(sin, "Kg campo") / self._sum(campo, "Kg campo") * 100 if self._sum(campo, "Kg campo") else 0
            if sin_pct > 5: alert_items.append({"nivel": "ROJO" if sin_pct > 15 else "AMARILLO", "area": "Calidad", "kg": self._sum(sin, "Kg campo"), "mensaje": f"Sin aprovechamiento {self._format_pct(sin_pct)}", "accion": "Completar aprovechamientos"})
        if self._sum(previstos, "Kg estimados") > 0:
            alert_items.append({"nivel": "AMARILLO", "area": "Comercial", "kg": self._sum(previstos, "Kg estimados"), "mensaje": f"Pedidos previstos {self._format_kg(self._sum(previstos, 'Kg estimados'))}", "accion": "Confirmar demanda"})
        severity = {"ROJO": 0, "AMARILLO": 1, "VERDE": 2}
        return sorted(alert_items, key=lambda a: (severity.get(a["nivel"], 3), -a.get("kg", 0)))

    def _add_direction_alerts_recommendations(self, story: list, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict]) -> None:
        self._section_title(story, "ALERTAS Y RECOMENDACIONES", "direccion_alertas")
        all_items = self._build_alert_items(campo, almacen, pendientes, previstos)
        self._add_risk_panel(story, all_items)
        items = all_items[:10]
        alerts = [["Nivel", "Área", "Resumen", "Acción"]]
        for a in items:
            alerts.append([a["nivel"], a["area"], self._short_text(a["mensaje"], 70), self._short_text(a["accion"], 45)])
        if len(alerts) == 1:
            alerts.append(["VERDE", "General", "Sin alertas automáticas.", "Mantener seguimiento"])
        story.append(self._table(alerts, row_styles=[(i, row[0]) for i, row in enumerate(alerts[1:],1)], col_widths=[2.5*cm, 3.5*cm, 13*cm, 7*cm], center_cols=[0], font_size=7))
        story.append(Spacer(1, 8))
        self._add_section_summary(story, "RECOMENDACIONES OPERATIVAS", self._build_direction_recommendations(campo, almacen, pendientes, previstos)[:8] or ["Sin recomendaciones automáticas con los datos disponibles."])

    def _add_alertas(self, story: list, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict]) -> None:
        self._section_title(story, "RIESGOS / ALERTAS", "riesgos_alertas")
        today = datetime.now().date()
        alert_items: list[dict[str, Any]] = []
        grouped: dict[tuple[str, str, str], list[dict]] = {}
        for r in pendientes:
            if self._sum([r], "Kg pendiente") <= 0:
                continue
            key = (str(self._value(r, "Pedido") or ""), str(self._value(r, "Cliente") or ""), str(self._value(r, "Fecha salida") or ""))
            grouped.setdefault(key, []).append(r)
        for (pedido, cliente, fecha), grows in grouped.items():
            status = self._date_status_label(fecha, today)
            if status not in {"HOY", "MAÑANA"}:
                continue
            kg = self._sum(grows, "Kg pendiente")
            palets = self._sum(grows, "Palets pendientes")
            grupo = self._main_value(grows, "Grupo varietal")
            nivel = "ROJO" if status == "HOY" else "AMARILLO"
            alert_items.append({"nivel": nivel, "area": "Producción", "kg": kg, "mensaje": f"Pedido {pedido or '-'} de {cliente or '-'} sale {'hoy' if nivel == 'ROJO' else 'mañana'} con {self._format_kg(kg)} pendientes en {len(grows)} líneas" + (f" ({grupo})." if grupo else "."), "accion": "Priorizar fabricación/expedición hoy." if nivel == "ROJO" else "Planificar fabricación antes del cierre de mañana."})
        stock_gv = self._group_rows(almacen, ["Grupo varietal"], {"Kg stock": "Kg stock"})
        demanda_gv = self._group_rows(pendientes, ["Grupo varietal"], {"Kg pendiente": "Kg pendiente"})
        stock_map = {r["Grupo varietal"]: r["Kg stock"] for r in stock_gv}
        for d in demanda_gv:
            deficit = d["Kg pendiente"] - stock_map.get(d["Grupo varietal"], 0)
            if deficit > 0:
                alert_items.append({"nivel": "AMARILLO", "area": "Almacén", "kg": deficit, "mensaje": f"Demanda de {d['Grupo varietal'] or 'Sin grupo'} supera stock almacén en {self._format_kg(deficit)}.", "accion": "Revisar stock campo y plan de confección."})
        if campo:
            sin = [r for r in campo if self._aprovechamiento_estado_row(r) == "Sin aprovechamiento"]
            sin_pct = self._sum(sin, "Kg campo") / self._sum(campo, "Kg campo") * 100 if self._sum(campo, "Kg campo") else 0
            if sin_pct > 5:
                alert_items.append({"nivel": "ROJO" if sin_pct > 15 else "AMARILLO", "area": "Calidad", "kg": self._sum(sin, "Kg campo"), "mensaje": f"Stock campo sin aprovechamiento informado: {self._format_pct(sin_pct)} ({self._format_kg(self._sum(sin, 'Kg campo'))}).", "accion": "Completar aprovechamientos antes de cerrar planificación."})
        severity = {"ROJO": 0, "AMARILLO": 1, "VERDE": 2}
        alert_items = sorted(alert_items, key=lambda a: (severity.get(a["nivel"], 3), -a.get("kg", 0)))
        total_alerts = len(alert_items)
        self._add_risk_panel(story, alert_items)
        alert_items = alert_items[:15]

        alerts: list[list[Any]] = [["Nivel", "Área", "Mensaje", "Acción sugerida"]]
        for a in alert_items:
            alerts.append([a["nivel"], a["area"], self._compact_text(a["mensaje"], 110), self._compact_text(a["accion"], 70)])
        if total_alerts > 15:
            alerts.append(["AMARILLO", "Resumen", f"{total_alerts - 15} alertas adicionales no mostradas.", "Revisar detalle."])
        if len(alerts) == 1:
            alerts.append(["VERDE", "General", "Sin alertas automáticas.", "Mantener seguimiento."])
        story.append(self._table(alerts, row_styles=[(i, row[0].upper()) for i, row in enumerate(alerts[1:], start=1)], col_widths=[2.2*cm, 3*cm, 14*cm, 8*cm], center_cols=[0]))
        story.append(PageBreak())

    def _add_capacidad(self, story: list) -> None:
        self._section_title(story, "CAPACIDAD PRODUCTIVA", "capacidad_productiva")
        story.append(Paragraph("Capacidad productiva no incluida en esta versión del informe.", self._normal))
        story.append(PageBreak())

    def _compact_text(self, value: Any, limit: int = 100) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"

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
        if "Fecha" in column:
            return self._format_date_es(value)
        if "%" in column or "Cobertura" in column:
            return self._format_pct(value) if str(value or "").strip() else ""
        if "Kg" in column or "Neto" in column or "Destrío" in column or "Merma" in column:
            return self._format_kg(value) if str(value).strip() else ""
        if any(x in column for x in ("Palets", "Cajas")):
            return self._format_number(self._to_float(value), 0) if str(value).strip() else ""
        return str(value or "").replace(" 00:00:00", "")

    def _table(self, data: list[list[Any]], repeat: int = 1, header: bool = True, col_widths: list[float] | None = None, row_styles: list[tuple[int, str]] | None = None, right_cols: Sequence[int] | None = None, center_cols: Sequence[int] | None = None, font_size: float | None = None) -> Table:
        right_set = set(right_cols or [])
        center_set = set(center_cols or [])
        max_cols = max((len(row) for row in data), default=0)
        technical = max_cols > 18
        if technical:
            logger.warning("PDF table with %s columns detected; applying technical compact mode.", max_cols)
        for row_idx, row in enumerate(data):
            for col_idx, cell in enumerate(row):
                text = str(cell or "")
                if len(text) > 120:
                    logger.warning("PDF extreme text length detected at row %s col %s (%s chars).", row_idx, col_idx, len(text))
        effective_font = font_size or (5.0 if technical else 7.0)
        if data and header:
            for idx, col in enumerate(data[0]):
                label = str(col)
                if len(label) > 28:
                    logger.warning("PDF long table header detected: %s", label)
                if any(token in label for token in ("Kg", "Palets", "Cajas", "%", "Nº", "Total", "Teórico", "Terminado", "Pendiente", "Neto", "Merma", "Destrío")):
                    right_set.add(idx)
                if any(token in label for token in ("Estado", "Semáforo", "Nivel", "Prioridad")):
                    center_set.add(idx)
        wrapped = []
        for row_idx, row in enumerate(data):
            rendered = []
            for i, c in enumerate(row):
                if isinstance(c, Paragraph):
                    rendered.append(c)
                    continue
                base = self._cell_tiny if effective_font <= 5.5 else self._cell_small
                if i in right_set:
                    base = ParagraphStyle(f"{base.name}Right{row_idx}_{i}", parent=base, alignment=TA_RIGHT)
                elif i in center_set or (header and row_idx == 0):
                    base = ParagraphStyle(f"{base.name}Center{row_idx}_{i}", parent=base, alignment=TA_CENTER)
                rendered.append(self._p(c, base))
            wrapped.append(rendered)
        t = Table(wrapped, repeatRows=repeat, colWidths=col_widths)
        pad = 0.7 if technical else 1.7
        style = [("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), pad), ("RIGHTPADDING", (0,0), (-1,-1), pad), ("TOPPADDING", (0,0), (-1,-1), pad), ("BOTTOMPADDING", (0,0), (-1,-1), pad)]
        if header: style += [("BACKGROUND", (0,0), (-1,0), colors.HexColor(self.COLOR_HEADER_BG)), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold")]
        for col in center_set:
            style.append(("ALIGN", (col, 0), (col, -1), "CENTER"))
        for col in right_set:
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
            "PEDIDO_PARCIAL": "#FFF3CD", "PEDIDO_TERMINADO": "#D4EDDA",
            "HARVESTSYNC": "#D9EAF7", "REAL_PESOSFRES": "#E2F0D9", "LOTEADO": "#E7E6E6",
            "MANUAL": "#FFF2CC", "ESTIMADO_MANUAL": "#FFF2CC", "SIN_APROVECHAMIENTO": "#F4CCCC",
            "GRUPO_APROVECHAMIENTO": "#D9EAF7", "SUBTOTAL_APROVECHAMIENTO": "#EAF3F8", "TOTAL_APROVECHAMIENTO": "#D9D9D9",
        }
        for row_idx, marker in row_styles or []:
            marker_text = str(marker).upper()
            if marker_text == "PEDIDO_DAY_BREAK":
                style.append(("LINEABOVE", (0, row_idx), (-1, row_idx), 1.4, colors.HexColor("#9DC3E6")))
            elif marker_text in {"PEDIDO_PARCIAL", "PEDIDO_TERMINADO"}:
                style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor(color_map[marker_text])))
                style.append(("FONTNAME", (9, row_idx), (9, row_idx), "Helvetica-Bold"))
            elif marker_text in color_map:
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
            ("VISIÓN COMERCIAL", pending_rows),
            ("VISIÓN PRODUCCIÓN", pending_rows),
            ("VISIÓN CALIDAD / APROVECHAMIENTOS", kwargs.get("stock_campo_rows", [])),
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
