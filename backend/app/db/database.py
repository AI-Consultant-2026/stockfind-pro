"""SQLite connection management for StockFind Pro.

SQLite is used for the MVP because it needs zero setup and the whole
simulated universe (~70 stocks x 10 years daily bars + fundamentals) fits
comfortably in a single file. The data-access layer here is intentionally
thin — engines never write raw SQL themselves, they go through
`data_providers`, so swapping SQLite for Postgres later is a one-file change.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "stockfind.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(reset: bool = False):
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    conn = get_connection()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    return DB_PATH
