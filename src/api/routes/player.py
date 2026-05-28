"""Player API routes."""

from fastapi import APIRouter, HTTPException
from src.api.schemas import ApiResponse, PlayerCreate, PlayerUpdate
from src.common.database import get_connection, fetch_one, fetch_all, execute
from src.common.models import gen_id
from src.common.utils import jd
from src.rag.retriever import retrieve_relevant_memories

router = APIRouter(prefix="/api/v1/player", tags=["player"])


@router.post("")
def create_player(req: PlayerCreate):
    conn = get_connection()
    try:
        pid = f"player_{gen_id()}"
        execute(conn, """INSERT INTO player(id, name, birth_date, gender, appearance, personality, career)
                      VALUES(?, ?, ?, ?, ?, ?, ?)""",
                (pid, req.name, req.birth_date, req.gender,
                 jd(req.appearance), jd(req.personality), req.career))
        conn.commit()
        row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (pid,))
        return ApiResponse(data=dict(row))
    finally:
        conn.close()


@router.get("/{player_id}")
def get_player(player_id: str):
    conn = get_connection()
    try:
        row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (player_id,))
        if not row:
            raise HTTPException(404, "Player not found")
        return ApiResponse(data=dict(row))
    finally:
        conn.close()


@router.put("/{player_id}")
def update_player(player_id: str, req: PlayerUpdate):
    conn = get_connection()
    try:
        row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (player_id,))
        if not row:
            raise HTTPException(404, "Player not found")

        updates = {}
        if req.name is not None:
            updates["name"] = req.name
        if req.birth_date is not None:
            updates["birth_date"] = req.birth_date
        if req.gender is not None:
            updates["gender"] = req.gender
        if req.appearance is not None:
            updates["appearance"] = jd(req.appearance)
        if req.personality is not None:
            updates["personality"] = jd(req.personality)
        if req.career is not None:
            updates["career"] = req.career

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [player_id]
            execute(conn, f"UPDATE player SET {set_clause}, updated_at = datetime('now') WHERE id = ?", values)
            conn.commit()

        row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (player_id,))
        return ApiResponse(data=dict(row))
    finally:
        conn.close()


@router.get("/{player_id}/relationships")
def get_relationships(player_id: str):
    """Get how all NPCs feel about the player (NPC→Player direction)."""
    conn = get_connection()
    try:
        # Read NPC→Player direction — this is the NPC's perspective (favorability toward player)
        rows = fetch_all(conn, """SELECT r.*, n.name as entity_b_name FROM relationship r
                                LEFT JOIN npc n ON r.entity_a_id = n.id
                                WHERE r.entity_b_id = ? AND r.entity_b_type = 'player'
                                AND r.entity_a_type = 'npc'
                                ORDER BY r.favorability DESC""", (player_id,))
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()


@router.get("/{player_id}/memories")
def get_memories(player_id: str, npc_id: str = "", limit: int = 20, offset: int = 0):
    conn = get_connection()
    try:
        if npc_id:
            rows = fetch_all(conn,
                "SELECT * FROM memory WHERE entity_id = ? AND related_entity_id = ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (player_id, npc_id, limit, offset))
        else:
            rows = fetch_all(conn,
                "SELECT * FROM memory WHERE entity_id = ? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (player_id, limit, offset))
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()


@router.post("/{player_id}/memories/search")
async def search_memories(player_id: str, req: dict):
    query = req.get("query", "")
    npc_id = req.get("npc_id", "")
    top_k = req.get("top_k", 5)
    if not query:
        raise HTTPException(400, "query is required")
    memories = await retrieve_relevant_memories(query, player_id, npc_id, top_k)
    return ApiResponse(data=memories)


@router.get("/{player_id}/goals")
def get_goals(player_id: str):
    conn = get_connection()
    try:
        rows = fetch_all(conn,
            "SELECT * FROM goal WHERE entity_id = ? AND entity_type = 'player' AND status = 'active'",
            (player_id,))
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()


@router.get("/{player_id}/location")
async def get_location(player_id: str):
    """Get player's current location (scene, room). Reads from Redis."""
    from src.common.message_broker import RedisBroker
    broker = RedisBroker()
    await broker.connect()
    try:
        loc = await broker.kv_get(f"state:player:{player_id}:location")
        if loc:
            return ApiResponse(data=loc)
        # Fallback: read from DB
        conn = get_connection()
        try:
            row = fetch_one(conn,
                "SELECT p.current_scene_id, p.home_scene_id, s.name as scene_name, s.scene_type "
                "FROM player p LEFT JOIN scene s ON p.current_scene_id = s.id "
                "WHERE p.id = ?", (player_id,))
            if row:
                return ApiResponse(data={
                    "scene_id": row["current_scene_id"],
                    "scene_name": row.get("scene_name", ""),
                    "scene_type": row.get("scene_type", ""),
                    "home_scene_id": row.get("home_scene_id", ""),
                    "room_name": "",
                })
        finally:
            conn.close()
        return ApiResponse(data={"scene_id": "", "scene_name": "", "scene_type": "", "room_name": ""})
    finally:
        await broker.disconnect()
