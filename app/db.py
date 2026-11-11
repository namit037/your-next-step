"""Database setup: where the SQLite file lives, its schema, and connections."""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "occupations.db"

# One table for both countries. `country` is part of the key, so UK and US
# records never overlap. Fields that a source doesn't provide stay NULL.
SCHEMA = """
CREATE TABLE IF NOT EXISTS occupations (
    id          INTEGER PRIMARY KEY,
    country     TEXT NOT NULL CHECK (country IN ('UK', 'US')),
    code        TEXT NOT NULL,          -- official job code (SOC)
    title       TEXT NOT NULL,
    median_pay  REAL,                   -- median annual pay, in `currency`
    currency    TEXT NOT NULL,          -- 'GBP' or 'USD'
    growth_pct  REAL,                   -- projected employment change, percent
    education   TEXT,                   -- typical entry education (US only)
    employment  INTEGER,                -- number of jobs
    source      TEXT NOT NULL,          -- where the row came from
    UNIQUE (country, code)
);
CREATE INDEX IF NOT EXISTS idx_occupations_country_title
    ON occupations (country, title);
"""


def get_db_path() -> Path:
    """Path of the database file. Can be overridden with the DB_PATH env var."""
    return Path(os.environ.get("DB_PATH", DEFAULT_DB_PATH))


def connect(path: Path) -> sqlite3.Connection:
    """Open a connection whose rows can be read by column name."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the table and index if they don't exist yet."""
    conn.executescript(SCHEMA)
    conn.commit()
