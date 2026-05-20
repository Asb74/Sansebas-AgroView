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

    def get_staff_summary(self) -> dict:
        return self.repository.get_staff_summary()

    def save_staff_summary(self, data: dict) -> None:
        self.repository.save_staff_summary(data)

    def get_staff_areas(self) -> list[dict]:
        return self.repository.get_staff_areas()

    def save_staff_areas(self, rows: list[dict]) -> None:
        self.repository.save_staff_areas(rows)

    def reset_staff_defaults(self) -> None:
        self.repository.reset_staff_defaults()

    def get_packaging_types(self) -> list[dict]:
        return self.repository.get_packaging_types()

    def save_packaging_types(self, rows: list[dict]) -> None:
        self.repository.save_packaging_types(rows)

    def reset_packaging_defaults(self) -> None:
        self.repository.reset_packaging_defaults()

    def get_lines(self) -> list[dict]:
        return self.repository.get_lines()

    def save_lines(self, rows: list[dict]) -> None:
        self.repository.save_lines(rows)

    def reset_lines_defaults(self) -> None:
        self.repository.reset_lines_defaults()

    def get_performance_rules(self) -> list[dict]:
        return self.repository.get_performance_rules()

    def save_performance_rules(self, rows: list[dict]) -> None:
        self.repository.save_performance_rules(rows)

    def reset_performance_defaults(self) -> None:
        self.repository.reset_performance_defaults()

    def get_penalty_rules(self) -> list[dict]:
        return self.repository.get_penalty_rules()

    def save_penalty_rules(self, rows: list[dict]) -> None:
        self.repository.save_penalty_rules(rows)

    def reset_penalty_defaults(self) -> None:
        self.repository.reset_penalty_defaults()


    def get_semaphore_rules(self) -> list[dict]:
        return self.repository.get_semaphore_rules()

    def save_semaphore_rules(self, rows: list[dict]) -> None:
        self.repository.save_semaphore_rules(rows)

    def reset_semaphore_defaults(self) -> None:
        self.repository.reset_semaphore_defaults()
