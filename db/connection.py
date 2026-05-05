from pathlib import Path
import sqlite3
import logging

from config import DB_DIR, DB_PEDIDOS

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    return Path(DB_DIR) / DB_PEDIDOS


def db_exists() -> bool:
    return get_db_path().exists()


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as exc:
        logger.exception("Error al conectar con SQLite: %s", exc)
        raise
