#!/usr/bin/env python3
"""
Pre-generate TTS audio for career greeting templates.

Generates one .wav file per (NPC, greeting template) pair and saves to
frontend/assets/audio/greetings/. Audio playback is instant — no TTS delay.

Usage: python scripts/pregen_greetings.py
Requires: mlx_audio venv with mlx + mlx-audio installed
"""

import json
import os
import sys
import sqlite3
import hashlib
from pathlib import Path

# ── Config ────────────────────────────────────────────

DB_PATH = os.environ.get("DB_PATH", "data/city_town.db")
VOICE_REFS_DIR = os.environ.get("TTS_VOICE_REFS_DIR", "frontend/assets/voices")
AUDIO_OUT_DIR = os.environ.get("TTS_AUDIO_DIR", "frontend/assets/audio/greetings")
MODEL_PATH = os.environ.get("TTS_MODEL_PATH", "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16")

CAREER_GREETINGS: dict[str, list[str]] = {
    "咖啡店主": [
        "欢迎光临阳光咖啡店！今天想喝点什么？",
        "你好呀，来看看我们新到的咖啡豆吧～",
        "欢迎！老位置还给你留着呢。",
    ],
    "咖啡店员": [
        "欢迎光临！请问需要点什么呢？",
        "你好～今天有限定特调哦，要不要试试？",
        "欢迎光临阳光咖啡店！",
    ],
    "图书管理员": [
        "欢迎来到图书馆，请保持安静哦～",
        "你好，需要帮忙找什么书吗？",
        "欢迎～最近新到了一批书，可以来看看。",
    ],
    "超市店主": [
        "欢迎光临便民超市！随便看看～",
        "你好！今天蔬菜很新鲜哦。",
        "欢迎光临，有什么需要尽管问我。",
    ],
    "超市收银员": [
        "欢迎光临！",
        "你好～需要购物袋吗？",
        "欢迎光临便民超市！",
    ],
    "内科医生": [
        "你好，请坐。哪里不舒服？",
        "你好，先量一下体温吧。",
        "请进，今天感觉怎么样？",
    ],
    "护士": [
        "你好，请问有预约吗？",
        "欢迎来到小镇医院，请先挂号哦~",
        "你好，量一下血压吧。",
    ],
    "语文教师": [
        "同学们好，请回到座位上。",
        "你好呀，今天来旁听吗？",
        "欢迎来到学校～",
    ],
}


def load_npcs(db_path: str) -> list[dict]:
    """Load NPCs that have both a career and a voice reference file."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, name, career, voice_type FROM npc "
            "WHERE career IS NOT NULL AND career != '' AND is_active = 1"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def has_voice_ref(npc_id: str) -> bool:
    """Check if a voice reference file exists for this NPC."""
    ref_wav = Path(VOICE_REFS_DIR) / f"{npc_id}_ref.wav"
    ref_txt = Path(VOICE_REFS_DIR) / f"{npc_id}_ref.txt"
    return ref_wav.exists() and ref_txt.exists()


def generate_greeting_audio(
    model, voice_ref: dict, text: str, output_path: str,
) -> bool:
    """Generate a single greeting audio file. Returns True on success."""
    import mlx.core as mx
    from mlx_audio.audio_io import write as audio_write

    try:
        audio_chunks = []
        est_tokens = max(128, min(1024, len(text) * 10))
        for result in model.generate(
            text=text,
            ref_audio=voice_ref["audio"],
            ref_text=voice_ref["text"],
            language="Chinese",
            temperature=0.45,
            max_tokens=est_tokens,
        ):
            audio_chunks.append(result.audio)

        audio = mx.concatenate(audio_chunks, axis=0) if len(audio_chunks) > 1 else audio_chunks[0]
        audio_write(output_path, audio, 24000, format="wav")
        return True
    except Exception as e:
        print(f"  ERROR generating audio: {e}", file=sys.stderr)
        return False


def main():
    print("=== Career Greeting Audio Pre-Generation ===")

    # Load MLX model
    print(f"Loading model: {MODEL_PATH}")
    from mlx_audio.tts.utils import load_model
    from mlx_audio.utils import load_audio

    model = load_model(MODEL_PATH)
    print(f"Model loaded. sample_rate={model.sample_rate}")

    # Ensure output directory exists
    out_dir = Path(AUDIO_OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load NPCs with careers
    npcs = load_npcs(DB_PATH)
    print(f"\nFound {len(npcs)} NPCs with careers")

    total = 0
    generated = 0
    skipped = 0

    for npc in npcs:
        npc_id = npc["id"]
        career = npc["career"]
        name = npc["name"]

        # Check career has greeting templates
        if career not in CAREER_GREETINGS:
            print(f"  SKIP {name} ({npc_id}): no greeting templates for career '{career}'")
            continue

        # Check voice reference exists
        if not has_voice_ref(npc_id):
            print(f"  SKIP {name} ({npc_id}): missing voice reference file")
            skipped += len(CAREER_GREETINGS[career])
            continue

        # Load voice reference
        from mlx_audio.utils import load_audio as _load_audio

        ref_wav = Path(VOICE_REFS_DIR) / f"{npc_id}_ref.wav"
        ref_txt = Path(VOICE_REFS_DIR) / f"{npc_id}_ref.txt"
        voice_ref = {
            "audio": _load_audio(str(ref_wav), sample_rate=24000),
            "text": ref_txt.read_text().strip(),
        }

        templates = CAREER_GREETINGS[career]
        print(f"\n{name} ({npc_id}) — {career} — {len(templates)} greetings:")

        for i, text in enumerate(templates):
            total += 1
            file_hash = int(hashlib.md5(text.encode()).hexdigest()[:8], 16) % 10000
            filename = f"{npc_id}_{file_hash:04d}.wav"
            filepath = str(out_dir / filename)

            if Path(filepath).exists():
                print(f"  [{i+1}/{len(templates)}] SKIP (exists): {text[:40]}...")
                skipped += 1
                continue

            print(f"  [{i+1}/{len(templates)}] Generating: {text[:40]}...", end=" ", flush=True)
            if generate_greeting_audio(model, voice_ref, text, filepath):
                print("OK")
                generated += 1
            else:
                print("FAILED")

    print(f"\n=== Done: {generated} generated, {skipped} skipped, {total} total ===")


if __name__ == "__main__":
    main()
