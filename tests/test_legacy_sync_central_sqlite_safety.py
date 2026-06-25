from pathlib import Path

import pytest

from services.legacy_sync_service import (
    CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE,
    LegacySyncService,
    is_central_sqlite_path,
)


def test_is_central_sqlite_path_detects_unc_central_children():
    assert is_central_sqlite_path(Path(r"\\Personal\C\BasesSQLite\DBPedidos.sqlite"))
    assert is_central_sqlite_path(Path(r"//Personal/C/BasesSQLite/DBfruta.sqlite"))
    assert not is_central_sqlite_path(Path(r"C:\Sansebas AgroView\runtime_db\DBPedidos.sqlite"))


def test_import_csv_to_sqlite_blocks_replacing_central_sqlite(tmp_path):
    service = LegacySyncService.__new__(LegacySyncService)
    csv_path = tmp_path / "pedidos.csv"
    csv_path.write_text("Id;Nombre\n1;Pedido\n", encoding="utf-8")

    with pytest.raises(PermissionError, match=CENTRAL_SQLITE_WRITE_BLOCK_MESSAGE):
        service._import_csv_to_sqlite(
            csv_path=csv_path,
            sqlite_path=Path(r"\\Personal\C\BasesSQLite\DBPedidos.sqlite"),
            table_name="Pedidos",
            mode="REEMPLAZAR_TABLA",
        )
