"""
Home access control — two-level: apartment entry + per-room permissions.

Apartment level: can you enter the building? Based on best relationship with any resident.
Room level: which specific rooms can you enter?
  - Public rooms (客厅/厨房/浴室): follow apartment-level access
  - Private rooms (bedrooms): require partner relationship with the room's owner
"""

# Access levels for public rooms indexed by relationship type + favorability
_ACCESS_TABLE = {
    "stranger":    {"min_fav": -100, "rooms": []},
    "dislike":     {"min_fav":  -30, "rooms": []},
    "enemy":       {"min_fav":  -30, "rooms": []},
    "acquaintance":{"min_fav":    0, "rooms": ["客厅"]},
    "friend":      {"min_fav":   30, "rooms": ["客厅", "厨房", "浴室"]},
    "best_friend": {"min_fav":   60, "rooms": ["客厅", "厨房", "浴室"]},
    "boyfriend":   {"min_fav":   80, "rooms": ["客厅", "厨房", "浴室"]},
    "girlfriend":  {"min_fav":   80, "rooms": ["客厅", "厨房", "浴室"]},
    "spouse":      {"min_fav":   80, "rooms": ["客厅", "厨房", "浴室"]},
}

# Partner-level relations that can enter owner's private bedroom
_PARTNER_RELATIONS = {"boyfriend", "girlfriend", "spouse"}

# Room name keywords that map to public room types
_PUBLIC_ROOM_KEYWORDS = ["客厅", "厨房", "浴室"]

# Rooms whose accessibility changes dynamically based on occupancy
# When occupied by someone, these rooms become inaccessible to others
_OCCUPIABLE_ROOM_KEYWORDS = ["浴室"]


def get_accessible_rooms(relationship_type: str, favorability: int) -> list[str]:
    """Return list of public room TYPE names the visitor can enter."""
    entry = _ACCESS_TABLE.get(relationship_type)
    if entry is None:
        return []
    if favorability < entry["min_fav"]:
        return []
    return entry["rooms"]


def can_enter_home(relationship_type: str, favorability: int) -> bool:
    """Can the visitor enter the NPC's home building at all?"""
    rooms = get_accessible_rooms(relationship_type, favorability)
    return len(rooms) > 0


def _is_public_room(room_name: str) -> bool:
    """Check if a room is a public/shared room."""
    return any(kw in room_name for kw in _PUBLIC_ROOM_KEYWORDS)


def can_enter_specific_room(
    room_name: str,
    room_access: str,
    room_owner: str,
    best_rel_type: str,
    best_fav: int,
    player_rels: dict[str, dict],
) -> bool:
    """Check if the player can enter a SPECIFIC room.

    Args:
        room_name: e.g. "苏晓萌卧室", "客厅", "厨房"
        room_access: "public" or "private"
        room_owner: NPC ID who owns this room (private rooms only)
        best_rel_type: player's best relationship type with any apartment resident
        best_fav: player's best favorability with any apartment resident
        player_rels: dict of {npc_id: {relationship_type, favorability}} for all residents
    """
    if room_access == "public":
        # Public rooms: check apartment-level access
        accessible_types = get_accessible_rooms(best_rel_type, best_fav)
        return any(t in room_name for t in accessible_types)

    # Private room: must be partner of the room's owner
    if not room_owner:
        return False

    rel = player_rels.get(room_owner, {})
    owner_rel_type = rel.get("relationship_type", "stranger")
    owner_fav = rel.get("favorability", 0)

    return owner_rel_type in _PARTNER_RELATIONS and owner_fav >= 80


def can_enter_room(relationship_type: str, favorability: int, room_name: str) -> bool:
    """DEPRECATED: use can_enter_specific_room() instead.
    Legacy check — treats all rooms as public."""
    rooms = get_accessible_rooms(relationship_type, favorability)
    for accessible in rooms:
        if accessible in room_name:
            return True
    return False


def is_resident(npc_id: str, scene_residents: list[str]) -> bool:
    """NPCs who live in this apartment have full access."""
    return npc_id in scene_residents


def get_access_error(relationship_type: str, favorability: int) -> dict:
    """Return a structured error for API responses."""
    if not can_enter_home(relationship_type, favorability):
        return {
            "error": "access_denied",
            "reason": f"你和TA还不够熟悉（当前关系：{relationship_type}，好感度：{favorability}）",
            "message": "你和TA还不够熟悉，不便打扰",
            "required_relation": "acquaintance",
            "required": "至少需要「认识的人」关系且好感度 ≥ 0",
        }
    return {
        "error": "room_restricted",
        "reason": "你的关系等级不足以进入这个区域",
        "message": "你的关系等级不足以进入这个区域",
        "required_relation": "friend",
        "accessible_rooms": get_accessible_rooms(relationship_type, favorability),
    }


def _is_occupiable_room(room_name: str) -> bool:
    """Check if a room's accessibility depends on occupancy (e.g. bathroom)."""
    return any(kw in room_name for kw in _OCCUPIABLE_ROOM_KEYWORDS)


def compute_room_access(
    rooms: list[dict],
    residents: list[str],
    best_rel_type: str,
    best_fav: int,
    player_rels: dict[str, dict],
    occupied_rooms: set | None = None,
) -> list[dict]:
    """Compute per-room access for all rooms in a home scene.

    Returns the rooms list with an added `can_enter` boolean per room.
    occupied_rooms: set of room name keywords that are currently occupied
                    (e.g. {"浴室"} means someone is in the bathroom).
    """
    occupied = occupied_rooms or set()
    result = []
    for room in rooms:
        room_name = room.get("name", "")
        room_access = room.get("access", "public")
        room_owner = room.get("owner", "")

        can_enter = can_enter_specific_room(
            room_name=room_name,
            room_access=room_access,
            room_owner=room_owner,
            best_rel_type=best_rel_type,
            best_fav=best_fav,
            player_rels=player_rels,
        )

        # Dynamic occupancy: a normally-accessible room becomes unavailable when occupied
        if can_enter and _is_occupiable_room(room_name):
            if any(kw in room_name for kw in occupied):
                can_enter = False

        result.append({**room, "can_enter": can_enter})

    return result
