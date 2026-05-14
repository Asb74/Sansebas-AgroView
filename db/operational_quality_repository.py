from __future__ import annotations

from datetime import datetime

from db.connection import get_connection

DEFAULTS_PERCENT = {
    "CAMPO_REAL": (80, 20, 15, 1, 100, 1),
    "ALMACEN_INDUSTRIAL": (80, 20, 5, 0, 100, 1),
    "PRECALIBRADO": (80, 20, 8, 0, 100, 1),
    "ALMACEN_COMERCIAL": (95, 5, 2, 0, 50, 1),
    "DESCONOCIDO": (80, 20, 10, 0, 80, 1),
}


class OperationalQualityRepository:
    def ensure_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS OperationalQualitySettings (
                    Id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Origen TEXT UNIQUE NOT NULL,
                    PrimeraPct REAL NOT NULL,
                    SegundaPct REAL NOT NULL,
                    DestrioFallbackPct REAL NOT NULL,
                    UsarDestrioHistorico INTEGER NOT NULL DEFAULT 0,
                    IndustriaRecuperablePct REAL NOT NULL,
                    Activo INTEGER NOT NULL DEFAULT 1,
                    FechaCreacion TEXT,
                    FechaModificacion TEXT
                )
                """
            )

    def get_all(self) -> list[dict]:
        self.ensure_schema()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM OperationalQualitySettings ORDER BY Origen").fetchall()
        return [dict(r) for r in rows]

    def upsert_many(self, rows: list[dict]) -> None:
        self.ensure_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            for r in rows:
                conn.execute(
                    """
                    INSERT INTO OperationalQualitySettings (Origen, PrimeraPct, SegundaPct, DestrioFallbackPct, UsarDestrioHistorico, IndustriaRecuperablePct, Activo, FechaCreacion, FechaModificacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(Origen) DO UPDATE SET
                        PrimeraPct=excluded.PrimeraPct,
                        SegundaPct=excluded.SegundaPct,
                        DestrioFallbackPct=excluded.DestrioFallbackPct,
                        UsarDestrioHistorico=excluded.UsarDestrioHistorico,
                        IndustriaRecuperablePct=excluded.IndustriaRecuperablePct,
                        Activo=excluded.Activo,
                        FechaModificacion=excluded.FechaModificacion
                    """,
                    (
                        r["Origen"], r["PrimeraPct"], r["SegundaPct"], r["DestrioFallbackPct"],
                        int(r["UsarDestrioHistorico"]), r["IndustriaRecuperablePct"], int(r["Activo"]), now, now,
                    ),
                )

    def ensure_defaults(self) -> None:
        self.ensure_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            for origen, vals in DEFAULTS_PERCENT.items():
                p1, p2, d, h, ir, a = vals
                conn.execute(
                    """
                    INSERT INTO OperationalQualitySettings (Origen, PrimeraPct, SegundaPct, DestrioFallbackPct, UsarDestrioHistorico, IndustriaRecuperablePct, Activo, FechaCreacion, FechaModificacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(Origen) DO NOTHING
                    """,
                    (origen, p1/100.0, p2/100.0, d/100.0, h, ir/100.0, a, now, now),
                )

    def reset_defaults(self) -> None:
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            for origen, vals in DEFAULTS_PERCENT.items():
                p1, p2, d, h, ir, a = vals
                conn.execute(
                    """
                    INSERT INTO OperationalQualitySettings (Origen, PrimeraPct, SegundaPct, DestrioFallbackPct, UsarDestrioHistorico, IndustriaRecuperablePct, Activo, FechaCreacion, FechaModificacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(Origen) DO UPDATE SET
                        PrimeraPct=excluded.PrimeraPct,
                        SegundaPct=excluded.SegundaPct,
                        DestrioFallbackPct=excluded.DestrioFallbackPct,
                        UsarDestrioHistorico=excluded.UsarDestrioHistorico,
                        IndustriaRecuperablePct=excluded.IndustriaRecuperablePct,
                        Activo=excluded.Activo,
                        FechaModificacion=excluded.FechaModificacion
                    """,
                    (origen, p1/100.0, p2/100.0, d/100.0, h, ir/100.0, a, now, now),
                )
