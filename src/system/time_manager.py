"""
Game clock manager. Ticks at configurable speed.
1 real second = GAME_SPEED_MULTIPLIER game seconds (default 120 = 2 game minutes).
"""

import asyncio
from config.settings import settings
from src.common.utils import get_day_phase, get_season, game_time_to_str


class TimeManager:
    def __init__(self, broker, day=1, hour=8, minute=0):
        self.broker = broker
        self.day = day
        self.hour = hour
        self.minute = minute
        self.total_minutes = day * 24 * 60 + hour * 60 + minute
        
    def load_from_db(self):
        """Load persisted game time from database."""
        from src.common.database import get_connection, fetch_one
        import json
        conn = get_connection()
        try:
            row = fetch_one(conn, "SELECT value FROM game_state WHERE key = 'game_time'")
            if row:
                data = json.loads(row["value"])
                self.day = data["day"]
                self.hour = data["hour"]
                self.minute = data["minute"]
                self.total_minutes = self.day * 24 * 60 + self.hour * 60 + self.minute
        except Exception:
            pass
        finally:
            conn.close()
        self.multiplier = settings.game_speed_multiplier
        self._tick_interval = 1.0  # real seconds per tick
        self._game_minutes_per_tick = self.multiplier / 60.0  # game minutes per real second

    @property
    def season(self) -> str:
        return get_season(self.day)

    @property
    def phase(self) -> str:
        return get_day_phase(self.hour)

    def state_dict(self) -> dict:
        return {
            "day": self.day,
            "hour": self.hour,
            "minute": self.minute,
            "season": self.season,
            "phase": self.phase,
            "time_str": game_time_to_str(self.day, self.hour, self.minute),
        }

    async def tick(self):
        """Advance game time by one real second's worth of game time."""
        self.total_minutes += self._game_minutes_per_tick
        # Recalculate day/hour/minute
        self.day = int(self.total_minutes // (24 * 60))
        remaining = self.total_minutes % (24 * 60)
        self.hour = int(remaining // 60)
        self.minute = int(remaining % 60)

    def current_time_str(self) -> str:
        return game_time_to_str(self.day, self.hour, self.minute)

    def save_to_db(self):
        """Save game time to database for persistence across restarts."""
        from src.common.database import get_connection, execute, fetch_one
        import json
        conn = get_connection()
        try:
            existing = fetch_one(conn, "SELECT key FROM game_state WHERE key = 'game_time'")
            if existing:
                execute(conn, "UPDATE game_state SET value = ?, updated_at = datetime('now') WHERE key = 'game_time'",
                        (json.dumps({"day": self.day, "hour": self.hour, "minute": self.minute}),))
            else:
                execute(conn, "INSERT INTO game_state(key, value) VALUES('game_time', ?)",
                        (json.dumps({"day": self.day, "hour": self.hour, "minute": self.minute}),))
            conn.commit()
        finally:
            conn.close()

    async def run_tick(self):
        """One full tick: advance time and publish."""
        await self.tick()
        # Publish every 15 game minutes (NPC decision cycle) to reduce noise
        if self.minute % 15 == 0:
            await self.broker.publish("system:time", self.state_dict())
            await self.broker.kv_set("state:game_time", self.state_dict())
            # Persist to DB every 30 game minutes
            if self.minute % 30 == 0:
                self.save_to_db()
