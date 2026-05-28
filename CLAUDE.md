# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (Python 3.14+ required)
python -m venv venv && source venv/bin/activate && pip install -r requirements.txt

# Start / stop / status
python -m src.supervisor start
python -m src.supervisor stop
python -m src.supervisor status

# Re-initialize database (⚠️ DESTROYS all dialogue/memory/relationship data)
python scripts/init_db.py

# Run tests (pytest with fakeredis for Redis)
pytest tests/ -v

# Run a single NPC process directly (for debugging)
python -m src.npc.process npc_li_ming

# Run LLM Gateway standalone
python -m src.llm.gateway

# Pre-generate career greeting audio (requires mlx_audio venv)
# Must be run once after NPC career assignments change
python scripts/pregen_greetings.py

# Verify all modules import correctly
python -c "from src.npc.process import NpcProcess; from src.npc.intimacy_engine import IntimacyEngine; from src.npc.personality import PersonalityEngine; from src.common.home_access import get_access_error; print('OK')"
```

Redis must be running on `localhost:6379`. LM Studio must be running on the host configured in `.env` (`LMSTUDIO_BASE_URL`).

## Architecture

**Multi-process design with Redis IPC.** The `Supervisor` (`src/supervisor.py`) spawns 25 child processes: 1 system, 1 LLM Gateway, 1 TTS Gateway, 1 player, 1 API server (uvicorn), and 18 NPCs. Zero shared memory — all communication through Redis.

**Three Redis mechanisms:**
- **Pub/Sub** — broadcasts (time ticks, weather changes, social events, dialogue responses, NPC state)
- **Streams** — reliable point-to-point message queues with consumer groups (LLM requests, per-NPC dialogue/social inboxes, TTS requests)
- **KV Store** — shared state (NPC/player/scene state, game time)

### Game Time & NPC Decision Frequency

**Time scaling:** `game_speed_multiplier = 15` → 1 real second = 15 game seconds. One real minute = 1 game hour. ~96 real minutes = 1 game day.

**System tick:** 1 real second per tick, advances 0.25 game minutes.

**NPC autonomous cycle:** fires every **15 game minutes** = **60 real seconds**. Within each cycle, decisions run in crisis-first priority order:

| Priority | Decision | Frequency |
|----------|----------|-----------|
| 1 | Physiology crisis | Every cycle (hunger<20 / thirst<20 / energy<10 → go home, use items) |
| 2 | Perception | Every cycle (scan scene for players/NPCs/items) |
| 3 | Inner thought | Very rare (~1% chance every 5 ticks, min 200-tick interval) |
| 4 | NPC↔NPC social handshake | Every ~2 min (30-tick cooldown) |
| 5 | Autonomous action display | Every cycle (pick new action when previous expires) |
| 6 | Intimate action check | Every cycle when player present (probability 2-50% per action, personality-driven) |
| 7 | Brain decision | Every cycle (move / greet / avoid / approach player) |
| 8 | Social feed browse | Every 30 ticks (~2 min) |
| 9 | Social feed post | Low frequency (internal cooldowns) |
| 10 | Goal evaluation | Once per game day at 23:45 |

**Key cooldowns:**
- Greeting player: 60 ticks (1 game hour)
- NPC social: 30 ticks
- Intimate actions: 60-480 game minutes depending on action type
- Dialogue idle timeout: 600 ticks (10 real minutes)

### NPC Decision Loop

**Crisis-first priority** — thirst > hunger > energy > social/free behavior. When a crisis triggers, the NPC immediately moves home (or uses items if already home) and recovers. Crisis thresholds: thirst < 20, hunger < 20, energy < 10.

**Photo NPCs** (13 out of 18) have empty schedules in the database. `generate_default_schedule()` in `movement.py` auto-creates a basic daily rhythm: leave home at ~7-8am, lunch at 12, afternoon wander, return home at ~20:00.

**NPC→player proactive interactions:** When the player enters an NPC's scene, the NPC may greet (if fav ≥ 0), avoid (if fav < 0), or initiate an action (via brain decision). All proactive interactions now include TTS voice output (fire-and-forget).

### Home & Apartment System

**5 home scenes** (apt_a/b/c/d + home_player), each with JSON `rooms` (living room, kitchen, bathroom, private bedrooms) and `residents` lists. **102 items** across all homes with `function` field: `sleep`, `cook`, `eat`, `drink`, `wash`, `entertain`, `rest`, `store`, `couple_intimate`. Beds have composite function `sleep,couple_intimate` — sleep for anyone, couple actions for partners only.

**Access control** (`src/common/home_access.py`): relationship-based room permissions.
- Stranger: denied entirely
- Acquaintance (fav ≥ 0): living room only
- Friend (fav ≥ 30): living room + kitchen + bathroom
- Partner (fav ≥ 80): all rooms including bedrooms
- Residents have full access regardless

**NPC crisis at home:** Uses `_find_room_by_function()` to locate the right room/item — sleeps in bedroom, cooks in kitchen, drinks water at sink. Activity text is contextual: "在卧室床上睡觉", "在厨房做饭", "在厨房喝水".

### 39-Set Personality System

`src/npc/personality.py` — `PersonalityEngine` class that calculates personality modifiers for intimacy, social behavior, and action bonuses. `config/npc_personality_map.json` maps each of the 18 NPCs to primary + secondary + romance personality IDs from the 39-set system.

Key modifiers:
- **intimacy_mod**: ranges from 0.0 (自闭社恐) to 2.5 (病娇偏执). Typical: 活泼乐天=1.8, 高冷禁欲=0.2, 善良温柔=1.5
- **home_style**: personality-driven home ambiance (warm/quiet/minimal/lively/etc.)
- **get_action_bonus(action_type)**: per-action probability boost based on personality affinity

Personality descriptions are rendered into all LLM prompts via `personality_desc` template variable — rich behavioral descriptions like "温柔体贴，主动为他人着想，共情能力强" supplement the simple tags.

### Intimacy Engine

`src/npc/intimacy_engine.py` — `IntimacyEngine` class that checks 12 intimate actions (喂饭, 擦嘴, 整理衣领, 系围裙, 靠肩膀, 牵手散步, 突然拥抱, 撒娇要抱抱, 做饭给你吃, 送礼物, 吹头发, 一起看电视) each autonomous cycle when the player is present.

Probability formula: `base_prob × mood_mod × personality_mod × time_mod × home_bonus × fav_bonus`, capped at 50%. Integrated into `process.py` via `_check_intimate_actions()` → `_execute_intimate_action()` which generates LLM narrative and sends to player via dialogue outbound stream with `intimate: "true"` flag.

### Dialogue Flow

Frontend WebSocket → API Server → `stream:dialogue:{npc_id}` → NPC consumes → LLM Gateway → Pub/Sub `dialogue:response` → WebSocket → Frontend.

NPC-initiated messages (greetings, actions, intimate actions) flow through `stream:dialogue:outbound` with `initiated_by_npc: "true"`.

### LLM Gateway

`src/llm/gateway.py`: standalone process consuming `stream:llm:requests` with a priority queue (CRITICAL/HIGH/MEDIUM/LOW/BATCH), 8 concurrent workers, circuit breaker with retry. Routes requests by `call_type` to either the 35B main model or 4B social model.

## Critical Constraints

**Data safety:** `scripts/init_db.py` drops and recreates ALL tables — dialogue history, memories, relationships are permanently lost. Never run it without the user's explicit consent to reset everything. For schema-only changes, use `ALTER TABLE` migrations in SQL directly instead.

**Both models are Qwen "thinking" variants** (uncensored-hauhaucs-aggressive fine-tunes). They spend 90-95% of completion tokens on internal reasoning before producing output. A simple NPC greeting consumes ~3000 reasoning tokens and takes 60-120s. **Never set `max_tokens` below 4096** for these models, or the reasoning phase will consume the entire budget leaving zero output tokens.

**Never use stop tokens** (e.g., `stop=["玩家:", "Player:"]`) with thinking models. The stop patterns match content inside the model's reasoning trace, causing premature termination before any output is produced.

**Gateway timeout:** `llm_gateway_request_timeout` is set to 300s in `config/settings.py`. The thinking models routinely need 60-180s per request.

**NPC autonomous request flood:** 18 NPCs each generate periodic `inner_thought`, `post`, and `social_open` requests through the LLM Gateway. These are priority LOW (3), but workers are blocked for 60-120s each. If the autonomous cycle fires faster than the gateway clears the queue, the backlog grows indefinitely. Reduce autonomous frequency or increase worker count if the gateway shows growing `XLEN stream:llm:requests`.

## Key Files

| File | Role |
|------|------|
| `src/supervisor.py` | Process lifecycle manager; defines NPC IDs and startup order |
| `src/npc/process.py` | NPC main loop: autonomous cycle, dialogue/social consumers, crisis resolution, intimate actions, TTS integration |
| `src/npc/dialogue.py` | All LLM-powered NPC speech: `respond_to_player`, `respond_to_action`, `generate_social_performance`, greetings, inner thoughts, posts, life events |
| `src/npc/brain.py` | Decision engine: intent generation, crisis detection, player interaction decisions |
| `src/npc/physiology.py` | Hunger/thirst/energy/social bars, age stages, death conditions, crisis detection |
| `src/npc/personality.py` | 39-set personality engine: intimacy/social modifiers, action bonuses, home style |
| `src/npc/intimacy_engine.py` | NPC→player intimate action decision engine: 12 actions, personality-driven probability with cooldowns |
| `src/npc/action_rules.py` | Player-to-NPC action system with boundary violation detection |
| `src/npc/action_selector.py` | Rule-based autonomous action selection (no LLM): picks idle/social actions with cooldowns |
| `src/npc/relationship.py` | Directed relationship graphs (favorability/familiarity/intimacy) |
| `src/npc/movement.py` | Scene movement + `generate_default_schedule()` for photo NPCs without schedules |
| `src/npc/memory.py` | Episodic memory: store/recall interactions, importance-based retention |
| `src/npc/perception.py` | Environment perception: scan Redis for players/NPCs in current scene |
| `src/npc/social_handshake.py` | Rule-based NPC-NPC social negotiation (no LLM): invitation → evaluation → performance |
| `src/npc/mood.py` | Mood state machine with intensity, decay, and event-driven transitions |
| `src/npc/social_feed.py` | Social feed manager: create posts, likes, comments, feed generation |
| `src/common/home_access.py` | Home access control: relationship→room permissions, `can_enter_home()`, `can_enter_room()` |
| `src/common/message_broker.py` | Redis abstraction (Pub/Sub + Streams + KV) |
| `src/common/database.py` | SQLite connection pool (row_factory=Row, WAL mode, foreign keys) |
| `src/llm/gateway.py` | LLM Gateway process: priority queue, circuit breaker, dual-model routing |
| `src/llm/gateway_client.py` | Client library for submitting requests to the LLM Gateway |
| `src/llm/lmstudio_client.py` | Thin httpx wrapper around LM Studio's `/v1/chat/completions` |
| `src/llm/prompts.py` | All Jinja2 prompt templates — now includes `personality_desc` in all NPC prompts |
| `src/llm/tts_gateway.py` | TTS Gateway: MLX voice cloning, sentence-level streaming audio generation |
| `src/api/server.py` | FastAPI app + WebSocket endpoint; mounts SPA frontend; home access checks |
| `src/api/websocket_manager.py` | WebSocket connection management, subscribes to Redis Pub/Sub (including home scene updates) |
| `src/api/routes/scene.py` | Scene API: list/get scenes with parsed rooms/residents JSON |
| `src/api/routes/player.py` | Player API: location endpoint (Redis + DB fallback) |
| `src/system/process.py` | System process: game clock, weather, scene management |
| `src/system/scene_manager.py` | Scene entry/exit: stores player location in Redis with full context, home access gating |
| `config/settings.py` | Pydantic BaseSettings, reads from `.env` |
| `config/game_config.yaml` | Game parameters (weather transitions, romance thresholds, intimacy decay rates) |
| `config/npc_personality_map.json` | 18 NPCs → 39-set personality ID mapping (primary + secondary + romance) |
| `scripts/init_db.py` | Database initialization: schema, seed data (scenes, NPCs, relationships, home items, player) |

## Model Routing

In `src/llm/gateway.py`, the `_CRITICAL_TYPES` set controls which model handles each `call_type`:

- **35B model** (`lmstudio_model`): `player_dialogue`, `player_action`, `confession`, `proposal`, `breakup`, `violation` — player-facing quality matters
- **4B model** (`lmstudio_social_model`): `greeting`, `inner_thought`, `action_narrative`, `social_open`, `social_reply`, `social_performance`, `post`, `comment_reply`, `goal_eval` — NPC background throughput

## Testing the Dialogue Pipeline

Submit a message directly to an NPC's dialogue stream and listen for the response:

```python
import redis.asyncio as aioredis

