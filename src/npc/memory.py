"""
NPC memory system. Short-term (recent ~20) and long-term (up to 200).
Important memories are promoted from short-term to long-term.
"""

from typing import Optional
from src.common.database import get_connection, execute, fetch_all
from src.common.models import gen_id


class MemoryManager:
    def __init__(self, npc_id: str):
        self.npc_id = npc_id
        self._short_term: list[dict] = []
        self._short_term_limit = 20
        self._long_term_limit = 200

    def load_recent(self, db_path: str = "", limit: int = 20):
        """Load recent memories from database."""
        conn = get_connection(db_path)
        try:
            rows = fetch_all(conn,
                "SELECT * FROM memory WHERE entity_id = ? AND entity_type = 'npc' "
                "ORDER BY created_at DESC LIMIT ?",
                (self.npc_id, limit))
            self._short_term = [dict(r) for r in rows]
        finally:
            conn.close()

    def add(self, content: str, game_time: str, memory_type: str = "short_term",
            importance: int = 5, emotion: str = "", scene_id: str = "",
            related_entity_id: str = "", related_entity_type: str = "",
            db_path: str = "") -> dict:
        """Add a new memory. Returns the memory dict."""
        mem = {
            "id": gen_id(),
            "entity_id": self.npc_id,
            "entity_type": "npc",
            "memory_type": memory_type,
            "content": content,
            "related_entity_id": related_entity_id or None,
            "related_entity_type": related_entity_type or None,
            "importance": importance,
            "emotion": emotion or None,
            "scene_id": scene_id or None,
            "game_time": game_time,
        }

        # Persist to database
        conn = get_connection(db_path)
        try:
            execute(conn, """INSERT INTO memory(id, entity_id, entity_type, memory_type, content,
                           related_entity_id, related_entity_type, importance, emotion, scene_id, game_time)
                           VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (mem["id"], mem["entity_id"], mem["entity_type"], mem["memory_type"],
                     mem["content"], mem["related_entity_id"], mem["related_entity_type"],
                     mem["importance"], mem["emotion"], mem["scene_id"], mem["game_time"]))
            conn.commit()
        finally:
            conn.close()

        # Add to short-term, evict if needed
        self._short_term.insert(0, mem)
        while len(self._short_term) > self._short_term_limit:
            evicted = self._short_term.pop()
            # Promote important memories to long-term
            if evicted["importance"] >= 6:
                self._promote_to_long_term(evicted, db_path)

        return mem

    def _promote_to_long_term(self, mem: dict, db_path: str = ""):
        """Promote a short-term memory to long-term."""
        conn = get_connection(db_path)
        try:
            execute(conn,
                "UPDATE memory SET memory_type = 'long_term' WHERE id = ?",
                (mem["id"],))
            conn.commit()
        finally:
            conn.close()

        # Enforce long-term limit
        if self._count_long_term(db_path) > self._long_term_limit:
            self._evict_oldest_long_term(db_path)

    def _count_long_term(self, db_path: str = "") -> int:
        conn = get_connection(db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM memory WHERE entity_id = ? AND memory_type = 'long_term'",
                (self.npc_id,)).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    def _evict_oldest_long_term(self, db_path: str = ""):
        conn = get_connection(db_path)
        try:
            conn.execute(
                "DELETE FROM memory WHERE id IN "
                "(SELECT id FROM memory WHERE entity_id = ? AND memory_type = 'long_term' "
                "ORDER BY importance ASC, created_at ASC LIMIT 1)",
                (self.npc_id,))
            conn.commit()
        finally:
            conn.close()

    def get_recent(self, limit: int = 10) -> list[dict]:
        """Get recent short-term memories."""
        return self._short_term[:limit]

    def get_recent_formatted(self, limit: int = 5) -> str:
        """Get recent memories formatted for prompt injection."""
        memories = self.get_recent(limit)
        if not memories:
            return "（暂无最近记忆）"
        return "\n".join(
            f"- ({m['game_time']}) {m['content']}" for m in memories
        )

    async def consolidate_memories(self, game_time: str, llm_client=None):
        """Phase 5: Consolidate today's important memories into long-term at day end."""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM memory WHERE entity_id = ? AND entity_type = 'npc' "
                "AND memory_type = 'short_term' AND importance >= 5 "
                "ORDER BY created_at DESC LIMIT 20",
                (self.npc_id,)).fetchall()
            if not rows:
                return

            memories = [dict(r) for r in rows]
            if len(memories) < 3:
                return

            # Simple consolidation: tag high-importance as long_term
            for m in memories:
                if m["importance"] >= 7:
                    conn.execute(
                        "UPDATE memory SET memory_type = 'long_term' WHERE id = ?",
                        (m["id"],))
                elif m["importance"] <= 2:
                    conn.execute("DELETE FROM memory WHERE id = ?", (m["id"],))
            conn.commit()
        finally:
            conn.close()

    def get_recent_about(self, entity_id: str, limit: int = 5, db_path: str = "") -> list[dict]:
        """Get recent memories about a specific entity."""
        conn = get_connection(db_path)
        try:
            rows = fetch_all(conn,
                "SELECT * FROM memory WHERE entity_id = ? AND related_entity_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (self.npc_id, entity_id, limit))
            return [dict(r) for r in rows]
        finally:
            conn.close()
