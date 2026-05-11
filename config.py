from pathlib import Path
import logging

DB_DIR = r"\\Personal\C\BasesSQLite"
DB_PEDIDOS = "DBPedidos.sqlite"
DB_FRUTA = "DBfruta.sqlite"
DB_CALIDAD = "BdCalidad.sqlite"
DB_LOTEADO = r"\\Personal\C\BasesSQLite\bdloteado.sqlite"

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
