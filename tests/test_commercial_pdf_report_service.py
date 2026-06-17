from pathlib import Path

import pytest

from services.commercial_pdf_report_service import CommercialPdfReportService, REPORTLAB_AVAILABLE


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


@pytest.mark.skipif(not REPORTLAB_AVAILABLE, reason="ReportLab no instalado")
def test_stock_almacen_oculta_tipo_nombre_palet_si_no_hay_datos(monkeypatch, tmp_path):
    captured = []
    service = CommercialPdfReportService()
    original = service._table

    def spy(data, *args, **kwargs):
        captured.append(data)
        return original(data, *args, **kwargs)

    monkeypatch.setattr(service, "_table", spy)
    service.generate(
        tmp_path / "almacen_sin_palet.pdf",
        stock_almacen_rows=[{"Grupo varietal": "G1", "Marca": "M", "Confección": "C", "Calibre": "10", "Categoría": "I", "Kg stock": 500, "Palets": 1, "Cajas": 20}],
    )
    almacen_tables = [t for t in captured if t and t[0] and t[0][0] == "Grupo varietal" and "Calibre / categoría" in t[0]]
    assert almacen_tables
    assert "Tipo palet" not in almacen_tables[0][0]
    assert "Nombre palet" not in almacen_tables[0][0]


@pytest.mark.skipif(not REPORTLAB_AVAILABLE, reason="ReportLab no instalado")
def test_pedidos_incluye_mix_timeline_y_matriz(monkeypatch, tmp_path):
    captured = []
    service = CommercialPdfReportService()
    original = service._table

    def spy(data, *args, **kwargs):
        captured.append(data)
        return original(data, *args, **kwargs)

    monkeypatch.setattr(service, "_table", spy)
    service.generate(
        tmp_path / "pendientes_matriz.pdf",
        pedidos_pendientes_rows=[
            {"Semana": "24", "Fecha salida": "2026-06-16", "Cliente": "Cliente A", "Grupo confección": "ENCAJADO", "Grupo varietal": "BLANCA SIN SEMILLAS", "Kg pedido teórico": 1000, "Kg hecho real": 200, "Kg pendiente": 800, "Palets pendientes": 4},
            {"Semana": "24", "Fecha salida": "2026-06-16", "Cliente": "Cliente A", "Grupo confección": "GRANEL", "Grupo varietal": "NEGRA CON SEMILLAS", "Kg pedido teórico": 500, "Kg hecho real": 100, "Kg pendiente": 400, "Palets pendientes": 2},
        ],
    )
    assert any(t and t[0] == ["Grupo confección", "% palets", "Palets", "Kg pendiente"] for t in captured)
    assert any(t and t[0] == ["Fecha", "Kg teórico", "Kg terminado", "Kg pendiente", "Palets pendientes", "Barra visual"] for t in captured)
    assert any(t and "BLANCA SIN SEMILLAS Palets" in t[0] and "TOTAL Pendiente" in t[0] for t in captured)

@pytest.mark.skipif(not REPORTLAB_AVAILABLE, reason="ReportLab no instalado")
def test_aprovechamiento_detalle_partida_muestra_toneladas(monkeypatch, tmp_path):
    captured = []
    service = CommercialPdfReportService()
    original = service._table

    def spy(data, *args, **kwargs):
        captured.append(data)
        return original(data, *args, **kwargs)

    monkeypatch.setattr(service, "_table", spy)
    stock_row = {
        "IdPartida": "P1",
        "Boleta": "B1",
        "IdSocio": "S1",
        "Nombre socio": "Socio Uno",
        "Fecha carga": "2026-06-17",
        "Kg campo": 437916,
    }
    detalle_key = service._detalle_partida_key(stock_row)

    service.generate(
        tmp_path / "aprovechamiento_toneladas.pdf",
        stock_campo_rows=[stock_row],
        aprovechamiento_campo_detalle={
            detalle_key: [
                {"Calibre": "CAL 0", "Kg disponibles": 8648, "Origen aprovechamiento": "HARVESTSYNC", "Destrío %": 5, "Industria %": 2},
                {"Calibre": "CAL 10", "Kg disponibles": 9220, "Origen aprovechamiento": "HARVESTSYNC", "Destrío %": 5, "Industria %": 2},
            ]
        },
    )

    detalle_tables = [t for t in captured if t and t[0] and t[0][0] == "IdPartida" and "T entregadas" in t[0]]
    assert detalle_tables
    table = detalle_tables[0]
    assert "Kg entregado" not in table[0]
    assert table[0][5] == "T entregadas"
    assert table[0][9] == "T CAL 0"
    assert table[0][19] == "T CAL 10"
    assert table[0][20] == "T estimadas"
    assert table[1][5] == "437.9"
    assert table[1][9] == "8.6"
    assert table[1][19] == "9.2"
    assert table[1][20] == "17.9"
    assert table[-1][5] == "437.9"
    assert table[-1][9] == "8.6"
    assert table[-1][19] == "9.2"
    assert table[-1][20] == "17.9"
