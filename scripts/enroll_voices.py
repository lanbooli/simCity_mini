#!/usr/bin/env python3
"""
One-time voice enrollment: generate reference audio for each NPC
using the VoiceDesign model. These reference files are then used by
the TTS Gateway with the Base model for ICL voice cloning.

Usage:
    source /path/to/mlx_audio/bin/activate
    export HF_ENDPOINT=https://hf-mirror.com
    python scripts/enroll_voices.py
"""

import os
import sys
from pathlib import Path

import mlx.core as mx
from mlx_audio.tts.utils import load_model
from mlx_audio.audio_io import write as audio_write

# ── NPC Voice Profiles (English instruct for VoiceDesign) ─

VOICE_PROFILES = {
    "npc_li_ming": (
        "A warm and gentle young male voice with smooth and rounded timbre, "
        "medium pitch with natural resonance, calm and unhurried pace, "
        "soft vocal style with light breath support, friendly and approachable."
    ),
    "npc_wang_fang": (
        "A cute and lively young female voice with bright and clear timbre, "
        "slightly high pitch with light and bouncy quality, quick and energetic pace, "
        "sweet vocal style with soft breathiness, cheerful and bubbly."
    ),
    "npc_zhang_wei": (
        "A deep and resonant mature male voice with rich and full timbre, "
        "low pitch with chest resonance and gravitas, slow and measured pace, "
        "authoritative vocal style with firm projection, calm and steady."
    ),
    "npc_chen_xue": (
        "A soft and elegant intellectual female voice with warm and refined timbre, "
        "medium-low pitch with smooth and even quality, moderate and deliberate pace, "
        "cultured vocal style with precise articulation, gentle and composed."
    ),
    "npc_liu_jie": (
        "A warm and enthusiastic middle-aged female voice with hearty and full timbre, "
        "medium pitch with robust and lively quality, energetic and flowing pace, "
        "approachable vocal style with strong projection, warm and inviting."
    ),
    # ── Photo NPCs (all female, distinct vocal personalities) ──
    "npc_photo_01": (
        "A bright and bubbly young female voice with clear and sparkling timbre, "
        "medium-high pitch with bouncy and cheerful quality, quick and lively pace, "
        "sweet and innocent vocal style, full of energy and smiles."
    ),
    "npc_photo_02": (
        "A soft and gentle young female voice with warm and refined timbre, "
        "medium pitch with smooth and calm quality, moderate and thoughtful pace, "
        "intellectual vocal style with clear enunciation, kind and patient."
    ),
    "npc_photo_03": (
        "A lively and gossipy young female voice with bright and expressive timbre, "
        "medium pitch with animated and varied quality, fast and excited pace, "
        "friendly vocal style with dramatic flair, warm and sociable."
    ),
    "npc_photo_04": (
        "A mature and cool adult female voice with firm and controlled timbre, "
        "medium-low pitch with measured and crisp quality, steady and deliberate pace, "
        "businesslike vocal style with occasional warmth underneath, composed and direct."
    ),
    "npc_photo_05": (
        "A sunny and athletic young female voice with bright and energetic timbre, "
        "medium pitch with strong and vibrant quality, quick and bouncy pace, "
        "outgoing vocal style with breathy undertones, enthusiastic and sporty."
    ),
    "npc_photo_06": (
        "A quiet and refined young female voice with soft and elegant timbre, "
        "medium-low pitch with gentle and calm quality, slow and measured pace, "
        "scholarly vocal style with cultured articulation, introverted and graceful."
    ),
    "npc_photo_07": (
        "A shy and timid young female voice with soft and airy timbre, "
        "slightly high pitch with fragile and wispy quality, hesitant and slow pace, "
        "gentle vocal style with light breathiness, sweet and easily flustered."
    ),
    "npc_photo_08": (
        "A cool and aloof adult female voice with smooth and controlled timbre, "
        "low pitch with icy and composed quality, slow and deliberate pace, "
        "detached vocal style with hidden warmth, mysterious and elegant."
    ),
    "npc_photo_09": (
        "A relaxed and easygoing young female voice with warm and laid-back timbre, "
        "medium pitch with smooth and unhurried quality, slow and leisurely pace, "
        "casual vocal style with a gentle smile in the tone, calm and carefree."
    ),
    "npc_photo_10": (
        "A sensitive and artistic young female voice with delicate and airy timbre, "
        "medium-high pitch with soft and fragile quality, slow and thoughtful pace, "
        "gentle vocal style with emotional nuance, introspective and tender."
    ),
    "npc_photo_11": (
        "A hyperactive and chatty young female voice with bright and rapid timbre, "
        "high pitch with bouncy and excited quality, very fast and energetic pace, "
        "enthusiastic vocal style with bubbly inflection, curious and unstoppable."
    ),
    "npc_photo_12": (
        "A strong and assertive adult female voice with firm and resonant timbre, "
        "medium-low pitch with sharp and decisive quality, quick and confident pace, "
        "commanding vocal style with protective warmth for allies, bold and direct."
    ),
    "npc_photo_13": (
        "A mischievous and playful young female voice with coquettish and bright timbre, "
        "medium-high pitch with bouncy and teasing quality, quick and lively pace, "
        "flirtatious vocal style with dramatic intonation, cheeky and fashion-conscious."
    ),
}

VOICE_DESIGN_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"
VOICES_DIR = Path(__file__).parent.parent / "frontend" / "assets" / "voices"
SAMPLE_RATE = 24000


def main():
    print(f"Loading VoiceDesign model: {VOICE_DESIGN_MODEL}")
    model = load_model(VOICE_DESIGN_MODEL)
    print(f"Model loaded. sample_rate={model.sample_rate}")

    VOICES_DIR.mkdir(parents=True, exist_ok=True)

    for npc_id, instruct in VOICE_PROFILES.items():
        txt_path = VOICES_DIR / f"{npc_id}_ref.txt"
        wav_path = VOICES_DIR / f"{npc_id}_ref.wav"

        if not txt_path.exists():
            print(f"  SKIP {npc_id}: no ref text at {txt_path}")
            continue

        ref_text = txt_path.read_text().strip()
        print(f"\n{npc_id}: \"{ref_text}\"")
        print(f"  instruct: {instruct[:80]}...")

        audio_chunks = []
        for result in model.generate_voice_design(
            text=ref_text,
            instruct=instruct,
            language="Chinese",
            temperature=0.4,  # Low temp for consistent reference voice
            max_tokens=2048,
        ):
            audio_chunks.append(result.audio)

        audio = mx.concatenate(audio_chunks, axis=0) if len(audio_chunks) > 1 else audio_chunks[0]
        audio_write(str(wav_path), audio, SAMPLE_RATE, format="wav")

        duration = audio.size / SAMPLE_RATE
        print(f"  → {wav_path} ({duration:.1f}s, {audio.size} samples)")

    print(f"\nDone! {len(VOICE_PROFILES)} voice references saved to {VOICES_DIR}")


if __name__ == "__main__":
    main()
