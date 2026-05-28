"""Pydantic request/response schemas for the API."""

from typing import Optional
from pydantic import BaseModel, Field


# ── Response envelope ──────────────────────────────

class ApiResponse(BaseModel):
    status: str = "ok"
    data: Optional[dict | list] = None
    error: Optional[str] = None


# ── Dialogue ───────────────────────────────────────

class DialogueRequest(BaseModel):
    player_id: str
    npc_id: str
    content: str


class DialogueResponse(BaseModel):
    msg_id: str
    status: str = "sent"


# ── Player ─────────────────────────────────────────

class PlayerCreate(BaseModel):
    name: str
    birth_date: str = "2000-01-01"
    gender: str = "other"
    appearance: dict = {}
    personality: list[str] = []
    career: str = ""


class PlayerUpdate(BaseModel):
    name: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    appearance: Optional[dict] = None
    personality: Optional[list[str]] = None
    career: Optional[str] = None


# ── Memory Search ──────────────────────────────────

class MemorySearchRequest(BaseModel):
    query: str
    npc_id: str = ""
    top_k: int = 5


# ── TTS ────────────────────────────────────────────

class TtsGenerateRequest(BaseModel):
    npc_id: str
    text: str
    player_id: str = "player_001"
    mood: str = "neutral"


# ── Relationship ───────────────────────────────────

class RelationshipUpdate(BaseModel):
    favorability: Optional[int] = None
    familiarity: Optional[int] = None
    relationship_type: Optional[str] = None


class RelationshipSummary(BaseModel):
    entity_b_id: str
    entity_b_name: str = ""
    relationship_type: str
    favorability: int
    familiarity: int
    interaction_count: int
