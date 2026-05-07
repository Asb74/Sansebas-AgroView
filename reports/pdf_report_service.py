from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


class PdfReportService:
    def __init__(self) -> None:
        self.reportlab_available = True
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

            self.colors = colors
            self.A4 = A4
            self.landscape = landscape
            self.getSampleStyleSheet = getSampleStyleSheet
            self.cm = cm
            self.Image = Image
            self.Paragraph = Paragraph
            self.SimpleDocTemplate = SimpleDocTemplate
            self.Spacer = Spacer
            self.Table = Table
            self.TableStyle = TableStyle
            self.PageBreak = PageBreak
        except Exception:
            self.reportlab_available = False

    def generate(self, output_path: str, report_data: dict[str, Any]) -> tuple[bool, str]:
        if not self.reportlab_available:
            return False, "Instala reportlab con: c:/python313/python.exe -m pip install reportlab"

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        pagesize = self.landscape(self.A4)
        doc = self.SimpleDocTemplate(
            str(output),
            pagesize=pagesize,
            leftMargin=1.2 * self.cm,
            rightMargin=1.2 * self.cm,
            topMargin=1.0 * self.cm,
            bottomMargin=1.2 * self.cm,
        )

        styles = self.getSampleStyleSheet()
        header_style = styles["Normal"].clone("HeaderCell")
        header_style.fontSize = 7
        header_style.leading = 8
        header_style.alignment = 1
        body_style = styles["Normal"].clone("BodyCell")
        body_style.fontSize = 7
        body_style.leading = 8
        body_style.alignment = 0
        story = []

        title = report_data.get("title", "Informe")
        generated_at = report_data.get("generated_at", "")
        story.append(self.Paragraph(f"<b>{title}</b>", styles["Title"]))
        story.append(self.Spacer(1, 6))
        story.append(self.Paragraph(f"Generado: {generated_at}", styles["Normal"]))
        story.append(self.Spacer(1, 8))

        filters = report_data.get("filters", [])
        if filters:
            story.append(self.Paragraph("<b>Filtros activos</b>", styles["Heading3"]))
            filter_rows = [[k, v] for k, v in filters]
            t = self.Table(filter_rows, colWidths=[4.5 * self.cm, 22.0 * self.cm], repeatRows=0)
            t.setStyle(
                self.TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.3, self.colors.grey),
                        ("BACKGROUND", (0, 0), (0, -1), self.colors.whitesmoke),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(t)
            story.append(self.Spacer(1, 10))

        kpis = report_data.get("kpis", [])
        if kpis:
            story.append(self.Paragraph("<b>KPIs principales</b>", styles["Heading3"]))
            kpi_rows = [[k, v] for k, v in kpis]
            t = self.Table(kpi_rows, colWidths=[8.0 * self.cm, 8.0 * self.cm], repeatRows=0)
            t.setStyle(
                self.TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.3, self.colors.grey),
                        ("BACKGROUND", (0, 0), (0, -1), self.colors.whitesmoke),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(t)
            story.append(self.Spacer(1, 10))

        chart_images = report_data.get("chart_images", [])
        for idx, img_path in enumerate(chart_images):
            path = Path(str(img_path))
            if not path.exists():
                continue
            story.append(self.Paragraph(f"<b>Gráfica {idx + 1}</b>", styles["Heading3"]))
            story.append(self.Image(str(path), width=25.0 * self.cm, height=9.0 * self.cm))
            story.append(self.Spacer(1, 8))

        tables = report_data.get("tables", [])
        for i, table_payload in enumerate(tables):
            title = table_payload.get("title", f"Tabla {i+1}")
            columns = table_payload.get("columns", [])
            rows = table_payload.get("rows", [])
            if not columns:
                continue
            story.append(self.Paragraph(f"<b>{title}</b>", styles["Heading3"]))

            header_cells = [
                self.cell_paragraph(self._wrap_header(str(col)), header_style, prewrapped=True)
                for col in columns
            ]
            body = [header_cells]
            for row in rows:
                body.append([self.cell_paragraph(row.get(c, ""), body_style) for c in columns])

            available_w = 27.3 * self.cm
            col_widths = self._col_widths(columns, available_w)
            if len(columns) >= 14:
                for style_obj in (header_style, body_style):
                    style_obj.fontSize = 6
                    style_obj.leading = 7
            t = self.Table(body, colWidths=col_widths, repeatRows=1)
            t.setStyle(
                self.TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.25, self.colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), self.colors.lightgrey),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ]
                )
            )
            story.append(t)
            story.append(self.Spacer(1, 8))
            if i < len(tables) - 1:
                story.append(self.PageBreak())

        def _footer(canvas, doc_obj):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.drawString(doc_obj.leftMargin, 0.7 * self.cm, "Sansebas AgroView")
            canvas.restoreState()

        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return True, f"Informe PDF generado: {output}"

    @staticmethod
    def _wrap_header(text: str) -> str:
        return text.replace(" / ", "<br/>").replace(" por ", "<br/>").replace(" medio ", " medio<br/>")

    def cell_paragraph(self, value: Any, style, prewrapped: bool = False):
        text = "" if value is None else str(value)
        text = text.strip()
        if not prewrapped:
            text = escape(text)
            text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")
        return self.Paragraph(text, style)

    @staticmethod
    def _col_widths(columns: list[str], total_width: float) -> list[float]:
        weights = []
        for col in columns:
            name = col.lower()
            if "observ" in name:
                w = 2.4
            elif "cliente" in name:
                w = 2.0
            elif "variedades principales" in name:
                w = 2.3
            elif "categorías principales" in name or "categorias principales" in name:
                w = 2.2
            elif "calibres principales" in name:
                w = 2.2
            elif "variedad" in name or "causa" in name or "pais" in name:
                w = 1.7
            elif "importe" in name or "precio" in name or "desvi" in name:
                w = 1.25
            elif "fecha" in name:
                w = 1.2
            else:
                w = 1.0
            weights.append(w)
        total = sum(weights) if weights else 1.0
        return [total_width * (w / total) for w in weights]
