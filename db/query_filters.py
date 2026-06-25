from typing import Any, Iterable

PEDIDOS_FIELD_MAP = {
    "campana": "Campaña",
    "cultivo": "Cultivo",
    "empresa": "EMPRESA",
    "semana": "Semana",
    "cliente": "Cliente",
    "var_coop": "VarCoop",
    "pais": "Pais",
    "var_cliente": "VarCliente",
    "calibre": "Calibre",
    "categoria": "Categoria",
    "marca": "Marca",
}

LIKE_FIELDS: set[str] = set()


def pedidos_base_clause(alias: str = "p") -> str:
    prefix = f"{alias}." if alias else ""
    column = f'{prefix}"Cancelado"'
    return (
        f"({column} IS NULL OR "
        f"UPPER(TRIM(CAST({column} AS TEXT))) IN ('', '0', 'FALSE', 'F', 'NO', 'N'))"
    )


def pedidos_base_where(alias: str = "p") -> tuple[list[str], list[Any]]:
    return [pedidos_base_clause(alias)], []


def _normalize_filter_values(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        value = raw.strip()
        return [value] if value else []
    if isinstance(raw, Iterable):
        out: list[str] = []
        for item in raw:
            value = str(item or "").strip()
            if value:
                out.append(value)
        return out
    value = str(raw).strip()
    return [value] if value else []


def build_pedidos_filters(filters: dict[str, Any], alias: str = "p") -> tuple[list[str], list[Any], list[str]]:
    clauses: list[str] = []
    params: list[Any] = []
    missing_fields: list[str] = []
    prefix = f"{alias}." if alias else ""

    for key, column in PEDIDOS_FIELD_MAP.items():
        values = _normalize_filter_values(filters.get(key))
        if not values:
            continue
        if len(values) == 1:
            clauses.append(f'CAST({prefix}"{column}" AS TEXT) = ?')
            params.append(values[0])
        else:
            placeholders = ", ".join(["?"] * len(values))
            clauses.append(f'CAST({prefix}"{column}" AS TEXT) IN ({placeholders})')
            params.extend(values)
    return clauses, params, missing_fields


def build_pedidos_where(filters: dict[str, Any], alias: str = "p", include_base: bool = True) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if include_base:
        clauses.append(pedidos_base_clause(alias))

    mapped_clauses, mapped_params, _ = build_pedidos_filters(filters, alias=alias)
    clauses.extend(mapped_clauses)
    params.extend(mapped_params)

    fecha_desde = str(filters.get("fecha_desde", "") or "").strip()
    if fecha_desde:
        prefix = f"{alias}." if alias else ""
        clauses.append(f'{prefix}"FechaSalida" >= ?')
        params.append(fecha_desde)

    fecha_hasta = str(filters.get("fecha_hasta", "") or "").strip()
    if fecha_hasta:
        prefix = f"{alias}." if alias else ""
        clauses.append(f'{prefix}"FechaSalida" <= ?')
        params.append(fecha_hasta)

    return build_where_sql(clauses), params


def build_where_sql(clauses: list[str]) -> str:
    if not clauses:
        return ""
    return "WHERE " + " AND ".join(clauses)
