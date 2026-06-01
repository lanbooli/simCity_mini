"""
Admin panel API routes — only available in DEBUG mode.
Provides endpoints for modifying NPCs, relationships, game state, and triggering test events.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from config.settings import settings
from src.common.database import get_connection, fetch_one, fetch_all, execute
from src.common.models import gen_id
from src.common.utils import clamp
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_CMD_CHANNEL = "admin:process:cmd"
PROCESS_STATUS_FILE = Path(__file__).parent.parent.parent.parent / "data" / "processes.json"

ADMIN_ENABLED = settings.admin_enabled or os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")


def _require_admin():
    if not ADMIN_ENABLED:
        raise HTTPException(404, "Not found")


# ── NPC operations ──────────────────────────────────

@router.get("/npcs")
def list_all_npcs():
    """List all NPCs with full details for admin panel."""
    _require_admin()
    conn = get_connection()
    try:
        rows = fetch_all(conn,
            "SELECT id, name, gender, personality, current_scene_id, "
            "current_mood, current_activity, attributes, is_active, is_dead, death_cause, appearance "
            "FROM npc ORDER BY name")
        result = []
        for r in rows:
            d = dict(r)
            d["personality"] = json.loads(d.get("personality", "[]"))
            d["attributes"] = json.loads(d.get("attributes", "{}"))
            d["appearance"] = json.loads(d.get("appearance", "{}"))
            result.append(d)
        return {"status": "ok", "data": result}
    finally:
        conn.close()


@router.get("/npcs/{npc_id}")
def get_npc_admin(npc_id: str):
    """Get full NPC data including attributes for admin editing."""
    _require_admin()
    conn = get_connection()
    try:
        row = fetch_one(conn,
            "SELECT * FROM npc WHERE id = ?", (npc_id,))
        if not row:
            raise HTTPException(404, "NPC not found")
        d = dict(row)
        for field in ("appearance", "clothing", "personality", "schedule", "attributes"):
            try:
                d[field] = json.loads(d.get(field, "{}") if field != "personality" else d.get(field, "[]"))
            except (json.JSONDecodeError, TypeError):
                pass
        return {"status": "ok", "data": d}
    finally:
        conn.close()


@router.post("/npcs/{npc_id}")
async def update_npc(npc_id: str, request: dict):
    """Update NPC attributes, mood, scene, activity, personality, or active status."""
    _require_admin()
    conn = get_connection()
    try:
        existing = fetch_one(conn, "SELECT * FROM npc WHERE id = ?", (npc_id,))
        if not existing:
            raise HTTPException(404, "NPC not found")

        updates = {}
        # Attributes (stamina/speed/strength)
        if "attributes" in request:
            attrs = request["attributes"]
            updates["attributes"] = json.dumps({
                "stamina": clamp(attrs.get("stamina", 5), 1, 10),
                "speed": clamp(attrs.get("speed", 5), 1, 10),
                "strength": clamp(attrs.get("strength", 5), 1, 10),
            })

        # Mood
        if "current_mood" in request:
            mood = request["current_mood"]
            if mood in ("happy", "neutral", "sad", "angry", "excited", "bored", "fear", "traumatized"):
                updates["current_mood"] = mood

        # Scene / location
        if "current_scene_id" in request:
            scene_id = request["current_scene_id"]
            updates["current_scene_id"] = scene_id
            # Also update scene_npc table
            execute(conn,
                "INSERT OR REPLACE INTO scene_npc(scene_id, npc_id, role) VALUES(?, ?, 'visitor')",
                (scene_id, npc_id))

        # Activity
        if "current_activity" in request:
            updates["current_activity"] = request["current_activity"]

        # Personality tags
        if "personality" in request:
            updates["personality"] = json.dumps(request["personality"], ensure_ascii=False)

        # Active status
        if "is_active" in request:
            updates["is_active"] = 1 if request["is_active"] else 0

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [npc_id]
            execute(conn, f"UPDATE npc SET {set_clause}, updated_at = datetime('now') WHERE id = ?", tuple(values))
            conn.commit()

        return {"status": "ok", "data": {"npc_id": npc_id, "updated": list(updates.keys())}}
    finally:
        conn.close()


@router.post("/npcs/{npc_id}/resurrect")
async def resurrect_npc(npc_id: str, request: dict = None):
    """Resurrect a dead NPC: set is_dead=0, is_active=1. Optionally reset age."""
    _require_admin()
    conn = get_connection()
    try:
        row = fetch_one(conn, "SELECT id, name, is_dead, birth_date FROM npc WHERE id = ?", (npc_id,))
        if not row:
            raise HTTPException(404, "NPC not found")
        if not row["is_dead"]:
            return {"status": "ok", "data": {"npc_id": npc_id, "message": f"{row['name']} 未死亡，无需复活"}}

        new_age = None
        if request and isinstance(request, dict):
            new_age = request.get("age")
            if new_age is not None:
                new_age = clamp(int(new_age), 1, 120)

        if new_age is not None:
            birth_year = 2026 - new_age
            new_birth = f"{birth_year:04d}-01-01"
            execute(conn,
                "UPDATE npc SET is_dead = 0, is_active = 1, death_cause = '', "
                "current_activity = '', current_item_id = '', "
                "birth_date = ?, updated_at = datetime('now') WHERE id = ?",
                (new_birth, npc_id))
            conn.commit()
            logger.info(f"Admin resurrected NPC {row['name']} ({npc_id}) at age {new_age} (birth={new_birth})")
            # Notify supervisor to start the NPC process
            try:
                import redis as _redis
                _r = _redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
                _cmd = json.dumps({"action": "start", "process": npc_id, "timestamp": datetime.now(timezone.utc).isoformat()})
                _r.publish(ADMIN_CMD_CHANNEL, _cmd)
                _r.close()
                logger.info(f"Published start command for resurrected NPC {npc_id}")
            except Exception as e:
                logger.warning(f"Failed to publish start command for NPC {npc_id}: {e}")
            return {"status": "ok", "data": {"npc_id": npc_id, "name": row["name"], "resurrected": True, "new_age": new_age}}
        else:
            execute(conn,
                "UPDATE npc SET is_dead = 0, is_active = 1, death_cause = '', "
                "current_activity = '', current_item_id = '', updated_at = datetime('now') WHERE id = ?",
                (npc_id,))
            conn.commit()
            logger.info(f"Admin resurrected NPC {row['name']} ({npc_id})")
            # Notify supervisor to start the NPC process
            try:
                import redis as _redis
                _r = _redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
                _cmd = json.dumps({"action": "start", "process": npc_id, "timestamp": datetime.now(timezone.utc).isoformat()})
                _r.publish(ADMIN_CMD_CHANNEL, _cmd)
                _r.close()
                logger.info(f"Published start command for resurrected NPC {npc_id}")
            except Exception as e:
                logger.warning(f"Failed to publish start command for NPC {npc_id}: {e}")
            return {"status": "ok", "data": {"npc_id": npc_id, "name": row["name"], "resurrected": True}}
    finally:
        conn.close()


@router.get("/npcs/{npc_id}/memories")
def get_npc_memories(npc_id: str, limit: int = 50):
    """Get NPC memory list for admin viewing."""
    _require_admin()
    conn = get_connection()
    try:
        rows = fetch_all(conn,
            "SELECT id, content, memory_type, importance, emotion, game_time, created_at "
            "FROM memory WHERE entity_id = ? AND entity_type = 'npc' "
            "ORDER BY created_at DESC LIMIT ?",
            (npc_id, limit))
        return {"status": "ok", "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/npcs/{npc_id}/dialogues")
def get_npc_dialogues(npc_id: str, limit: int = 50):
    """Get NPC dialogue history for admin viewing."""
    _require_admin()
    conn = get_connection()
    try:
        rows = fetch_all(conn,
            "SELECT d.id, d.speaker_id, d.speaker_type, d.listener_id, d.listener_type, "
            "d.content, d.favorability_change, d.game_time, d.created_at "
            "FROM dialogue d "
            "WHERE (d.speaker_id = ? AND d.speaker_type = 'npc') "
            "   OR (d.listener_id = ? AND d.listener_type = 'npc') "
            "ORDER BY d.created_at DESC LIMIT ?",
            (npc_id, npc_id, limit))
        return {"status": "ok", "data": [dict(r) for r in rows]}
    finally:
        conn.close()


# ── Relationship operations ─────────────────────────

@router.get("/relationships")
def list_all_relationships():
    """List all relationships for admin browsing."""
    _require_admin()
    conn = get_connection()
    try:
        rows = fetch_all(conn, """
            SELECT r.*,
                   COALESCE(n.name, p.name) as entity_a_name,
                   COALESCE(n2.name, p2.name) as entity_b_name
            FROM relationship r
            LEFT JOIN npc n ON r.entity_a_id = n.id AND r.entity_a_type = 'npc'
            LEFT JOIN player p ON r.entity_a_id = p.id AND r.entity_a_type = 'player'
            LEFT JOIN npc n2 ON r.entity_b_id = n2.id AND r.entity_b_type = 'npc'
            LEFT JOIN player p2 ON r.entity_b_id = p2.id AND r.entity_b_type = 'player'
            ORDER BY r.entity_a_id, r.entity_b_id
        """)
        return {"status": "ok", "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/relationships")
def set_relationship(request: dict):
    """
    Set or update a relationship between any two entities.
    Body: {entity_a_id, entity_a_type, entity_b_id, entity_b_type, ...fields}

    Convenience presets: use "preset" key instead of individual fields:
      "stranger" → fav=0, fam=0, comfort=0, type=stranger
      "friend"   → fav=50, fam=30, comfort=30, type=friend
      "lover"    → fav=85, fam=60, comfort=85, type=boyfriend/girlfriend, love_eligible=1
      "spouse"   → fav=95, fam=90, comfort=100, type=spouse, love_eligible=1
      "enemy"    → fav=-80, fam=5, comfort=0, type=enemy
    """
    _require_admin()
    conn = get_connection()
    try:
        entity_a_id = request["entity_a_id"]
        entity_a_type = request["entity_a_type"]
        entity_b_id = request["entity_b_id"]
        entity_b_type = request["entity_b_type"]

        presets = {
            "stranger": {"relationship_type": "stranger", "favorability": 0, "familiarity": 0, "intimacy_comfort": 0, "love_eligible": 0, "jealousy_level": 0},
            "friend": {"relationship_type": "friend", "favorability": 50, "familiarity": 30, "intimacy_comfort": 30, "love_eligible": 0, "jealousy_level": 0},
            "lover": {"relationship_type": "boyfriend" if request.get("target_gender") == "female" else "girlfriend", "favorability": 85, "familiarity": 60, "intimacy_comfort": 85, "love_eligible": 1, "jealousy_level": 0, "committed_since": "Day 1 · 08:00"},
            "spouse": {"relationship_type": "spouse", "favorability": 95, "familiarity": 90, "intimacy_comfort": 100, "love_eligible": 1, "jealousy_level": 0, "committed_since": "Day 1 · 08:00", "married_since": "Day 1 · 08:00"},
            "enemy": {"relationship_type": "enemy", "favorability": -80, "familiarity": 5, "intimacy_comfort": 0, "love_eligible": 0, "jealousy_level": 50},
        }

        if "preset" in request:
            preset_name = request["preset"]
            if preset_name not in presets:
                raise HTTPException(400, f"Unknown preset: {preset_name}. Available: {list(presets.keys())}")
            values = presets[preset_name]
        else:
            values = {}
            for field in ("relationship_type", "favorability", "familiarity", "intimacy_comfort",
                         "jealousy_level", "love_eligible", "interaction_count",
                         "committed_since", "married_since", "breakup_count", "divorced", "violation_count"):
                if field in request:
                    values[field] = request[field]

        # Check if relationship exists
        existing = fetch_one(conn,
            "SELECT id FROM relationship WHERE entity_a_id = ? AND entity_a_type = ? AND entity_b_id = ? AND entity_b_type = ?",
            (entity_a_id, entity_a_type, entity_b_id, entity_b_type))

        if existing:
            set_clause = ", ".join(f"{k} = ?" for k in values)
            sql_params = list(values.values()) + [existing["id"]]
            execute(conn, f"UPDATE relationship SET {set_clause}, updated_at = datetime('now') WHERE id = ?", tuple(sql_params))
        else:
            rel_id = gen_id()
            fields = ["id", "entity_a_id", "entity_a_type", "entity_b_id", "entity_b_type"] + list(values.keys())
            placeholders = ", ".join("?" * len(fields))
            field_values = [rel_id, entity_a_id, entity_a_type, entity_b_id, entity_b_type] + list(values.values())
            execute(conn, f"INSERT INTO relationship ({', '.join(fields)}) VALUES ({placeholders})", tuple(field_values))

        conn.commit()
        return {"status": "ok", "data": {"updated": True, "values": values}}
    finally:
        conn.close()


# ── Game state operations ───────────────────────────

@router.get("/game-state")
def get_game_state():
    """Get current game state snapshot."""
    _require_admin()
    conn = get_connection()
    try:
        rows = fetch_all(conn, "SELECT key, value FROM game_state")
        state = {}
        for r in rows:
            try:
                state[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                state[r["key"]] = r["value"]

        # Add counts
        state["_counts"] = {
            "npc": conn.execute("SELECT COUNT(*) as c FROM npc").fetchone()["c"],
            "scene": conn.execute("SELECT COUNT(*) as c FROM scene").fetchone()["c"],
            "relationship": conn.execute("SELECT COUNT(*) as c FROM relationship").fetchone()["c"],
            "dialogue": conn.execute("SELECT COUNT(*) as c FROM dialogue").fetchone()["c"],
            "memory": conn.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"],
        }
        return {"status": "ok", "data": state}
    finally:
        conn.close()


@router.post("/game-state")
def set_game_state(request: dict):
    """Modify game state: time, weather, season, etc."""
    _require_admin()
    conn = get_connection()
    try:
        if "game_time" in request:
            gt = request["game_time"]
            execute(conn, "INSERT OR REPLACE INTO game_state(key, value) VALUES(?, ?)",
                    ("game_time", json.dumps({"day": gt.get("day", 1), "hour": gt.get("hour", 8), "minute": gt.get("minute", 0)})))

        if "weather" in request:
            execute(conn, "INSERT OR REPLACE INTO game_state(key, value) VALUES(?, ?)",
                    ("weather", json.dumps({"type": request["weather"]})))

        conn.commit()
        return {"status": "ok", "data": {"updated": list(request.keys())}}
    finally:
        conn.close()


# ── Trigger operations (quick test) ─────────────────

@router.post("/trigger")
def trigger_event(request: dict):
    """
    Trigger a test event. Supported types:
    - npc_decide: Force NPC to run a decision cycle
    - npc_social: Force two NPCs to socialize
    - npc_confess: Force NPC to confess to player
    - npc_propose: Force NPC to propose to player
    - jealousy: Simulate NPC witnessing player intimacy with another
    - boundary_violation: Simulate boundary violation
    - reset_cooldowns: Clear all action cooldowns for an NPC
    - time_skip: Skip game time forward
    """
    _require_admin()
    event_type = request.get("type", "")
    data = request.get("data", {})

    # These triggers are published to Redis for NPC/System processes to consume
    # The admin route just publishes the event; actual processing happens in the target process
    result = {"type": event_type, "dispatched": True, "note": "Event published. Processing depends on target process running."}

    # Note: actual Redis publishing requires the broker instance.
    # We store the trigger in game_state for processes to pick up.
    conn = get_connection()
    try:
        trigger_data = {
            "type": event_type,
            "data": data,
            "triggered_at": "now",
        }
        execute(conn, "INSERT OR REPLACE INTO game_state(key, value) VALUES(?, ?)",
                ("admin_trigger", json.dumps(trigger_data)))
        conn.commit()
    finally:
        conn.close()

    return {"status": "ok", "data": result}


@router.post("/reset-all")
def reset_all_memories_and_dialogues():
    """Reset all NPC memories, dialogues, and relationships. Keeps NPCs and player intact."""
    _require_admin()
    conn = get_connection()
    try:
        # Clear dialogue table
        dialogue_count = conn.execute("SELECT COUNT(*) as c FROM dialogue").fetchone()["c"]
        execute(conn, "DELETE FROM dialogue")

        # Clear memory embeddings first (FK to memory)
        emb_count = conn.execute("SELECT COUNT(*) as c FROM memory_embedding").fetchone()["c"]
        execute(conn, "DELETE FROM memory_embedding")

        # Clear memory table
        memory_count = conn.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]
        execute(conn, "DELETE FROM memory")

        # Reset all relationships to stranger defaults
        rel_count = conn.execute("SELECT COUNT(*) as c FROM relationship").fetchone()["c"]
        execute(conn, """UPDATE relationship SET
            relationship_type = 'stranger',
            favorability = 0,
            familiarity = 0,
            intimacy_comfort = 0,
            love_eligible = 0,
            jealousy_level = 0,
            interaction_count = 0,
            committed_since = NULL,
            married_since = NULL,
            breakup_count = 0,
            divorced = 0,
            violation_count = 0,
            updated_at = datetime('now')
        """)

        conn.commit()
        return {"status": "ok", "data": {
            "dialogues_deleted": dialogue_count,
            "memories_deleted": memory_count,
            "embeddings_deleted": emb_count,
            "relationships_reset": rel_count,
        }}
    finally:
        conn.close()


@router.post("/reset-cooldowns/{npc_id}")
def reset_cooldowns(npc_id: str):
    """Reset all action cooldowns for an NPC. Useful when testing rapid interactions."""
    _require_admin()
    conn = get_connection()
    try:
        execute(conn, "INSERT OR REPLACE INTO game_state(key, value) VALUES(?, ?)",
                ("admin_reset_cooldowns", json.dumps({"npc_id": npc_id})))
        conn.commit()
        return {"status": "ok", "data": {"npc_id": npc_id, "cooldowns_reset": True}}
    finally:
        conn.close()


# ── Process management ──────────────────────────────


@router.get("/processes")
def list_processes():
    """List all managed processes with status from the supervisor's status file."""
    _require_admin()
    if not PROCESS_STATUS_FILE.exists():
        return {"status": "ok", "data": {"updated_at": None, "processes": {}}}

    try:
        data = json.loads(PROCESS_STATUS_FILE.read_text())
        return {"status": "ok", "data": data}
    except (json.JSONDecodeError, OSError) as e:
        return {"status": "ok", "data": {"updated_at": None, "processes": {}, "error": str(e)}}


