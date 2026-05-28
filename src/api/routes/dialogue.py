"""Dialogue API routes."""

from fastapi import APIRouter, HTTPException
from src.api.schemas import ApiResponse, DialogueRequest
from src.common.database import get_connection, fetch_all
from src.common.models import gen_id
from src.common.utils import game_time_to_str

router = APIRouter(prefix="/api/v1/dialogue", tags=["dialogue"])


@router.post("")
async def send_dialogue(req: DialogueRequest):
    """Send a dialogue message to an NPC. Returns msg_id for tracking."""
    from src.common.message_broker import RedisBroker

    broker = RedisBroker()
    await broker.connect()
    try:
        msg_id = gen_id()
        # Get current game time from Redis
        game_time = await broker.kv_get("state:game_time")
        time_str = ""
        if game_time:
            time_str = game_time_to_str(
                game_time.get("day", 1),
                game_time.get("hour", 8),
                game_time.get("minute", 0),
            )

        await broker.stream_add("stream:dialogue:inbound", {
            "player_id": req.player_id,
            "npc_id": req.npc_id,
            "content": req.content,
            "game_time": time_str,
        })

        return ApiResponse(data={"msg_id": msg_id, "status": "sent"})
    finally:
        await broker.disconnect()


@router.get("/history/{player_id}/{npc_id}")
def get_dialogue_history(player_id: str, npc_id: str, limit: int = 50):
    conn = get_connection()
    try:
        rows = fetch_all(conn, """SELECT * FROM dialogue
                                WHERE (speaker_id = ? AND listener_id = ?)
                                   OR (speaker_id = ? AND listener_id = ?)
                                ORDER BY created_at ASC, rowid ASC LIMIT ?""",
                       (player_id, npc_id, npc_id, player_id, limit))
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()
