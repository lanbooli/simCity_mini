"""
NPC perception module. Queries Redis for entities present in the same scene.
"""

from dataclasses import dataclass, field


@dataclass
class PerceivedEntity:
    id: str
    entity_type: str  # 'npc' or 'player'
    name: str = ""
    mood: str = "neutral"
    activity: str = ""
    in_dialogue: bool = False


@dataclass
class PerceptionData:
    scene_id: str
    scene_name: str = ""
    scene_type: str = "indoor"
    game_time: dict = field(default_factory=dict)
    weather: str = "sunny"
    npcs_present: list[PerceivedEntity] = field(default_factory=list)
    players_present: list[PerceivedEntity] = field(default_factory=list)

    @property
    def all_entities(self) -> list[PerceivedEntity]:
        return self.npcs_present + self.players_present

    @property
    def other_npc_ids(self) -> set[str]:
        return {e.id for e in self.npcs_present}


class Perception:
    """Gathers perceptual data for an NPC from Redis state."""

    def __init__(self, npc_id: str, broker):
        self.npc_id = npc_id
        self.broker = broker
        self._player_name_cache: str | None = None

    async def perceive(
        self, scene_id: str, scene_name: str = "", scene_type: str = "indoor",
        game_time: dict | None = None, weather: str = "sunny",
    ) -> PerceptionData:
        data = PerceptionData(
            scene_id=scene_id,
            scene_name=scene_name,
            scene_type=scene_type,
            game_time=game_time or {},
            weather=weather,
        )

        # Query scene NPC list
        scene_state = await self.broker.kv_get(f"state:scene:{scene_id}:npcs")
        npc_ids: list[str] = []
        if scene_state and isinstance(scene_state, dict):
            npc_ids = scene_state.get("npcs", [])
        elif scene_state and isinstance(scene_state, str):
            import json
            try:
                npc_ids = json.loads(scene_state).get("npcs", [])
            except Exception:
                npc_ids = []

        for eid in npc_ids:
            if eid == self.npc_id:
                continue
            entity_state = await self.broker.kv_get(f"state:npc:{eid}")
            if entity_state and isinstance(entity_state, dict):
                data.npcs_present.append(PerceivedEntity(
                    id=eid,
                    entity_type="npc",
                    name=entity_state.get("name", eid),
                    mood=entity_state.get("mood", "neutral"),
                    activity=entity_state.get("current_activity", ""),
                    in_dialogue=entity_state.get("in_dialogue", False),
                ))

        # Check for player in scene
        player_state = await self.broker.kv_get("state:player:player_001:location")
        if player_state and isinstance(player_state, dict):
            if player_state.get("scene_id") == scene_id:
                # Read player name from DB fresh each time (user may have changed it)
                try:
                    from src.common.database import get_connection, fetch_one
                    _conn = get_connection()
                    try:
                        _row = fetch_one(_conn, "SELECT name FROM player WHERE id = 'player_001'")
                        if _row and _row.get("name"):
                            self._player_name_cache = _row["name"]
                    finally:
                        _conn.close()
                except Exception:
                    pass
                _player_name = self._player_name_cache or "玩家" 
                data.players_present.append(PerceivedEntity(
                    id="player_001",
                    entity_type="player",
                    name=_player_name,
                ))

        return data
