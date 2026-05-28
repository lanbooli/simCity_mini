"""
Player process: manages player state, memory, and dialogue orchestration.
"""

import asyncio
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from src.common.message_broker import RedisBroker
from src.common.database import get_connection, fetch_one
from src.common.utils import setup_logging
from src.player.memory import PlayerMemory
from src.player.dialogue_manager import PlayerDialogueManager

logger = setup_logging("player", settings.log_level)


class PlayerProcess:
    def __init__(self, player_id: str = "player_001"):
        self.player_id = player_id
        self.player_data: dict = {}
        self.broker = RedisBroker()
        self.dialogue_mgr: PlayerDialogueManager = None
        self._running = False

    async def start(self):
        logger.info(f"Player process starting: {self.player_id}")
        await self.broker.connect()

        # Load player data
        conn = get_connection()
        try:
            row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (self.player_id,))
            if row:
                self.player_data = dict(row)
                logger.info(f"Player {self.player_data['name']} loaded")
        finally:
            conn.close()

        self._running = True  # Set BEFORE creating background tasks

        self.dialogue_mgr = PlayerDialogueManager(self.broker, self.player_id)
        self.dialogue_mgr.player_name = self.player_data.get("name", "玩家")
        self.dialogue_mgr.player_attrs = self.player_data.get("attributes", '{"stamina":5,"speed":5,"strength":5}')

        # Subscribe to dialogue inbound stream
        inbound_stream = "stream:dialogue:inbound"
        await self.broker.stream_create_group(inbound_stream, "group_player")
        asyncio.create_task(self._inbound_consumer(inbound_stream))

        # Subscribe to dialogue outbound stream
        outbound_stream = "stream:dialogue:outbound"
        await self.broker.stream_create_group(outbound_stream, "group_player_out")
        asyncio.create_task(self._outbound_consumer(outbound_stream))

        # Subscribe to game time
        await self.broker.subscribe("system:time", self._on_time)

        logger.info("Player process ready")

    async def _inbound_consumer(self, stream: str):
        """Consume dialogue requests from the API layer."""
        consumer = "consumer_player_in"
        while self._running:
            try:
                msgs = await self.broker.stream_read_group(
                    stream, "group_player", consumer, count=1, block_ms=2000,
                )
                for msg_id, fields in msgs:
                    await self.dialogue_mgr.handle_dialogue_request(fields)
                    await self.broker.stream_ack(stream, "group_player", msg_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Inbound consumer error: {e}")
                await asyncio.sleep(1)

    async def _outbound_consumer(self, stream: str):
        """Consume NPC responses and forward to API."""
        consumer = "consumer_player_out"
        while self._running:
            try:
                msgs = await self.broker.stream_read_group(
                    stream, "group_player_out", consumer, count=1, block_ms=2000,
                )
                for msg_id, fields in msgs:
                    await self.dialogue_mgr.handle_dialogue_response(fields)
                    await self.broker.stream_ack(stream, "group_player_out", msg_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Outbound consumer error: {e}")
                await asyncio.sleep(1)

    async def _on_time(self, data: dict):
        pass  # Future: player-specific time-based events

    async def run(self):
        await self.start()
        while self._running:
            await asyncio.sleep(1.0)

    async def shutdown(self):
        logger.info("Player process shutting down...")
        self._running = False
        await self.broker.disconnect()


def main():
    player_id = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--player-id" and i + 1 < len(args):
            player_id = args[i + 1]
        elif not arg.startswith("--"):
            player_id = arg
    if not player_id:
        player_id = os.environ.get("PLAYER_ID", "player_001")
    proc = PlayerProcess(player_id)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(proc.shutdown()))

    try:
        loop.run_until_complete(proc.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(proc.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
