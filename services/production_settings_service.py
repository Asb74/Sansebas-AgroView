from __future__ import annotations

from db.production_settings_repository import ProductionSettingsRepository


class ProductionSettingsService:
    def __init__(self, repository: ProductionSettingsRepository | None = None) -> None:
        self.repository = repository or ProductionSettingsRepository()

    def get_general_settings(self) -> dict:
        return self.repository.get_general_settings()

    def save_general_settings(self, data: dict) -> None:
        self.repository.save_general_settings(data)

    def reset_general_defaults(self) -> None:
        self.repository.reset_general_defaults()
