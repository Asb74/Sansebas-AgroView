import logging
import sqlite3
from pathlib import Path
from typing import Any

from config import DB_DIR

logger = logging.getLogger(__name__)


class AgroviewCalcRepository:
    DB_FILE = "DBAgroViewCalc.sqlite"
    TABLE = "PreciosOrientativosCalc"
    FILTER_MAP_CALC = {
        "campana": ("Campaña", "exact"),
        "cultivo": ("Cultivo", "like"),
        "empresa": ("EMPRESA", "exact"),
        "semana": ("Semana", "exact"),
        "cliente": ("Cliente", "like"),
        "var_coop": ("VarCoop", "like"),
    }

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (Path(DB_DIR) / self.DB_FILE)

    def initialize(self) -> None:
        logger.info("Ruta DBAgroViewCalc.sqlite: %s", self.db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS "{self.TABLE}" (
                  IdPedidoLora TEXT NOT NULL,
                  Linea INTEGER NOT NULL DEFAULT 0,
                  "Campaña" TEXT,
                  Cultivo TEXT,
                  EMPRESA INTEGER,
                  Semana INTEGER,
                  FechaSalida TEXT,
                  Cliente TEXT,
                  VarCoop TEXT,
                  Confeccion TEXT,
                  GrupoConfeccion TEXT,
                  Calibre TEXT,
                  CalibreU TEXT,
                  EurosOrientativosOriginal REAL,
                  EurosOrientativosCalc REAL,
                  Origen TEXT,
                  Metodo TEXT,
                  SemanaPrecioUsada TEXT,
                  MuestrasUsadas INTEGER,
                  MediaGrupo REAL,
                  MediaCalibre REAL,
                  IdsUsados TEXT,
                  Observaciones TEXT,
                  FechaCalculo TEXT,
                  UsuarioCalculo TEXT,
                  PRIMARY KEY (IdPedidoLora, Linea)
                )
                """
            )
            conn.commit()
        logger.info("Tabla auxiliar lista: %s", self.TABLE)

    def fetch_calc_map(self, keys: list[tuple[str, int]]) -> dict[tuple[str, int], dict[str, Any]]:
        if not keys:
            return {}
        out: dict[tuple[str, int], dict[str, Any]] = {}
        with self._connect() as conn:
            for pedido_id, linea in keys:
                row = conn.execute(
                    f'SELECT * FROM "{self.TABLE}" WHERE "IdPedidoLora" = ? AND "Linea" = ?',
                    [pedido_id, linea],
                ).fetchone()
                if row:
                    out[(pedido_id, linea)] = dict(row)
        return out

    def upsert_calcs(self, rows: list[dict[str, Any]]) -> tuple[int, int]:
        inserted = 0
        updated = 0
        with self._connect() as conn:
            for row in rows:
                pedido_id = str(row.get("IdPedidoLora") or "").strip()
                linea = self._to_int(row.get("Linea"), default=0)
                if not pedido_id:
                    continue

                exists = conn.execute(
                    f'SELECT 1 FROM "{self.TABLE}" WHERE "IdPedidoLora" = ? AND "Linea" = ?',
                    [pedido_id, linea],
                ).fetchone()

                conn.execute(
                    f"""
                    INSERT INTO "{self.TABLE}" (
                      IdPedidoLora, Linea, "Campaña", Cultivo, EMPRESA, Semana, FechaSalida, Cliente, VarCoop,
                      Confeccion, GrupoConfeccion, Calibre, CalibreU, EurosOrientativosOriginal, EurosOrientativosCalc,
                      Origen, Metodo, SemanaPrecioUsada, MuestrasUsadas, MediaGrupo, MediaCalibre, IdsUsados,
                      Observaciones, FechaCalculo, UsuarioCalculo
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(IdPedidoLora, Linea) DO UPDATE SET
                      "Campaña"=excluded."Campaña",
                      Cultivo=excluded.Cultivo,
                      EMPRESA=excluded.EMPRESA,
                      Semana=excluded.Semana,
                      FechaSalida=excluded.FechaSalida,
                      Cliente=excluded.Cliente,
                      VarCoop=excluded.VarCoop,
                      Confeccion=excluded.Confeccion,
                      GrupoConfeccion=excluded.GrupoConfeccion,
                      Calibre=excluded.Calibre,
                      CalibreU=excluded.CalibreU,
                      EurosOrientativosOriginal=excluded.EurosOrientativosOriginal,
                      EurosOrientativosCalc=excluded.EurosOrientativosCalc,
                      Origen=excluded.Origen,
                      Metodo=excluded.Metodo,
                      SemanaPrecioUsada=excluded.SemanaPrecioUsada,
                      MuestrasUsadas=excluded.MuestrasUsadas,
                      MediaGrupo=excluded.MediaGrupo,
                      MediaCalibre=excluded.MediaCalibre,
                      IdsUsados=excluded.IdsUsados,
                      Observaciones=excluded.Observaciones,
                      FechaCalculo=excluded.FechaCalculo,
                      UsuarioCalculo=excluded.UsuarioCalculo
                    """,
                    [
                        pedido_id,
                        linea,
                        row.get("Campaña"),
                        row.get("Cultivo"),
                        self._to_int(row.get("Empresa")),
                        self._to_int(row.get("Semana")),
                        row.get("FechaSalida"),
                        row.get("Cliente"),
                        row.get("VarCoop"),
                        row.get("Confeccion"),
                        row.get("GrupoConfeccion"),
                        row.get("Calibre"),
                        row.get("CalibreU"),
                        row.get("EurosOrientativos"),
                        row.get("EurosOrientativosCalc"),
                        row.get("OrigenPrecioOrientativo"),
                        row.get("Metodo"),
                        row.get("SemanaPrecioUsada"),
                        self._to_int(row.get("MuestrasUsadas")),
                        row.get("MediaGrupo"),
                        row.get("MediaCalibre"),
                        row.get("IdsUsados"),
                        row.get("Observaciones"),
                        row.get("FechaCalculo"),
                        row.get("UsuarioCalculo"),
                    ],
                )
                if exists:
                    updated += 1
                else:
                    inserted += 1
            conn.commit()
        return inserted, updated

    def delete_calculations_by_filters(self, filters: dict[str, Any]) -> int:
        clauses, params = self._build_calc_where(filters)

        query = f'DELETE FROM "{self.TABLE}"'
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        else:
            logger.warning("Eliminación sin filtros: se eliminarán todos los cálculos auxiliares")

        with self._connect() as conn:
            cur = conn.execute(query, params)
            conn.commit()
            deleted = int(cur.rowcount or 0)

        logger.info("Eliminación en auxiliar. Filtros=%s SQL=%s Registros eliminados=%s", filters, query, deleted)
        return deleted

    def _build_calc_where(self, filters: dict[str, Any]) -> tuple[list[str], list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        for key, value in filters.items():
            v = str(value or "").strip()
            if not v:
                continue
            if key not in self.FILTER_MAP_CALC:
                continue

            column, mode = self.FILTER_MAP_CALC[key]
            if mode == "like":
                clauses.append(f'"{column}" LIKE ?')
                params.append(f"%{v}%")
            else:
                clauses.append(f'CAST("{column}" AS TEXT) = ?')
                params.append(v)

        return clauses, params

    def _connect(self) -> sqlite3.Connection:
        logger.info("Abriendo DBAgroViewCalc.sqlite sin URI: %s", self.db_path)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _to_int(value: Any, default: int | None = None) -> int | None:
        try:
            return int(float(str(value).strip()))
        except Exception:
            return default
