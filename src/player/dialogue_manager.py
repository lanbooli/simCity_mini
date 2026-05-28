"""
Player dialogue manager. Orchestrates the full dialogue flow:
receives dialogue from API → routes to NPC → collects response → forwards to API.
"""

import asyncio
from src.common.message_broker import RedisBroker
from src.common.utils import game_time_to_str
from src.common.database import get_connection, fetch_one
from src.player.memory import PlayerMemory
from src.rag.retriever import retrieve_relevant_memories


class PlayerDialogueManager:
    def __init__(self, broker: RedisBroker, player_id: str):
        self.broker = broker
        self.player_id = player_id
        self.player_name = "玩家"
        self.player_attrs: str = '{"stamina":5,"speed":5,"strength":5}'
        self.memory = PlayerMemory(player_id)

    async def handle_dialogue_request(self, fields: dict) -> str:
        """
        Process a dialogue request from the frontend.
        Returns the msg_id for tracking.
        """
        npc_id = fields.get("npc_id", "")
        content = fields.get("content", "")
        game_time = fields.get("game_time", "")

        if not npc_id or not content:
            return ""

        # Build context with RAG-retrieved memories
        context = await self._build_context(npc_id, content)

        # Forward to NPC's dialogue stream (with player attributes)
        msg_id = await self.broker.stream_add(f"stream:dialogue:{npc_id}", {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "content": content,
            "game_time": game_time,
            "context": context,
            "player_attrs": self.player_attrs,
        })

        # Record player-side memory
        self.memory.add_memory(
            content=f"我对{npc_id}说: {content[:200]}",
            game_time=game_time,
            related_entity_id=npc_id,
            related_entity_type="npc",
            importance=3,
        )

        return msg_id

    async def _build_context(self, npc_id: str, query: str) -> str:
        """Build context for NPC dialogue using RAG memory retrieval."""
        memories = await retrieve_relevant_memories(
            query=query,
            player_id=self.player_id,
            npc_id=npc_id,
            top_k=5,
        )
        if not memories:
            return ""
        lines = []
        for m in memories:
            similarity = m.get("_similarity", 0)
            lines.append(f"- [相似度:{similarity:.2f}] ({m.get('game_time', '')}) {m['content'][:100]}")
        return "\n".join(lines)

    async def handle_dialogue_response(self, fields: dict):
        """
        Process NPC's dialogue response.
        Records memory and prepares for forwarding to API.
        """
        npc_id = self._decode(fields, "npc_id")
        npc_name = self._decode(fields, "npc_name")
        content = self._decode(fields, "content")
        favorability_change = int(self._decode(fields, "favorability_change", "0"))
        game_time = self._decode(fields, "game_time")
        audio_url = self._decode(fields, "audio_url", "")
        initiated_by_npc = self._decode(fields, "initiated_by_npc", "")
        action_name = self._decode(fields, "action_name", "")

        if not content or not npc_id:
            return

        # Record player memory of NPC's response
        self.memory.add_memory(
            content=f"{npc_name}({npc_id})对我说: {content[:200]}",
            game_time=game_time,
            memory_type="short_term",
            related_entity_id=npc_id,
            related_entity_type="npc",
            importance=max(3, abs(favorability_change) + 2),
            emotion="joy" if favorability_change > 0 else ("anger" if favorability_change < -1 else ""),
        )

        # Look up relationship to include favorability_after etc. for frontend display
        rel_data = {}
        try:
            conn = get_connection()
            row = fetch_one(conn,
                "SELECT * FROM relationship WHERE entity_a_id = ? AND entity_a_type = 'npc' "
                "AND entity_b_id = ? AND entity_b_type = 'player'",
                (npc_id, self.player_id))
            if row:
                rel_data = dict(row)
            conn.close()
        except Exception:
            pass

        # Forward response to API via Redis pub/sub — include all fields
        await self.broker.publish("dialogue:response", {
            "player_id": self.player_id,
            "npc_id": npc_id,
            "npc_name": npc_name,
            "content": content,
            "favorability_change": str(favorability_change),
            "favorability_before": rel_data.get("favorability", 0),
            "favorability_after": rel_data.get("favorability", 0),
            "familiarity_after": rel_data.get("familiarity", 0),
            "mood_before": "",
            "new_mood": "",
            "relationship_type": rel_data.get("relationship_type", "stranger"),
            "game_time": game_time,
            "audio_url": audio_url,
            "initiated_by_npc": initiated_by_npc,
            "action_name": action_name,
        })

    @staticmethod
    def _decode(fields: dict, key: str, default: str = "") -> str:
        """Decode a field from bytes or string key."""
        val = fields.get(key.encode() if isinstance(key, str) else key, fields.get(key, default))
        if isinstance(val, bytes):
            return val.decode("utf-8")
        return str(val) if val is not None else default
