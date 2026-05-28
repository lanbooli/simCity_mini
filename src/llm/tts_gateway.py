#!/usr/bin/env python3
"""
TTS Gateway: standalone process that synthesizes NPC voice audio.

Loads Qwen3-TTS-12Hz-1.7B-Base with ICL voice cloning.
Consumes text from Redis stream, generates audio sentence-by-sentence,
pushes audio chunk URLs to frontend via pub/sub.

Usage: python -m src.llm.tts_gateway
Requires: mlx_audio venv (Python 3.14 + mlx + mlx-audio + redis)
"""

import asyncio
import json
import logging
import os
import re
import signal
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger("tts_gateway")

# ── Config (from env vars) ──────────────────────────

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
MODEL_PATH = os.environ.get("TTS_MODEL_PATH", "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16")
VOICE_REFS_DIR = os.environ.get("TTS_VOICE_REFS_DIR", "frontend/assets/voices")
AUDIO_OUT_DIR = os.environ.get("TTS_AUDIO_DIR", "frontend/assets/audio")
MAX_CONCURRENT = int(os.environ.get("TTS_MAX_CONCURRENT", "3"))
NARRATOR_MODEL_PATH = os.environ.get("TTS_NARRATOR_MODEL_PATH", "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16")
NARRATOR_INSTRUCT = os.environ.get("TTS_NARRATOR_INSTRUCT", "标准女声，吐字清晰，语调自然，播音员风格")
REQUEST_STREAM = "stream:tts:requests"
CONSUMER_GROUP = "tts_gateway_group"
POLL_BLOCK_MS = 2000
POLL_BATCH_SIZE = 5
CLEANUP_AGE_HOURS = 1

# ── Mood → Temperature ──────────────────────────────

MOOD_TEMPERATURES = {
    "happy": 0.55,
    "excited": 0.65,
    "sad": 0.30,
    "angry": 0.35,
    "neutral": 0.40,
    "flustered": 0.45,
    "romantic": 0.50,
    "fearful": 0.30,
    "touched": 0.52,
    "nervous": 0.42,
    "shy": 0.38,
}

# ── Sentence Splitting ──────────────────────────────

_SENTENCE_RE = re.compile(r"[^。！？~…；;!?\n]+[。！？~…；;!?\n]?")


def _split_sentences(text: str) -> list[str]:
    """Split Chinese text into sentences by punctuation."""
    parts = _SENTENCE_RE.findall(text)
    if not parts:
        return [text]
    # Merge very short fragments with neighbors
    result = []
    buf = ""
    for p in parts:
        if len(p) <= 2 and buf:
            buf += p
        elif len(p) <= 2:
            buf = p
        else:
            if buf:
                result.append(buf)
                buf = ""
            result.append(p)
    if buf:
        if result:
            result[-1] += buf
        else:
            result.append(buf)
    return result or [text]


# ── TTS Gateway ──────────────────────────────────────

