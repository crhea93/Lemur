import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BASE_DIR / "data"
DATA_DIR = Path(os.getenv("LEMUR_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser()
DB_PATH = Path(os.getenv("LEMUR_DB_PATH", str(DATA_DIR / "lemur.db"))).expanduser()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
