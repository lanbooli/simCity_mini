"""NPC API routes."""

import json
import logging
import redis as sync_redis
from fastapi import APIRouter, HTTPException
from src.api.schemas import ApiResponse, RelationshipUpdate
from src.common.database import get_connection, fetch_one, fetch_all, execute
from src.common.models import gen_id
from src.common.utils import now_iso, clamp
from config.settings import settings

logger = logging.getLogger("api")

router = APIRouter(prefix="/api/v1/npc", tags=["npc"])


@router.get("s")
def list_npcs():
    conn = get_connection()
    try:
        rows = fetch_all(conn, """SELECT id, name, gender, voice_type, personality,
                                current_scene_id, current_mood, current_activity,
                                career, home_scene_id, appearance
                                FROM npc WHERE is_active = 1""")
        result = []
        for r in rows:
            d = dict(r)
            d["personality"] = json.loads(d.get("personality", "[]"))
            try:
                d["appearance"] = json.loads(d.get("appearance", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass
            result.append(d)
        return ApiResponse(data=result)
    finally:
        conn.close()


@router.get("/{npc_id}")
def get_npc(npc_id: str):
    conn = get_connection()
    try:
        row = fetch_one(conn,
            "SELECT n.*, s.name as scene_name FROM npc n "
            "LEFT JOIN scene s ON n.current_scene_id = s.id WHERE n.id = ?",
            (npc_id,))
        if not row:
            raise HTTPException(404, "NPC not found")
        d = dict(row)
        # Parse JSON fields
        for field in ("appearance", "clothing", "personality", "schedule"):
            try:
                d[field] = json.loads(d.get(field, "{}"))
            except (json.JSONDecodeError, TypeError):
                pass

        # Get goals
        goals = fetch_all(conn,
            "SELECT * FROM goal WHERE entity_id = ? AND entity_type = 'npc' AND status = 'active'",
            (npc_id,))
        d["goals"] = [dict(g) for g in goals]

        # Get NPC→NPC relationships
        rels = fetch_all(conn, """SELECT r.*, n.name as entity_b_name FROM relationship r
                                LEFT JOIN npc n ON r.entity_b_id = n.id
                                WHERE r.entity_a_id = ? AND r.entity_a_type = 'npc'
                                AND r.entity_b_type = 'npc'""", (npc_id,))
        d["relationships"] = [dict(rel) for rel in rels]

        # Pregnancy info
        preg = fetch_one(conn,
            "SELECT * FROM pregnancy WHERE mother_id = ? AND status = 'pregnant'",
            (npc_id,))
        d["pregnancy"] = dict(preg) if preg else None

        # Children
        children = fetch_all(conn,
            "SELECT n.id, n.name, n.gender, n.birth_date FROM relationship r "
            "JOIN npc n ON r.entity_b_id = n.id "
            "WHERE r.entity_a_id = ? AND r.entity_a_type = 'npc' "
            "AND r.relationship_type = 'child' AND r.entity_b_type = 'npc'",
            (npc_id,))
        d["children"] = [dict(c) for c in children]

        # Is sleeping?
        gt = fetch_one(conn, "SELECT value FROM game_state WHERE key = 'game_time'")
        if gt:
            import json as _j2
            gtd = _j2.loads(gt["value"]) if isinstance(gt["value"], str) else gt["value"]
            gh = gtd.get("hour", 12)
            age = 25
            try:
                bd = d.get("birth_date", "2001-01-01")
                age = 2026 - int(bd.split("-")[0])
            except Exception:
                pass
            d["sleeping"] = (gh >= 22 or gh < 6) if age >= 3 else (gh >= 20 or gh < 8)
        else:
            d["sleeping"] = False

        return ApiResponse(data=d)
    finally:
        conn.close()


@router.get("/{npc_id}/relationship/{player_id}")
def get_npc_player_relationship(npc_id: str, player_id: str):
    """Get NPC→Player relationship. Always returns NPC's perspective toward the player."""
    conn = get_connection()
    try:
        # Prefer NPC→Player direction (how NPC feels about player)
        row = fetch_one(conn, """SELECT r.*, n.name as npc_name, p.name as player_name
                               FROM relationship r
                               LEFT JOIN npc n ON r.entity_a_id = n.id
                               LEFT JOIN player p ON r.entity_b_id = p.id
                               WHERE r.entity_a_id = ? AND r.entity_a_type = 'npc'
                               AND r.entity_b_id = ? AND r.entity_b_type = 'player'
                               LIMIT 1""",
                (npc_id, player_id))
        if not row:
            return ApiResponse(data={"relationship_type": "stranger", "favorability": 0, "familiarity": 0})
        return ApiResponse(data=dict(row))
    finally:
        conn.close()


@router.put("/{npc_id}/relationship/{player_id}")
def update_npc_player_relationship(npc_id: str, player_id: str, req: RelationshipUpdate):
    """Update relationship values for testing/debugging. Updates both directions."""
    conn = get_connection()
    try:
        # Find or create NPC→Player relationship
        row = fetch_one(conn, """SELECT * FROM relationship
            WHERE entity_a_id = ? AND entity_a_type = 'npc'
            AND entity_b_id = ? AND entity_b_type = 'player'""",
            (npc_id, player_id))
        if not row:
            # Create if not exists
            rid = gen_id()
            execute(conn, """INSERT INTO relationship(id, entity_a_id, entity_a_type, entity_b_id, entity_b_type,
                relationship_type, favorability, familiarity, interaction_count)
                VALUES(?, ?, 'npc', ?, 'player', 'stranger', 0, 0, 0)""",
                (rid, npc_id, player_id))
        else:
            rid = row["id"]

        # Build updates for NPC→Player
        updates = {}
        if req.favorability is not None:
            updates["favorability"] = clamp(req.favorability, -100, 100)
        if req.familiarity is not None:
            updates["familiarity"] = clamp(req.familiarity, 0, 100)
        if req.relationship_type is not None:
            updates["relationship_type"] = req.relationship_type

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [rid]
            execute(conn, f"UPDATE relationship SET {set_clause}, updated_at = datetime('now') WHERE id = ?", values)

        # Also update Player→NPC direction (for bidirectional consistency)
        prow = fetch_one(conn, """SELECT * FROM relationship
            WHERE entity_a_id = ? AND entity_a_type = 'player'
            AND entity_b_id = ? AND entity_b_type = 'npc'""",
            (player_id, npc_id))
        if prow:
            if updates:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                values = list(updates.values()) + [prow["id"]]
                execute(conn, f"UPDATE relationship SET {set_clause}, updated_at = datetime('now') WHERE id = ?", values)

        conn.commit()

        # Notify NPC process to reload its cached relationship from DB
        try:
            r = sync_redis.from_url(settings.redis_url)
            r.publish("system:rel_reload", json.dumps({"npc_id": npc_id, "player_id": player_id}))
            r.close()
            logger.info(f"Published rel_reload for npc={npc_id} player={player_id}")
        except Exception as e:
            logger.warning(f"Failed to publish rel_reload: {e}")

        # Return updated relationship
        row = fetch_one(conn, """SELECT * FROM relationship WHERE id = ?""", (rid,))
        return ApiResponse(data=dict(row))
    finally:
        conn.close()


@router.get("/{npc_id}/relationships")
def get_npc_relationships(npc_id: str):
    """Get all relationships for an NPC (both NPC↔NPC and NPC↔player)."""
    conn = get_connection()
    try:
        rels = fetch_all(conn, """SELECT r.*,
            CASE WHEN r.entity_b_type = 'npc' THEN n.name
                 WHEN r.entity_b_type = 'player' THEN p.name
                 ELSE 'Unknown' END as target_name
            FROM relationship r
            LEFT JOIN npc n ON r.entity_b_id = n.id AND r.entity_b_type = 'npc'
            LEFT JOIN player p ON r.entity_b_id = p.id AND r.entity_b_type = 'player'
            WHERE r.entity_a_id = ? AND r.entity_a_type = 'npc'
            ORDER BY r.favorability DESC""", (npc_id,))
        # Also check incoming relationships (where NPC is target)
        incoming = fetch_all(conn, """SELECT r.*,
            CASE WHEN r.entity_a_type = 'npc' THEN n.name
                 WHEN r.entity_a_type = 'player' THEN p.name
                 ELSE 'Unknown' END as target_name
            FROM relationship r
            LEFT JOIN npc n ON r.entity_a_id = n.id AND r.entity_a_type = 'npc'
            LEFT JOIN player p ON r.entity_a_id = p.id AND r.entity_a_type = 'player'
            WHERE r.entity_b_id = ? AND r.entity_b_type = 'npc'
            AND r.entity_a_id NOT IN (SELECT entity_b_id FROM relationship
                WHERE entity_a_id = ? AND entity_a_type = 'npc')
            ORDER BY r.favorability DESC""", (npc_id, npc_id))
        return ApiResponse(data={
            "outgoing": [dict(r) for r in rels],
            "incoming": [dict(r) for r in incoming],
        })
    finally:
        conn.close()


@router.get("/{npc_id}/schedule")
def get_npc_schedule(npc_id: str):
    conn = get_connection()
    try:
        row = fetch_one(conn, "SELECT schedule FROM npc WHERE id = ?", (npc_id,))
        if not row:
            raise HTTPException(404, "NPC not found")
        schedule = json.loads(row["schedule"] or "{}")
        return ApiResponse(data=schedule)
    finally:
        conn.close()
