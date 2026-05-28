"""
Event manager. Schedules and dispatches game events.
"""

from src.common.database import get_connection, fetch_all, execute
from src.common.models import gen_id
from src.common.utils import game_time_to_minutes, jd


class EventManager:
    def __init__(self, broker):
        self.broker = broker
        self._active_events: list[dict] = []

    def load_events(self, db_path: str = ""):
        """Load active events from database."""
        conn = get_connection(db_path)
        try:
            rows = fetch_all(conn,
                "SELECT * FROM game_event WHERE is_active = 1 ORDER BY start_game_time")
            self._active_events = [dict(r) for r in rows]
        finally:
            conn.close()

    async def check_events(self, current_time_str: str):
        """Check for events that should activate at current game time."""
        current_mins = game_time_to_minutes(*self._parse_time(current_time_str))

        for evt in self._active_events:
            start_mins = game_time_to_minutes(*self._parse_time(evt["start_game_time"]))
            if start_mins <= current_mins and evt.get("_fired") != True:
                evt["_fired"] = True
                await self.broker.publish("system:events", {
                    "event_id": evt["id"],
                    "title": evt["title"],
                    "description": evt["description"],
                    "event_type": evt["event_type"],
                    "scene_id": evt.get("scene_id"),
                })

            # Check expiry
            if evt.get("end_game_time"):
                end_mins = game_time_to_minutes(*self._parse_time(evt["end_game_time"]))
                if current_mins >= end_mins:
                    evt["is_active"] = False

    async def create_event(self, title: str, description: str, event_type: str,
                           start_time: str, end_time: str = "", scene_id: str = "",
                           affected_entities: list = None):
        """Create and publish a new event."""
        evt = {
            "id": gen_id(),
            "event_type": event_type,
            "scene_id": scene_id or None,
            "title": title,
            "description": description,
            "start_game_time": start_time,
            "end_game_time": end_time or None,
            "is_active": True,
            "affected_entities": jd(affected_entities or []),
        }
        conn = get_connection()
        try:
            execute(conn, """INSERT INTO game_event(id, event_type, scene_id, title, description,
                           start_game_time, end_game_time, is_active, affected_entities)
                           VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (evt["id"], evt["event_type"], evt["scene_id"], evt["title"],
                     evt["description"], evt["start_game_time"], evt["end_game_time"],
                     evt["is_active"], evt["affected_entities"]))
            conn.commit()
        finally:
            conn.close()

        self._active_events.append(evt)
        await self.broker.publish("system:events", evt)

    @staticmethod
    def _parse_time(time_str: str) -> tuple[int, int, int]:
        """Parse 'Day X, HH:MM' to (day, hour, minute)."""
        try:
            parts = time_str.replace("Day ", "").split(", ")
            day = int(parts[0])
            h, m = parts[1].split(":")
            return day, int(h), int(m)
        except Exception:
            return 1, 8, 0
