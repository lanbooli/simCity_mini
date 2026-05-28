"""TTS API routes - on-demand voice generation for replay."""

import uuid

from fastapi import APIRouter

from src.api.schemas import ApiResponse, TtsGenerateRequest
from src.common.message_broker import RedisBroker

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])


@router.post("/generate")
async def tts_generate(req: TtsGenerateRequest):
    """Request TTS generation for arbitrary text. Returns request_id for tracking."""
    broker = RedisBroker()
    await broker.connect()
    try:
        request_id = str(uuid.uuid4())
        await broker.stream_add("stream:tts:requests", {
            "request_id": request_id,
            "npc_id": req.npc_id,
            "text": req.text,
            "mood": req.mood,
            "reply_to": "tts:chunk",
            "player_id": req.player_id,
        })
        return ApiResponse(data={"request_id": request_id, "status": "submitted"})
    finally:
        await broker.disconnect()
