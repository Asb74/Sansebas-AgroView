from typing import Any

from db.forfait_repository import ForfaitRepository


class ForfaitService:
    def __init__(self, repository: ForfaitRepository | None = None) -> None:
        self.repository = repository or ForfaitRepository()

    def import_forfait_excel(
        self,
        file_path: str,
        cultivo: str,
        campana: str,
        sheet_name: str = "NARANJA",
    ) -> tuple[int, int, list[dict[str, Any]]]:
        return self.repository.import_forfait_excel(file_path, cultivo, campana, sheet_name)

    def fetch_excel_sheet_names(self, file_path: str) -> list[str]:
        return self.repository.fetch_excel_sheet_names(file_path)

    def validate_related_forfait_sheet(self, file_path: str, sheet_name: str) -> tuple[bool, list[str], list[str]]:
        return self.repository.validate_related_forfait_sheet(file_path, sheet_name)

    def import_related_forfait_excel(self, file_path: str, sheet_name: str) -> dict[str, Any]:
        return self.repository.import_related_forfait_excel(file_path, sheet_name)

    def fetch_related_forfait(self, cultivo: str | None = None, campana: str | None = None) -> list[dict[str, Any]]:
        return self.repository.fetch_related_forfait(cultivo, campana)

    def update_related_forfait_field(self, id_forfait: int, field_name: str, value: Any) -> dict[str, Any]:
        return self.repository.update_related_forfait_field(id_forfait, field_name, value)

    def reset_related_forfait(self, cultivo: str, campana: str) -> int:
        return self.repository.reset_related_forfait(cultivo, campana)

    def fetch_forfaits(self, cultivo: str, campana: str) -> list[dict[str, Any]]:
        return self.repository.fetch_forfaits(cultivo, campana)

    def fetch_mapping_rows(self, cultivo: str, campana: str) -> list[dict[str, Any]]:
        return self.repository.fetch_mapping_rows(cultivo, campana)

    def reset_mapping_rows(self, cultivo: str, campana: str) -> int:
        return self.repository.reset_mapping_rows(cultivo, campana)

    def fetch_coverage_rows(self, cultivo: str, campana: str, only_missing: bool = False) -> list[dict[str, Any]]:
        return self.repository.fetch_coverage_rows(cultivo, campana, only_missing)

    def update_forfait_field(self, id_forfait: int, field_name: str, value: Any) -> dict[str, Any]:
        return self.repository.update_forfait_field(id_forfait, field_name, value)

    def update_forfait_row(self, id_forfait: int, data: dict[str, Any]) -> dict[str, Any]:
        return self.repository.update_forfait_row(id_forfait, data)

    def regenerate_forfait_key(self, row: dict[str, Any]) -> str:
        return self.repository.regenerate_forfait_key(row)

    def validate_unique_forfait_key(
        self,
        cultivo: str,
        campana: str,
        clave_forfait: str,
        exclude_id: int | None = None,
    ) -> bool:
        return self.repository.validate_unique_forfait_key(cultivo, campana, clave_forfait, exclude_id)

    def update_equivalence(
        self,
        cultivo: str,
        campana: str,
        confeccion_pedido: str,
        clave_forfait: str,
        estado: str,
        observaciones: str = "",
    ) -> None:
        self.repository.update_equivalence(
            cultivo,
            campana,
            confeccion_pedido,
            clave_forfait,
            estado,
            observaciones,
        )

    def format_forfait_option(self, row: dict[str, Any]) -> str:
        return self.repository.format_forfait_option(row)

    def format_forfait_label(self, row: dict[str, Any]) -> str:
        return self.repository.format_forfait_label(row)
