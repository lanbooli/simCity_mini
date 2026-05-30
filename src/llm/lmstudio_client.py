"""
LM Studio client - OpenAI-compatible API.
Supports both standard and streaming chat completions.
Reserved: voice interface hook for future TTS/STT integration.
"""

from __future__ import annotations

import json
import httpx
from config.settings import settings
import logging
logger = logging.getLogger("llm_gateway")


class LMStudioClient:
    """Async HTTP client for OpenAI-compatible APIs (LM Studio, DeepSeek, etc.)."""

    def __init__(self, base_url: str = "", model: str = "",
                 api_key: str = "", timeout: float = 120.0):
        self.base_url = base_url or settings.lmstudio_base_url
        self.model = model or settings.lmstudio_model
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self):
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.5,
        max_tokens: int = 1024,
        stop: list[str] | None = None,
        thinking: bool = False,
    ) -> str:
        """Send a chat completion request and return the response text."""
        await self._ensure_client()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # DeepSeek thinking mode
        if thinking and self.api_key:
            payload["thinking"] = {"type": "enabled"}
        # repeat_penalty is LM Studio specific, DeepSeek doesn't support it
        if not self.api_key:
            payload["repeat_penalty"] = 1.15
        if stop:
            payload["stop"] = stop

        resp = await self._client.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "") or ""
        # Log if content is empty but response was successful
        if not content:
            logger.warning(
                "[LMStudio] empty content from model=%s. "
                "msg keys=%s finish_reason=%s",
                self.model, list(msg.keys()), choice.get("finish_reason", "?"),
            )
        return content

    async def chat_stream(self, messages: list[dict], temperature: float = 0.5):
        """Stream chat completion tokens. Yields text chunks."""
        await self._ensure_client()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 256,
            "stream": True,
        }

        async with self._client.stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            json=payload,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        delta = json.loads(chunk)
                        content = delta.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    # ── Future voice interface hooks ──────────────

    async def voice_transcribe(self, audio_data: bytes) -> str:
        """[FUTURE] Transcribe voice to text via LM Studio's whisper endpoint."""
        raise NotImplementedError("Voice transcription will be added in a future update.")

    async def voice_synthesize(self, text: str, voice_profile: str = "") -> bytes:
        """[FUTURE] Synthesize text to speech with NPC voice profile."""
        raise NotImplementedError("Voice synthesis will be added in a future update.")


# Global client instance
_client: LMStudioClient | None = None


def get_client() -> LMStudioClient:
    global _client
    if _client is None:
        _client = LMStudioClient()
    return _client


async def close_client():
    global _client
    if _client:
        await _client.close()
        _client = None
