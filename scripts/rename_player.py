"""
Migration: rename default player from "玩家" to a real name.
Run this to fix LLM hallucinating wrong names.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.database import get_connection, execute, fetch_one

def migrate(new_name: str = "新居民"):
    """Rename the default player. Usage: python scripts/rename_player.py 你的名字"""
    if len(sys.argv) > 1:
        new_name = sys.argv[1]
    
    conn = get_connection()
    try:
        row = fetch_one(conn, "SELECT id, name FROM player WHERE id = 'player_001'")
        if not row:
            print("Player not found!")
            return
        old_name = row["name"]
        if old_name == new_name:
            print(f"Name already set to '{new_name}', nothing to do.")
            return
        execute(conn, "UPDATE player SET name = ? WHERE id = 'player_001'", (new_name,))
        conn.commit()
        print(f"Player renamed: '{old_name}' → '{new_name}'")
        print("Restart the game for changes to take effect.")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