class TTSGateway:
    def __init__(self):
        self._model = None
        self._narrator_model = None
        self._voice_refs: dict[str, dict] = {}  # npc_id → {audio, text}
        self._redis: Optional[aioredis.Redis] = None
        self._running = False
        self._sem: Optional[asyncio.Semaphore] = None
        self._audio_dir = Path(AUDIO_OUT_DIR)
        self._instance_id = str(uuid.uuid4())[:8]

    async def start(self):
        logger.info(f"TTS Gateway {self._instance_id} starting...")

        # Load models
        from mlx_audio.tts.utils import load_model
        
        # Base model: NPC voice cloning (ref_audio + ref_text)
        logger.info(f"Loading NPC TTS model: {MODEL_PATH}")
        self._model = load_model(MODEL_PATH)
        logger.info(f"NPC model loaded. sample_rate={self._model.sample_rate}")
        
        # VoiceDesign model: narrator voice (instruct-based)
        logger.info(f"Loading narrator TTS model: {NARRATOR_MODEL_PATH}")
        self._narrator_model = load_model(NARRATOR_MODEL_PATH)
        logger.info(f"Narrator model loaded. sample_rate={self._narrator_model.sample_rate}")

        # Load voice references
        self._load_voice_refs()

        # Connect Redis
        self._redis = aioredis.from_url(REDIS_URL)
        await self._redis.ping()

        # Create consumer group
        try:
            await self._redis.xgroup_create(
                REQUEST_STREAM, CONSUMER_GROUP, id="0", mkstream=True,
            )
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

        # Start workers
        self._running = True
        self._sem = asyncio.Semaphore(MAX_CONCURRENT)
        self._consumer_name = f"tts_gateway_{self._instance_id}"

        # Clean up stale consumers from previous crashed instances
        await self._cleanup_stale_consumers()

        self._tasks = [
            asyncio.create_task(self._poll_loop(self._consumer_name)),
            asyncio.create_task(self._cleanup_loop()),
        ]
        logger.info(f"TTS Gateway {self._instance_id} ready (max_concurrent={MAX_CONCURRENT})")
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def shutdown(self):
        logger.info(f"TTS Gateway {self._instance_id} shutting down...")
        self._running = False
        for t in getattr(self, "_tasks", []):
            t.cancel()
        if self._redis:
            # Remove this consumer from the group to prevent zombie accumulation
            consumer = getattr(self, "_consumer_name", "")
            if consumer:
                try:
                    await self._redis.xgroup_delconsumer(REQUEST_STREAM, CONSUMER_GROUP, consumer)
                    logger.info(f"Removed consumer '{consumer}' from group")
                except Exception as e:
                    logger.warning(f"Failed to remove consumer: {e}")
            # Clean up idle consumers from dead instances (>60s idle)
            try:
                consumers = await self._redis.xinfo_consumers(REQUEST_STREAM, CONSUMER_GROUP)
                for c in consumers:
                    if c["idle"] > 60000 and c["pending"] == 0:
                        try:
                            await self._redis.xgroup_delconsumer(REQUEST_STREAM, CONSUMER_GROUP, c["name"])
                            logger.info(f"Cleaned idle consumer: {c['name']}")
                        except Exception:
                            pass
            except Exception:
                pass
            await self._redis.close()
            self._redis = None
        self._model = None
        self._narrator_model = None
        logger.info("TTS Gateway stopped.")

    def _load_voice_refs(self):
        """Load NPC reference audio files from VOICE_REFS_DIR."""
        from mlx_audio.utils import load_audio

        refs_dir = Path(VOICE_REFS_DIR)
        if not refs_dir.exists():
            logger.warning(f"Voice refs dir not found: {refs_dir}")
            return

        for wav_path in refs_dir.glob("*_ref.wav"):
            npc_id = wav_path.stem.replace("_ref", "")
            txt_path = refs_dir / f"{npc_id}_ref.txt"
            if not txt_path.exists():
                logger.warning(f"Missing ref text for {npc_id}: {txt_path}")
                continue

            try:
                audio = load_audio(str(wav_path), sample_rate=24000)
                text = txt_path.read_text().strip()
                self._voice_refs[npc_id] = {"audio": audio, "text": text}
                logger.info(f"Voice ref loaded: {npc_id} ({len(text)} chars, {audio.size} samples)")
            except Exception as e:
                logger.error(f"Failed to load voice ref {npc_id}: {e}")

    async def _poll_loop(self, consumer_name: str):
        # Recover pending messages from previous crashed instances
        await self._claim_pending(consumer_name)

        while self._running:
            try:
                msgs = await self._redis.xreadgroup(
                    CONSUMER_GROUP, consumer_name,
                    streams={REQUEST_STREAM: ">"},
                    count=POLL_BATCH_SIZE,
                    block=POLL_BLOCK_MS,
                )
                for _stream_name, entries in msgs:
                    for msg_id, fields in entries:
                        if not self._running:
                            break
                        asyncio.create_task(self._process(msg_id, fields))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poll error: {e}")
                await asyncio.sleep(1)

    async def _cleanup_stale_consumers(self):
        """Remove idle consumers with no pending messages left by dead instances."""
        try:
            consumers = await self._redis.xinfo_consumers(REQUEST_STREAM, CONSUMER_GROUP)
            cleaned = 0
            for c in consumers:
                if c["name"] != self._consumer_name and c["pending"] == 0 and c["idle"] > 30000:
                    try:
                        await self._redis.xgroup_delconsumer(REQUEST_STREAM, CONSUMER_GROUP, c["name"])
                        cleaned += 1
                    except Exception:
                        pass
            if cleaned:
                logger.info(f"Cleaned {cleaned} stale consumer(s) at startup")
        except Exception:
            pass

    async def _claim_pending(self, consumer_name: str):
        """Claim and reprocess pending messages left by previous instances."""
        try:
            pending_info = await self._redis.xpending(REQUEST_STREAM, CONSUMER_GROUP)
            pending_count = pending_info.get("pending", 0) if isinstance(pending_info, dict) else 0
            if pending_count == 0:
                return

            logger.info(f"Found {pending_count} pending TTS messages, claiming...")
            pending_msgs = await self._redis.xpending_range(
                REQUEST_STREAM, CONSUMER_GROUP,
                min="-", max="+", count=pending_count,
            )
            for entry in pending_msgs:
                msg_id = entry["message_id"]
                times_delivered = entry.get("times_delivered", 0)
                if times_delivered > 3:
                    logger.warning(f"Skipping {msg_id} (delivered {times_delivered}x, likely poison)")
                    await self._redis.xack(REQUEST_STREAM, CONSUMER_GROUP, msg_id)
                    await self._redis.xdel(REQUEST_STREAM, msg_id)
                    continue
                claimed = await self._redis.xclaim(
                    REQUEST_STREAM, CONSUMER_GROUP,
                    consumer_name, min_idle_time=0,
                    message_ids=[msg_id],
                )
                if claimed:
                    for cid, fields in claimed:
                        logger.info(f"Claimed pending TTS {cid}")
                        asyncio.create_task(self._process(cid, fields))
        except Exception as e:
            logger.error(f"Claim pending error: {e}")

    async def _process(self, msg_id: bytes, fields: dict):
        async with self._sem:
            try:
                await self._process_request(msg_id, fields)
            except Exception as e:
                logger.error(f"Process error for {msg_id}: {e}")
            finally:
                try:
                    await self._redis.xack(REQUEST_STREAM, CONSUMER_GROUP, msg_id)
                except Exception:
                    pass

    async def _process_request(self, msg_id: bytes, fields: dict):
        req_id = fields.get(b"request_id", fields.get("request_id", "?")).decode() if isinstance(fields.get(b"request_id"), bytes) else fields.get("request_id", "?")
        if isinstance(req_id, bytes):
            req_id = req_id.decode()

        npc_id = fields.get(b"npc_id", fields.get("npc_id", "")).decode() if isinstance(fields.get(b"npc_id"), bytes) else fields.get("npc_id", "")
        if isinstance(npc_id, bytes):
            npc_id = npc_id.decode()

        text = fields.get(b"text", fields.get("text", "")).decode() if isinstance(fields.get(b"text"), bytes) else fields.get("text", "")
        if isinstance(text, bytes):
            text = text.decode()

        mood = fields.get(b"mood", fields.get("mood", "neutral")).decode() if isinstance(fields.get(b"mood"), bytes) else fields.get("mood", "neutral")
        if isinstance(mood, bytes):
            mood = mood.decode()

        reply_to = fields.get(b"reply_to", fields.get("reply_to", "")).decode() if isinstance(fields.get(b"reply_to"), bytes) else fields.get("reply_to", "")
        if isinstance(reply_to, bytes):
            reply_to = reply_to.decode()

        player_id = fields.get(b"player_id", fields.get("player_id", "")).decode() if isinstance(fields.get(b"player_id"), bytes) else fields.get("player_id", "")
        if isinstance(player_id, bytes):
            player_id = player_id.decode()

        if not text or not npc_id:
            logger.warning(f"Missing text or npc_id for {req_id}")
            return

        # Check for segments (stage direction + dialogue) or fallback to whole text
        segments_raw = fields.get(b"segments", fields.get("segments", ""))
        if isinstance(segments_raw, bytes):
            segments_raw = segments_raw.decode()
        if segments_raw:
            try:
                segments = json.loads(segments_raw)
            except (json.JSONDecodeError, TypeError):
                segments = []
        else:
            segments = []

        temperature = MOOD_TEMPERATURES.get(mood, 0.4)

        import mlx.core as mx
        from mlx_audio.audio_io import write as audio_write

        if segments:
            # Segmented TTS: each segment uses appropriate voice ref
            logger.info(
                f"TTS {req_id}: npc={npc_id} mood={mood} temp={temperature} "
                f"segments={len(segments)}"
            )
            t_start = time.monotonic()
            chunk_idx = 0
            total_sentences = 0
            
            # Count total sentences for is_last tracking
            for seg in segments:
                total_sentences += len(_split_sentences(seg.get("text", "")))
            
            for seg in segments:
                seg_text = seg.get("text", "").strip()
                seg_type = seg.get("type", "dialogue")
                if not seg_text:
                    continue
                
                # Pick voice ref: narrator for stage, NPC for dialogue
                if seg_type == "stage":
                    # Use VoiceDesign model with instruct
                    try:
                        est_tokens = max(128, min(1024, len(seg_text) * 10))
                        audio_chunks = []
                        gen_start = time.monotonic()
                        for result in self._narrator_model.generate(
                            text=seg_text,
                            instruct=NARRATOR_INSTRUCT,
                            language="Chinese",
                            temperature=temperature,
                            max_tokens=est_tokens,
                        ):
                            audio_chunks.append(result.audio)

                        audio = mx.concatenate(audio_chunks, axis=0) if len(audio_chunks) > 1 else audio_chunks[0]
                        gen_elapsed = (time.monotonic() - gen_start) * 1000

                        filename = f"{req_id}_{chunk_idx:03d}.wav"
                        filepath = self._audio_dir / filename
                        audio_write(str(filepath), audio, 24000, format="wav")

                        is_last = (chunk_idx >= total_sentences - 1)
                        chunk_msg = json.dumps({
                            "request_id": req_id,
                            "chunk_index": chunk_idx,
                            "total_chunks": total_sentences,
                            "audio_url": f"/assets/audio/{filename}",
                            "text": seg_text,
                            "npc_id": npc_id,
                                "player_id": player_id,
                            "is_last": is_last,
                        }, ensure_ascii=False)

                        if reply_to:
                            await self._redis.publish(reply_to, chunk_msg)

                        logger.info(
                            f"TTS {req_id} segment=narrator chunk {chunk_idx}/{total_sentences}: "
                            f"gen={gen_elapsed:.0f}ms chars={len(seg_text)}"
                        )
                        chunk_idx += 1
                    except Exception as e:
                        logger.error(f"TTS {req_id} narrator chunk failed: {e}")
                        chunk_idx += 1
                else:
                    # NPC dialogue: use base model with voice cloning
                    ref = self._voice_refs.get(npc_id)
                    if not ref:
                        logger.warning(f"No voice ref for npc={npc_id}, skipping dialogue TTS")
                        continue
                    sentences = _split_sentences(seg_text)
                    for i, sentence in enumerate(sentences):
                        if not sentence.strip():
                            continue
                        try:
                            est_tokens = max(128, min(1024, len(sentence) * 10))
                            audio_chunks = []
                            gen_start = time.monotonic()
                            for result in self._model.generate(
                                text=sentence,
                                ref_audio=ref["audio"],
                                ref_text=ref["text"],
                                language="Chinese",
                                temperature=temperature,
                                max_tokens=est_tokens,
                            ):
                                audio_chunks.append(result.audio)

                            audio = mx.concatenate(audio_chunks, axis=0) if len(audio_chunks) > 1 else audio_chunks[0]
                            gen_elapsed = (time.monotonic() - gen_start) * 1000

                            filename = f"{req_id}_{chunk_idx:03d}.wav"
                            filepath = self._audio_dir / filename
                            audio_write(str(filepath), audio, 24000, format="wav")

                            is_last = (chunk_idx >= total_sentences - 1)
                            chunk_msg = json.dumps({
                                "request_id": req_id,
                                "chunk_index": chunk_idx,
                                "total_chunks": total_sentences,
                                "audio_url": f"/assets/audio/{filename}",
                                "text": sentence,
                                "npc_id": npc_id,
                                "player_id": player_id,
                                "is_last": is_last,
                            }, ensure_ascii=False)

                            if reply_to:
                                await self._redis.publish(reply_to, chunk_msg)

                            logger.info(
                                f"TTS {req_id} segment=npc chunk {chunk_idx}/{total_sentences}: "
                                f"gen={gen_elapsed:.0f}ms chars={len(sentence)}"
                            )
                            chunk_idx += 1
                        except Exception as e:
                            logger.error(f"TTS {req_id} npc segment chunk {i} failed: {e}")
                            chunk_idx += 1
            
            total_elapsed = (time.monotonic() - t_start) * 1000
            logger.info(
                f"TTS {req_id} complete: {total_elapsed:.0f}ms total, "
                f"{chunk_idx} chunks"
            )
        else:
            # Legacy: whole text as NPC dialogue
            ref = self._voice_refs.get(npc_id)
            if not ref:
                logger.warning(f"No voice ref for {npc_id}, skipping TTS")
                return

            logger.info(
                f"TTS {req_id}: npc={npc_id} mood={mood} temp={temperature} "
                f"chars={len(text)}"
            )

            sentences = _split_sentences(text)
            t_start = time.monotonic()

            for i, sentence in enumerate(sentences):
                if not sentence.strip():
                    continue

                try:
                    est_tokens = max(128, min(1024, len(sentence) * 10))
                    audio_chunks = []
                    gen_start = time.monotonic()
                    for result in self._model.generate(
                        text=sentence,
                        ref_audio=ref["audio"],
                        ref_text=ref["text"],
                        language="Chinese",
                        temperature=temperature,
                        max_tokens=est_tokens,
                    ):
                        audio_chunks.append(result.audio)

                    audio = mx.concatenate(audio_chunks, axis=0) if len(audio_chunks) > 1 else audio_chunks[0]
                    gen_elapsed = (time.monotonic() - gen_start) * 1000

                    filename = f"{req_id}_{i:03d}.wav"
                    filepath = self._audio_dir / filename
                    audio_write(str(filepath), audio, 24000, format="wav")

                    is_last = (i == len(sentences) - 1)
                    chunk_msg = json.dumps({
                        "request_id": req_id,
                        "chunk_index": i,
                        "total_chunks": len(sentences),
                        "audio_url": f"/assets/audio/{filename}",
                        "text": sentence,
                        "npc_id": npc_id,
                                "player_id": player_id,
                        "is_last": is_last,
                    }, ensure_ascii=False)

                    if reply_to:
                        await self._redis.publish(reply_to, chunk_msg)

                    logger.info(
                        f"TTS {req_id} chunk {i}/{len(sentences)}: "
                        f"gen={gen_elapsed:.0f}ms chars={len(sentence)}"
                    )

                except Exception as e:
                    logger.error(f"TTS {req_id} chunk {i} failed: {e}")

            total_elapsed = (time.monotonic() - t_start) * 1000
            logger.info(
                f"TTS {req_id} complete: {total_elapsed:.0f}ms total, "
                f"{len(sentences)} chunks"
            )

    async def _cleanup_loop(self):
        """Periodically clean old audio files and stale consumers."""
        while self._running:
            await asyncio.sleep(600)  # every 10 minutes
            try:
                now = time.time()
                cutoff = now - CLEANUP_AGE_HOURS * 3600
                for f in self._audio_dir.glob("*.wav"):
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        logger.debug(f"Cleaned up old audio: {f.name}")
                # Also clean stale consumers periodically
                await self._cleanup_stale_consumers()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")


# ── Entry Point ─────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    gateway = TTSGateway()
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
