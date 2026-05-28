from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


# ── Enums ──────────────────────────────────────────────

ENTITY_TYPES = ("player", "npc")
SCENE_TYPES = ("indoor", "outdoor", "home")
SCENE_ROLES = ("worker", "visitor", "resident")
MEMORY_TYPES = ("short_term", "long_term", "life_event")
GOAL_TYPES = ("life", "work", "relationship")
GOAL_STATUSES = ("active", "completed", "abandoned")
EVENT_TYPES = ("global", "scene", "personal")
MOODS = ("happy", "neutral", "sad", "angry", "excited", "bored")
WEATHERS = ("sunny", "cloudy", "rainy", "stormy", "snowy")
RELATIONSHIP_TYPES = (
    "parent", "sibling", "child",
    "stranger", "acquaintance", "friend", "best_friend",
    "boyfriend", "girlfriend", "spouse",
    "dislike", "enemy",
)


# ── Data Models ────────────────────────────────────────

class Player(BaseModel):
    id: str = Field(default_factory=gen_id)
    name: str
    birth_date: str
    gender: str
    appearance: dict = {}
    personality: list[str] = []
    career: Optional[str] = None
    current_scene_id: Optional[str] = None
    home_scene_id: Optional[str] = None


class Npc(BaseModel):
    id: str = Field(default_factory=gen_id)
    name: str
    birth_date: str
    gender: str
    appearance: dict = {}
    clothing: dict = {}
    voice_type: str = "young cute girl"
    personality: list[str] = []
    current_scene_id: Optional[str] = None
    home_scene_id: Optional[str] = None
    current_mood: str = "neutral"
    current_activity: Optional[str] = None
    is_active: bool = True


class Scene(BaseModel):
    id: str = Field(default_factory=gen_id)
    name: str
    description: str = ""
    scene_type: str = "indoor"
    weather_affected: bool = True
    max_capacity: int = 20
    icon: str = ""
    rooms: list[dict] = []
    residents: list[str] = []


class Relationship(BaseModel):
    id: str = Field(default_factory=gen_id)
    entity_a_id: str
    entity_a_type: str  # 'player' | 'npc'
    entity_b_id: str
    entity_b_type: str  # 'player' | 'npc'
    relationship_type: str = "stranger"
    favorability: int = 0
    familiarity: int = 0
    interaction_count: int = 0
    last_interaction_at: Optional[str] = None


class Memory(BaseModel):
    id: str = Field(default_factory=gen_id)
    entity_id: str
    entity_type: str
    memory_type: str = "short_term"
    content: str
    related_entity_id: Optional[str] = None
    related_entity_type: Optional[str] = None
    importance: int = 5
    emotion: Optional[str] = None
    scene_id: Optional[str] = None
    game_time: str = ""


class Goal(BaseModel):
    id: str = Field(default_factory=gen_id)
    entity_id: str
    entity_type: str
    goal_type: str  # 'life' | 'work' | 'relationship'
    description: str
    priority: int = 5
    is_short_term: bool = True
    progress: float = 0.0
    status: str = "active"
    parent_goal_id: Optional[str] = None


class Dialogue(BaseModel):
    id: str = Field(default_factory=gen_id)
    speaker_id: str
    speaker_type: str
    listener_id: str
    listener_type: str
    content: str
    scene_id: Optional[str] = None
    game_time: str = ""
    favorability_change: int = 0


class GameEvent(BaseModel):
    id: str = Field(default_factory=gen_id)
    event_type: str
    scene_id: Optional[str] = None
    title: str
    description: str = ""
    start_game_time: str
    end_game_time: Optional[str] = None
    is_active: bool = True
    affected_entities: list[dict] = []


class Item(BaseModel):
    id: str = Field(default_factory=gen_id)
    scene_id: Optional[str] = None
    owner_npc_id: Optional[str] = None
    name: str
    description: str = ""
    item_type: str = "decoration"
    function: Optional[str] = None
    room_name: Optional[str] = None
    is_interactive: bool = False
    is_usable: bool = True


# ── Message Envelope ───────────────────────────────────

class Message(BaseModel):
    msg_id: str = Field(default_factory=gen_id)
    msg_type: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    source: dict = {}
    target: dict = {}
    payload: dict = {}
