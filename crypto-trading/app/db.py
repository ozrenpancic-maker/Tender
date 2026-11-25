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
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS ne dodaje nove stupce na već postojeću tablicu - ovo je za takve
    slučajeve (npr. `available_date` dodan u macro_series nakon što je tablica već postojala)."""
    try:
        conn.execute("ALTER TABLE macro_series ADD COLUMN available_date TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # stupac već postoji
    try:
        # Default 1440 (dnevno) - postojeći runovi su svi bili dnevni prije ovog dodatka.
        conn.execute("ALTER TABLE paper_run ADD COLUMN interval_min INTEGER NOT NULL DEFAULT 1440")
    except sqlite3.OperationalError:
        pass  # stupac već postoji
    for ddl in [
        "ALTER TABLE auto_trader_run ADD COLUMN trade_mode TEXT NOT NULL DEFAULT 'scalp'",
        "ALTER TABLE auto_trader_run ADD COLUMN min_hold_periods INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE auto_trader_run ADD COLUMN take_profit_pct REAL",
        "ALTER TABLE auto_trader_run ADD COLUMN stop_loss_pct REAL",
        "ALTER TABLE paper_run ADD COLUMN execution_mode TEXT NOT NULL DEFAULT 'taker'",
        "ALTER TABLE paper_run ADD COLUMN pending_side TEXT",
        "ALTER TABLE paper_run ADD COLUMN pending_limit_price REAL",
        "ALTER TABLE paper_run ADD COLUMN pending_posted_at INTEGER",
        "ALTER TABLE paper_run ADD COLUMN pending_ticks INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE paper_run ADD COLUMN daily_loss_limit_pct REAL",
        "ALTER TABLE paper_run ADD COLUMN day_start_equity REAL",
        "ALTER TABLE paper_run ADD COLUMN day_start_date TEXT",
        "ALTER TABLE paper_run ADD COLUMN daily_halted INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # stupac već postoji
