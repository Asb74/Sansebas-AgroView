from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter


def normalize_bool(value) -> int:
    if value is None:
        return 0
    normalized = str(value).strip().upper()
    if normalized in {"1", "S", "SI", "SÍ", "TRUE", "X", "Y", "YES"}:
        return 1
    if normalized in {"0", "N", "NO", "FALSE", "", "NONE"}:
        return 0
    return 1 if normalized else 0


def normalize_number(value) -> float:
    if value in (None, ""):
        raise ValueError("empty numeric")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if text == "":
        raise ValueError("empty numeric")
    return float(text)


def validate_required_columns(headers: list[str], required_columns: list[str]) -> None:
    missing = [column for column in required_columns if column not in headers]
    if missing:
        raise ValueError(f"Faltan columnas obligatorias: {', '.join(missing)}")


def export_master_to_excel(rows: list[dict], config: dict) -> str | None:
    target = filedialog.asksaveasfilename(
        defaultextension=".xlsx",
        initialfile=config.get("default_filename", "maestro_productivo.xlsx"),
        filetypes=[("Excel", "*.xlsx")],
    )
    if not target:
        return None

    columns = config["columns"]
    wb = Workbook()
    ws = wb.active
    ws.title = config.get("sheet_name", "Maestro")
    ws.append(columns)
    for row in rows:
        ws.append([row.get(column, "") for column in columns])

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for col_idx, header in enumerate(columns, start=1):
        max_len = len(str(header))
        for cell in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=2, max_row=ws.max_row):
            max_len = max(max_len, len(str(cell[0].value or "")))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 2, 60)

    output_path = Path(target)
    wb.save(output_path)
    return output_path.as_posix()


def import_master_from_excel(path: str, config: dict) -> tuple[list[dict], list[str]]:
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header_row = next(rows_iter, None)
    if not header_row:
        raise ValueError("El Excel no contiene cabeceras.")

    headers = [str(h or "").strip() for h in header_row]
    validate_required_columns(headers, config.get("required_columns", []))

    columns = config.get("columns", headers)
    numeric_columns = set(config.get("numeric_columns", []))
    boolean_columns = set(config.get("boolean_columns", []))
    required_columns = set(config.get("required_columns", []))

    normalized_rows: list[dict] = []
    errors: list[str] = []

    for excel_row_index, values in enumerate(rows_iter, start=2):
        row = {headers[i]: values[i] if i < len(values) else None for i in range(len(headers))}
        clean_row: dict = {column: row.get(column, "") for column in columns}

        for column in required_columns:
            if str(row.get(column) or "").strip() == "":
                errors.append(f"Fila {excel_row_index}: {column} obligatorio.")

        for column in numeric_columns:
            raw = row.get(column)
            if raw in (None, ""):
                clean_row[column] = 0.0
                continue
            try:
                clean_row[column] = normalize_number(raw)
            except ValueError:
                errors.append(f"Fila {excel_row_index}: {column} no es numérico válido ({raw}).")

        for column in boolean_columns:
            clean_row[column] = normalize_bool(row.get(column))

        normalized_rows.append(clean_row)

    return normalized_rows, errors
