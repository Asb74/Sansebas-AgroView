from __future__ import annotations

from datetime import datetime
import json

from db.connection import get_connection

DEFAULT_GENERAL_SETTINGS = {
    "horas_turno": 8.0,
    "numero_turnos": 1,
    "horas_descanso": 0.5,
    "tipo_campana": "Normal",
    "tipo_volcado": "Compacta",
    "tipos_volcado_activos": ["Compacta"],
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
DEFAULT_STAFF_SUMMARY = {
    "personal_total": 0,
    "personal_directo": 0,
    "personal_indirecto": 0,
    "horas_por_persona": 7.5,
    "ausencias_previstas": 0,
    "observaciones": "",
}
DEFAULT_STAFF_AREAS = [
    ("Volcado", "Directo", 0, 0, 0, 1, ""),
    ("Tría principal", "Directo", 0, 0, 0, 1, ""),
    ("Tría mallas", "Directo", 0, 0, 0, 1, ""),
    ("Mallas", "Directo", 0, 0, 0, 1, ""),
    ("Encajado", "Directo", 0, 0, 0, 1, ""),
    ("Granel manual", "Directo", 0, 0, 0, 1, ""),
    ("Granelera", "Directo", 0, 0, 0, 1, ""),
    ("Calibrador", "Soporte", 0, 0, 0, 1, ""),
    ("Calidad", "Indirecto", 0, 0, 0, 1, ""),
    ("Control destrío", "Soporte", 0, 0, 0, 1, ""),
    ("Alimentación", "Soporte", 0, 0, 0, 1, ""),
    ("Loteado", "Soporte", 0, 0, 0, 1, ""),
    ("Expedición", "Indirecto", 0, 0, 0, 1, ""),
    ("Carretilleros", "Indirecto", 0, 0, 0, 1, ""),
    ("Flejado", "Soporte", 0, 0, 0, 1, ""),
    ("Mantenimiento", "Soporte", 0, 0, 0, 1, ""),
    ("Limpieza", "Indirecto", 0, 0, 0, 1, ""),
    ("Encargados", "Indirecto", 0, 0, 0, 1, ""),
]


class ProductionSettingsRepository:
    def __init__(self) -> None:
        self.ensure_defaults()
        self.ensure_staff_defaults()

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
                    tipos_volcado_activos TEXT,
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
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(production_general_settings)").fetchall()
            }
            if "tipos_volcado_activos" not in columns:
                conn.execute("ALTER TABLE production_general_settings ADD COLUMN tipos_volcado_activos TEXT")

    def ensure_defaults(self) -> None:
        self.ensure_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_general_settings (
                    id, horas_turno, numero_turnos, horas_descanso, tipo_campana,
                    tipo_volcado, tipos_volcado_activos, saturacion_maxima_pct, permitir_horas_extra,
                    permitir_segundo_turno, priorizar_pedidos_reales,
                    permitir_adelantar_produccion, agrupar_pedidos_compatibles,
                    minimizar_cambios_formato, kg_objetivo_dia, palets_objetivo_dia,
                    pedidos_maximos_recomendados, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    1,
                    DEFAULT_GENERAL_SETTINGS["horas_turno"],
                    DEFAULT_GENERAL_SETTINGS["numero_turnos"],
                    DEFAULT_GENERAL_SETTINGS["horas_descanso"],
                    DEFAULT_GENERAL_SETTINGS["tipo_campana"],
                    DEFAULT_GENERAL_SETTINGS["tipo_volcado"],
                    json.dumps(DEFAULT_GENERAL_SETTINGS["tipos_volcado_activos"], ensure_ascii=False),
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
        data = dict(row) if row else {"id": 1, **DEFAULT_GENERAL_SETTINGS}
        data["tipos_volcado_activos"] = self._parse_tipos_volcado_activos(data)
        return data

    def save_general_settings(self, data: dict) -> None:
        self.ensure_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_general_settings (
                    id, horas_turno, numero_turnos, horas_descanso, tipo_campana,
                    tipo_volcado, tipos_volcado_activos, saturacion_maxima_pct, permitir_horas_extra,
                    permitir_segundo_turno, priorizar_pedidos_reales,
                    permitir_adelantar_produccion, agrupar_pedidos_compatibles,
                    minimizar_cambios_formato, kg_objetivo_dia, palets_objetivo_dia,
                    pedidos_maximos_recomendados, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    horas_turno=excluded.horas_turno,
                    numero_turnos=excluded.numero_turnos,
                    horas_descanso=excluded.horas_descanso,
                    tipo_campana=excluded.tipo_campana,
                    tipo_volcado=excluded.tipo_volcado,
                    tipos_volcado_activos=excluded.tipos_volcado_activos,
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
                    data["tipos_volcado_activos"][0] if data["tipos_volcado_activos"] else DEFAULT_GENERAL_SETTINGS["tipo_volcado"],
                    json.dumps(data["tipos_volcado_activos"], ensure_ascii=False),
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

    def _parse_tipos_volcado_activos(self, data: dict) -> list[str]:
        raw = data.get("tipos_volcado_activos")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    cleaned = [str(item).strip() for item in parsed if str(item).strip()]
                    if cleaned:
                        return cleaned
            except (ValueError, TypeError):
                cleaned = [item.strip() for item in str(raw).split(",") if item.strip()]
                if cleaned:
                    return cleaned

        legacy = str(data.get("tipo_volcado", "")).strip()
        return [legacy] if legacy else list(DEFAULT_GENERAL_SETTINGS["tipos_volcado_activos"])

    def ensure_staff_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_staff_summary (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    personal_total INTEGER NOT NULL,
                    personal_directo INTEGER NOT NULL,
                    personal_indirecto INTEGER NOT NULL,
                    horas_por_persona REAL NOT NULL,
                    ausencias_previstas INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_staff_areas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    area TEXT NOT NULL UNIQUE,
                    tipo_personal TEXT NOT NULL,
                    disponible INTEGER NOT NULL,
                    minimo_operativo INTEGER NOT NULL,
                    optimo INTEGER NOT NULL,
                    activo INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_staff_defaults(self) -> None:
        self.ensure_staff_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_staff_summary (
                    id, personal_total, personal_directo, personal_indirecto,
                    horas_por_persona, ausencias_previstas, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    1,
                    DEFAULT_STAFF_SUMMARY["personal_total"],
                    DEFAULT_STAFF_SUMMARY["personal_directo"],
                    DEFAULT_STAFF_SUMMARY["personal_indirecto"],
                    DEFAULT_STAFF_SUMMARY["horas_por_persona"],
                    DEFAULT_STAFF_SUMMARY["ausencias_previstas"],
                    DEFAULT_STAFF_SUMMARY["observaciones"],
                    now,
                ),
            )
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_staff_areas").fetchone()["n"]
            if existing == 0:
                conn.executemany(
                    """
                    INSERT INTO production_staff_areas (
                        area, tipo_personal, disponible, minimo_operativo, optimo, activo, observaciones, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [(*row, now) for row in DEFAULT_STAFF_AREAS],
                )

    def get_staff_summary(self) -> dict:
        self.ensure_staff_defaults()
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM production_staff_summary WHERE id = 1").fetchone()
        return dict(row) if row else {"id": 1, **DEFAULT_STAFF_SUMMARY}

    def save_staff_summary(self, data: dict) -> None:
        self.ensure_staff_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_staff_summary (
                    id, personal_total, personal_directo, personal_indirecto,
                    horas_por_persona, ausencias_previstas, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    personal_total=excluded.personal_total,
                    personal_directo=excluded.personal_directo,
                    personal_indirecto=excluded.personal_indirecto,
                    horas_por_persona=excluded.horas_por_persona,
                    ausencias_previstas=excluded.ausencias_previstas,
                    observaciones=excluded.observaciones,
                    updated_at=excluded.updated_at
                """,
                (
                    1,
                    data["personal_total"],
                    data["personal_directo"],
                    data["personal_indirecto"],
                    data["horas_por_persona"],
                    data["ausencias_previstas"],
                    data.get("observaciones", ""),
                    now,
                ),
            )

    def get_staff_areas(self) -> list[dict]:
        self.ensure_staff_defaults()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM production_staff_areas ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def save_staff_areas(self, rows: list[dict]) -> None:
        self.ensure_staff_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_staff_areas")
            conn.executemany(
                """
                INSERT INTO production_staff_areas (
                    area, tipo_personal, disponible, minimo_operativo, optimo, activo, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["area"],
                        row["tipo_personal"],
                        int(row["disponible"]),
                        int(row["minimo_operativo"]),
                        int(row["optimo"]),
                        int(row["activo"]),
                        row.get("observaciones", ""),
                        now,
                    )
                    for row in rows
                ],
            )

    def reset_staff_defaults(self) -> None:
        self.ensure_staff_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_staff_areas")
            conn.executemany(
                """
                INSERT INTO production_staff_areas (
                    area, tipo_personal, disponible, minimo_operativo, optimo, activo, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(*row, now) for row in DEFAULT_STAFF_AREAS],
            )
        self.save_staff_summary(DEFAULT_STAFF_SUMMARY)

    def delete_staff_area(self, area_id: int) -> None:
        self.ensure_staff_schema()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_staff_areas WHERE id = ?", (area_id,))
