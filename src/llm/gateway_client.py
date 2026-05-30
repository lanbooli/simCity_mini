"""
GatewayClient: Library used by game processes to submit LLM requests
to the LLM Gateway via Redis streams.

Replaces direct LMStudioClient.chat() calls.
"""

import asyncio
import json
import uuid
import logging
_log = logging.getLogger("gateway_client")
from datetime import datetime, timedelta, timezone
from enum import IntEnum
from typing import Optional

from src.common.message_broker import RedisBroker


# ── Priority ──────────────────────────────────────

class Priority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BATCH = 4


# ── Token Budgets (max system chars per call type) ─

TOKEN_BUDGETS = {
    "player_dialogue": 4000,
    "player_action": 3500,
    "social_open": 1500,
    "social_reply": 1500,
    "greeting": 1000,
    "action_narrative": 1500,
    "confession": 2000,
    "proposal": 2000,
    "breakup": 2000,
    "violation": 2000,
    "inner_thought": 800,
    "post": 1000,
    "comment_reply": 800,
    "goal_eval": 1200,
    "social_performance": 1500,
}

# ── Priority Mapping ──────────────────────────────

PRIORITY_MAP = {
    "player_dialogue": Priority.CRITICAL,
    "player_action": Priority.CRITICAL,
    "social_open": Priority.HIGH,
    "social_reply": Priority.HIGH,
    "greeting": Priority.MEDIUM,
    "action_narrative": Priority.MEDIUM,
    "confession": Priority.MEDIUM,
    "proposal": Priority.MEDIUM,
    "breakup": Priority.MEDIUM,
    "violation": Priority.MEDIUM,
    "inner_thought": Priority.LOW,
    "post": Priority.LOW,
    "comment_reply": Priority.LOW,
    "goal_eval": Priority.BATCH,
    "social_performance": Priority.LOW,
}


# LLM Generation Parameters
# call_type -> {max_tokens, temperature}
# Main model (35B/thinking): generous max_tokens for quality
# Social model (4B/non-thinking): leaner for throughput
LLM_PARAMS = {
    "player_dialogue":    {"max_tokens": 4000, "temperature": 0.7},
    "player_action":      {"max_tokens": 4000, "temperature": 0.7},
    "confession":         {"max_tokens": 4000, "temperature": 0.8},
    "proposal":           {"max_tokens": 4000, "temperature": 0.8},
    "breakup":            {"max_tokens": 4000, "temperature": 0.8},
    "violation":          {"max_tokens": 4000, "temperature": 0.8},
    "social_open":        {"max_tokens": 2048, "temperature": 0.7},
    "social_reply":       {"max_tokens": 2048, "temperature": 0.7},
    "greeting":           {"max_tokens": 1024, "temperature": 0.8},
    "action_narrative":   {"max_tokens": 2048, "temperature": 0.8},
    "inner_thought":      {"max_tokens": 1024, "temperature": 0.5},
    "post":               {"max_tokens": 2048, "temperature": 0.8},
    "comment_reply":      {"max_tokens": 1024, "temperature": 0.8},
    "goal_eval":          {"max_tokens": 1024, "temperature": 0.5},
    "social_performance": {"max_tokens": 2048, "temperature": 0.8},
}

def get_llm_params(call_type):
    """(max_tokens, temperature) for a call type."""
    p = LLM_PARAMS.get(call_type, {})
    return p.get("max_tokens", 1024), p.get("temperature", 0.7)


# ── Context Trimming ──────────────────────────────

def trim_context(messages: list[dict], call_type: str) -> tuple[list[dict], bool]:
    """Trim messages to fit token budget. Primary trim, runs in caller process."""
    budget = TOKEN_BUDGETS.get(call_type, 3000)
    total = sum(len(m.get("content", "")) for m in messages)

    if total <= budget:
        return messages, False

    trimmed = False
    result = []
    for msg in messages:
        if msg["role"] == "system":
            content = msg["content"]
            if len(content) > budget:
                keep_head = budget * 3 // 4
                keep_tail = budget // 4
                content = content[:keep_head] + "\n\n[...内容已截断以控制token数量...]\n\n" + content[-keep_tail:]
                trimmed = True
            result.append({"role": "system", "content": content})
        else:
            result.append(msg)
    return result, trimmed


