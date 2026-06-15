from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - fallback para entornos sin dependencias instaladas
    REPORTLAB_AVAILABLE = False


class CommercialPdfReportService:
    """Genera el informe comercial diario desde las filas ya filtradas en pantalla."""

    def default_filename(self, now: datetime | None = None) -> str:
        return f"InformeComercial_{(now or datetime.now()).strftime('%Y%m%d_%H%M')}.pdf"

    def generate(
        self,
        target_path: str | Path,
        *,
        filters: dict[str, Any] | None = None,
        stock_campo_rows: list[dict] | None = None,
        stock_almacen_rows: list[dict] | None = None,
        pedidos_pendientes_rows: list[dict] | None = None,
        pedidos_previstos_rows: list[dict] | None = None,
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
                generated_at=generated_at or datetime.now(),
            )
            return target
        self._styles = getSampleStyleSheet()
        self._small = ParagraphStyle("Small", parent=self._styles["Normal"], fontSize=6.2, leading=7.2, alignment=TA_LEFT)
        self._normal = ParagraphStyle("NormalCompact", parent=self._styles["Normal"], fontSize=8, leading=9.5)
        self._section = ParagraphStyle("Section", parent=self._styles["Heading2"], fontSize=11, leading=13, spaceBefore=4, spaceAfter=5)
        self._title = ParagraphStyle("Title", parent=self._styles["Heading1"], fontSize=15, leading=17)

        campo = list(stock_campo_rows or [])
        almacen = list(stock_almacen_rows or [])
        pendientes = list(pedidos_pendientes_rows or [])
        previstos = list(pedidos_previstos_rows or [])
        story: list[Any] = []
        self._add_header(story, filters or {}, generated_at or datetime.now())
        self._add_summary(story, campo, almacen, pendientes, previstos)
        self._add_section(story, "STOCK CAMPO", campo, ["Fecha carga", "Semana", "Socio", "Variedad", "Grupo varietal", "Boleta", "Color", "Estado aprovechamiento", "Kg campo", "Kg estimados calculados"], ["Cultivo", "Grupo varietal", "Variedad"], ["Cultivo", "Grupo varietal", "Variedad", "Fecha carga", "Boleta"], "Kg campo")
        self._add_section(story, "STOCK ALMACÉN", almacen, ["Variedad", "Grupo varietal", "Calibre", "Categoría", "Marca", "IdConfeccion", "Confección", "Palets", "Cajas", "Kg stock", "Agrupado", "Tipo palet", "Nombre palet"], ["Grupo varietal", "Marca", "Confección"], ["Grupo varietal", "Marca", "Confección", "Calibre", "Categoría"], "Kg stock")
        self._add_section(story, "PEDIDOS PENDIENTES", pendientes, ["Fecha salida", "Cliente", "IdPedidoLora", "Línea", "Grupo varietal", "Variedad", "Calibre", "Categoría", "Marca", "Confección", "Grupo confección", "Kg pedido teórico", "Kg hecho real", "Kg pendiente", "Palets pedido", "Palets pendientes"], ["Grupo confección", "IdPedidoLora"], ["Grupo confección", "IdPedidoLora", "Grupo varietal", "Confección"], "Kg pendiente")
        self._add_section(story, "PEDIDOS PREVISTOS / NO CONFIRMADOS", previstos, ["Estado", "Fecha salida", "Cliente", "Grupo varietal", "Variedad", "Calibre", "Categoría", "Marca", "Confección prevista", "Grupo confección", "Perfil confección", "Kg estimados", "Palets estimados", "Observaciones"], ["Grupo confección", "Cliente"], ["Grupo confección", "Cliente", "Grupo varietal", "Confección prevista"], "Kg estimados")
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

    def _add_header(self, story: list, filters: dict, generated_at: datetime) -> None:
        story.append(Paragraph("Informe comercial diario", self._title))
        data = [["Fecha/hora generación", generated_at.strftime("%Y-%m-%d %H:%M")], ["Campaña", self._filter_text(filters.get("campana"))], ["Cultivo", self._filter_text(filters.get("cultivo"))], ["Empresa", self._filter_text(filters.get("empresa"))], ["Semana", self._filter_text(filters.get("semana"))], ["Variedad Coop", self._filter_text(filters.get("var_coop"))], ["Grupo varietal", self._filter_text(filters.get("grupo_varietal"))], ["Marca", self._filter_text(filters.get("marca"))], ["Fecha desde / hasta", f"{filters.get('fecha_desde') or 'TODOS'} / {filters.get('fecha_hasta') or 'TODOS'}"], ["Modo pedidos", filters.get("pedidos_modo_label") or filters.get("pedidos_modo", "TODOS")]]
        story.append(self._table(data, repeat=0, header=False, col_widths=[4*cm, 21*cm]))
        story.append(Spacer(1, 6))

    def _add_summary(self, story: list, campo: list[dict], almacen: list[dict], pendientes: list[dict], previstos: list[dict]) -> None:
        rows = [["KPI", "Valor"], ["Kg stock campo", self._num(self._sum(campo, "Kg campo"))], ["Kg stock almacén", self._num(self._sum(almacen, "Kg stock"))], ["Kg pedidos pendientes", self._num(self._sum(pendientes, "Kg pendiente"))], ["Kg pedidos previstos", self._num(self._sum(previstos, "Kg estimados"))], ["Nº partidas campo", str(len(campo))], ["Nº grupos varietales campo", str(len({r.get('Grupo varietal','') for r in campo if r.get('Grupo varietal','')}))], ["Nº variedades campo", str(len({r.get('Variedad','') for r in campo if r.get('Variedad','')}))], ["Nº pedidos pendientes", str(len({r.get('IdPedidoLora','') for r in pendientes if r.get('IdPedidoLora','')}))], ["Nº pedidos previstos", str(len(previstos))]]
        story.append(Paragraph("RESUMEN EJECUTIVO", self._section)); story.append(self._table(rows, col_widths=[8*cm, 5*cm])); story.append(PageBreak())

    def _add_section(self, story: list, title: str, rows: list[dict], columns: list[str], groups: list[str], sort_keys: list[str], kg_field: str) -> None:
        story.append(Paragraph(title, self._section))
        if not rows:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal)); story.append(PageBreak()); return
        sorted_rows = sorted(rows, key=lambda r: tuple(str(r.get(k, "")) for k in sort_keys))
        data = [columns]
        last = {g: None for g in groups}; buckets = {g: [] for g in groups}
        for r in sorted_rows:
            for idx, g in enumerate(groups):
                v = r.get(g, "")
                if last[g] is not None and v != last[g]:
                    for sg in reversed(groups[idx:]):
                        if buckets[sg]: data.append([f"Subtotal {sg}: {last[sg]}"] + [""]*(len(columns)-2) + [self._num(self._sum(buckets[sg], kg_field))]); buckets[sg]=[]
                    break
            for g in groups: last[g] = r.get(g, ""); buckets[g].append(r)
            data.append([self._format_cell(r.get(c, ""), c) for c in columns])
        for sg in reversed(groups):
            if buckets[sg]: data.append([f"Subtotal {sg}: {last[sg]}"] + [""]*(len(columns)-2) + [self._num(self._sum(buckets[sg], kg_field))])
        data.append([f"Total {title.lower()}"] + [""]*(len(columns)-2) + [self._num(self._sum(sorted_rows, kg_field))])
        story.append(self._table(data)); story.append(PageBreak())

    def _format_cell(self, value: Any, column: str) -> str:
        if "Kg" in column: return self._num(value)
        if any(x in column for x in ("Palets", "Cajas")): return self._num(value, 2).rstrip('0').rstrip('.') if str(value).strip() else ""
        return str(value or "")

    def _table(self, data: list[list[Any]], repeat: int = 1, header: bool = True, col_widths: list[float] | None = None) -> Table:
        wrapped = [[self._p(c) for c in row] for row in data]
        t = Table(wrapped, repeatRows=repeat, colWidths=col_widths)
        style = [("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 2), ("RIGHTPADDING", (0,0), (-1,-1), 2)]
        if header: style += [("BACKGROUND", (0,0), (-1,0), colors.HexColor("#D9EAF7")), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold")]
        for i, row in enumerate(data):
            if row and str(row[0]).startswith(("Subtotal", "Total")):
                style += [("FONTNAME", (0,i), (-1,i), "Helvetica-Bold"), ("BACKGROUND", (0,i), (-1,i), colors.HexColor("#F1F1F1"))]
        t.setStyle(TableStyle(style)); return t

    def _generate_minimal_pdf(self, target: Path, **kwargs: Any) -> None:
        """Fallback PDF válido cuando ReportLab aún no está instalado en el entorno."""
        filters = kwargs.get("filters", {}) or {}
        lines = [
            "Informe comercial diario",
            f"Fecha/hora generación: {kwargs.get('generated_at').strftime('%Y-%m-%d %H:%M')}",
            f"Campaña: {self._filter_text(filters.get('campana'))}",
            f"Cultivo: {self._filter_text(filters.get('cultivo'))}",
            f"Empresa: {self._filter_text(filters.get('empresa'))}",
        ]
        sections = [
            ("RESUMEN EJECUTIVO", []),
            ("STOCK CAMPO", kwargs.get("stock_campo_rows", [])),
            ("STOCK ALMACÉN", kwargs.get("stock_almacen_rows", [])),
            ("PEDIDOS PENDIENTES", kwargs.get("pedidos_pendientes_rows", [])),
            ("PEDIDOS PREVISTOS / NO CONFIRMADOS", kwargs.get("pedidos_previstos_rows", [])),
        ]
        for title, rows in sections:
            lines.append("")
            lines.append(title)
            if rows:
                for row in rows[:40]:
                    lines.append(" | ".join(f"{k}: {v}" for k, v in row.items() if not str(k).startswith("__"))[:150])
            else:
                lines.append("Sin datos para los filtros actuales.")
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
