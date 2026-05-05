import logging
from datetime import datetime
from typing import Any

from db.connection import get_connection

logger = logging.getLogger(__name__)


class PedidosRepository:
    TABLE_NAME = "Pedidos"

    COLUMNS = [
        "IdPedidoLora", "IdPedidoCom", "Semana", "FechaSalida", "Cliente", "Pais",
        "Confeccion", "Categoria", "VarCliente", "VarCoop", "Calibre", "Marca",
        "Cajas", "NetoCliente", "NetoCoop", "NetoCaja", "EurosKG", "VB",
        "EurosOrientativos", "FechaVC", "Cobro", "Comision", "FechaCobro",
        "Matricula", "Observaciones", "Transporte", "Campaña", "Cultivo",
        "NPalet", "NomPalet",
    ]

    def fetch_pedidos(self, filters: dict[str, Any], limit: int = 500) -> list[dict[str, Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []

        if filters.get("campana"):
            where_clauses.append('"Campaña" = ?')
            params.append(filters["campana"])

        if filters.get("fecha_desde"):
            self._validate_date(filters["fecha_desde"])
            where_clauses.append("date(FechaSalida) >= date(?)")
            params.append(filters["fecha_desde"])

        if filters.get("fecha_hasta"):
            self._validate_date(filters["fecha_hasta"])
            where_clauses.append("date(FechaSalida) <= date(?)")
            params.append(filters["fecha_hasta"])

        if filters.get("cliente"):
            where_clauses.append("Cliente LIKE ?")
            params.append(f"%{filters['cliente']}%")

        if filters.get("var_coop"):
            where_clauses.append("VarCoop LIKE ?")
            params.append(f"%{filters['var_coop']}%")

        if filters.get("pais"):
            where_clauses.append("Pais LIKE ?")
            params.append(f"%{filters['pais']}%")

        query = f"SELECT {', '.join(self.COLUMNS)} FROM {self.TABLE_NAME}"
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY FechaSalida DESC LIMIT ?"
        params.append(limit)

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