# ── Gateway Client ────────────────────────────────

class GatewayError(Exception):
    pass


# ── Stream routing: player vs NPC ───────────────────

PLAYER_STREAM = "stream:llm:player"
NPC_STREAM = "stream:llm:npc"

# Call types that go to the player-dedicated stream
PLAYER_CALL_TYPES = {
    "player_dialogue", "player_action",
    "confession", "proposal", "breakup", "violation",
    "greeting", "action_narrative",
}


def _stream_for(call_type: str) -> str:
    """Route call_type to the appropriate Redis stream."""
    return PLAYER_STREAM if call_type in PLAYER_CALL_TYPES else NPC_STREAM


class GatewayClient:
    """Sends LLM requests to the Gateway via Redis stream, awaits response via pub/sub."""

    REQUEST_STREAM = "stream:llm:requests"  # deprecated, kept for compat

    def __init__(self, broker: RedisBroker):
        self._broker = broker
        self._pending: dict[str, asyncio.Future] = {}
        self._listener_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def submit(
        self, *,
        priority: Priority,
        call_type: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 256,
        stop: list[str] | None = None,
        timeout: float = 120.0,
    ) -> str:
        """Submit request to gateway and await response. Raises GatewayError on failure."""
        request_id = str(uuid.uuid4())
        reply_channel = f"llm:response:{request_id}"

        # Trim context before queuing
        messages, _ = trim_context(messages, call_type)

        # Create future for response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        # Ensure listener is running
        await self._ensure_listener()

        # Subscribe to reply channel
        await self._broker.subscribe(reply_channel, self._make_handler(request_id, future))

        try:
            # Add request to appropriate stream (player vs NPC)
            stream = _stream_for(call_type)
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=timeout)).isoformat()
            await self._broker.stream_add(stream, {
                "request_id": request_id,
                "priority": str(priority.value),
                "call_type": call_type,
                "messages_json": json.dumps(messages, ensure_ascii=False),
                "temperature": str(temperature),
                "max_tokens": str(max_tokens),
                "stop_json": json.dumps(stop) if stop else "",
                "reply_to": reply_channel,
                "expires_at": expires_at,
            })

            # Await response
            result = await asyncio.wait_for(future, timeout=timeout)
            _log.info("[CLI %s] response status=%s len=%d",
                       request_id[:8], result.get("status", "?"),
                       len(result.get("content", "")))
            if result["status"] != "success":
                raise GatewayError(result.get("error", "Unknown gateway error"))
            return result["content"]

        except asyncio.TimeoutError:
            raise GatewayError(f"LLM gateway request timed out after {timeout}s")
        finally:
            self._pending.pop(request_id, None)
            try:
                await self._broker._pubsub.unsubscribe(reply_channel)
            except Exception:
                pass

    def _make_handler(self, request_id: str, future: asyncio.Future):
        """Create a pub/sub handler for a specific request."""
        async def handler(data: dict):
            if future.done():
                return
            future.set_result(data)
        return handler

    async def _ensure_listener(self):
        pass  # RedisBroker.subscribe already sets up the listener


# ── Global Instance ───────────────────────────────

_gateway_client: Optional[GatewayClient] = None
_init_broker: Optional[RedisBroker] = None


def init_gateway_client(broker: RedisBroker):
    """Initialize the global GatewayClient with a broker instance."""
    global _gateway_client, _init_broker
    _gateway_client = GatewayClient(broker)
    _init_broker = broker


def get_gateway_client() -> GatewayClient:
    """Get the global GatewayClient. Falls back to None if not initialized."""
    return _gateway_client
