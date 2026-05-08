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
        if report_data.get("report_variant") == "desviacion_cliente_executive":
            return self._generate_desviacion_cliente_executive(doc, story, styles, report_data, output)

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

    def _generate_desviacion_cliente_executive(self, doc, story, styles, report_data: dict[str, Any], output: Path) -> tuple[bool, str]:
        title = report_data.get("title", "RANKING DE CLIENTES")
        subtitle = report_data.get("subtitle", "Análisis comercial y rentabilidad")
        story.append(self.Paragraph(f"<b>{title}</b>", styles["Title"]))
        story.append(self.Paragraph(subtitle, styles["Heading3"]))
        story.append(self.Spacer(1, 6))

        generated_at = report_data.get("generated_at", "")
        filters = report_data.get("filters", [])
        filtros_txt = " / ".join([f"{k}: {v}" for k, v in filters]) if filters else "Sin filtros"
        story.append(self.Paragraph(f"Filtros activos: {filtros_txt}", styles["Normal"]))
        story.append(self.Paragraph(f"Fecha generación: {generated_at}", styles["Normal"]))
        story.append(self.Spacer(1, 8))

        kpis = report_data.get("kpis", [])
        if kpis:
            kpi_data: list[list[Any]] = []
            for i in range(0, len(kpis), 2):
                left = kpis[i]
                right = kpis[i + 1] if i + 1 < len(kpis) else ("", "")
                kpi_data.append([f"<b>{left[0]}</b><br/>{left[1]}", f"<b>{right[0]}</b><br/>{right[1]}"])
            kpi_table = self.Table(
                [[self.Paragraph(c, styles["Normal"]) for c in row] for row in kpi_data],
                colWidths=[13.5 * self.cm, 13.5 * self.cm],
            )
            kpi_table.setStyle(
                self.TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.4, self.colors.lightgrey),
                        ("BACKGROUND", (0, 0), (-1, -1), self.colors.whitesmoke),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(kpi_table)
            story.append(self.Spacer(1, 10))

        tables = report_data.get("tables", [])
        if tables:
            ranking = tables[0]
            columns = ranking.get("columns", [])
            rows = ranking.get("rows", [])
            body = [columns]
            for row in rows:
                body.append([row.get(col, "") for col in columns])
            t = self.Table(body, colWidths=[1.5 * self.cm, 8.2 * self.cm, 3.0 * self.cm, 4.0 * self.cm, 4.0 * self.cm, 4.0 * self.cm], repeatRows=1)
            style = [
                ("GRID", (0, 0), (-1, -1), 0.25, self.colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), self.colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
            for idx, r in enumerate(rows, start=1):
                style.append(("BACKGROUND", (3, idx), (3, idx), self._priority_color(str(r.get("Prioridad", "")))))
                style.append(("BACKGROUND", (4, idx), (4, idx), self._estado_color(str(r.get("Estado", "")))))
            t.setStyle(self.TableStyle(style))
            story.append(self.Paragraph("<b>Ranking de clientes</b>", styles["Heading3"]))
            story.append(t)

        story.append(self.Spacer(1, 10))
        story.append(self.Paragraph("Estado: calidad comercial/rentabilidad del cliente.", styles["Normal"]))
        story.append(self.Paragraph("Prioridad: importancia estratégica para el negocio.", styles["Normal"]))

        def _footer(canvas, doc_obj):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.drawString(doc_obj.leftMargin, 0.7 * self.cm, "Sansebas AgroView")
            canvas.restoreState()

        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return True, f"Informe PDF generado: {output}"

    def _estado_color(self, estado: str):
        mapping = {
            "BUENO": self.colors.HexColor("#4CAF50"),
            "ACEPTABLE": self.colors.HexColor("#A5D6A7"),
            "MALO": self.colors.HexColor("#EF5350"),
            "REVISAR": self.colors.HexColor("#FFB74D"),
            "SIN_DATOS": self.colors.HexColor("#BDBDBD"),
        }
        return mapping.get((estado or "").upper(), self.colors.white)

    def _priority_color(self, prioridad: str):
        mapping = {
            "CRÍTICA": self.colors.HexColor("#B71C1C"),
            "CRITICA": self.colors.HexColor("#B71C1C"),
            "MUY ALTA": self.colors.HexColor("#E64A19"),
            "ALTA": self.colors.HexColor("#FB8C00"),
            "MEDIA": self.colors.HexColor("#FDD835"),
            "BAJA": self.colors.HexColor("#C5E1A5"),
        }
        return mapping.get((prioridad or "").upper(), self.colors.white)

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
