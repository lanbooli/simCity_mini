"""
System process: orchestrates game time, weather, scenes, and events.
Runs as an independent OS process.
"""

import asyncio
import signal
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from src.common.message_broker import RedisBroker
from src.common.utils import setup_logging
from src.system.time_manager import TimeManager
from src.system.weather_manager import WeatherManager
from src.system.scene_manager import SceneManager
from src.system.event_manager import EventManager

logger = setup_logging("system", settings.log_level)


class SystemProcess:
    def __init__(self):
        self.broker = RedisBroker()
        self.time_mgr: TimeManager = None
        self.weather_mgr: WeatherManager = None
        self.scene_mgr: SceneManager = None
        self.event_mgr: EventManager = None
        self._running = False
        self._tick_count = 0
        self._weather_check_interval = 60  # check weather every 60 game minutes (30 real seconds)

    async def start(self):
        logger.info("System process starting...")
        await self.broker.connect()

        # Load state from database first (for initial weather, time, etc.)
        from src.common.database import get_connection, fetch_one
        import json
        conn = get_connection()
        try:
            weather_row = fetch_one(conn, "SELECT value FROM game_state WHERE key = 'weather'")
            initial_weather = json.loads(weather_row["value"]).get("type", "sunny") if weather_row else "sunny"
        finally:
            conn.close()

        # Initialize managers
        self.time_mgr = TimeManager(self.broker)
        self.time_mgr.load_from_db()  # Restore persisted game time
        self.weather_mgr = WeatherManager(self.broker, initial=initial_weather)
        self.scene_mgr = SceneManager(self.broker)
        self.event_mgr = EventManager(self.broker)

        # Load state from database
        self.scene_mgr.load_from_db()
        self.event_mgr.load_events()

        # Publish initial state
        await self.broker.publish("system:time", self.time_mgr.state_dict())
        await self.broker.publish("system:weather", self.weather_mgr.state_dict())

        # Handle NPC movement requests
        await self.broker.subscribe("npc_movement", self._on_npc_movement)

        logger.info(f"System process ready. Game speed: {settings.game_speed_multiplier}x")
        self._running = True

    async def _on_npc_movement(self, data: dict):
        """Handle NPC movement request."""
        npc_id = data.get("npc_id")
        scene_id = data.get("scene_id")
        if npc_id and scene_id:
            changed = await self.scene_mgr.npc_enter(npc_id, scene_id)
            if changed:
                await self.broker.publish("npc_movement_ack", {
                    "npc_id": npc_id,
                    "scene_id": scene_id,
                    "success": True,
                })

    async def run(self):
        """Main game loop."""
        await self.start()

        _health_tick = 0
        while self._running:
            _health_tick += 1
            if _health_tick % 15 == 0:
                try:
                    await self.broker.report_health(
                        "system",
                        status="alive",
                        extra={"tick": self._tick_count},
                    )
                except Exception as e:
                    logger.warning(f"System health report failed: {e}")
            await self.time_mgr.run_tick()
            self._tick_count += 1

            # Weather check every ~60 game minutes
            if self._tick_count % int(self._weather_check_interval / (settings.game_speed_multiplier / 60)) == 0:
                await self.weather_mgr.try_transition(self.time_mgr.season)

            # Event check every game hour
            if self.time_mgr.minute == 0 and self._tick_count > 1:
                await self.event_mgr.check_events(self.time_mgr.current_time_str())

            await asyncio.sleep(1.0)  # 1 real second per tick

    async def shutdown(self):
        logger.info("System process shutting down...")
        self._running = False
        # Save final state to database
        await self.broker.disconnect()


def main():
    proc = SystemProcess()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        def handler():
            logger.info(f"Received {sig.name}, shutting down...")
            asyncio.ensure_future(proc.shutdown())
        loop.add_signal_handler(sig, handler)

    try:
        loop.run_until_complete(proc.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(proc.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
