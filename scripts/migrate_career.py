"""
Migration: add career column to npc table and set career values.
Does NOT destroy any existing data.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.database import get_connection, execute, fetch_all

CAREER_MAP = {
    "npc_li_ming": "咖啡店主",
    "npc_chen_xue": "图书管理员",
    "npc_liu_jie": "超市店主",
}

def migrate():
    conn = get_connection()
    try:
        # Check if career column already exists
        cols = fetch_all(conn, "PRAGMA table_info(npc)")
        col_names = [c["name"] for c in cols]
        
        if "career" not in col_names:
            print("Adding career column to npc table...")
            execute(conn, "ALTER TABLE npc ADD COLUMN career TEXT")
            print("  ✓ career column added")
        else:
            print("  career column already exists, skipping")
        
        # Update career values for NPCs
        for npc_id, career in CAREER_MAP.items():
            execute(conn, "UPDATE npc SET career = ? WHERE id = ?", (career, npc_id))
            print(f"  ✓ {npc_id} → {career}")
        
        conn.commit()
        print("\nMigration complete! No data was destroyed.")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
