"""Spajanje na SQLite bazu i inicijalizacija dodatnih tablica (iznad postojeće povijesne sheme)."""
import sqlite3
from pathlib import Path

from app.config import DB_PATH

EXTRA_SCHEMA = Path(__file__).resolve().parent.parent / "data" / "schema_extra.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema() -> None:
    conn = get_connection()
    try:
        conn.executescript(EXTRA_SCHEMA.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
