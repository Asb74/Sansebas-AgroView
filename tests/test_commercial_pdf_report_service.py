from pathlib import Path

from services.commercial_pdf_report_service import CommercialPdfReportService


def _assert_pdf(path: Path) -> None:
    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")
    assert path.stat().st_size > 1000


def test_generate_pdf_sin_datos(tmp_path):
    path = CommercialPdfReportService().generate(tmp_path / "sin_datos.pdf", filters={})
    _assert_pdf(path)


def test_generate_pdf_con_stock_campo(tmp_path):
    path = CommercialPdfReportService().generate(
        tmp_path / "campo.pdf",
        filters={"campana": ["2025"]},
        stock_campo_rows=[{"Cultivo": "Naranja", "Grupo varietal": "G1", "Variedad": "V1", "Boleta": "B1", "Kg campo": 1234.5}],
    )
    _assert_pdf(path)


def test_generate_pdf_con_stock_almacen(tmp_path):
    path = CommercialPdfReportService().generate(
        tmp_path / "almacen.pdf",
        stock_almacen_rows=[{"Grupo varietal": "G1", "Marca": "M", "Confección": "C", "Kg stock": 500, "Palets": 1, "Cajas": 20}],
    )
    _assert_pdf(path)


def test_generate_pdf_con_pedidos_pendientes(tmp_path):
    path = CommercialPdfReportService().generate(
        tmp_path / "pendientes.pdf",
        pedidos_pendientes_rows=[{"Grupo confección": "GC", "IdPedidoLora": "P1", "Grupo varietal": "G1", "Confección": "C", "Kg pendiente": 700}],
    )
    _assert_pdf(path)


def test_generate_pdf_con_pedidos_previstos(tmp_path):
    path = CommercialPdfReportService().generate(
        tmp_path / "previstos.pdf",
        pedidos_previstos_rows=[{"Grupo confección": "GC", "Cliente": "Cliente", "Grupo varietal": "G1", "Confección prevista": "C", "Kg estimados": 300}],
    )
    _assert_pdf(path)


def test_generate_pdf_no_falla_si_faltan_columnas_opcionales(tmp_path):
    path = CommercialPdfReportService().generate(
        tmp_path / "faltan_columnas.pdf",
        stock_campo_rows=[{"Kg campo": 1}],
        stock_almacen_rows=[{"Kg stock": 2}],
        pedidos_pendientes_rows=[{"Kg pendiente": 3}],
        pedidos_previstos_rows=[{"Kg estimados": 4}],
    )
    _assert_pdf(path)
