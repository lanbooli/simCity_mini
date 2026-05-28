#!/usr/bin/env python3
"""Migration: add social_post, social_like, social_comment tables."""
import sqlite3, os, sys

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "city_town.db")

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}, skipping.")
    sys.exit(0)

conn = sqlite3.connect(db_path)
try:
    existing = set()
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        existing.add(row[0])

    if "social_post" not in existing:
        conn.execute("""CREATE TABLE IF NOT EXISTS social_post (
            id TEXT PRIMARY KEY, author_id TEXT NOT NULL, author_type TEXT NOT NULL,
            content TEXT NOT NULL, post_type TEXT NOT NULL DEFAULT 'general',
            visibility TEXT NOT NULL DEFAULT 'public',
            scene_id TEXT, mood TEXT, related_entity_id TEXT,
            game_time TEXT NOT NULL DEFAULT '',
            like_count INTEGER NOT NULL DEFAULT 0, comment_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')))""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_post_author ON social_post(author_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_post_time ON social_post(created_at)")
        print("Created social_post table.")

    if "social_like" not in existing:
        conn.execute("""CREATE TABLE IF NOT EXISTS social_like (
            id TEXT PRIMARY KEY, post_id TEXT NOT NULL, user_id TEXT NOT NULL,
            user_type TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(post_id, user_id, user_type))""")
        print("Created social_like table.")

    if "social_comment" not in existing:
        conn.execute("""CREATE TABLE IF NOT EXISTS social_comment (
            id TEXT PRIMARY KEY, post_id TEXT NOT NULL, author_id TEXT NOT NULL,
            author_type TEXT NOT NULL, content TEXT NOT NULL,
            game_time TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')))""")
        print("Created social_comment table.")

    conn.commit()
    print("Migration complete.")
finally:
    conn.close()
