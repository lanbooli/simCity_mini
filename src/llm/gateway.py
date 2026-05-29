#!/usr/bin/env python3
"""
LLM Gateway: standalone process that manages all LLM requests.

Consumes requests from Redis stream, queues by priority, forwards to LM Studio
with max 8 concurrent workers, circuit breaker, retry, and graceful degradation.

Usage: python -m src.llm.gateway
"""

import asyncio
import json
import os
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

import redis.asyncio as aioredis

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from src.common.utils import setup_logging
from src.llm.lmstudio_client import LMStudioClient

logger = setup_logging("llm_gateway", settings.log_level)


# ── Priority ──────────────────────────────────────

class Priority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BATCH = 4


# ── Circuit Breaker ───────────────────────────────

class CircuitBreaker:
    """State machine protecting LM Studio from overload."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self._threshold = failure_threshold
        self._recovery = recovery_timeout
        self._failure_count = 0
        self._state = self.CLOSED
        self._last_failure = 0.0

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_open(self) -> bool:
        if self._state == self.CLOSED:
            return False
        if self._state == self.OPEN:
            if time.monotonic() - self._last_failure >= self._recovery:
                self._state = self.HALF_OPEN
                logger.info("Circuit breaker: OPEN → HALF_OPEN (probing)")
                return False
            return True
        return False  # HALF_OPEN

    def record_success(self):
        if self._state == self.HALF_OPEN:
            logger.info("Circuit breaker: HALF_OPEN → CLOSED (recovered)")
        self._state = self.CLOSED
        self._failure_count = 0

    def record_failure(self):
        self._failure_count += 1
        self._last_failure = time.monotonic()
        if self._state == self.HALF_OPEN or self._failure_count >= self._threshold:
            self._state = self.OPEN
            logger.warning(
                f"Circuit breaker: → OPEN ({self._failure_count} failures, "
                f"recovery in {self._recovery}s)"
            )


# ── Gateway Config ────────────────────────────────

@dataclass
class GatewayConfig:
    max_concurrent: int = 8
    player_workers: int = 2      # dedicated workers for player stream
    npc_workers: int = 6         # workers for NPC stream
    redis_url: str = "redis://localhost:6379"
    player_stream: str = "stream:llm:player"
    npc_stream: str = "stream:llm:npc"
    consumer_group: str = "gateway_group"
    # Provider config
    llm_provider: str = "lmstudio"  # "deepseek" | "lmstudio"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_main_model: str = "deepseek-v4-pro"
    deepseek_social_model: str = "deepseek-v4-flash"
    deepseek_main_thinking: bool = True  # v4-pro uses thinking mode for quality
    # LM Studio
    lmstudio_base_url: str = ""
    lmstudio_main_model: str = ""
    lmstudio_social_model: str = ""
    request_timeout: float = 120.0
    circuit_threshold: int = 5
    circuit_recovery: float = 30.0
    retry_max: int = 3
    retry_base_delay: float = 1.0
    poll_batch_size: int = 10
    poll_block_ms: int = 2000
    stale_timeout: float = 300.0


def _decode_fields(fields: dict) -> dict:
    """Decode bytes keys/values from Redis xreadgroup into str dict."""
    result = {}
    for k, v in fields.items():
        key = k.decode("utf-8") if isinstance(k, bytes) else k
        val = v.decode("utf-8") if isinstance(v, bytes) else v
        result[key] = val
    return result


# ── Token budget trimming (redundant safety net) ──

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


def _estimate_chars(messages: list[dict]) -> int:
    return sum(len(m.get("content", "")) for m in messages)


def _safety_trim(messages: list[dict], call_type: str) -> list[dict]:
    """Redundant safety trim in gateway (primary trim is in caller)."""
    budget = TOKEN_BUDGETS.get(call_type, 3000)
    total = _estimate_chars(messages)
    if total <= budget:
        return messages

    result = []
    for msg in messages:
        if msg["role"] == "system":
            content = msg["content"]
            if len(content) > budget:
                keep_head = budget * 3 // 4
                keep_tail = budget // 4
                content = content[:keep_head] + "\n\n[...已截断...]\n\n" + content[-keep_tail:]
            result.append({"role": "system", "content": content})
        else:
            result.append(msg)
    return result


# ── Gateway Worker ────────────────────────────────

class GatewayWorker:
    def __init__(self, cfg: GatewayConfig, circuit_breaker: CircuitBreaker):
        self.cfg = cfg
        self.cb = circuit_breaker
        self._main_client: Optional[LMStudioClient] = None
        self._social_client: Optional[LMStudioClient] = None
        self._resolve_provider()

    def _resolve_provider(self):
        """Determine base_url, model, api_key for main and social clients."""
        if self.cfg.llm_provider == "deepseek":
            self._main_base_url = self.cfg.deepseek_base_url
            self._main_model = self.cfg.deepseek_main_model
            self._main_thinking = self.cfg.deepseek_main_thinking
            self._social_base_url = self.cfg.deepseek_base_url
            self._social_model = self.cfg.deepseek_social_model
            self._social_thinking = False  # v4-flash no thinking for speed/cost
            self._api_key = self.cfg.deepseek_api_key
            logger.info("GatewayWorker using DeepSeek: main=%s (thinking=%s), social=%s",
                         self._main_model, self._main_thinking, self._social_model)
        else:
            self._main_base_url = self.cfg.lmstudio_base_url
            self._main_model = self.cfg.lmstudio_main_model
            self._main_thinking = False
            self._social_base_url = self.cfg.lmstudio_base_url
            self._social_model = self.cfg.lmstudio_social_model
            self._social_thinking = False
            self._api_key = ""
            logger.info("GatewayWorker using LM Studio: main=%s, social=%s",
                         self._main_model, self._social_model)

    @property
    def main_client(self) -> LMStudioClient:
        if self._main_client is None:
            self._main_client = LMStudioClient(
                base_url=self._main_base_url,
                model=self._main_model,
                api_key=self._api_key,
                timeout=self.cfg.request_timeout,
            )
        return self._main_client

    @property
    def social_client(self) -> LMStudioClient:
        if self._social_client is None:
            self._social_client = LMStudioClient(
                base_url=self._social_base_url,
                model=self._social_model,
                api_key=self._api_key,
                timeout=self.cfg.request_timeout,
            )
        return self._social_client

    async def process(self, request: dict) -> dict:
        """Process one request. Returns response dict for pub/sub."""
        req_id = request.get("request_id", "?")
        call_type = request.get("call_type", "unknown")

        # Model routing strategy (both models are thinking models, similar speed):
        # 35B (faster per-token, higher quality) → player-facing critical interactions
        # 4B (smaller, more concurrent throughput) → NPC autonomous background chatter
        _CRITICAL_TYPES = {
            "player_dialogue", "player_action",
            "confession", "proposal", "breakup", "violation",
        }
        if call_type in _CRITICAL_TYPES:
            client = self.main_client    # v4-pro (thinking) — quality for player experience
            use_thinking = self._main_thinking
        else:
            client = self.social_client  # v4-flash (non-thinking) — throughput for NPC
            use_thinking = self._social_thinking
        try:
            messages = json.loads(request.get("messages_json", "[]"))
            temperature = float(request.get("temperature", "0.7"))
            max_tokens = int(request.get("max_tokens", "256"))
            stop_raw = request.get("stop_json", "")
            stop = json.loads(stop_raw) if stop_raw else None
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            return self._error_response(req_id, f"Malformed request: {e}")

        messages = _safety_trim(messages, call_type)

        if self.cb.is_open:
            return self._error_response(req_id, "Circuit breaker open — LM Studio unavailable")

        last_error = ""
        for attempt in range(self.cfg.retry_max):
            try:
                raw = await client.chat(
                    messages, temperature=temperature,
                    max_tokens=max_tokens, stop=stop,
                    thinking=use_thinking,
                )
                self.cb.record_success()
                return {
                    "request_id": req_id,
                    "status": "success",
                    "content": raw,
                    "error": "",
                }
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                self.cb.record_failure()
                if self.cb.is_open:
                    break
                if attempt < self.cfg.retry_max - 1:
                    delay = self.cfg.retry_base_delay * (2 ** attempt)
                    logger.warning(
                        f"Retry {attempt + 1}/{self.cfg.retry_max} for {req_id} "
                        f"after {delay:.1f}s: {last_error}"
                    )
                    await asyncio.sleep(delay)

        return self._error_response(req_id, last_error or "All retries exhausted")

    def _error_response(self, req_id: str, error: str) -> dict:
        return {"request_id": req_id, "status": "error", "content": "", "error": error}


# ── Gateway ───────────────────────────────────────

class Gateway:
    def __init__(self, cfg: GatewayConfig):
        self.cfg = cfg
        self._redis: Optional[aioredis.Redis] = None
        self._running = False
        self._seq = 0
        # Separate queues for player and NPC streams
        self._player_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._npc_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._cb = CircuitBreaker(cfg.circuit_threshold, cfg.circuit_recovery)
        self._worker = GatewayWorker(cfg, self._cb)
        self._instance_id = str(uuid.uuid4())[:8]
        self._stats = {"processed": 0, "errors": 0, "stale": 0, "dropped_low": 0, "last_report": time.monotonic()}

    async def start(self):
        logger.info(f"Gateway {self._instance_id} starting, "
                     f"player_workers={self.cfg.player_workers}, npc_workers={self.cfg.npc_workers}")
        self._redis = aioredis.from_url(self.cfg.redis_url)
        await self._redis.ping()

        # Create consumer groups for both streams (idempotent)
        for stream in (self.cfg.player_stream, self.cfg.npc_stream):
            try:
                await self._redis.xgroup_create(
                    stream, self.cfg.consumer_group,
                    id="0", mkstream=True,
                )
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

        self._running = True
        consumer_name = f"gateway_{self._instance_id}"
        self._tasks = [
            # Poll loops - one per stream
            asyncio.create_task(self._poll_loop(consumer_name, self.cfg.player_stream, self._player_queue, "player")),
            asyncio.create_task(self._poll_loop(consumer_name + "_npc", self.cfg.npc_stream, self._npc_queue, "npc")),
            # Player-dedicated workers
            *[asyncio.create_task(self._run_player_worker(i)) for i in range(self.cfg.player_workers)],
            # NPC workers
            *[asyncio.create_task(self._run_npc_worker(i)) for i in range(self.cfg.npc_workers)],
            asyncio.create_task(self._stats_reporter()),
        ]
        logger.info(f"Gateway {self._instance_id} ready — "
                     f"player={self.cfg.player_stream}, npc={self.cfg.npc_stream}")
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def shutdown(self):
        logger.info(f"Gateway {self._instance_id} shutting down...")
        self._running = False
        for t in getattr(self, '_tasks', []):
            t.cancel()
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info(f"Gateway stopped. Stats: processed={self._stats['processed']}, "
                     f"errors={self._stats['errors']}, stale={self._stats['stale']}, "
                     f"dropped_low={self._stats['dropped_low']}")

    async def _poll_loop(self, consumer_name: str, stream: str, queue: asyncio.PriorityQueue, label: str):
        """Read from a Redis stream, push to the appropriate priority queue."""
        while self._running:
            try:
                msgs = await self._redis.xreadgroup(
                    self.cfg.consumer_group, consumer_name,
                    streams={stream: ">"},
                    count=self.cfg.poll_batch_size,
                    block=self.cfg.poll_block_ms,
                )
                for stream_name, entries in msgs:
                    for msg_id, fields in entries:
                        if not self._running:
                            break
                        fields = _decode_fields(fields)
                        # Check stale
                        expires = fields.get("expires_at", "")
                        if expires:
                            try:
                                from datetime import datetime
                                exp = datetime.fromisoformat(expires)
                                if (datetime.utcnow() - exp).total_seconds() > 0:
                                    await self._redis.xack(stream, self.cfg.consumer_group, msg_id)
                                    self._stats["stale"] += 1
                                    continue
                            except (ValueError, TypeError):
                                pass

                        # Drop stale LOW-priority requests (>60s old in NPC queue)
                        if label == "npc":
                            now_ts = time.monotonic()
                            queue_size = queue.qsize()
                            if queue_size > 50:  # If NPC queue is backed up, start dropping
                                priority = int(fields.get("priority", "3"))
                                if priority >= Priority.LOW:
                                    await self._redis.xack(stream, self.cfg.consumer_group, msg_id)
                                    self._stats["dropped_low"] += 1
                                    continue

                        priority = int(fields.get("priority", "2"))
                        self._seq += 1
                        await queue.put((priority, self._seq, msg_id, fields, self._redis, stream))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll error [{label}]: {e}")
                await asyncio.sleep(1)

    async def _run_player_worker(self, worker_id: int):
        """Dedicated worker for player stream — guaranteed capacity."""
        await self._run_worker_from_queue(worker_id, self._player_queue, "player")

    async def _run_npc_worker(self, worker_id: int):
        """Worker for NPC stream — processes background LLM tasks."""
        await self._run_worker_from_queue(worker_id, self._npc_queue, "npc")

    async def _run_worker_from_queue(self, worker_id: int, queue: asyncio.PriorityQueue, label: str):
        """Pull from a priority queue, process the request."""
        while self._running:
            try:
                priority, seq, msg_id, fields, redis_conn, stream = await queue.get()
            except asyncio.CancelledError:
                break

            req_id = fields.get("request_id", "?")
            t0 = time.monotonic()
            result = await self._worker.process(fields)
            elapsed = (time.monotonic() - t0) * 1000

            self._stats["processed"] += 1
            if result["status"] != "success":
                self._stats["errors"] += 1

            result["latency_ms"] = elapsed
            result["gateway_id"] = self._instance_id

            # Publish response
            reply_to = fields.get("reply_to", "")
            if reply_to:
                try:
                    await redis_conn.publish(reply_to, json.dumps(result, ensure_ascii=False))
                except Exception as e:
                    logger.error(f"Failed to publish response for {req_id}: {e}")

            # ACK the stream message
            try:
                await redis_conn.xack(stream, self.cfg.consumer_group, msg_id)
            except Exception as e:
                logger.error(f"Failed to ACK {msg_id}: {e}")

            prio_name = Priority(priority).name
            status_icon = "✓" if result["status"] == "success" else "✗"
            logger.debug(
                f"[{label}/{prio_name}] {status_icon} {req_id} "
                f"call_type={fields.get('call_type','?')} "
                f"latency={elapsed:.0f}ms"
            )

    async def _stats_reporter(self):
        """Periodic stats reporting and health check."""
        broker = None
        try:
            from src.common.message_broker import RedisBroker
            broker = RedisBroker()
            await broker.connect()
        except Exception:
            pass
        while self._running:
            await asyncio.sleep(60)
            now = time.monotonic()
            elapsed = now - self._stats["last_report"]
            rate = self._stats["processed"] / max(elapsed, 1)
            logger.info(
                f"Gateway stats: processed={self._stats['processed']} "
                f"errors={self._stats['errors']} stale={self._stats['stale']} "
                f"dropped_low={self._stats['dropped_low']} "
                f"rate={rate:.1f}/s circuit={self._cb.state} "
                f"player_q={self._player_queue.qsize()} npc_q={self._npc_queue.qsize()}"
            )
            if broker:
                try:
                    await broker.report_health(
                        "llm_gateway",
                        status="alive",
                        extra={
                            "processed": self._stats["processed"],
                            "errors": self._stats["errors"],
                            "circuit": self._cb.state,
                        },
                    )
                except Exception:
                    pass
            self._stats["last_report"] = now


# ── Entry Point ───────────────────────────────────

def main():
    cfg = GatewayConfig(
        max_concurrent=settings.llm_gateway_max_concurrent,
        player_workers=2,
        npc_workers=max(settings.llm_gateway_max_concurrent - 2, 1),
        redis_url=settings.redis_url,
        llm_provider=settings.llm_provider,
        deepseek_api_key=settings.deepseek_api_key,
        deepseek_base_url=settings.deepseek_base_url,
        deepseek_main_model=settings.deepseek_main_model,
        deepseek_social_model=settings.deepseek_social_model,
        deepseek_main_thinking=settings.deepseek_main_thinking,
        lmstudio_base_url=settings.lmstudio_base_url,
        lmstudio_main_model=settings.lmstudio_model,
        lmstudio_social_model=settings.lmstudio_social_model,
        request_timeout=settings.llm_gateway_request_timeout,
        circuit_threshold=settings.llm_gateway_circuit_threshold,
        circuit_recovery=settings.llm_gateway_circuit_recovery,
        retry_max=settings.llm_gateway_retry_max,
        retry_base_delay=settings.llm_gateway_retry_base_delay,
    )

    gateway = Gateway(cfg)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _shutdown():
        logger.info("Received SIGTERM/SIGINT")
        asyncio.ensure_future(gateway.shutdown(), loop=loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: _shutdown())

    try:
        loop.run_until_complete(gateway.start())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(gateway.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
