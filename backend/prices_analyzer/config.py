import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = BACKEND_DIR / "db" / "offers.sqlite3"
BOOKS_URL = "https://books.toscrape.com/"
HTTP_TIMEOUT = 15
HTTP_RETRIES = 2
REQUEST_PAUSE = 0.5


def database_path():
    return Path(os.environ.get("PRICES_ANALYZER_DB", DEFAULT_DB))