redis = aioredis.from_url("redis://localhost:6379")

# The field MUST be "content", not "message"
await redis.xadd("stream:dialogue:npc_wang_fang", {
    "player_id": "player_001",
    "player_name": "测试玩家",
    "content": "你好！",
    "game_time": "Day 1, 08:00",
    "context": "",
})

# Listen on pub/sub
pubsub = redis.pubsub()
await pubsub.subscribe("dialogue:response")
# Response fields: npc_id, npc_name, player_id, content, favorability_change, new_mood
```

## Testing NPC Process Directly

```python
import asyncio
from src.npc.process import NpcProcess

async def test():
    proc = NpcProcess("npc_photo_01")
    await proc.start()
    print(f"NPC: {proc.npc_data['name']}")
    print(f"Home: {proc._home_scene_name}")
    print(f"Intimacy mod: {proc._intimacy_engine.personality_engine.intimacy_mod:.2f}")
    # Simulate crisis
    proc.physiology.energy = 5.0
    crisis = proc.physiology.crisis()
    await proc._resolve_crisis(crisis, {"day": 3, "hour": 22, "minute": 0})
    print(f"After crisis: energy={proc.physiology.energy:.0f}, activity={proc.npc_data['current_activity']}")
    await proc.shutdown()

asyncio.run(test())
```

## TTS Voice System

5 NPC voice types (Chinese descriptions stored in NPC data): 温和青年男声, 年轻女孩可爱型, 低沉成熟男声, 温柔知性女声, 热情中年女声. The TTS Gateway runs in the `mlx_audio` venv (separate from the game venv) to access MLX libraries. TTS is fire-and-forget — NPC sends text response immediately, then submits TTS request async; audio chunks arrive later via `tts:chunk:*` Pub/Sub channels. NPC-initiated greetings and actions also trigger TTS.
