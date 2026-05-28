"""
WebSocket manager. Bridges Redis pub/sub messages to browser WebSocket connections.
"""

import asyncio
import json
from typing import Optional
from fastapi import WebSocket

from src.common.message_broker import RedisBroker


def _ALL_NPC_IDS():
    base = ["npc_li_ming", "npc_wang_fang", "npc_zhang_wei", "npc_chen_xue", "npc_liu_jie"]
    photos = [f"npc_photo_{i:02d}" for i in range(1, 14)]
    return base + photos


class WSManager:
    def __init__(self, broker: RedisBroker):
        self.broker = broker
        self._connections: dict[str, WebSocket] = {}  # player_id -> WS
        self._listening = False

    async def connect(self, player_id: str, ws: WebSocket):
        await ws.accept()
        self._connections[player_id] = ws
        if not self._listening:
            self._listening = True
            asyncio.create_task(self._subscribe_channels())

    def disconnect(self, player_id: str):
        self._connections.pop(player_id, None)

    async def send_to_player(self, player_id: str, message: dict):
        ws = self._connections.get(player_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(player_id)

    async def broadcast(self, message: dict):
        disconnected = []
        for pid, ws in self._connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(pid)
        for pid in disconnected:
            self.disconnect(pid)

    async def _subscribe_channels(self):
        """Subscribe to Redis channels and fan out to WebSocket clients."""
        # Time updates → broadcast
        await self.broker.subscribe("system:time", self._on_time)
        # Weather updates → broadcast
        await self.broker.subscribe("system:weather", self._on_weather)
        # Events → broadcast
        await self.broker.subscribe("system:events", self._on_event)
        # Scene updates → broadcast (public + home scenes)
        for sid in ["scene_coffee_shop", "scene_park", "scene_school", "scene_library", "scene_market",
                     "apt_a", "apt_b", "apt_c", "apt_d", "home_player"]:
            await self.broker.subscribe(f"scene:{sid}:update", self._on_scene_update)

        # NPC state updates → broadcast - all 18 NPCs
        for nid in _ALL_NPC_IDS():
            await self.broker.subscribe(f"npc:{nid}:state", self._on_npc_state)

        # Dialogue responses → specific player
        await self.broker.subscribe("dialogue:response", self._on_dialogue_response)
        # TTS audio chunks → specific player
        await self.broker.subscribe("tts:chunk", self._on_tts_chunk)
        # Social events (NPC↔NPC, NPC→player, inner thoughts) → broadcast
        await self.broker.subscribe("system:social_event", self._on_social_event)

    async def _on_time(self, data: dict):
        await self.broadcast({"type": "time_update", "data": data})

    async def _on_weather(self, data: dict):
        await self.broadcast({"type": "weather_update", "data": data})

    async def _on_event(self, data: dict):
        await self.broadcast({"type": "event_announce", "data": data})

    async def _on_scene_update(self, data: dict):
        await self.broadcast({"type": "scene_update", "data": data})

    async def _on_npc_state(self, data: dict):
        await self.broadcast({"type": "npc_state_update", "data": data})

    async def _on_dialogue_response(self, data: dict):
        player_id = data.get("player_id", "")
        if player_id:
            await self.send_to_player(player_id, {
                "type": "dialogue_response",
                "data": {
                    "npc_id": data.get("npc_id"),
                    "npc_name": data.get("npc_name"),
                    "content": data.get("content"),
                    "favorability_change": data.get("favorability_change"),
                    "favorability_before": data.get("favorability_before"),
                    "favorability_after": data.get("favorability_after"),
                    "familiarity_after": data.get("familiarity_after"),
                    "mood_before": data.get("mood_before"),
                    "new_mood": data.get("new_mood"),
                    "relationship_type": data.get("relationship_type"),
                    "game_time": data.get("game_time"),
                    "audio_url": data.get("audio_url", ""),
                    "initiated_by_npc": data.get("initiated_by_npc", ""),
                    "action_name": data.get("action_name", ""),
                },
            })
        else:
            await self.broadcast({"type": "dialogue_response", "data": data})

    async def _on_tts_chunk(self, data: dict):
        player_id = data.get("player_id", "")
        await self.send_to_player(player_id, {
            "type": "tts_audio",
            "data": {
                "request_id": data.get("request_id"),
                "npc_id": data.get("npc_id", ""),
                "chunk_index": data.get("chunk_index"),
                "total_chunks": data.get("total_chunks"),
                "audio_url": data.get("audio_url"),
                "text": data.get("text", ""),
                "is_last": data.get("is_last", False),
            },
        })

    async def _on_social_event(self, data: dict):
        await self.broadcast({"type": "social_event", "data": data})
