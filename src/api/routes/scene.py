"""Scene API routes."""

import json

from fastapi import APIRouter, HTTPException
from src.api.schemas import ApiResponse
from src.common.database import get_connection, fetch_one, fetch_all
from src.npc.dialogue import CAREER_WORKPLACE

router = APIRouter(prefix="/api/v1/scene", tags=["scene"])

# Reverse mapping: scene_id → list of career keywords
_SCENE_STAFF_CAREERS: dict[str, list[str]] = {}
for _career, _scene_id in CAREER_WORKPLACE.items():
    _SCENE_STAFF_CAREERS.setdefault(_scene_id, []).append(_career)


def _get_scene_staff(conn, scene_id: str) -> list[dict]:
    """Get NPCs who work at this scene (based on career→workplace mapping)."""
    careers = _SCENE_STAFF_CAREERS.get(scene_id, [])
    if not careers:
        return []
    placeholders = ",".join("?" for _ in careers)
    rows = fetch_all(conn,
        f"SELECT id, name, career, gender FROM npc WHERE career IN ({placeholders}) AND is_active = 1",
        careers)
    return [dict(r) for r in rows]


def _parse_json_field(value, default=None):
    """Parse a JSON field that may be a string or already parsed."""
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return value


@router.get("s")
def list_scenes():
    conn = get_connection()
    try:
        rows = fetch_all(conn, """SELECT s.*, COUNT(sn.npc_id) as npc_count
                                FROM scene s LEFT JOIN scene_npc sn ON s.id = sn.scene_id
                                GROUP BY s.id""")
        result = []
        for r in rows:
            d = dict(r)
            d["rooms"] = _parse_json_field(d.get("rooms"), [])
            d["residents"] = _parse_json_field(d.get("residents"), [])
            d["staff"] = _get_scene_staff(conn, d["id"])
            result.append(d)
        return ApiResponse(data=result)
    finally:
        conn.close()


@router.get("/{scene_id}")
def get_scene(scene_id: str, player_id: str = ""):
    conn = get_connection()
    try:
        row = fetch_one(conn, "SELECT * FROM scene WHERE id = ?", (scene_id,))
        if not row:
            raise HTTPException(404, "Scene not found")
        d = dict(row)

        # Parse JSON fields
        d["rooms"] = _parse_json_field(d.get("rooms"), [])
        d["residents"] = _parse_json_field(d.get("residents"), [])
        d["staff"] = _get_scene_staff(conn, scene_id)

        # NPCs currently in the scene
        npcs = fetch_all(conn, """SELECT n.id, n.name, n.gender, n.career,
                                n.current_mood, n.current_activity,
                                sn.role, json_extract(n.appearance, '$.avatar') as avatar,
                                json_extract(n.appearance, '$.fullbody') as fullbody,
                                json_extract(n.personality, '$') as personality
                                FROM scene_npc sn JOIN npc n ON sn.npc_id = n.id
                                WHERE sn.scene_id = ? AND n.is_active = 1""", (scene_id,))
        d["npcs"] = [dict(n) for n in npcs]

        # Items in the scene (parse function JSON field)
        items = fetch_all(conn, "SELECT * FROM item WHERE scene_id = ?", (scene_id,))
        d["items"] = [dict(i) for i in items]

        # Active events in this scene
        events = fetch_all(conn, """SELECT * FROM game_event WHERE scene_id = ?
                                  AND is_active = 1""", (scene_id,))
        d["events"] = [dict(e) for e in events]

        # Home access check for home scenes with player_id
        if d.get("scene_type") == "home" and player_id:
            from src.common.home_access import can_enter_home, get_access_error, compute_room_access
            residents = d["residents"]
            rooms = d["rooms"]

            # Detect bathroom occupancy from resident NPCs' current activity
            occupied_rooms = set()
            if residents:
                placeholders = ','.join('?' * len(residents))
                resident_npcs = fetch_all(conn,
                    f"SELECT id, current_activity FROM npc WHERE id IN ({placeholders})",
                    residents)
                for n in resident_npcs:
                    activity = n.get("current_activity", "") or ""
                    if any(kw in activity for kw in ["浴室", "洗澡", "淋浴", "泡澡", "沐浴"]):
                        occupied_rooms.add("浴室")
                        break

            # Player is a resident → full access (but bathroom may be occupied)
            if player_id in residents:
                resident_rooms = []
                for r in rooms:
                    room_name = r.get("name", "")
                    can_enter = True
                    if any(kw in room_name for kw in ["浴室"]) and "浴室" in occupied_rooms:
                        can_enter = False
                    resident_rooms.append({**r, "can_enter": can_enter})
                d["home_access"] = {
                    "can_enter": True, "is_resident": True,
                    "rooms": resident_rooms,
                }
            else:
                # Find best relationship and all player rels
                best_rel_type = "stranger"
                best_fav = -999
                player_rels: dict[str, dict] = {}
                for resident_id in residents:
                    rel = fetch_one(conn,
                        "SELECT relationship_type, favorability FROM relationship "
                        "WHERE entity_a_id = ? AND entity_a_type = 'npc' "
                        "AND entity_b_id = ? AND entity_b_type = 'player'",
                        (resident_id, player_id))
                    if rel:
                        fav = rel.get("favorability", 0)
                        player_rels[resident_id] = {
                            "relationship_type": rel.get("relationship_type", "stranger"),
                            "favorability": fav,
                        }
                        if fav > best_fav:
                            best_fav = fav
                            best_rel_type = rel.get("relationship_type", "stranger")

                if not player_rels or not can_enter_home(best_rel_type, best_fav):
                    error_info = get_access_error(best_rel_type, best_fav) if player_rels else {
                        "error": "access_denied",
                        "message": "你和这里的住户素不相识，不便打扰",
                        "required_relation": "acquaintance",
                    }
                    d["home_access"] = {
                        "can_enter": False,
                        "error": error_info.get("error", "access_denied"),
                        "message": error_info.get("message", "不便打扰"),
                        "required_relation": error_info.get("required_relation", ""),
                    }
                else:
                    rooms_with_access = compute_room_access(
                        rooms=rooms, residents=residents,
                        best_rel_type=best_rel_type, best_fav=best_fav,
                        player_rels=player_rels,
                        occupied_rooms=occupied_rooms,
                    )
                    d["home_access"] = {
                        "can_enter": True, "is_resident": False,
                        "rooms": rooms_with_access,
                        "relationship": best_rel_type,
                        "favorability": best_fav,
                    }

        return ApiResponse(data=d)
    finally:
        conn.close()


@router.get("/{scene_id}/npcs")
def get_scene_npcs(scene_id: str):
    conn = get_connection()
    try:
        rows = fetch_all(conn, """SELECT n.id, n.name, n.gender, n.career,
                                n.current_mood, n.current_activity, sn.role,
                                json_extract(n.appearance, '$.avatar') as avatar
                                FROM scene_npc sn JOIN npc n ON sn.npc_id = n.id
                                WHERE sn.scene_id = ? AND n.is_active = 1""", (scene_id,))
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()


@router.get("/{scene_id}/items")
def get_scene_items(scene_id: str):
    conn = get_connection()
    try:
        rows = fetch_all(conn, "SELECT * FROM item WHERE scene_id = ?", (scene_id,))
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()
