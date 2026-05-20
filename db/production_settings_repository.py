from __future__ import annotations

from datetime import datetime

from db.connection import get_connection

DEFAULT_GENERAL_SETTINGS = {
    "horas_turno": 8.0,
    "numero_turnos": 1,
    "horas_descanso": 0.5,
    "tipo_campana": "Normal",
    "tipo_volcado": "Compacta",
    "saturacion_maxima_pct": 90.0,
    "permitir_horas_extra": 1,
    "permitir_segundo_turno": 0,
    "priorizar_pedidos_reales": 1,
    "permitir_adelantar_produccion": 1,
    "agrupar_pedidos_compatibles": 1,
    "minimizar_cambios_formato": 1,
    "kg_objetivo_dia": 0.0,
    "palets_objetivo_dia": 0.0,
    "pedidos_maximos_recomendados": 0,
}


class ProductionSettingsRepository:
    def ensure_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_general_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    horas_turno REAL NOT NULL,
                    numero_turnos INTEGER NOT NULL,
                    horas_descanso REAL NOT NULL,
                    tipo_campana TEXT NOT NULL,
                    tipo_volcado TEXT NOT NULL,
                    saturacion_maxima_pct REAL NOT NULL,
                    permitir_horas_extra INTEGER NOT NULL,
                    permitir_segundo_turno INTEGER NOT NULL,
                    priorizar_pedidos_reales INTEGER NOT NULL,
                    permitir_adelantar_produccion INTEGER NOT NULL,
                    agrupar_pedidos_compatibles INTEGER NOT NULL,
                    minimizar_cambios_formato INTEGER NOT NULL,
                    kg_objetivo_dia REAL NOT NULL,
                    palets_objetivo_dia REAL NOT NULL,
                    pedidos_maximos_recomendados INTEGER NOT NULL,
                    updated_at TEXT
                )
                """
            )

    def ensure_defaults(self) -> None:
        self.ensure_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_general_settings (
                    id, horas_turno, numero_turnos, horas_descanso, tipo_campana,
                    tipo_volcado, saturacion_maxima_pct, permitir_horas_extra,
                    permitir_segundo_turno, priorizar_pedidos_reales,
                    permitir_adelantar_produccion, agrupar_pedidos_compatibles,
                    minimizar_cambios_formato, kg_objetivo_dia, palets_objetivo_dia,
                    pedidos_maximos_recomendados, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    1,
                    DEFAULT_GENERAL_SETTINGS["horas_turno"],
                    DEFAULT_GENERAL_SETTINGS["numero_turnos"],
                    DEFAULT_GENERAL_SETTINGS["horas_descanso"],
                    DEFAULT_GENERAL_SETTINGS["tipo_campana"],
                    DEFAULT_GENERAL_SETTINGS["tipo_volcado"],
                    DEFAULT_GENERAL_SETTINGS["saturacion_maxima_pct"],
                    DEFAULT_GENERAL_SETTINGS["permitir_horas_extra"],
                    DEFAULT_GENERAL_SETTINGS["permitir_segundo_turno"],
                    DEFAULT_GENERAL_SETTINGS["priorizar_pedidos_reales"],
                    DEFAULT_GENERAL_SETTINGS["permitir_adelantar_produccion"],
                    DEFAULT_GENERAL_SETTINGS["agrupar_pedidos_compatibles"],
                    DEFAULT_GENERAL_SETTINGS["minimizar_cambios_formato"],
                    DEFAULT_GENERAL_SETTINGS["kg_objetivo_dia"],
                    DEFAULT_GENERAL_SETTINGS["palets_objetivo_dia"],
                    DEFAULT_GENERAL_SETTINGS["pedidos_maximos_recomendados"],
                    now,
                ),
            )

    def get_general_settings(self) -> dict:
        self.ensure_defaults()
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM production_general_settings WHERE id = 1").fetchone()
        return dict(row) if row else {"id": 1, **DEFAULT_GENERAL_SETTINGS}

    def save_general_settings(self, data: dict) -> None:
        self.ensure_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_general_settings (
                    id, horas_turno, numero_turnos, horas_descanso, tipo_campana,
                    tipo_volcado, saturacion_maxima_pct, permitir_horas_extra,
                    permitir_segundo_turno, priorizar_pedidos_reales,
                    permitir_adelantar_produccion, agrupar_pedidos_compatibles,
                    minimizar_cambios_formato, kg_objetivo_dia, palets_objetivo_dia,
                    pedidos_maximos_recomendados, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    horas_turno=excluded.horas_turno,
                    numero_turnos=excluded.numero_turnos,
                    horas_descanso=excluded.horas_descanso,
                    tipo_campana=excluded.tipo_campana,
                    tipo_volcado=excluded.tipo_volcado,
                    saturacion_maxima_pct=excluded.saturacion_maxima_pct,
                    permitir_horas_extra=excluded.permitir_horas_extra,
                    permitir_segundo_turno=excluded.permitir_segundo_turno,
                    priorizar_pedidos_reales=excluded.priorizar_pedidos_reales,
                    permitir_adelantar_produccion=excluded.permitir_adelantar_produccion,
                    agrupar_pedidos_compatibles=excluded.agrupar_pedidos_compatibles,
                    minimizar_cambios_formato=excluded.minimizar_cambios_formato,
                    kg_objetivo_dia=excluded.kg_objetivo_dia,
                    palets_objetivo_dia=excluded.palets_objetivo_dia,
                    pedidos_maximos_recomendados=excluded.pedidos_maximos_recomendados,
                    updated_at=excluded.updated_at
                """,
                (
                    1,
                    data["horas_turno"],
                    data["numero_turnos"],
                    data["horas_descanso"],
                    data["tipo_campana"],
                    data["tipo_volcado"],
                    data["saturacion_maxima_pct"],
                    int(data["permitir_horas_extra"]),
                    int(data["permitir_segundo_turno"]),
                    int(data["priorizar_pedidos_reales"]),
                    int(data["permitir_adelantar_produccion"]),
                    int(data["agrupar_pedidos_compatibles"]),
                    int(data["minimizar_cambios_formato"]),
                    data["kg_objetivo_dia"],
                    data["palets_objetivo_dia"],
                    data["pedidos_maximos_recomendados"],
                    now,
                ),
            )

    def reset_general_defaults(self) -> None:
        self.save_general_settings(DEFAULT_GENERAL_SETTINGS)
