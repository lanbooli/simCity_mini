"""
Migration: add Phase 4.0/8/9 relationship columns to existing databases.
Safe to run on new databases (columns may already exist from updated schema.sql).
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.database import get_connection, execute


MIGRATIONS = [
    "ALTER TABLE relationship ADD COLUMN intimacy_comfort INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE relationship ADD COLUMN love_eligible INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE relationship ADD COLUMN committed_since TEXT",
    "ALTER TABLE relationship ADD COLUMN married_since TEXT",
    "ALTER TABLE relationship ADD COLUMN jealousy_level INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE relationship ADD COLUMN breakup_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE relationship ADD COLUMN divorced INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE relationship ADD COLUMN violation_count INTEGER NOT NULL DEFAULT 0",
]


def migrate():
    conn = get_connection()
    try:
        existing = set()
        rows = conn.execute("PRAGMA table_info(relationship)").fetchall()
        for r in rows:
            existing.add(r["name"])

        for sql in MIGRATIONS:
            col_name = sql.split("ADD COLUMN ")[1].split(" ")[0]
            if col_name in existing:
                print(f"  SKIP {col_name} — already exists")
                continue
            try:
                execute(conn, sql)
                print(f"  ADDED {col_name}")
            except Exception as e:
                print(f"  ERROR adding {col_name}: {e}")

        conn.commit()
        print("Migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
