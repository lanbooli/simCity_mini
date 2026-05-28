"""
Hybrid retriever: vector similarity search + SQLite metadata join.
"""

import asyncio
import logging

from src.rag.embeddings import encode_text
from src.rag.vector_store import search_similar
from src.common.database import get_connection, fetch_one

logger = logging.getLogger("rag.retriever")


async def retrieve_relevant_memories(
    query: str,
    player_id: str,
    npc_id: str = "",
    top_k: int = 5,
) -> list[dict]:
    """
    Retrieve player memories relevant to the query.
    Combines vector similarity with metadata filtering.

    Returns list of full memory records from SQLite.
    Non-blocking: runs embedding encoding in thread pool.
    Graceful degradation: returns empty list on failure.
    """
    try:
        # Encode query in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        query_embedding = await loop.run_in_executor(None, encode_text, query)

        # Build metadata filter
        metadata_filter = {"entity_id": player_id, "entity_type": "player"}
        if npc_id:
            metadata_filter["related_entity_id"] = npc_id

        # Vector search
        results = search_similar(query_embedding, top_k=top_k, filter_metadata=metadata_filter)

        # Join with SQLite for full memory records
        conn = get_connection()
        try:
            full_memories = []
            for r in results:
                row = fetch_one(conn,
                    "SELECT * FROM memory WHERE id = ? AND entity_id = ?",
                    (r["id"], player_id))
                if row:
                    mem = dict(row)
                    mem["_similarity"] = 1.0 - r.get("distance", 0)
                    full_memories.append(mem)
            return full_memories
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"RAG retrieval failed (non-fatal): {e}")
        return []


def retrieve_dialogue_history(player_id: str, npc_id: str,
                              limit: int = 10) -> list[dict]:
    """Retrieve recent dialogue history between player and NPC."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM dialogue WHERE "
            "(speaker_id = ? AND listener_id = ?) OR "
            "(speaker_id = ? AND listener_id = ?) "
            "ORDER BY created_at DESC LIMIT ?",
            (player_id, npc_id, npc_id, player_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
