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
            {"Semana": "24", "Fecha salida": "2026-06-17", "Cliente": "Cliente A", "Grupo confección": "ENCAJADO", "Grupo varietal": "BLANCA SIN SEMILLAS", "Kg pedido teórico": 1000, "Kg hecho real": 200, "Kg pendiente": 800, "Palets pendientes": 4},
            {"Semana": "24", "Fecha salida": "2026-06-17", "Cliente": "Cliente A", "Grupo confección": "GRANEL", "Grupo varietal": "NEGRA CON SEMILLAS", "Kg pedido teórico": 500, "Kg hecho real": 100, "Kg pendiente": 400, "Palets pendientes": 2},
        ],
    )
    assert any(t and t[0] == ["Grupo confección", "% palets", "Palets", "Kg pendiente"] for t in captured)
    assert any(t and t[0] == ["Fecha salida", "Nº pedidos", "Palets pendientes", "Kg teórico", "Kg terminado", "Kg pendiente", "% pendiente", "Barra visual"] for t in captured)
    assert any(t and "BLANCA SIN SEMILLAS Palets" in t[0] and "TOTAL Pendiente" in t[0] for t in captured)

@pytest.mark.skipif(not REPORTLAB_AVAILABLE, reason="ReportLab no instalado")
def test_aprovechamiento_detalle_partida_muestra_porcentajes_y_subtotales(monkeypatch, tmp_path):
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
    assert table[0][6] == "T comerciales"
    assert table[0][8] == "Destrío %"
    assert table[0][9] == "Industria %"
    assert table[0][10] == "CAL 0 %"
    assert table[0][20] == "CAL 10 %"
    assert table[0][21] == "% comercial total"
    assert table[1][0] == "GRUPO VARIETAL: SIN GRUPO VARIETAL"
    assert table[2][5] == ""
    assert table[2][6] == ""
    assert table[2][8] == "5,0"
    assert table[2][9] == "2,0"
    assert table[2][10] == "2,0"
    assert table[2][20] == "2,1"
    assert table[2][21] == "4,1"
    assert table[3][0] == "SUBTOTAL SIN GRUPO VARIETAL"
    assert table[3][1] == "1"
    assert table[3][5] == "437,9"
    assert table[3][6] == "17,9"
    assert table[3][8] == "5,0"
    assert table[3][10] == "2,0"
    assert table[3][20] == "2,1"
    assert table[3][21] == "4,1"
    assert table[4][0] == "TOTAL GENERAL"
    assert table[4][1] == "1"
    assert not any(t and t[0] and str(t[0][0]).startswith("SUBTOTAL GRUPO VARIETAL") for t in captured)

@pytest.mark.skipif(not REPORTLAB_AVAILABLE, reason="ReportLab no instalado")
def test_prevision_recoleccion_incluye_matriz_semanal(monkeypatch, tmp_path):
    captured = []
    service = CommercialPdfReportService()
    original = service._table

    def spy(data, *args, **kwargs):
        captured.append(data)
        return original(data, *args, **kwargs)

    monkeypatch.setattr(service, "_table", spy)
    service.generate(
        tmp_path / "prevision_matriz.pdf",
        filters={"cultivo": ["SANDIA"]},
        prevision_recoleccion_rows=[
            {"Fecha_date": "2026-06-17", "FechaR_date": "2026-06-10", "IdSocio": "1", "Socio": "Socio A", "Boleta": "B1", "Variedad": "V1", "KgAprox": 60000},
            {"Fecha_date": "2026-06-18", "FechaR_date": "2026-06-10", "IdSocio": "1", "Socio": "Socio A", "Boleta": "B2", "Variedad": "V1", "KgAprox": 10000},
            {"Fecha_date": "2026-06-17", "FechaR_date": "2026-06-10", "IdSocio": "2", "Socio": "Socio B", "Boleta": "B3", "Variedad": "V2", "Cultivo": "CITRICOS", "KgAprox": 5000},
        ],
    )

    matrix_tables = [t for t in captured if t and t[0][:3] == ["Socio", "Cult.", "Variedad"] and "miércoles-17" in t[0]]
    assert matrix_tables
    table = matrix_tables[0]
    assert table[0] == ["Socio", "Cult.", "Variedad", "miércoles-17", "jueves-18", "viernes-19", "sábado-20", "domingo-21", "lunes-22", "martes-23", "Total"]
    assert ["Socio A", "SA", "V1", "60.0", "10.0", "-", "-", "-", "-", "-", "70.0"] in table
    assert ["Socio B", "CI", "V2", "5.0", "-", "-", "-", "-", "-", "-", "5.0"] in table
    assert table[-1] == ["TOTAL", "", "", "65.0", "10.0", "-", "-", "-", "-", "-", "75.0"]


