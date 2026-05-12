from pathlib import Path
import logging

CENTRAL_SQLITE_DIR = r"\\Personal\C\BasesSQLite"
RUNTIME_SQLITE_DIR = r"C:\Sansebas AgroView\runtime_db"
RUNTIME_SNAPSHOT_FILE = str(Path(RUNTIME_SQLITE_DIR) / "snapshot_info.txt")

DB_PEDIDOS = "DBPedidos.sqlite"
DB_FRUTA = "DBfruta.sqlite"
DB_CALIDAD = "BdCalidad.sqlite"
DB_LOTEADO = "bdloteado.sqlite"
DB_EEPPL = "DBEEPPL.sqlite"
SQLITE_DATABASES = [DB_LOTEADO, DB_PEDIDOS, DB_FRUTA, DB_CALIDAD, DB_EEPPL]

DB_DIR = RUNTIME_SQLITE_DIR

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "app.log"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
