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

    def fetch_forfaits(self, cultivo: str, campana: str) -> list[dict[str, Any]]:
        return self.repository.fetch_forfaits(cultivo, campana)

    def fetch_mapping_rows(self, cultivo: str, campana: str) -> list[dict[str, Any]]:
        return self.repository.fetch_mapping_rows(cultivo, campana)

    def reset_mapping_rows(self, cultivo: str, campana: str) -> int:
        return self.repository.reset_mapping_rows(cultivo, campana)

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
