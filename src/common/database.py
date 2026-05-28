"""
SQLite database connection management and migration.
"""

from __future__ import annotations

import sqlite3
import os
from typing import Optional

from config.settings import settings


SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_db_path() -> str:
    """Resolve database path relative to project root."""
    if os.path.isabs(settings.database_path):
        return settings.database_path
    # Assume we're in city-town/ directory
    return settings.database_path


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Get a new SQLite connection with WAL mode and foreign keys enabled."""
    path = db_path or get_db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def run_migrations(db_path: Optional[str] = None) -> None:
    """Execute schema.sql to create all tables if they don't exist."""
    path = db_path or get_db_path()
    conn = get_connection(path)
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            sql = f.read()
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


def execute(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Cursor:
    """Execute a single SQL statement."""
    return conn.execute(sql, params)


def execute_many(conn: sqlite3.Connection, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
    """Execute a SQL statement with multiple parameter sets."""
    return conn.executemany(sql, params_list)


def fetch_one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Optional[dict]:
    """Fetch a single row as dict."""
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def fetch_all(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    """Fetch all rows as list of dicts."""
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
