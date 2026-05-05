import logging
from datetime import datetime
from typing import Any

from db.connection import get_connection

logger = logging.getLogger(__name__)


class PedidosRepository:
    TABLE_NAME = "Pedidos"
    PAGE_SIZE = 500
    CAMPANA_COLUMN = "Campa\u00f1a"
    EXPECTED_OPTIONAL_COLUMNS = ["Cultivo", "Empresa"]

    COLUMNS = [
        "IdPedidoLora", "IdPedidoCom", "Semana", "FechaSalida", "Cliente", "Pais",
        "Confeccion", "Categoria", "VarCliente", "VarCoop", "Calibre", "Marca",
        "Cajas", "NetoCliente", "NetoCoop", "NetoCaja", "EurosKG", "VB",
        "EurosOrientativos", "FechaVC", "Cobro", "Comision", "FechaCobro",
        "Matricula", "Observaciones", "Transporte", CAMPANA_COLUMN, "Cultivo", "Empresa",
        "NPalet", "NomPalet",
    ]

    _warned_missing_columns: set[str] = set()

    def get_missing_filter_columns(self) -> list[str]:
        available_columns = self._get_available_columns()
        missing: list[str] = []
        for column in self.EXPECTED_OPTIONAL_COLUMNS:
            if column not in available_columns:
                missing.append(column)
                if column not in self._warned_missing_columns:
                    logger.warning("Columna esperada no disponible en %s: %s", self.TABLE_NAME, column)
                    self._warned_missing_columns.add(column)
        return missing

    def fetch_pedidos(self, filters: dict[str, Any], limit: int = PAGE_SIZE, offset: int = 0) -> list[dict[str, Any]]:
        available_columns = self._get_available_columns()
        selected_columns = [column for column in self.COLUMNS if column in available_columns]
        if not selected_columns:
            logger.warning("No hay columnas disponibles para consultar en la tabla %s", self.TABLE_NAME)
            return []

        where_clauses: list[str] = []
        params: list[Any] = []

        self._add_filter(where_clauses, params, available_columns, filters, "campana", self.CAMPANA_COLUMN, exact=True)
        self._add_filter(where_clauses, params, available_columns, filters, "cliente", "Cliente", exact=False)
        self._add_filter(where_clauses, params, available_columns, filters, "var_coop", "VarCoop", exact=False)
        self._add_filter(where_clauses, params, available_columns, filters, "pais", "Pais", exact=False)
        self._add_filter(where_clauses, params, available_columns, filters, "cultivo", "Cultivo", exact=False)
        self._add_filter(where_clauses, params, available_columns, filters, "empresa", "Empresa", exact=False)

        if filters.get("fecha_desde") and "FechaSalida" in available_columns:
            self._validate_date(str(filters["fecha_desde"]))
            where_clauses.append(f"date({self._quote_identifier('FechaSalida')}) >= date(?)")
            params.append(filters["fecha_desde"])

        if filters.get("fecha_hasta") and "FechaSalida" in available_columns:
            self._validate_date(str(filters["fecha_hasta"]))
            where_clauses.append(f"date({self._quote_identifier('FechaSalida')}) <= date(?)")
            params.append(filters["fecha_hasta"])

        query = f"SELECT {', '.join(self._quote_identifier(c) for c in selected_columns)} FROM {self._quote_identifier(self.TABLE_NAME)}"
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        if "FechaSalida" in available_columns:
            query += f" ORDER BY {self._quote_identifier('FechaSalida')} DESC"
        else:
            query += f" ORDER BY {self._quote_identifier(selected_columns[0])} DESC"

        query += " LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)

        try:
            with get_connection() as conn:
                rows = conn.execute(query, params).fetchall()
                return [dict(row) for row in rows]
        except Exception as exc:
            logger.exception("Error en consulta de pedidos: %s", exc)
            raise

    @staticmethod
    def _validate_date(value: str) -> None:
        datetime.strptime(value, "%Y-%m-%d")

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        escaped = identifier.replace('"', '""')
        return f'"{escaped}"'

    def _get_available_columns(self) -> set[str]:
        query = f"PRAGMA table_info({self._quote_identifier(self.TABLE_NAME)})"
        with get_connection() as conn:
            rows = conn.execute(query).fetchall()
        return {str(row["name"]) for row in rows}

    def _add_filter(
        self,
        where_clauses: list[str],
        params: list[Any],
        available_columns: set[str],
        filters: dict[str, Any],
        filter_key: str,
        column_name: str,
        exact: bool,
    ) -> None:
        value = str(filters.get(filter_key, "")).strip()
        if not value or column_name not in available_columns:
            return

        if exact:
            where_clauses.append(f"{self._quote_identifier(column_name)} = ?")
            params.append(value)
            return

        where_clauses.append(f"{self._quote_identifier(column_name)} LIKE ?")
        params.append(f"%{value}%")