def test_prevision_recoleccion_filtra_por_fecha_no_fechar(tmp_path):
    import sqlite3
    from datetime import datetime

    from config import DB_FRUTA
    from db.planning_repository import PlanningRepository

    fruta_path = tmp_path / DB_FRUTA
    with sqlite3.connect(fruta_path) as conn:
        conn.execute(
            """
            CREATE TABLE Prevision (
                Fecha TEXT,
                FechaR TEXT,
                KgAprox TEXT,
                IdSocio TEXT,
                Socio TEXT,
                Boleta TEXT,
                Variedad TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO Prevision VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("2026-06-18", "2026-06-10", "1000", "1", "Socio válido", "B1", "V1"),
                ("2026-06-19", "31/12/1899", "2000", "2", "Socio con FechaR vacía", "B2", "V2"),
                ("2026-06-17", "2026-06-20", "3000", "3", "Socio pasado", "B3", "V3"),
                ("", "2026-06-20", "4000", "4", "Socio sin fecha", "B4", "V4"),
                (None, "2026-06-20", "5000", "5", "Socio fecha nula", "B5", "V5"),
                ("31/12/1899", "2026-06-20", "6000", "6", "Socio fecha cero", "B6", "V6"),
                ("2026-06-20", "2026-06-20", "0", "7", "Socio sin kg", "B7", "V7"),
            ],
        )

    repo = PlanningRepository(base_dir=tmp_path)
    rows = repo.get_prevision_recoleccion({}, today=datetime(2026, 6, 18))

    assert [row["Boleta"] for row in rows] == ["B1", "B2"]
    assert [row["Fecha_date"] for row in rows] == ["2026-06-18", "2026-06-19"]
    assert rows[0]["FechaR_date"] == "2026-06-10"


@pytest.mark.skipif(not REPORTLAB_AVAILABLE, reason="ReportLab no instalado")
def test_prevision_recoleccion_detalle_solo_dia_operativo(monkeypatch, tmp_path):
    from datetime import datetime

    captured = []
    service = CommercialPdfReportService()
    original = service._table

    def spy(data, *args, **kwargs):
        captured.append(data)
        return original(data, *args, **kwargs)

    monkeypatch.setattr(service, "_table", spy)
    monkeypatch.setattr(service, "_prevision_operational_detail_date", lambda: datetime(2026, 6, 19).date())
    service.generate(
        tmp_path / "prevision_operativa.pdf",
        prevision_recoleccion_rows=[
            {"Fecha_date": "2026-06-18", "IdSocio": "1", "Socio": "Socio Hoy", "Boleta": "B18", "Variedad": "V1", "KgAprox": 1000},
            {"Fecha_date": "2026-06-19", "IdSocio": "2", "Socio": "Socio Mañana", "Boleta": "B19", "Variedad": "V2", "KgAprox": 2000},
        ],
    )

    detail_tables = [t for t in captured if t and t[0] and t[0][0] == "IdSocio" and "Kg aprox (t)" in t[0]]
    assert len(detail_tables) == 1
    assert any(row[2] == "B19" for row in detail_tables[0][1:])
    assert not any(len(row) > 2 and row[2] == "B18" for row in detail_tables[0][1:])
