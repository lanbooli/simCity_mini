"""
Player memory system with RAG integration.
Every interaction is stored and embeddable for future retrieval.
"""

from typing import Optional
from src.common.database import get_connection, execute, fetch_all, fetch_one
from src.common.models import gen_id
from src.rag.embeddings import encode_text
from src.rag.vector_store import add_memory, delete_memory


class PlayerMemory:
    def __init__(self, player_id: str):
        self.player_id = player_id

    def add_memory(self, content: str, game_time: str, memory_type: str = "short_term",
                   related_entity_id: str = "", related_entity_type: str = "",
                   importance: int = 5, emotion: str = "", scene_id: str = "",
                   embed: bool = True) -> dict:
        """Add a player memory with optional embedding."""
        mem = {
            "id": gen_id(),
            "entity_id": self.player_id,
            "entity_type": "player",
            "memory_type": memory_type,
            "content": content,
            "related_entity_id": related_entity_id or None,
            "related_entity_type": related_entity_type or None,
            "importance": importance,
            "emotion": emotion or None,
            "scene_id": scene_id or None,
            "game_time": game_time,
        }

        # Persist to SQLite
        conn = get_connection()
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

        # Embed and store in ChromaDB
        if embed:
            try:
                embedding = encode_text(content)
                add_memory(mem["id"], content, embedding, {
                    "entity_id": self.player_id,
                    "entity_type": "player",
                    "related_entity_id": related_entity_id or "",
                    "memory_type": memory_type,
                    "importance": importance,
                })
                # Record bridge
                conn = get_connection()
                try:
                    execute(conn,
                        "INSERT INTO memory_embedding(id, memory_id, chroma_id) VALUES(?, ?, ?)",
                        (gen_id(), mem["id"], mem["id"]))
                    conn.commit()
                finally:
                    conn.close()
            except Exception:
                pass  # Embedding failure is non-critical

        return mem

    def get_memories(self, limit: int = 20, offset: int = 0,
                     npc_id: str = "") -> list[dict]:
        """Get paginated player memories."""
        conn = get_connection()
        try:
            if npc_id:
                rows = fetch_all(conn,
                    "SELECT * FROM memory WHERE entity_id = ? AND related_entity_id = ? "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (self.player_id, npc_id, limit, offset))
            else:
                rows = fetch_all(conn,
                    "SELECT * FROM memory WHERE entity_id = ? "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (self.player_id, limit, offset))
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_memories_about_npc(self, npc_id: str, limit: int = 10) -> list[dict]:
        """Get recent memories about a specific NPC."""
        conn = get_connection()
        try:
            rows = fetch_all(conn,
                "SELECT * FROM memory WHERE entity_id = ? AND related_entity_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (self.player_id, npc_id, limit))
            return [dict(r) for r in rows]
        finally:
            conn.close()
