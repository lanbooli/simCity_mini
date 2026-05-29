"""
Redis-based inter-process communication.

Provides:
- Pub/Sub channels for broadcasting
- Streams for reliable message queues (with consumer groups)
- Key-Value store for shared lightweight state
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import traceback
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

import redis.asyncio as aioredis

from config.settings import settings


# ── Abstract Interface ─────────────────────────────────

class MessageBroker(ABC):
    @abstractmethod
    async def publish(self, channel: str, message: dict) -> int: ...

    @abstractmethod
    async def subscribe(self, channel: str, handler: Callable[[dict], Any]) -> None: ...

    @abstractmethod
    async def stream_add(self, stream: str, data: dict, maxlen: int = 1000) -> str: ...

    @abstractmethod
    async def stream_read_group(
        self, stream: str, group: str, consumer: str,
        count: int = 1, block_ms: int = 5000,
    ) -> list[tuple[str, dict]]: ...

    @abstractmethod
    async def stream_create_group(self, stream: str, group: str) -> bool: ...

    @abstractmethod
    async def kv_get(self, key: str) -> Optional[dict]: ...

    @abstractmethod
    async def kv_set(self, key: str, value: dict) -> None: ...

    @abstractmethod
    async def kv_delete(self, key: str) -> None: ...
    async def acquire_lock(self, key: str, ttl_seconds: int = 5) -> bool: ...
    async def release_lock(self, key: str) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...


# ── Redis Implementation ───────────────────────────────

class RedisBroker(MessageBroker):
    def __init__(self, url: str = ""):
        self.url = url or settings.redis_url
        self._redis: Optional[aioredis.Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._handlers: dict[str, list[Callable]] = {}
        self._listener_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(
            self.url, decode_responses=True,
            socket_connect_timeout=5, socket_keepalive=True,
            retry_on_timeout=True, health_check_interval=30,
        )
        await self._redis.ping()

    async def disconnect(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def _ensure_connected(self):
        if self._redis is None:
            await self.connect()

    # ── Pub/Sub ─────────────────────────────────────

    async def publish(self, channel: str, message: dict) -> int:
        await self._ensure_connected()
        return await self._redis.publish(channel, json.dumps(message, ensure_ascii=False))

    async def subscribe(self, channel: str, handler: Callable[[dict], Any]) -> None:
        await self._ensure_connected()
        self._handlers.setdefault(channel, []).append(handler)

        if self._pubsub is None:
            self._pubsub = self._redis.pubsub()
            self._listener_task = asyncio.create_task(self._listen_loop())

        await self._pubsub.subscribe(channel)

    async def _listen_loop(self) -> None:
        """Background task that reads pubsub messages and dispatches to handlers."""
        while True:
            try:
                if self._pubsub is None:
                    await asyncio.sleep(0.1)
                    continue
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.5,
                )
                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    channel = message["channel"]
                    for handler in self._handlers.get(channel, []):
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                asyncio.create_task(handler(data))
                            else:
                                handler(data)
                        except Exception:
                            traceback.print_exc()
            except asyncio.CancelledError:
                break
            except Exception:
                traceback.print_exc()
                await asyncio.sleep(1)

    # ── Streams ─────────────────────────────────────

    async def stream_add(self, stream: str, data: dict, maxlen: int = 1000) -> str:
        await self._ensure_connected()
        msg_id = await self._redis.xadd(
            stream, data, maxlen=maxlen, approximate=True,
        )
        return msg_id

    async def stream_read_group(
        self, stream: str, group: str, consumer: str,
        count: int = 1, block_ms: int = 5000,
    ) -> list[tuple[str, dict]]:
        await self._ensure_connected()
        results = await self._redis.xreadgroup(
            group, consumer, {stream: ">"}, count=count, block=block_ms,
        )
        out = []
        if results:
            for stream_name, messages in results:
                for msg_id, fields in messages:
                    decoded = {}
                    for k, v in fields.items():
                        key = k.decode("utf-8") if isinstance(k, bytes) else k
                        val = v.decode("utf-8") if isinstance(v, bytes) else v
                        decoded[key] = val
                    out.append((msg_id, decoded))
        return out

    async def stream_create_group(self, stream: str, group: str) -> bool:
        await self._ensure_connected()
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
            return True
        except aioredis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                return False  # group already exists
            raise
        return False

    async def stream_ack(self, stream: str, group: str, msg_id: str) -> None:
        await self._ensure_connected()
        await self._redis.xack(stream, group, msg_id)

    # ── KV Store ────────────────────────────────────

    async def kv_get(self, key: str) -> Optional[dict]:
        await self._ensure_connected()
        val = await self._redis.get(key)
        return json.loads(val) if val else None

    async def kv_set(self, key: str, value: dict) -> None:
        await self._ensure_connected()
        await self._redis.set(key, json.dumps(value, ensure_ascii=False))

    async def kv_delete(self, key: str) -> None:
        await self._ensure_connected()
        await self._redis.delete(key)

    async def acquire_lock(self, key: str, ttl_seconds: int = 5) -> bool:
        """Try to acquire a Redis lock. Returns True if acquired."""
        await self._ensure_connected()
        acquired = await self._redis.set(key, "1", nx=True, expire=ttl_seconds)
        return bool(acquired)

    async def release_lock(self, key: str) -> None:
        """Release a Redis lock."""
        await self._ensure_connected()
        await self._redis.delete(key)

    # ── Health Check ────────────────────────────────────

    async def report_health(self, name: str, status: str = "alive", extra: dict | None = None) -> None:
        """Report process health to Redis. Called periodically by each process."""
        data = {
            "name": name,
            "status": status,
            "pid": os.getpid(),
            "timestamp": time.time(),
        }
        if extra:
            data.update(extra)
        await self.kv_set(f"health:{name}", data)

    async def get_health(self, name: str) -> dict | None:
        """Get health status of a process."""
        return await self.kv_get(f"health:{name}")

    async def get_all_healths(self, prefix: str = "health:") -> dict[str, dict]:
        """Get health status of all processes matching prefix."""
        await self._ensure_connected()
        keys = await self._redis.keys(f"{prefix}*")
        result = {}
        for key in keys:
            val = await self._redis.get(key)
            if val:
                k = key.decode() if isinstance(key, bytes) else key
                name = k[len(prefix):]
                result[name] = json.loads(val)
        return result
