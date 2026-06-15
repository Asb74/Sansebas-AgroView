from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

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
        self._add_stock_campo(story, campo)
        self._add_stock_almacen(story, almacen)
        self._add_pedidos(story, "PEDIDOS PENDIENTES", pendientes, kg_field="Kg pendiente", confeccion_field="Confección", previsto=False)
        self._add_pedidos(story, "PEDIDOS PREVISTOS / NO CONFIRMADOS", previstos, kg_field="Kg estimados", confeccion_field="Confección prevista", previsto=True)
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
        kg_campo = self._sum(campo, "Kg campo")
        kg_almacen = self._sum(almacen, "Kg stock")
        kg_pendientes = self._sum(pendientes, "Kg pendiente")
        kg_previstos = self._sum(previstos, "Kg estimados")
        rows = [
            ["Bloque", "KPI", "Valor"],
            ["Disponibilidad", "Kg stock campo", self._num(kg_campo)],
            ["Disponibilidad", "Kg stock almacén", self._num(kg_almacen)],
            ["Disponibilidad", "Kg total disponible", self._num(kg_campo + kg_almacen)],
            ["Demanda", "Kg pedidos pendientes", self._num(kg_pendientes)],
            ["Demanda", "Kg pedidos previstos", self._num(kg_previstos)],
            ["Demanda", "Kg demanda total", self._num(kg_pendientes + kg_previstos)],
            ["Diferencia", "Kg stock almacén - pedidos pendientes", self._num(kg_almacen - kg_pendientes)],
            ["Diferencia", "Kg campo + almacén - pendientes - previstos", self._num(kg_campo + kg_almacen - kg_pendientes - kg_previstos)],
        ]
        story.append(Paragraph("RESUMEN EJECUTIVO", self._section))
        story.append(self._table(rows, col_widths=[4*cm, 11*cm, 5*cm]))
        mini = self._group_rows(pendientes, ["Fecha salida"], {"Kg pendientes": "Kg pendiente"})
        if mini:
            story.append(Spacer(1, 6))
            story.append(Paragraph("Próximos días con kg pendientes", self._normal))
            story.append(self._table([["Fecha salida", "Kg pendientes"]] + [[r["Fecha salida"], self._num(r["Kg pendientes"])] for r in mini[:7]], col_widths=[5*cm, 5*cm]))
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
        total = self._sum(rows, "Kg campo")
        summary = self._group_rows(rows, ["Grupo varietal", "Variedad", "Estado aprovechamiento"], {"Kg campo": "Kg campo"}, count_label="Nº partidas")
        data = [["Grupo varietal", "Variedad", "Estado aprovechamiento", "Nº partidas", "Kg campo", "% sobre total"]]
        for r in summary:
            pct = (float(r["Kg campo"]) / total * 100) if total else 0
            data.append([r["Grupo varietal"], r["Variedad"], r["Estado aprovechamiento"], r["Nº partidas"], self._num(r["Kg campo"]), f"{pct:.1f}%"])
        story.append(Paragraph("Resumen por grupo varietal, variedad y estado", self._normal)); story.append(self._table(data)); story.append(Spacer(1, 6))
        self._add_section(story, "Detalle stock campo", rows, ["Fecha carga", "Semana", "Socio", "Variedad", "Grupo varietal", "Boleta", "Color", "Estado aprovechamiento", "Kg campo"], ["Grupo varietal", "Variedad"], ["Grupo varietal", "Variedad", "Fecha carga", "Boleta"], "Kg campo", page_break=False)
        story.append(PageBreak())

    def _add_stock_almacen(self, story: list, rows: list[dict]) -> None:
        story.append(Paragraph("STOCK ALMACÉN", self._section))
        if not rows:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal)); story.append(PageBreak()); return
        sums = {"Palets": "Palets", "Cajas": "Cajas", "Kg stock": "Kg stock"}
        self._add_group_summary(story, "Resumen por grupo varietal", rows, ["Grupo varietal"], sums)
        grouped = self._group_rows(rows, ["Grupo varietal", "Marca", "Confección"], sums)
        data = [["Grupo varietal", "Marca", "Confección", "Palets", "Cajas", "Kg stock", "Tipo palet", "Nombre palet"]]
        for r in grouped:
            matching = [row for row in rows if all(str(self._value(row, k) or "") == str(r.get(k, "")) for k in ("Grupo varietal", "Marca", "Confección"))]
            tipo = next((self._value(row, "Tipo palet") for row in matching if self._value(row, "Tipo palet")), "")
            nombre = next((self._value(row, "Nombre palet") for row in matching if self._value(row, "Nombre palet")), "")
            data.append([r["Grupo varietal"], r["Marca"], r["Confección"], self._format_cell(r["Palets"], "Palets"), self._format_cell(r["Cajas"], "Cajas"), self._format_cell(r["Kg stock"], "Kg stock"), tipo, nombre])
        story.append(Paragraph("Resumen por grupo varietal, marca y confección", self._normal))
        story.append(self._table(data))
        story.append(Spacer(1, 6))
        self._add_section(story, "Detalle stock almacén", rows, ["Variedad", "Grupo varietal", "Calibre", "Categoría", "Marca", "Confección", "Palets", "Cajas", "Kg stock", "Tipo palet", "Nombre palet"], ["Grupo varietal", "Marca", "Confección"], ["Grupo varietal", "Marca", "Confección", "Calibre", "Categoría"], "Kg stock", page_break=False)
        story.append(PageBreak())

    def _add_pedidos(self, story: list, title: str, rows: list[dict], *, kg_field: str, confeccion_field: str, previsto: bool) -> None:
        story.append(Paragraph(title, self._section))
        if not rows:
            story.append(Paragraph("Sin datos para los filtros actuales.", self._normal)); story.append(PageBreak()); return
        pedido_kg = "Kg estimados" if previsto else "Kg pedido teórico"
        palets = "Palets estimados" if previsto else "Palets pendientes"
        temporal = self._group_rows(rows, ["Fecha salida"], {"Kg pedido teórico": pedido_kg, "Kg hecho real": "Kg hecho real", "Kg pendiente": kg_field, "Palets pedido": "Palets pedido", "Palets pendientes": palets}, count_label="Nº pedidos")
        max_kg = max((r["Kg pendiente"] for r in temporal), default=0)
        data = [["Fecha salida", "Nº pedidos", "Kg pedido teórico", "Kg hecho real", "Kg pendiente", "Palets pedido", "Palets pendientes", "% pendiente", "Barra"]]
        for r in temporal:
            pct = (r["Kg pendiente"] / r["Kg pedido teórico"] * 100) if r["Kg pedido teórico"] else 0
            blocks = int(round((r["Kg pendiente"] / max_kg) * 12)) if max_kg else 0
            data.append([r["Fecha salida"], r["Nº pedidos"], self._num(r["Kg pedido teórico"]), self._num(r["Kg hecho real"]), self._num(r["Kg pendiente"]), self._num(r["Palets pedido"]), self._num(r["Palets pendientes"]), f"{pct:.1f}%", "█" * blocks])
        story.append(Paragraph("RESUMEN TEMPORAL DE PEDIDOS PENDIENTES" if not previsto else "RESUMEN TEMPORAL DE PEDIDOS PREVISTOS", self._normal)); story.append(self._table(data)); story.append(Spacer(1, 6))
        sums = {"Kg pedido teórico": pedido_kg, "Kg hecho real": "Kg hecho real", "Kg pendiente": kg_field, "Palets pendientes": palets}
        self._add_group_summary(story, "Resumen por grupo confección, grupo varietal y cliente", rows, ["Grupo confección", "Grupo varietal", "Cliente"], sums, count_label="Nº pedidos")
        detail_cols = ["Fecha salida", "Cliente", "Pedido", "Grupo varietal", confeccion_field, pedido_kg, "Kg hecho real", kg_field, palets]
        self._add_section(story, f"Detalle reducido {title.lower()}", rows, detail_cols, ["Grupo confección", "Pedido", "Grupo varietal"], ["Grupo confección", "Pedido", "Grupo varietal", "Fecha salida"], kg_field, page_break=False)
        story.append(PageBreak())

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
