from __future__ import annotations

from db.operational_quality_repository import DEFAULTS_PERCENT, OperationalQualityRepository


class OperationalQualityService:
    def __init__(self, repository: OperationalQualityRepository | None = None) -> None:
        self.repository = repository or OperationalQualityRepository()

    def ensure_defaults(self) -> None:
        self.repository.ensure_defaults()

    def get_settings(self) -> list[dict]:
        self.ensure_defaults()
        return self.repository.get_all()

    def save_settings(self, rows: list[dict]) -> None:
        self.repository.upsert_many(rows)

    def reset_defaults(self) -> None:
        self.repository.ensure_schema()
        self.repository.reset_defaults()

    def get_setting_for_origin(self, origen: str) -> dict:
        self.ensure_defaults()
        rows = self.repository.get_all()
        found = next((r for r in rows if r.get("Origen") == origen), None)
        if found:
            return found
        p1, p2, d, h, ir, a = DEFAULTS_PERCENT["DESCONOCIDO"]
        return {
            "Origen": "DESCONOCIDO",
            "PrimeraPct": p1 / 100.0,
            "SegundaPct": p2 / 100.0,
            "DestrioFallbackPct": d / 100.0,
            "UsarDestrioHistorico": h,
            "IndustriaRecuperablePct": ir / 100.0,
            "Activo": a,
        }
