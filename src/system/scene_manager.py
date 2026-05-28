"""
Scene manager. Tracks NPC presence in each scene and handles movement requests.
"""

from src.common.database import get_connection, fetch_all, execute


class SceneManager:
    def __init__(self, broker):
        self.broker = broker
        # In-memory cache: scene_id -> set of npc_ids
        self._scene_npcs: dict[str, set] = {}
        self._npc_scene: dict[str, str] = {}  # npc_id -> scene_id

    def load_from_db(self, db_path: str = ""):
        """Load initial scene-NPC mappings from SQLite."""
        conn = get_connection(db_path)
        try:
            rows = fetch_all(conn, "SELECT scene_id, npc_id, role FROM scene_npc")
            for r in rows:
                sid, nid = r["scene_id"], r["npc_id"]
                self._scene_npcs.setdefault(sid, set()).add(nid)
                self._npc_scene[nid] = sid

            # Also update npc table to match
            for nid, sid in self._npc_scene.items():
                execute(conn, "UPDATE npc SET current_scene_id = ? WHERE id = ?", (sid, nid))
            conn.commit()
        finally:
            conn.close()

    def get_scene_npcs(self, scene_id: str) -> list[str]:
        return list(self._scene_npcs.get(scene_id, set()))

    def get_npc_scene(self, npc_id: str) -> str:
        return self._npc_scene.get(npc_id, "")

    async def npc_enter(self, npc_id: str, scene_id: str) -> bool:
        """NPC enters a scene. Returns True if scene changed."""
        old_scene = self._npc_scene.get(npc_id)
        if old_scene == scene_id:
            return False

        # Remove from old scene
        if old_scene and old_scene in self._scene_npcs:
            self._scene_npcs[old_scene].discard(npc_id)

        # Add to new scene
        self._scene_npcs.setdefault(scene_id, set()).add(npc_id)
        self._npc_scene[npc_id] = scene_id

        # Update database
        conn = get_connection()
        try:
            if old_scene:
                execute(conn, "DELETE FROM scene_npc WHERE scene_id = ? AND npc_id = ? AND role != 'worker'",
                        (old_scene, npc_id))
            execute(conn, "INSERT OR REPLACE INTO scene_npc(scene_id, npc_id, role) VALUES(?, ?, 'visitor')",
                    (scene_id, npc_id))
            execute(conn, "UPDATE npc SET current_scene_id = ?, updated_at = datetime('now') WHERE id = ?",
                    (scene_id, npc_id))
            conn.commit()
        finally:
            conn.close()

        # Publish scene updates
        update = {"scene_id": scene_id, "npcs_present": self.get_scene_npcs(scene_id)}
        await self.broker.publish(f"scene:{scene_id}:update", update)

        if old_scene:
            old_update = {"scene_id": old_scene, "npcs_present": self.get_scene_npcs(old_scene)}
            await self.broker.publish(f"scene:{old_scene}:update", old_update)

        # Update Redis — both new and old scenes
        await self.broker.kv_set(f"state:scene:{scene_id}:npcs",
                                 {"npcs": self.get_scene_npcs(scene_id)})
        if old_scene:
            await self.broker.kv_set(f"state:scene:{old_scene}:npcs",
                                     {"npcs": self.get_scene_npcs(old_scene)})
        await self.broker.kv_set(f"state:npc:{npc_id}:location", {"scene_id": scene_id})

        return True

    async def player_enter(self, player_id: str, scene_id: str, room_name: str = ""):
        """Track player location in Redis with full context for status display."""
        # Load scene metadata
        scene_name = ""
        scene_type = ""
        rooms = []
        conn = get_connection()
        try:
            row = fetch_all(conn, "SELECT name, scene_type, rooms FROM scene WHERE id = ?", (scene_id,))
            if row:
                scene_name = row[0]["name"]
                scene_type = row[0].get("scene_type", "indoor")
                import json
                rooms_raw = row[0].get("rooms", "[]")
                rooms = json.loads(rooms_raw) if isinstance(rooms_raw, str) else (rooms_raw or [])
        finally:
            conn.close()

        location = {
            "scene_id": scene_id,
            "scene_name": scene_name,
            "scene_type": scene_type,
            "room_name": room_name,
            "rooms": rooms,
        }
        await self.broker.kv_set(f"state:player:{player_id}:location", location)

        # Also add player to scene npc list for NPC perception
        npcs = self.get_scene_npcs(scene_id)
        npcs.append(player_id)
        await self.broker.kv_set(f"state:scene:{scene_id}:npcs",
                                 {"npcs": npcs})

    def all_scene_ids(self) -> list[str]:
        return list(self._scene_npcs.keys())
