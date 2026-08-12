"""SQLite connection management for StockFind Pro.

SQLite is used for the MVP because it needs zero setup and the whole
simulated universe (~70 stocks x 10 years daily bars + fundamentals) fits
comfortably in a single file. The data-access layer here is intentionally
thin — engines never write raw SQL themselves, they go through
`data_providers`, so swapping SQLite for Postgres later is a one-file change.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# DB_DIR points at a Render persistent Disk's mount path in production (set via
# the DB_DIR env var) so the database — accounts included — survives redeploys.
# Unset locally, so local dev keeps writing next to the backend package as before.
DB_DIR = Path(os.environ["DB_DIR"]) if os.environ.get("DB_DIR") else Path(__file__).resolve().parent.parent.parent
DB_PATH = DB_DIR / "stockfind.db"
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


def log_activity(user_id: int | None, event_type: str, detail: str | None = None):
    with session() as conn:
        conn.execute(
            "INSERT INTO activity_log (user_id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
            (user_id, event_type, detail, datetime.now(timezone.utc).isoformat()),
        )