@router.post("/processes/{name}/restart")
def restart_process(name: str):
    """Publish a restart command to the supervisor via Redis."""
    _require_admin()
    try:
        import redis
        r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
        cmd = json.dumps({"action": "restart", "process": name, "timestamp": datetime.now(timezone.utc).isoformat()})
        r.publish(ADMIN_CMD_CHANNEL, cmd)
        r.close()
        return {"status": "ok", "data": {"process": name, "action": "restart", "dispatched": True}}
    except Exception as e:
        raise HTTPException(500, f"Failed to dispatch restart command: {e}")


@router.post("/processes/{name}/stop")
def stop_process(name: str):
    """Publish a stop command to the supervisor via Redis."""
    _require_admin()
    try:
        import redis
        r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
        cmd = json.dumps({"action": "stop", "process": name, "timestamp": datetime.now(timezone.utc).isoformat()})
        r.publish(ADMIN_CMD_CHANNEL, cmd)
        r.close()
        return {"status": "ok", "data": {"process": name, "action": "stop", "dispatched": True}}
    except Exception as e:
        raise HTTPException(500, f"Failed to dispatch stop command: {e}")


# ── Bulk state snapshot export ──────────────────────

@router.get("/export")
def export_full_state():
    """Export full game state as JSON for debugging."""
    _require_admin()
    conn = get_connection()
    try:
        state = {
            "player": [dict(r) for r in fetch_all(conn, "SELECT * FROM player")],
            "npcs": [dict(r) for r in fetch_all(conn, "SELECT id, name, gender, personality, current_scene_id, current_mood, current_activity, attributes, is_active FROM npc")],
            "scenes": [dict(r) for r in fetch_all(conn, "SELECT * FROM scene")],
            "relationships": [dict(r) for r in fetch_all(conn, "SELECT * FROM relationship LIMIT 200")],
            "game_state": {},
        }
        for r in fetch_all(conn, "SELECT key, value FROM game_state"):
            try:
                state["game_state"][r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                state["game_state"][r["key"]] = r["value"]

        return {"status": "ok", "data": state}
    finally:
        conn.close()


# ── Model Management ───────────────────────────────

import asyncio
import httpx
from config.settings import settings

MODEL_SWITCH_CHANNEL = "admin:model:switch"
REDIS_URL = settings.redis_url


@router.get("/models")
async def list_models():
    """List current models and available models from providers."""
    _require_admin()

    provider = settings.llm_provider
    current = {
        "provider": provider,
        "main_model": settings.deepseek_main_model if provider == "deepseek" else settings.lmstudio_model,
        "social_model": settings.deepseek_social_model if provider == "deepseek" else settings.lmstudio_social_model,
    }

    # Check provider health
    provider_online = False
    available = []
    if provider == "lmstudio":
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{settings.lmstudio_base_url}/v1/models")
                if resp.status_code == 200:
                    provider_online = True
                    data = resp.json()
                    available = [m.get("id", "") for m in data.get("data", [])]
        except Exception:
            pass
        # Fallback: always include currently configured models
        if not available:
            available = [
                settings.lmstudio_model,
                settings.lmstudio_social_model,
            ]
    elif provider == "deepseek":
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{settings.deepseek_base_url}/v1/models",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                )
                if resp.status_code == 200:
                    provider_online = True
                    data = resp.json()
                    available = [m.get("id", "") for m in data.get("data", [])]
        except Exception:
            pass
        if not available:
            available = [
                settings.deepseek_main_model,
                settings.deepseek_social_model,
                "deepseek-v4-pro",
                "deepseek-v4-flash",
                "deepseek-chat",
                "deepseek-reasoner",
            ]
    else:
        available = [current["main_model"], current["social_model"]]
    # Deduplicate while preserving order
    seen = set()
    available = [m for m in available if not (m in seen or seen.add(m))]

    return {
        "status": "ok",
        "data": {
            "current": current,
            "available": available,
            "providers": ["deepseek", "lmstudio"],
            "provider_online": provider_online,
        }
    }


@router.post("/models/switch")
async def switch_model(request: dict):
    """Switch main or social model. Takes effect immediately via Redis pub/sub."""
    _require_admin()

    target = request.get("target", "main")  # "main" or "social"
    model_name = request.get("model", "").strip()

    if not model_name:
        raise HTTPException(400, "model is required")

    if target not in ("main", "social"):
        raise HTTPException(400, "target must be 'main' or 'social'")

    try:
        import redis
        r = redis.from_url(REDIS_URL)
        cmd = json.dumps({
            "action": "switch_model",
            "target": target,
            "model": model_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        r.publish(MODEL_SWITCH_CHANNEL, cmd)

        # Also update .env for persistence
        env_key = f"DEEPSEEK_{'MAIN' if target == 'main' else 'SOCIAL'}_MODEL" if settings.llm_provider == "deepseek" else f"LMSTUDIO_{'MODEL' if target == 'main' else 'SOCIAL_MODEL'}"
        _update_env_file(env_key, model_name)

        # Reload settings in-process
        if settings.llm_provider == "deepseek":
            if target == "main":
                settings.deepseek_main_model = model_name
            else:
                settings.deepseek_social_model = model_name
        else:
            if target == "main":
                settings.lmstudio_model = model_name
            else:
                settings.lmstudio_social_model = model_name

        r.close()
        return {"status": "ok", "data": {"target": target, "model": model_name, "dispatched": True}}
    except Exception as e:
        raise HTTPException(500, f"Failed to switch model: {e}")


def _update_env_file(key: str, value: str):
    """Update a key=value line in .env file."""
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if not env_path.exists():
        return

    lines = env_path.read_text().splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break

    if not updated:
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n")

@router.post("/provider/switch")
async def switch_provider(request: dict):
    """Switch LLM provider (deepseek/lmstudio) immediately via Redis pub/sub."""
    _require_admin()

    provider = request.get("provider", "").strip()
    if provider not in ("deepseek", "lmstudio"):
        raise HTTPException(400, "provider must be 'deepseek' or 'lmstudio'")

    try:
        import redis
        r = redis.from_url(REDIS_URL)
        cmd = json.dumps({
            "action": "switch_provider",
            "provider": provider,
            "kwargs": {},  # future: pass model overrides
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        r.publish(MODEL_SWITCH_CHANNEL, cmd)
        r.close()

        # Also switch models to the new provider's defaults
        if provider == "deepseek":
            main_default = settings.deepseek_main_model
            social_default = settings.deepseek_social_model
        else:
            main_default = settings.lmstudio_model
            social_default = settings.lmstudio_social_model

        for target, model in [("main", main_default), ("social", social_default)]:
            r.publish(MODEL_SWITCH_CHANNEL, json.dumps({
                "action": "switch_model",
                "target": target,
                "model": model,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        # Update .env for persistence
        _update_env_file("LLM_PROVIDER", provider)
        settings.llm_provider = provider
        logger.info("Provider switched to %s (main=%s, social=%s)", provider, main_default, social_default)
        return {"status": "ok", "provider": provider, "main_model": main_default, "social_model": social_default, "message": f"已切换到 {provider}，即时生效"}
    except Exception as e:
        logger.error("Provider switch failed: %s", e)
        raise HTTPException(500, str(e))


# ── Player Messages ──────────────────────────────

@router.get("/player/{player_id}/messages")
def get_player_messages(player_id: str, unread_only: bool = False):
    """Get messages sent to a player by NPCs."""
    conn = get_connection()
    try:
        if unread_only:
            rows = fetch_all(conn,
                "SELECT * FROM player_messages WHERE player_id = ? AND is_read = 0 "
                "ORDER BY created_at DESC LIMIT 50",
                (player_id,))
        else:
            rows = fetch_all(conn,
                "SELECT * FROM player_messages WHERE player_id = ? "
                "ORDER BY created_at DESC LIMIT 50",
                (player_id,))
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()


@router.post("/player/{player_id}/messages/read")
def mark_messages_read(player_id: str, request: dict = None):
    """Mark all messages as read, or specific message by id."""
    conn = get_connection()
    try:
        msg_id = (request or {}).get("message_id", "")
        if msg_id:
            execute(conn, "UPDATE player_messages SET is_read = 1 WHERE id = ?", (msg_id,))
        else:
            execute(conn, "UPDATE player_messages SET is_read = 1 WHERE player_id = ?",
                    (player_id,))
        conn.commit()
        return ApiResponse(data={"status": "ok"})
    finally:
        conn.close()


@router.get("/player/{player_id}/messages/unread_count")
def get_unread_count(player_id: str):
    """Get count of unread player messages."""
    conn = get_connection()
    try:
        row = fetch_one(conn,
            "SELECT COUNT(*) as cnt FROM player_messages WHERE player_id = ? AND is_read = 0",
            (player_id,))
        return ApiResponse(data={"count": row["cnt"] if row else 0})
    finally:
        conn.close()
