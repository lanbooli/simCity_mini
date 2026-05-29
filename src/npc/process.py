"""
NPC process: autonomous agent with memory, relationships, dialogue, and movement.
Each NPC runs as an independent OS process.
"""

import asyncio
import json
import os
import random
import re
import signal
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import settings
from src.common.message_broker import RedisBroker
from src.common.database import get_connection, execute, fetch_one, fetch_all
from src.common.models import gen_id
from src.common.utils import setup_logging, game_time_to_str
from src.npc.mood import MoodManager
from src.npc.movement import MovementManager, generate_default_schedule
from src.npc.memory import MemoryManager
from src.npc.relationship import RelationshipManager
from src.npc.brain import Brain
from src.npc.dialogue import DialogueHandler, CAREER_WORKPLACE, CAREER_GREETINGS, parse_stage_and_dialogue
import hashlib
from src.npc.perception import Perception
from src.npc.social_feed import SocialFeedManager
from src.npc.physiology import PhysiologyManager
from src.npc.social_handshake import (
    decide_social_intent, evaluate_invitation, confirm_handshake,
    ConfirmedActivity, scene_has,
)
from src.npc.action_selector import ActionSelector, AutoActionResult
from src.npc.intimacy_engine import IntimacyEngine
from src.llm.gateway_client import init_gateway_client

logger = setup_logging("npc", settings.log_level)


class NpcProcess:
    def __init__(self, npc_id: str):
        self.npc_id = npc_id
        self.broker = RedisBroker()
        self.npc_data: dict = {}
        self.mood_mgr: MoodManager = None
        self.movement_mgr: MovementManager = None
        self.memory_mgr: MemoryManager = None
        self.relationship_mgr: RelationshipManager = None
        self.brain: Brain = None
        self.dialogue_handler: DialogueHandler = None
        self._running = False
        self._game_time: dict = {}
        self._scene_name: str = ""
        self._scene_type: str = ""
        self._all_scene_ids: list[str] = []
        self._idle_countdown: int = 600  # 10 minutes real time = 600 ticks
        self._in_dialogue_with: str = ""
        self._weather: str = "sunny"
        self._perception: Perception = None
        self._last_seen_entities: set[str] = set()
        self._action_cooldowns: dict[str, int] = {}
        self._social_cooldown: int = 0
        self._last_action_tick: int = 0
        self._tick_counter: int = 0
        self._llm_consecutive_failures: int = 0
        self._last_inner_thought_tick: int = -300  # min interval between thoughts
        self._days_passed: int = 0
        self._dialogue_lock = asyncio.Lock()
        self.physiology: PhysiologyManager = None
        self._auto_action: AutoActionResult | None = None
        self._auto_action_remaining: int = 0
        self._intimacy_engine: IntimacyEngine = None
        self._player_together_ticks: int = 0
        self._last_player_id: str = ""
        self._tasks: list[asyncio.Task] = []
        # Travel system
        self._is_traveling: bool = False
        self._travel_remaining: float = 0.0  # game minutes until arrival
        self._travel_target: str = ""
        self._travel_room: str = ""
        self._travel_activity: str = ""
        self._travel_reason: str = ""
        self._has_bike: bool = False  # NPCs with bike travel at 0.5x time
        self._distance_cache: dict = {}

    async def start(self):
        logger.info(f"NPC process starting: {self.npc_id}")
        await self.broker.connect()

        # Initialize gateway client for LLM calls
        init_gateway_client(self.broker)

        # Initialize physiology
        self.physiology = PhysiologyManager(self.npc_data)

        # Check if NPC has bike (from attributes)
        attrs = self.npc_data.get("attributes", "{}")
        if isinstance(attrs, str):
            import json
            attrs = json.loads(attrs)
        self._has_bike = attrs.get("has_bike", False)
        self._load_npc_data()
        await self._catch_up_schedule()

        logger.info(f"NPC {self.npc_data['name']} loaded. "
                     f"Scene: {self._scene_name}")

        # Initialize subsystems
        self.mood_mgr = MoodManager(self.npc_data.get("current_mood", "neutral"))

        # Auto-generate schedule for photo NPCs with empty schedules
        raw_schedule = json.loads(self.npc_data.get("schedule", "{}"))
        if not raw_schedule and self._home_scene_id:
            from src.npc.dialogue import CAREER_WORKPLACE
            career = self.npc_data.get("career", "")
            raw_schedule = generate_default_schedule(
                self._home_scene_id, self._all_scene_ids,
                career=career, career_workplace=CAREER_WORKPLACE,
            )
            if raw_schedule:
                logger.info(f"NPC {self.npc_data['name']}: auto-generated schedule "
                           f"(career={career}, day_types={list(raw_schedule.keys())})")

        self.movement_mgr = MovementManager(
            self.npc_id,
            raw_schedule,
            self.npc_data.get("current_scene_id", ""),
        )
        self.movement_mgr.set_available_scenes(self._all_scene_ids)
        # Apply schedule retroactively: if game is past NPC's bedtime, move them home
        # (handled later in start() after event loop is ready)
        self.memory_mgr = MemoryManager(self.npc_id)
        self.memory_mgr.load_recent()
        self.relationship_mgr = RelationshipManager(self.npc_id)
        self.relationship_mgr.load_relationships()

        self.brain = Brain(
            self.npc_id, self.movement_mgr, self.mood_mgr,
            self.relationship_mgr, self.memory_mgr,
            self.npc_data, self._all_scene_ids,
        )

        self.dialogue_handler = DialogueHandler(
            self.npc_data, self.memory_mgr,
            self.relationship_mgr, self.mood_mgr,
        )

        self._intimacy_engine = IntimacyEngine(
            npc_data=self.npc_data,
            relationship_mgr=self.relationship_mgr,
            mood=self.mood_mgr.current,
            scene_type=self._scene_type,
            scene_name=self._scene_name,
            game_hour=self._game_time.get("hour", 12),
            npc_energy=self.physiology.energy if self.physiology else 50.0,
            interaction_ctx=self.dialogue_handler.interaction_ctx if self.dialogue_handler else None,
        )

        self.social_feed_mgr = SocialFeedManager(self.npc_id, self.npc_data)

        self._perception = Perception(self.npc_id, self.broker)

        self._running = True  # Set BEFORE creating background tasks

        # Subscribe to game time
        await self.broker.subscribe("system:time", self._on_time_update)
        await self.broker.subscribe("system:weather", self._on_weather_update)
        # Subscribe to relationship reload notifications (from admin API)
        await self.broker.subscribe("system:rel_reload", self._on_rel_reload)
        # Subscribe to player entered scene events (for immediate greeting)
        await self.broker.subscribe("system:player_entered", self._on_player_entered)

        # Create and subscribe to personal dialogue stream
        stream = f"stream:dialogue:{self.npc_id}"
        await self.broker.stream_create_group(stream, f"group_{self.npc_id}")
        # Start consuming dialogue stream in a background task
        self._tasks.append(asyncio.create_task(self._dialogue_consumer(stream, f"group_{self.npc_id}")))

        # Social stream (NPC→NPC interactions)
        social_stream = f"stream:social:{self.npc_id}"
        await self.broker.stream_create_group(social_stream, f"group_social_{self.npc_id}")
        self._tasks.append(asyncio.create_task(self._social_consumer(social_stream, f"group_social_{self.npc_id}")))

        # Publish initial state
        await self._publish_state()

        logger.info(f"NPC {self.npc_data['name']} ready")

    def _load_npc_data(self):
        conn = get_connection()
        try:
            row = fetch_one(conn, "SELECT * FROM npc WHERE id = ?", (self.npc_id,))
            if not row:
                raise RuntimeError(f"NPC {self.npc_id} not found in database")
            self.npc_data = dict(row)

            # Load scene name and type
            scene_id = row["current_scene_id"]
            if scene_id:
                srow = fetch_one(conn, "SELECT name, scene_type FROM scene WHERE id = ?", (scene_id,))
                if srow:
                    self._scene_name = srow["name"]
                    self._scene_type = srow.get("scene_type", "indoor")
                else:
                    self._scene_name = "未知"
                    self._scene_type = "indoor"

            # Load all scene ids for movement
            scenes = fetch_all(conn, "SELECT id FROM scene")
            self._all_scene_ids = [s["id"] for s in scenes]

            # Home scene info
            self._home_scene_id = row.get("home_scene_id", "")
            if self._home_scene_id:
                hrow = fetch_one(conn, "SELECT name FROM scene WHERE id = ?", (self._home_scene_id,))
                self._home_scene_name = hrow["name"] if hrow else ""
            else:
                self._home_scene_name = ""
        finally:
            conn.close()

    async def _on_time_update(self, data: dict):
        """Handle game time tick with perception → intention → action → reflection."""
        self._game_time = data
        self._crisis_resolved_this_tick = False
        self._tick_counter += 1

        # Travel tick: count down and handle arrival
        if self._is_traveling and self._travel_remaining > 0:
            self._travel_remaining -= 1
            if self._travel_remaining <= 0:
                arrival = self._on_arrive()
                await self.broker.publish("npc_movement", {
                    "npc_id": self.npc_id,
                    "scene_id": arrival["scene_id"],
                    "room_name": arrival["room_name"],
                    "activity": arrival["activity"],
                    "reason": arrival["reason"],
                })
                await self._publish_state()
                # Don't return - allow full cycle now that we've arrived
            else:
                if data.get("minute", 0) % 15 == 0:
                    await self._publish_state()
                return  # Still traveling, skip everything else

        # Decrement cooldowns
        if self._social_cooldown > 0:
            self._social_cooldown -= 1
        for k in list(self._action_cooldowns):
            if self._action_cooldowns[k] > 0:
                self._action_cooldowns[k] -= 1
            else:
                del self._action_cooldowns[k]
        if self._auto_action_remaining > 0:
            self._auto_action_remaining -= 1
            if self._auto_action_remaining <= 0:
                self._auto_action = None
                await self._publish_state()

        # Check idle countdown for dialogue timeout
        if self._in_dialogue_with:
            self._idle_countdown -= 1
            if self._idle_countdown <= 0:
                logger.info(f"NPC {self.npc_data['name']}: dialogue idle timeout, resuming autonomy")
                self.brain.set_in_dialogue(False)
                self._in_dialogue_with = ""

        # Natural mood decay (every game hour)
        if data.get("minute") == 0:
            self.mood_mgr.update(hours_passed=1.0)

        # Physiology tick (every game hour)
        if data.get("minute") == 0 and self.physiology:
            self.physiology.tick(1.0)
            if self.physiology.is_dead:
                logger.info(f"NPC {self.npc_data['name']} has died: {self.physiology.death_cause}")
                self._persist_death()
                self._running = False
                await self._publish_state()
                return

        # Weekly check (aging, elder death roll) — triggers every 7 game days
        if data.get("hour") == 0 and data.get("minute") == 0 and self.physiology:
            self._days_passed += 1
            if self._days_passed % 1 == 0:
                self.physiology.daily_check()
                if self.physiology.is_dead:
                    logger.info(f"NPC {self.npc_data['name']} has died: {self.physiology.death_cause}")
                    self._persist_death()
                    self._running = False
                    await self._publish_state()
                    return

        # Run autonomous decision (every ~15 game minutes)
        if data.get("minute", 0) % 15 == 0 and not self._in_dialogue_with and not self._is_traveling:
            await self._autonomous_cycle(data)

    async def _on_weather_update(self, data: dict):
        """Handle weather changes."""
        weather = data.get("type", "")
        self._weather = weather
        if weather in ("rainy", "stormy"):
            if self.mood_mgr.current == "happy":
                if hasattr(self, '_weather_bad_count'):
                    self._weather_bad_count += 1
                else:
                    self._weather_bad_count = 1
                if self._weather_bad_count >= 3:
                    self.mood_mgr.set_mood("neutral", 0.4)

    async def _on_rel_reload(self, data: dict):
        """Reload relationship from DB when API updates it (e.g., debug panel)."""
        npc_id = data.get("npc_id", "")
        player_id = data.get("player_id", "")
        if npc_id != self.npc_id or not player_id:
            return
        conn = get_connection()
        try:
            row = fetch_one(conn,
                "SELECT * FROM relationship WHERE entity_a_id = ? AND entity_a_type = 'npc' "
                "AND entity_b_id = ? AND entity_b_type = 'player'",
                (self.npc_id, player_id))
            if row:
                rel = dict(row)
                self.relationship_mgr._cache[player_id] = rel
                logger.info(f"NPC {self.npc_data['name']}: reloaded relationship for {player_id}: "
                           f"type={rel.get('relationship_type')}, fav={rel.get('favorability')}, "
                           f"fam={rel.get('familiarity')}")
        finally:
            conn.close()

    async def _on_player_entered(self, data: dict):
        """Greet player when they enter this NPC's scene.
        Only one NPC per scene greets per entry (uses Redis lock)."""
        if not data or not isinstance(data, dict):
            return
        entered_scene_id = data.get("scene_id", "")
        player_id = data.get("player_id", "")
        player_name = data.get("player_name", "玩家")

        # Only react if player entered MY scene
        current_scene = self.npc_data.get("current_scene_id", "")
        if entered_scene_id != current_scene:
            return

        # Cross-verify: check player's actual location from Redis
        try:
            player_loc = await self.broker.kv_get(f"state:player:{player_id}:location")
            if player_loc and isinstance(player_loc, dict) and player_loc.get("scene_id") != current_scene:
                logger.debug(f"NPC {self.npc_data['name']}: player {player_name} entered event says {entered_scene_id} "
                           f"but Redis location says {player_loc.get('scene_id')}, skipping")
                return
        except Exception:
            pass

        # Don't greet if in dialogue
        if self._in_dialogue_with:
            return
        if "greet" in self._action_cooldowns and self._action_cooldowns["greet"] > 0:
            return

        # Check relationship
        rel = self.relationship_mgr.get_relation(player_id)
        if rel and rel["favorability"] < 0:
            return  # Hostile — no greeting

        # Determine if NPC is at their workplace
        career = self.npc_data.get("career", "")
        at_workplace = bool(career and current_scene and CAREER_WORKPLACE.get(career) == current_scene)

        # Only greet if player is acquaintance+ (fav >= 15) OR at workplace
        fav = rel["favorability"] if rel else 0
        if fav < 15 and not at_workplace:
            return

        # Only one NPC per scene per player entry (acquire lock)
        lock_key = f"lock:greet:{entered_scene_id}:{player_id}"
        if not await self.broker.acquire_lock(lock_key, ttl_seconds=3):
            return  # Another NPC is already greeting

        logger.info(f"NPC {self.npc_data['name']}: player {player_name} entered my scene{' (workplace)' if at_workplace else ''}, greeting")
        # Execute greeting directly (same as _execute_player_greeting but without perception lookup)
        self._action_cooldowns["greet"] = 60

        # Load player data
        player_data = None
        conn = get_connection()
        try:
            row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (player_id,))
            if row:
                player_data = dict(row)
        finally:
            conn.close()

        try:
            if at_workplace and career in CAREER_GREETINGS:
                # Career greeting templates (instant, no LLM)
                templates = CAREER_GREETINGS[career]
                greeting_text = random.choice(templates)
                greeting_text = greeting_text.replace("{name}", self.npc_data["name"])
                greeting = {"content": f"（看到{player_name}，露出职业的微笑）「{greeting_text}」", "favorability_change": 0}
                pregen_path = f"/assets/audio/greetings/{self.npc_id}_{int(hashlib.md5(greeting_text.encode()).hexdigest()[:8], 16) % 10000:04d}.wav"
                import os
                frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
                if os.path.exists(frontend_dir + pregen_path):
                    greeting["audio_url"] = pregen_path
            elif at_workplace:
                # Workplace but no career template — simple rule greeting
                greeting = {"content": f"（看到{player_name}，微笑着点头示意）「你好，欢迎！」", "favorability_change": 0}
            else:
                # Non-workplace: simple personality-based greeting (instant)
                rel_type = rel["relationship_type"] if rel else "stranger"
                if rel_type in ("friend", "best_friend", "boyfriend", "girlfriend", "spouse"):
                    greeting = {"content": f"（看到{player_name}，开心地挥手）「嘿，{player_name}！真巧在这里遇到你～」", "favorability_change": 1}
                elif rel_type == "acquaintance":
                    greeting = {"content": f"（看到{player_name}，礼貌地笑了笑）「{player_name}，你好啊。」", "favorability_change": 0}
                else:
                    greeting = {"content": f"（看到{player_name}，轻轻点头示意）", "favorability_change": 0}
        except Exception as e:
            logger.warning(f"Immediate greeting failed: {e}")
            greeting = {"content": f"（看到{player_name}，友好地点了点头）", "favorability_change": 0}

        self.relationship_mgr.update_interaction(player_id, 0, other_type="player")
        self.memory_mgr.add(
            content=f"在{self._scene_name}主动向{player_name}打招呼",
            game_time=self._game_time_str(),
            importance=3,
            related_entity_id=player_id,
            related_entity_type="player",
        )

        await self.broker.stream_add("stream:dialogue:outbound", {
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "player_id": player_id,
            "content": greeting["content"],
            "favorability_change": "0",
            "new_mood": self.mood_mgr.current,
            "game_time": self._game_time_str(),
            "initiated_by_npc": "true",
            "audio_url": greeting.get("audio_url", ""),
        })

        if greeting.get("content") and not greeting.get("audio_url"):
            asyncio.create_task(self._request_tts(greeting["content"]))

    async def _autonomous_cycle(self, data: dict):
        """Crisis-first decision loop: physiology → social handshake → free behavior."""
        scene_id = self.npc_data.get("current_scene_id", "")

        # ── CRISIS CHECK (highest priority, pure rules) ──
        if self.physiology:
            crisis = self.physiology.crisis()
            if crisis:
                await self._resolve_crisis(crisis, data)
                # Continue with rest of cycle instead of returning early
                # Prioritize movement back to scheduled scene after crisis resolved

        # ── Perceive environment ──
        perception = await self._perception.perceive(
            scene_id=scene_id,
            scene_name=self._scene_name,
            scene_type=self._scene_type,
            game_time=data,
            weather=self._weather,
        )

        # ── Passive social recovery (being around people) ──
        if self.physiology and not self.physiology.is_dead:
            if perception and len(perception.npcs_present) > 0:
                # Social recovery from being around other NPCs: 3 per tick (15 game min)
                self.physiology.recover("social", 3)

        # ── Decay interaction context (physical states) ──
        if hasattr(self, 'dialogue_handler') and self.dialogue_handler:
            self.dialogue_handler.interaction_ctx.tick(15)

        # ── Inner thought (rare, only when idle, with LLM failure backoff) ──
        ticks_since_last = self._tick_counter - self._last_inner_thought_tick
        if (self._tick_counter % 5 == 0 and random.random() < 0.01
                and ticks_since_last > 200 and self._llm_consecutive_failures < 3
                and not self._in_dialogue_with):
            self._last_inner_thought_tick = self._tick_counter
            await self._emit_inner_thought(perception)

        # ── NPC↔NPC Social via Handshake ──
        if self.physiology and self.physiology.wants_social() and self._social_cooldown <= 0:
            npcs_nearby = [
                {"id": e.id, "name": e.name,
                 "scene_id": getattr(e, 'scene_id', scene_id),
                 "scene_type": "indoor",
                 "in_dialogue": getattr(e, 'in_dialogue', False)}
                for e in perception.npcs_present
            ]
            intent = decide_social_intent(
                my_id=self.npc_id, my_scene_id=scene_id,
                my_scene_type=self._scene_type,
                my_phys=self.physiology, my_rels=self.relationship_mgr,
                candidates=npcs_nearby,
            )
            if intent:
                await self._execute_social_handshake(intent, data)
                return

        # ── Autonomous action display (pure rules, no LLM) ──
        if self._auto_action_remaining <= 0:
            await self._select_and_broadcast_auto_action(data, perception)

        # ── Intimate action check (personality-driven NPC→player) ──
        intimate_fired = False
        if self._intimacy_engine:
            intimate_fired = await self._check_intimate_actions(data, perception)

        # ── Brain decision for movement / player interaction ──
        # Skip brain player actions if intimacy engine just fired (avoid double-action)
        # Skip movement decisions for one cycle after crisis resolution
        if getattr(self, '_crisis_resolved_this_tick', False):
            self._crisis_resolved_this_tick = False
            # Still allow player interaction but skip movement
            if perception and perception.players_present:
                min_decision = {"action": "idle", "scene_id": None, "activity": self.npc_data.get("current_activity", ""),
                               "social_target": None, "reason": "post_crisis_settle"}
                if self.brain:
                    player_intent = self.brain._generate_player_intent(perception)
                    if player_intent:
                        min_decision = player_intent
                decision = min_decision
            else:
                decision = {"action": "idle", "scene_id": None, "activity": self.npc_data.get("current_activity", ""),
                           "social_target": None, "reason": "post_crisis_settle"}
        else:
            decision = self.brain.decide(data, perception)

        if decision["action"] == "move" and decision["scene_id"]:
            room_name = decision.get("room_name", "")
            if not room_name and decision["scene_id"] == self._home_scene_id:
                room_name = "客厅"
            self._start_travel(decision["scene_id"], room_name, decision["activity"], decision["reason"])
            await self._publish_state()

        elif decision.get("action") == "greet_player":
            await self._execute_player_greeting(perception)

        elif decision.get("action") == "avoid_player":
            await self._execute_avoid_player(perception, decision.get("reason", ""))

        elif decision.get("action") in ("approach_player", "npc_initiated_action"):
            await self._execute_player_action(decision, perception)

        # ── Social feed (skip when LLM is degraded) ──
        if self._llm_consecutive_failures < 3:
            await self._maybe_post_to_feed(data)
            if self._tick_counter % 30 == 0:
                await self._browse_and_interact_feed(data)

        # ── Goal evaluation (end of day) ──
        if data.get("hour") == 23 and data.get("minute") == 45:
            await self._evaluate_goals()

        # ── Update state ──
        if decision.get("activity") and decision.get("activity") != self.npc_data.get("current_activity"):
            self.npc_data["current_activity"] = decision["activity"]
            await self._publish_state()

        self._last_seen_entities = {e.id for e in perception.all_entities}

    async def _select_and_broadcast_auto_action(self, data: dict, perception):
        """Pick an autonomous action via ActionSelector and broadcast it."""
        game_hour = data.get("hour", 12)

        # Build nearby NPC list for targeted actions
        nearby_npcs = [
            {"id": e.id, "name": e.name, "in_dialogue": getattr(e, "in_dialogue", False)}
            for e in perception.npcs_present
        ]

        selector = ActionSelector(
            npc_data=self.npc_data,
            relationship_mgr=self.relationship_mgr,
            mood=self.mood_mgr.current,
            scene_type=self._scene_type,
            scene_name=self._scene_name,
            game_hour=game_hour,
        )

        result = selector.select_action(
            cooldowns=self._action_cooldowns,
            nearby_npcs=nearby_npcs,
            tick_counter=self._tick_counter,
        )

        if result:
            await self._broadcast_auto_action(result)

    async def _broadcast_auto_action(self, result: AutoActionResult):
        """Publish autonomous action as social_event and update NPC state."""
        self._auto_action = result
        self._auto_action_remaining = result.duration_ticks
        self._action_cooldowns[result.action_name] = result.cooldown_ticks

        # Derive room context when at home
        current_scene_id = self.npc_data.get("current_scene_id", "")
        room_name = ""
        if self._scene_type == "home":
            room_name = self._extract_room_from_activity(result.display_text)

        await self.broker.publish("system:social_event", {
            "interaction_id": gen_id(),
            "phase": "auto_action",
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "target_type": "npc" if result.target_id else "none",
            "target_id": result.target_id,
            "target_name": result.target_name,
            "action_name": result.action_name,
            "content": result.display_text,
            "icon": result.icon,
            "animation": result.animation,
            "category": result.category,
            "duration_ticks": str(result.duration_ticks),
            "scene_id": current_scene_id,
            "scene_type": self._scene_type,
            "room_name": room_name,
            "game_time": self._game_time_str(),
        })

        await self._publish_state()

        logger.debug(f"NPC {self.npc_data['name']} auto_action: {result.display_text}")

    async def _resolve_crisis(self, crisis: str, data: dict):
        """Move NPC to a scene that satisfies the crisis need. Pure rules.
        Priority: home scene > public scene with facility.
        Recovery happens immediately upon deciding what to do.
        After crisis resolution, marks flag so _autonomous_cycle skips movement for 1 tick."""
        self._crisis_resolved_this_tick = True
        current_scene = self.npc_data.get("current_scene_id", "")
        home_id = self._home_scene_id

        # Determine which room to move to based on crisis type
        need_funcs = {"hunger": ["eat", "cook"], "thirst": ["drink"], "energy": ["sleep"]}
        needed_funcs = need_funcs.get(crisis, ["drink"])

        # ── Energy crisis: prefer going home to sleep ──
        if crisis == "energy" and home_id:
            bedroom = self._find_room_by_function(home_id, "sleep")
            room_name = bedroom["name"] if bedroom else "卧室"
            activity = f"在{room_name}床上睡觉"
            self.npc_data["current_activity"] = activity
            if current_scene == home_id:
                # Already home — set room and sleep
                self._update_scene(home_id, room_name)
                logger.info(f"NPC {self.npc_data['name']}: crisis=energy, sleeping in {room_name}")
                await self._publish_state()
                self.physiology.recover("energy", 70)
            else:
                # Go home to sleep
                logger.info(f"NPC {self.npc_data['name']}: crisis=energy, going home, room={room_name}")
                self._start_travel(home_id, room_name, activity, "crisis_energy")
                self.physiology.recover("energy", 70)
            return

        # ── Hunger / thirst at home: use kitchen items ──
        if crisis in ("hunger", "thirst") and home_id and current_scene == home_id:
            is_hunger = crisis == "hunger"
            kitchen = self._find_room_by_function(home_id, "cook") if is_hunger else self._find_room_by_function(home_id, "drink")
            if is_hunger:
                kitchen = kitchen or self._find_room_by_function(home_id, "eat")
            room_name = kitchen["name"] if kitchen else "厨房"
            activity = f"在{room_name}做饭" if is_hunger else f"在{room_name}喝水"
            self.npc_data["current_activity"] = activity
            self._update_scene(home_id, room_name)
            logger.info(f"NPC {self.npc_data['name']}: crisis={crisis}, using {room_name}")
            await self._publish_state()
            if is_hunger:
                self.physiology.recover("hunger", 60)
                self.physiology.recover("thirst", 20)
            else:
                self.physiology.recover("thirst", 60)
            return

        # ── Fallback: find scene with items that satisfy the need ──
        private_funcs = ("sleep", "wash")
        candidates = []
        for sid in self._all_scene_ids:
            if sid == current_scene:
                continue
            conn = get_connection()
            try:
                func_pattern = " OR ".join([f"function LIKE '%,{f},%' OR function LIKE '{f},%' OR function LIKE '%,{f}' OR function = '{f}'" for f in needed_funcs])
                is_private = any(f in private_funcs for f in needed_funcs)
                if is_private:
                    row = fetch_one(conn,
                        f"SELECT 1 FROM item WHERE scene_id = ? AND ({func_pattern}) AND (owner_npc_id IS NULL OR owner_npc_id = ?) LIMIT 1",
                        (sid, self.npc_id))
                else:
                    row = fetch_one(conn,
                        f"SELECT 1 FROM item WHERE scene_id = ? AND ({func_pattern}) LIMIT 1",
                        (sid,))
                if row:
                    candidates.append(sid)
            finally:
                conn.close()

        # Fallback: try home scene if no public scene found
        if not candidates and self._home_scene_id and self._home_scene_id != current_scene:
            candidates = [self._home_scene_id]

        if not candidates:
            logger.warning(f"NPC {self.npc_data['name']}: crisis={crisis}, no scene with {needed_funcs} items found!")
            return

        target = random.choice(candidates)
        # Find the specific room for this crisis in the target scene
        target_room = ""
        for nf in needed_funcs:
            found = self._find_room_by_function(target, nf)
            if found:
                target_room = found.get("name", "")
                break
        activity_text = f"在{target_room}解决需求" if target_room else f"解决{crisis}需求"
        logger.info(f"NPC {self.npc_data['name']}: crisis={crisis}, moving to {target} room={target_room}")
        self._update_scene(target, target_room)
        await self.broker.publish("npc_movement", {
            "npc_id": self.npc_id,
            "scene_id": target,
            "room_name": target_room,
            "activity": activity_text,
            "reason": f"crisis_{crisis}",
        })
        if crisis == "hunger":
            self.physiology.recover("hunger", 60)
            self.physiology.recover("thirst", 20)
        elif crisis == "thirst":
            self.physiology.recover("thirst", 60)
        elif crisis == "energy":
            self.physiology.recover("energy", 70)

    # ── Travel system ─────────────────────────────────

    def _load_distance(self, from_scene: str, to_scene: str) -> float:
        """Get walking distance between two scenes in game minutes."""
        if not self._distance_cache:
            import json, os
            try:
                config_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")
                with open(os.path.join(config_dir, "scene_distances.json"), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._distance_cache = data.get("walk_minutes", {})
            except Exception:
                self._distance_cache = {}
        minutes = self._distance_cache.get(from_scene, {}).get(to_scene, 10)
        # Check bike attribute
        if self._has_bike:
            minutes *= 0.5
        return max(minutes, 1.0)

    def _start_travel(self, target_scene: str, room_name: str = "", activity: str = "", reason: str = ""):
        """Start traveling from current scene to target. NPC disappears during travel."""
        current_scene = self.npc_data.get("current_scene_id", "")
        if current_scene == target_scene:
            # Same scene, just update room
            self._update_scene(target_scene, room_name)
            return
        distance = self._load_distance(current_scene, target_scene)
        self._is_traveling = True
        self._travel_remaining = distance
        self._travel_target = target_scene
        self._travel_room = room_name
        self._travel_activity = activity
        self._travel_reason = reason
        # Update brain to know we're going (but not there yet)
        self.npc_data["current_activity"] = f"前往{target_scene}"
        logger.info(f"NPC {self.npc_data['name']}: traveling from {current_scene} to {target_scene} "
                   f"({distance:.0f} game min{' by bike' if self._has_bike else ' walking'})")

    def _on_arrive(self):
        """Called when NPC reaches destination. Updates scene and publishes."""
        self._is_traveling = False
        self._update_scene(self._travel_target, self._travel_room)
        logger.info(f"NPC {self.npc_data['name']}: arrived at {self._travel_target}")
        return {
            "scene_id": self._travel_target,
            "room_name": self._travel_room,
            "activity": self._travel_activity,
            "reason": self._travel_reason,
        }

    def _find_room_by_function(self, scene_id: str, func: str) -> dict | None:
        """Find a room in a home scene whose items support the given function.
        
        For private functions (sleep/wash), only returns rooms where the item
        is owned by this NPC or is shared (no owner). This prevents NPCs from
        using each other's bedrooms in shared apartments.
        For common functions (cook/eat/drink), any matching item is fine."""
        private_funcs = ("sleep", "wash")
        conn = get_connection()
        try:
            if func in private_funcs:
                # Private items: owned by this NPC OR shared (no owner)
                rows = fetch_all(conn,
                    "SELECT room_name, owner_npc_id FROM item WHERE scene_id = ? AND room_name IS NOT NULL AND function IS NOT NULL AND function LIKE ?",
                    (scene_id, f'%{func}%'))
                for row in rows:
                    owner = row.get("owner_npc_id", "") or ""
                    if not owner or owner == self.npc_id:
                        return {"name": row["room_name"]}
            else:
                # Common items: any matching room is fine (kitchen/living room)
                rows = fetch_all(conn,
                    "SELECT room_name FROM item WHERE scene_id = ? AND room_name IS NOT NULL AND function IS NOT NULL AND function LIKE ?",
                    (scene_id, f'%{func}%'))
                for row in rows:
                    return {"name": row["room_name"]}
        finally:
            conn.close()
        # Fallback: scan scene rooms JSON for bedroom/kitchen
        conn = get_connection()
        try:
            srow = fetch_one(conn, "SELECT rooms FROM scene WHERE id = ?", (scene_id,))
            if srow:
                rooms = json.loads(srow["rooms"]) if isinstance(srow["rooms"], str) else (srow["rooms"] or [])
                func_to_keyword = {"sleep": "卧室", "cook": "厨房", "eat": "厨房", "drink": "厨房", "wash": "浴室"}
                keyword = func_to_keyword.get(func, "")
                for r in rooms:
                    if keyword and keyword in r.get("name", ""):
                        return {"name": r["name"]}
        finally:
            conn.close()
        return None

    async def _execute_social_handshake(self, intent, data: dict):
        """Phase 1+3: Send invitation via stream, await handshake response, then perform."""
        target_id = intent.target_id
        target_name = intent.target_name

        # Send invitation to target's social stream
        await self.broker.stream_add(f"stream:social:{target_id}", {
            "type": "social_invitation",
            "from_npc_id": self.npc_id,
            "from_npc_name": self.npc_data["name"],
            "activity": intent.activity,
            "proposed_location": intent.proposed_location,
            "reason": intent.reason,
            "scene_id": self.npc_data.get("current_scene_id", ""),
            "game_time": self._game_time_str(),
        })
        self._social_cooldown = 30
        logger.info(f"NPC {self.npc_data['name']} sent invitation to {target_name}: {intent.activity}")

    async def _execute_social(self, target_id: str, perception):
        """Phase 3: NPC→NPC social interaction."""
        if self._social_cooldown > 0:
            return

        target = next((e for e in perception.npcs_present if e.id == target_id), None)
        if not target or target.in_dialogue:
            return

        # Check we have a relationship
        rel = self.relationship_mgr.get_relation(target_id)
        if not rel or rel["favorability"] < -20:
            return

        self._social_cooldown = 30

        # Generate opening via LLM
        try:
            opening = await self.dialogue_handler.generate_social_opening(
                target_name=target.name, target_id=target_id,
                scene_name=self._scene_name, game_time=self._game_time_str(),
            )
        except Exception as e:
            logger.warning(f"Social opening LLM failed: {e}")
            opening = {"content": f"（向{target.name}微笑致意）", "favorability_change": 1}

        # Update relationship on our side
        fav_delta = opening.get("favorability_change", 0)
        self.relationship_mgr.update_interaction(target_id, fav_delta, other_type="npc")
        self.mood_mgr.affect(fav_delta)

        # Create memory
        self.memory_mgr.add(
            content=f"在{self._scene_name}与{target.name}交谈: {opening['content'][:100]}",
            game_time=self._game_time_str(),
            importance=max(3, abs(fav_delta) + 2),
            related_entity_id=target_id,
            related_entity_type="npc",
        )

        # Send to target NPC's social stream
        await self.broker.stream_add(f"stream:social:{target_id}", {
            "from_npc_id": self.npc_id,
            "from_npc_name": self.npc_data["name"],
            "content": opening["content"],
            "favorability_change": str(fav_delta),
            "scene_id": self.npc_data.get("current_scene_id", ""),
            "game_time": self._game_time_str(),
        })

        # Broadcast social event for frontend
        await self.broker.publish("system:social_event", {
            "interaction_id": gen_id(),
            "phase": "open",
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "target_type": "npc",
            "target_id": target_id,
            "target_name": target.name,
            "content": opening["content"][:120],
            "favorability_change": fav_delta,
            "scene_id": self.npc_data.get("current_scene_id", ""),
            "game_time": self._game_time_str(),
        })

        logger.info(f"NPC {self.npc_data['name']} socialized with {target.name}: {opening['content'][:50]}...")

    def _game_time_str(self) -> str:
        return game_time_to_str(
            self._game_time.get("day", 1),
            self._game_time.get("hour", 8),
            self._game_time.get("minute", 0),
        )

    async def _execute_player_greeting(self, perception):
        """Phase 4: NPC greets player entering scene."""
        player = perception.players_present[0] if perception.players_present else None
        if not player:
            return
        rel = self.relationship_mgr.get_relation(player.id)
        if not rel or rel["favorability"] < 0:
            return
        if "greet" in self._action_cooldowns:
            return
        self._action_cooldowns["greet"] = 60

        # Load player data for identity-aware greeting
        player_data = None
        conn = get_connection()
        try:
            row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (player.id,))
            if row:
                player_data = dict(row)
        finally:
            conn.close()

        try:
            # Check if NPC is at their workplace for career-aware greeting
            career = self.npc_data.get("career", "")
            current_scene = self.npc_data.get("current_scene_id", "")
            at_workplace = bool(career and current_scene and CAREER_WORKPLACE.get(career) == current_scene)

            if at_workplace and career in CAREER_GREETINGS:
                # Use pre-generated template greeting (instant, no LLM)
                import random
                import os as _os
                templates = CAREER_GREETINGS[career]
                greeting_text = random.choice(templates)
                # Format with NPC name for personalization
                greeting_text = greeting_text.replace("{name}", self.npc_data["name"])
                greeting = {"content": f"（看到{player.name}，露出职业的微笑）「{greeting_text}」", "favorability_change": 0}
                # Pre-generated audio: only use if file actually exists
                pregen_path = f"/assets/audio/greetings/{self.npc_id}_{int(hashlib.md5(greeting_text.encode()).hexdigest()[:8], 16) % 10000:04d}.wav"
                frontend_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "frontend")
                if _os.path.exists(frontend_dir + pregen_path):
                    greeting["audio_url"] = pregen_path
            else:
                greeting = await self.dialogue_handler.generate_greeting(
                    player_name=player.name, player_id=player.id,
                    scene_name=self._scene_name, game_time=self._game_time_str(),
                    player_data=player_data,
                    at_workplace=at_workplace,
                )
        except Exception as e:
            logger.warning(f"Greeting LLM failed: {e}")
            greeting = {"content": f"（看到{player.name}，友好地点了点头）", "favorability_change": 0}

        self.relationship_mgr.update_interaction(player.id, 0, other_type="player")
        self.memory_mgr.add(
            content=f"在{self._scene_name}主动向{player.name}打招呼",
            game_time=self._game_time_str(),
            importance=3,
            related_entity_id=player.id,
            related_entity_type="player",
        )

        # Send to player via outbound stream
        await self.broker.stream_add("stream:dialogue:outbound", {
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "player_id": player.id,
            "content": greeting["content"],
            "favorability_change": "0",
            "new_mood": self.mood_mgr.current,
            "game_time": self._game_time_str(),
            "initiated_by_npc": "true",
            "audio_url": greeting.get("audio_url", ""),
        })

        # Fire-and-forget TTS (skip if using pre-generated audio)
        if greeting.get("content") and not greeting.get("audio_url"):
            asyncio.create_task(self._request_tts(greeting["content"]))

    async def _execute_avoid_player(self, perception, reason: str = ""):
        """Phase 4: NPC avoids player (low favorability)."""
        player = perception.players_present[0] if perception.players_present else None
        if not player:
            return

        other_scenes = [s for s in self._all_scene_ids if s != self.npc_data.get("current_scene_id")]
        if not other_scenes:
            return
        target = random.choice(other_scenes)

        logger.info(f"NPC {self.npc_data['name']} avoiding player, moving to {target}")
        await self.broker.publish("npc_movement", {
            "npc_id": self.npc_id,
            "scene_id": target,
            "room_name": "",
            "activity": "避开玩家",
            "reason": "avoiding_player",
        })

        self.memory_mgr.add(
            content=f"因为{reason}而避开{player.name}，离开了场景",
            game_time=self._game_time_str(),
            importance=4,
            related_entity_id=player.id,
            related_entity_type="player",
        )

        rel = self.relationship_mgr.get_relation(player.id)
        if rel:
            self.relationship_mgr.update_interaction(player.id, -1, other_type="player")

    async def _execute_player_action(self, decision: dict, perception):
        """Phase 4: NPC initiates an action toward the player."""
        player = perception.players_present[0] if perception.players_present else None
        if not player:
            return
        action_name = decision.get("action_name", decision.get("action"))
        if action_name in self._action_cooldowns:
            return

        # Load player data for identity-aware action narrative
        player_data = None
        conn = get_connection()
        try:
            row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (player.id,))
            if row:
                player_data = dict(row)
        finally:
            conn.close()

        # Generate action narrative
        try:
            narrative = await self.dialogue_handler.generate_action_narrative(
                target_name=player.name, target_id=player.id,
                action_name=action_name, action_desc=decision.get("action_desc", ""),
                scene_name=self._scene_name, game_time=self._game_time_str(),
                player_data=player_data,
            )
        except Exception as e:
            logger.warning(f"Action narrative LLM failed: {e}")
            narrative = {"content": f"（对{player.name}做了{action_name}动作）", "favorability_change": 0}

        fav_delta = narrative.get("favorability_change", 0)
        self.relationship_mgr.update_interaction(player.id, fav_delta, other_type="player")
        self.mood_mgr.affect(fav_delta)
        self._action_cooldowns[action_name] = decision.get("cooldown", 60)

        self.memory_mgr.add(
            content=f"主动对{player.name}做了{action_name}动作: {narrative['content'][:100]}",
            game_time=self._game_time_str(),
            importance=max(3, abs(fav_delta) + 3),
            related_entity_id=player.id,
            related_entity_type="player",
        )

        await self.broker.stream_add("stream:dialogue:outbound", {
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "player_id": player.id,
            "content": narrative["content"],
            "favorability_change": str(fav_delta),
            "new_mood": self.mood_mgr.current,
            "game_time": self._game_time_str(),
            "initiated_by_npc": "true",
            "action_name": action_name,
        })

        await self.broker.publish("system:social_event", {
            "interaction_id": gen_id(),
            "phase": "npc_action",
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "target_type": "player",
            "target_id": player.id,
            "target_name": player.name,
            "action_name": action_name,
            "content": narrative["content"][:120],
            "favorability_change": fav_delta,
            "scene_id": self.npc_data.get("current_scene_id", ""),
            "game_time": self._game_time_str(),
        })

        # Fire-and-forget TTS
        if narrative.get("content"):
            asyncio.create_task(self._request_tts(narrative["content"]))

    # ── Intimate action descriptions for LLM narrative ──────
    _INTIMATE_ACTION_DESCS = {
        # Original
        "feed_partner": "温柔地给玩家喂饭",
        "wipe_mouth": "帮玩家擦嘴",
        "fix_collar": "帮玩家整理衣领",
        "tie_apron": "帮玩家系围裙",
        "lean_on_shoulder": "靠在玩家肩膀上",
        "hold_hands_walk": "牵起玩家的手散步",
        "sudden_hug": "突然拥抱玩家",
        "ask_for_hug": "撒娇向玩家要抱抱",
        "cook_for_player": "给玩家做饭",
        "give_gift": "送给玩家一个小礼物",
        "blow_dry_hair": "帮玩家吹头发",
        "watch_tv_together": "邀请玩家一起看电视",
        # New physical intimacy
        "stand_close": "靠近玩家身旁",
        "cheek_kiss": "在玩家脸颊上亲了一下",
        "kiss": "温柔地亲吻玩家",
        "sweet_talk": "对玩家说甜甜的情话",
        "goodbye_kiss": "在玩家出门前亲了一下",
        # New affectionate/romantic
        "head_pat": "轻轻摸了摸玩家的头",
        "back_hug": "从背后温柔地抱住玩家",
        "forehead_kiss": "在玩家额头上轻轻亲了一下",
        "playful_punch": "假装生气地轻捶了玩家一下",
        "pull_sleeve": "害羞地拉了拉玩家的衣角",
        "fix_hair": "温柔地帮玩家整理被吹乱的头发",
        "arm_in_arm": "自然地挽起玩家的手臂",
        "whisper": "靠近玩家耳边轻声低语",
        "cover_blanket": "看到玩家累了，轻轻给玩家盖上毯子",
        "bring_tea": "给玩家端来一杯热茶",
        "share_snack": "把手里的零食分给玩家",
        "cuddle": "依偎到玩家身边",
    }

    # ── Intimate action favorability deltas ──────
    _INTIMATE_FAV_DELTAS = {
        # Original
        "feed_partner": 3, "wipe_mouth": 2, "fix_collar": 2,
        "tie_apron": 2, "lean_on_shoulder": 3, "hold_hands_walk": 2,
        "sudden_hug": 3, "ask_for_hug": 2, "cook_for_player": 4,
        "give_gift": 5, "blow_dry_hair": 3, "watch_tv_together": 2,
        # New
        "stand_close": 1, "cheek_kiss": 3, "kiss": 4,
        "sweet_talk": 2, "goodbye_kiss": 3,
        "head_pat": 2, "back_hug": 3, "forehead_kiss": 4,
        "playful_punch": 1, "pull_sleeve": 1, "fix_hair": 2,
        "arm_in_arm": 2, "whisper": 2, "cover_blanket": 2,
        "bring_tea": 2, "share_snack": 1, "cuddle": 3,
    }

    async def _check_intimate_actions(self, data: dict, perception) -> bool:
        """Check and potentially trigger NPC→player intimate actions.
        Returns True if an action was executed."""
        player = perception.players_present[0] if perception.players_present else None

        # Update engine state each cycle
        self._intimacy_engine.mood = self.mood_mgr.current
        self._intimacy_engine.scene_type = self._scene_type
        self._intimacy_engine.scene_name = self._scene_name
        self._intimacy_engine.game_hour = data.get("hour", 12)
        self._intimacy_engine.npc_energy = self.physiology.energy if self.physiology else 50.0

        # Tick cooldowns
        self._intimacy_engine.tick_cooldowns()

        # Track player together time
        if player:
            if player.id == self._last_player_id:
                self._player_together_ticks += 1
            else:
                self._player_together_ticks = 1
                self._last_player_id = player.id
        else:
            self._player_together_ticks = 0
            self._last_player_id = ""

        # Check intimate actions when player present and NPC not in dialogue
        if not player or self._in_dialogue_with:
            return False

        is_weekend = data.get("day", 1) % 7 in (6, 0)
        together_minutes = self._player_together_ticks * 15

        # Get player's current activity from perception if available
        player_activity = getattr(player, "activity", "") or ""

        result = self._intimacy_engine.check_actions(
            player_id=player.id,
            player_name=player.name,
            current_activity=player_activity,
            together_minutes=together_minutes,
            is_weekend=is_weekend,
        )

        if result:
            await self._execute_intimate_action(result, player)
            return True
        return False

    async def _execute_intimate_action(self, result: dict, player):
        """Execute an NPC→player intimate action with LLM narrative."""
        action_name = result["action_name"]
        action_desc = self._INTIMATE_ACTION_DESCS.get(action_name, result["label"])
        fav_delta = self._INTIMATE_FAV_DELTAS.get(action_name, 2)

        if action_name in self._action_cooldowns:
            return

        # Load player data for identity-aware narrative
        player_data = None
        conn = get_connection()
        try:
            row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (player.id,))
            if row:
                player_data = dict(row)
        finally:
            conn.close()

        # Generate narrative via LLM
        try:
            narrative = await self.dialogue_handler.generate_action_narrative(
                target_name=player.name, target_id=player.id,
                action_name=action_name, action_desc=action_desc,
                scene_name=self._scene_name, game_time=self._game_time_str(),
                player_data=player_data,
            )
        except Exception as e:
            logger.warning(f"Intimate action LLM failed for {action_name}: {e}")
            narrative = {
                "content": f"（{action_desc}）",
                "favorability_change": fav_delta,
            }

        llm_fav = narrative.get("favorability_change", fav_delta)
        self.relationship_mgr.update_interaction(player.id, llm_fav, other_type="player")
        self.mood_mgr.affect(llm_fav)
        self._action_cooldowns[action_name] = 60

        # Record in interaction context for continuity
        if hasattr(self, 'dialogue_handler') and self.dialogue_handler:
            self.dialogue_handler.interaction_ctx.add_action(
                action_name, action_desc, narrative.get("content", "")
            )

        self.memory_mgr.add(
            content=f"主动对{player.name}做了亲密动作{action_desc}: {narrative['content'][:100]}",
            game_time=self._game_time_str(),
            importance=max(3, abs(llm_fav) + 4),
            related_entity_id=player.id,
            related_entity_type="player",
        )

        # Send to player via outbound stream
        await self.broker.stream_add("stream:dialogue:outbound", {
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "player_id": player.id,
            "content": narrative["content"],
            "favorability_change": str(llm_fav),
            "new_mood": self.mood_mgr.current,
            "game_time": self._game_time_str(),
            "initiated_by_npc": "true",
            "action_name": action_name,
            "intimate": "true",
        })

        # Broadcast as social event
        await self.broker.publish("system:social_event", {
            "interaction_id": gen_id(),
            "phase": "intimate_action",
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "target_type": "player",
            "target_id": player.id,
            "target_name": player.name,
            "action_name": action_name,
            "content": narrative["content"][:120],
            "favorability_change": llm_fav,
            "scene_id": self.npc_data.get("current_scene_id", ""),
            "game_time": self._game_time_str(),
        })

        # Fire-and-forget TTS
        if narrative.get("content"):
            asyncio.create_task(self._request_tts(narrative["content"]))

        logger.info(f"NPC {self.npc_data['name']} intimate action {action_name} → {player.name}")

    async def _emit_inner_thought(self, perception):
        """Phase 5: Emit a brief inner thought visible to the player."""
        if self._llm_consecutive_failures >= 3:
            return
        try:
            thought = await self.dialogue_handler.generate_inner_thought(
                scene_name=self._scene_name,
                game_time=self._game_time_str(),
                weather=self._weather,
            )
            self._llm_consecutive_failures = 0
        except Exception:
            self._llm_consecutive_failures += 1
            return

        await self.broker.publish("system:social_event", {
            "interaction_id": gen_id(),
            "phase": "inner_thought",
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "target_type": "none",
            "target_id": "",
            "target_name": "",
            "content": thought,
            "scene_id": self.npc_data.get("current_scene_id", ""),
            "game_time": self._game_time_str(),
        })

    async def _maybe_post_to_feed(self, data: dict):
        """Phase 10: Check and generate social feed post via LLM."""
        personality = json.loads(self.npc_data.get("personality", "[]"))
        mood = self.mood_mgr.current
        has_event = self._tick_counter - self.social_feed_mgr._last_browse_tick < 60

        if not self.social_feed_mgr.should_post(personality, mood,
                                                 self._tick_counter, has_event):
            return

        # Get recent memory for context
        recent = self.memory_mgr.recent_memories[:3] if hasattr(self.memory_mgr, 'recent_memories') else []
        recent_text = "; ".join([m.get("content", "")[:80] for m in recent]) if recent else ""

        try:
            content = await self.dialogue_handler.generate_post_content(
                scene_name=self._scene_name,
                game_time=self._game_time_str(),
                recent_memory=recent_text,
            )
            self._llm_consecutive_failures = 0
        except Exception as e:
            self._llm_consecutive_failures += 1
            logger.warning(f"Post generation LLM failed (failures={self._llm_consecutive_failures}): {e}")
            return

        if not content or content.startswith("（"):
            return

        # Determine visibility based on personality
        visibility = "public"
        if "害羞" in personality or "内向" in personality:
            visibility = "friends"

        post_id = self.social_feed_mgr.create_post(
            content=content,
            post_type="general",
            visibility=visibility,
            scene_id=self.npc_data.get("current_scene_id", ""),
            mood=mood,
            game_time=self._game_time_str(),
        )

        logger.info(f"NPC {self.npc_data['name']} posted to feed: {content[:50]}...")

        # Broadcast as social event
        await self.broker.publish("system:social_event", {
            "interaction_id": gen_id(),
            "phase": "feed_post",
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "target_type": "none",
            "target_id": "",
            "target_name": "",
            "content": content[:120],
            "post_id": post_id,
            "scene_id": self.npc_data.get("current_scene_id", ""),
            "game_time": self._game_time_str(),
        })

    async def _browse_and_interact_feed(self, data: dict):
        """Phase 10: NPC browses social feed and may like/comment."""
        self.social_feed_mgr._last_browse_tick = self._tick_counter

        feed = self.social_feed_mgr.get_feed(self.npc_id, "npc", limit=5)
        if not feed:
            return

        personality = json.loads(self.npc_data.get("personality", "[]"))
        is_outgoing = "外向" in personality or "开朗" in personality

        for post in feed:
            if post["author_id"] == self.npc_id:
                continue

            # Like probability
            like_prob = 0.6 if self.relationship_mgr.get_or_create_relation(
                post["author_id"], post.get("author_type", "npc")
            ).get("relationship_type", "stranger") != "stranger" else (0.15 if is_outgoing else 0.05)

            if random.random() < like_prob:
                self.social_feed_mgr.like_post(post["id"], self.npc_id, "npc")

            # Comment probability
            comment_prob = 0.2 if like_prob > 0.15 else 0.03
            if random.random() < comment_prob and post.get("comment_count", 0) < 10:
                try:
                    reply = await self.dialogue_handler.generate_comment_reply(
                        post_content=post.get("content", ""),
                        comment_content="",
                        commenter_name=post.get("author_name", "某人"),
                        commenter_id=post["author_id"],
                    )
                    if reply and not reply.startswith("（"):
                        self.social_feed_mgr.add_comment(
                            post["id"], self.npc_id, "npc",
                            reply, self._game_time_str(),
                        )
                except Exception:
                    pass

    async def _evaluate_goals(self):
        """Phase 6: Evaluate active goal progress via LLM at end of day."""
        conn = get_connection()
        try:
            goals = fetch_all(conn, """SELECT * FROM goal
                WHERE entity_id = ? AND entity_type = 'npc' AND status = 'active'
                ORDER BY priority DESC LIMIT 3""", (self.npc_id,))
        finally:
            conn.close()

        for goal in goals:
            try:
                result = await self.dialogue_handler.evaluate_goal(dict(goal))
                delta = result.get("progress_delta", 0.0)
                thought = result.get("thought", "")
                if delta > 0:
                    new_progress = min(1.0, goal["progress"] + delta)
                    conn = get_connection()
                    try:
                        execute(conn, "UPDATE goal SET progress = ?, updated_at = datetime('now') WHERE id = ?",
                                (new_progress, goal["id"]))
                        if new_progress >= 1.0:
                            execute(conn, "UPDATE goal SET status = 'completed', completed_at = datetime('now') WHERE id = ?",
                                    (goal["id"],))
                        conn.commit()
                    finally:
                        conn.close()
                    if thought:
                        self.memory_mgr.add(
                            content=f"目标进展: {thought}",
                            game_time=self._game_time_str(),
                            importance=4,
                            related_entity_id="",
                            related_entity_type="npc",
                        )
            except Exception as e:
                logger.warning(f"Goal eval failed for {goal['id']}: {e}")

    async def _dialogue_consumer(self, stream: str, group: str):
        """Background task: consume dialogue requests from Redis stream."""
        consumer_name = f"consumer_{self.npc_id}"
        while self._running:
            try:
                messages = await self.broker.stream_read_group(
                    stream, group, consumer_name, count=1, block_ms=2000,
                )
                for msg_id, fields in messages:
                    await self._handle_dialogue(fields)
                    await self.broker.stream_ack(stream, group, msg_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dialogue consumer error: {e}")
                await asyncio.sleep(1)

    async def _social_consumer(self, stream: str, group: str):
        """Background task: consume NPC→NPC social interactions."""
        consumer_name = f"consumer_social_{self.npc_id}"
        while self._running:
            try:
                messages = await self.broker.stream_read_group(
                    stream, group, consumer_name, count=1, block_ms=2000,
                )
                for msg_id, fields in messages:
                    await self._handle_social(fields)
                    await self.broker.stream_ack(stream, group, msg_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Social consumer error: {e}")
                await asyncio.sleep(1)

    async def _handle_social(self, fields: dict):
        """Process incoming social interaction. Routes handshake invitations vs legacy."""
        msg_type = self._decode_field(fields, "type", "legacy")
        from_npc_id = self._decode_field(fields, "from_npc_id", "")
        from_npc_name = self._decode_field(fields, "from_npc_name", "")
        game_time = self._decode_field(fields, "game_time", self._game_time_str())

        if not from_npc_id:
            return

        # ── NEW: Handshake Invitation ──
        if msg_type == "social_invitation":
            from src.npc.social_handshake import SocialIntent, evaluate_invitation, HandshakeDecision, ConfirmedActivity
            intent = SocialIntent(
                target_id=self.npc_id, target_name=self.npc_data["name"],
                activity=self._decode_field(fields, "activity", "闲聊"),
                proposed_location=self._decode_field(fields, "proposed_location", ""),
                reason=self._decode_field(fields, "reason", ""),
            )
            response = evaluate_invitation(
                intent=intent,
                target_id=self.npc_id,
                target_phys=self.physiology,
                target_rels=self.relationship_mgr,
                target_scene_id=self.npc_data.get("current_scene_id", ""),
                target_scene_type=self._scene_type,
                target_in_dialogue=bool(self._in_dialogue_with),
            )

            if response.decision == HandshakeDecision.ACCEPT:
                # Both recover social
                if self.physiology:
                    self.physiology.recover("social", 25)
                fav_delta = 1 + (1 if self.physiology and self.physiology.social < 30 else 0)

                # Build participants for fused LLM call
                rel = self.relationship_mgr.get_or_create_relation(from_npc_id, "npc")
                participants = [
                    {"name": from_npc_name, "role_tag": "host",
                     "personality": "", "current_needs": "",
                     "relationship_to_other": f"{self._rel_type_cn(rel.get('relationship_type','stranger'))}，好感度{rel.get('favorability',0)}"},
                    {"name": self.npc_data["name"], "role_tag": "guest",
                     "personality": ", ".join(json.loads(self.npc_data.get("personality", "[]"))),
                     "current_needs": self.physiology.summary() if self.physiology else "状态良好",
                     "relationship_to_other": f"{self._rel_type_cn(rel.get('relationship_type','stranger'))}，好感度{rel.get('favorability',0)}"},
                ]

                try:
                    perf = await self.dialogue_handler.generate_social_performance(
                        activity=intent.activity,
                        location=self._scene_name,
                        duration_hint="short",
                        participants=participants,
                        shared_context=f"{from_npc_name}邀请{self.npc_data['name']}{intent.activity}。",
                    )
                except Exception as e:
                    logger.warning(f"Social performance LLM failed: {e}")
                    perf = {"dialogue_sequence": [
                        {"speaker": from_npc_name, "text": f"一起{intent.activity}吧？", "action": "微笑着说", "emotion": "友好"},
                        {"speaker": self.npc_data["name"], "text": "好啊。", "action": "点点头", "emotion": "平静"},
                    ], "end_condition": "natural"}

                # Update relationships both ways
                self.relationship_mgr.update_interaction(from_npc_id, fav_delta, other_type="npc")
                self.mood_mgr.affect(fav_delta)

                # Memory
                self.memory_mgr.add(
                    content=f"{from_npc_name}邀请我{intent.activity}，聊了一会儿",
                    game_time=game_time, importance=3,
                    related_entity_id=from_npc_id, related_entity_type="npc",
                )

                # Broadcast full dialogue sequence
                for turn in perf.get("dialogue_sequence", []):
                    await self.broker.publish("system:social_event", {
                        "interaction_id": gen_id(),
                        "phase": "performance",
                        "npc_id": self.npc_id if turn["speaker"] == self.npc_data["name"] else from_npc_id,
                        "npc_name": turn["speaker"],
                        "target_type": "npc",
                        "target_id": from_npc_id if turn["speaker"] == self.npc_data["name"] else self.npc_id,
                        "target_name": from_npc_name if turn["speaker"] == self.npc_data["name"] else self.npc_data["name"],
                        "content": f"{turn['text']}（{turn.get('action', '')}）",
                        "favorability_change": fav_delta,
                        "scene_id": self.npc_data.get("current_scene_id", ""),
                        "game_time": game_time,
                    })

                logger.info(f"NPC {self.npc_data['name']} social performance with {from_npc_name}: "
                            f"{len(perf.get('dialogue_sequence', []))} turns")
            else:
                # Rejected — just log
                logger.info(f"NPC {self.npc_data['name']} rejected invitation from {from_npc_name}: {response.reason}")
            return

        # ── LEGACY: old social_open/social_reply flow ──
        content = self._decode_field(fields, "content", "")
        if not content:
            return

        logger.info(f"NPC {self.npc_data['name']} received social from {from_npc_name}: {content[:50]}...")

        rel = self.relationship_mgr.get_or_create_relation(from_npc_id, "npc")
        try:
            reply = await self.dialogue_handler.respond_to_npc(
                other_npc_name=from_npc_name, other_npc_id=from_npc_id,
                other_message=content,
                scene_name=self._scene_name, game_time=game_time,
            )
        except Exception as e:
            logger.warning(f"Social reply LLM failed: {e}")
            reply = {"content": f"（对{from_npc_name}点了点头）", "favorability_change": 0}

        fav_delta = reply.get("favorability_change", 0)
        self.relationship_mgr.update_interaction(from_npc_id, fav_delta, other_type="npc")
        self.mood_mgr.affect(fav_delta)
        self.memory_mgr.add(
            content=f"{from_npc_name}在{self._scene_name}对我说: {content[:100]}; 我回应了",
            game_time=game_time, importance=max(3, abs(fav_delta) + 2),
            related_entity_id=from_npc_id, related_entity_type="npc",
        )
        self._save_social_dialogue(from_npc_id, from_npc_name, content, reply["content"], fav_delta, game_time)
        await self.broker.publish("system:social_event", {
            "interaction_id": gen_id(), "phase": "reply",
            "npc_id": self.npc_id, "npc_name": self.npc_data["name"],
            "target_type": "npc", "target_id": from_npc_id, "target_name": from_npc_name,
            "content": reply["content"][:120], "favorability_change": fav_delta,
            "scene_id": self.npc_data.get("current_scene_id", ""), "game_time": game_time,
        })

    def _save_social_dialogue(self, other_npc_id: str, other_npc_name: str,
                              their_msg: str, my_response: str, fav_change: int, game_time: str):
        """Persist NPC↔NPC dialogue to database."""
        conn = get_connection()
        try:
            conn.execute("""INSERT INTO dialogue(id, speaker_id, speaker_type, listener_id, listener_type,
                         content, scene_id, game_time, favorability_change)
                         VALUES(?, ?, 'npc', ?, 'npc', ?, ?, ?, ?)""",
                         (gen_id(), self.npc_id, other_npc_id, my_response,
                          self.npc_data.get("current_scene_id"), game_time, fav_change))
            conn.execute("""INSERT INTO dialogue(id, speaker_id, speaker_type, listener_id, listener_type,
                         content, scene_id, game_time, favorability_change)
                         VALUES(?, ?, 'npc', ?, 'npc', ?, ?, ?, 0)""",
                         (gen_id(), other_npc_id, self.npc_id, their_msg,
                          self.npc_data.get("current_scene_id"), game_time))
            conn.commit()
        finally:
            conn.close()

    def _decode_field(self, fields: dict, key: str, default: str = "") -> str:
        """Decode a field from Redis bytes or string key."""
        val = fields.get(key.encode() if isinstance(key, str) else key, fields.get(key, default))
        if isinstance(val, bytes):
            return val.decode("utf-8")
        return val if val is not None else default

    async def _handle_dialogue(self, fields: dict):
        """Process a dialogue request. Routes /action commands to action handler."""
        player_id = self._decode_field(fields, "player_id", "")
        content = self._decode_field(fields, "content", "")
        player_context = self._decode_field(fields, "context", "")
        game_time = self._decode_field(fields, "game_time", game_time_to_str(
            self._game_time.get("day", 1),
            self._game_time.get("hour", 8),
            self._game_time.get("minute", 0),
        ))

        if not content:
            return

        # Load player data from DB for identity-aware prompts
        player_data = None
        player_name = "玩家"
        if player_id:
            conn = get_connection()
            try:
                row = fetch_one(conn, "SELECT * FROM player WHERE id = ?", (player_id,))
                if row:
                    player_data = dict(row)
                    player_name = player_data.get("name", "玩家")
            finally:
                conn.close()

        # Dialogue lock: prevent concurrent handling that could confuse context
        async with self._dialogue_lock:
            # Interrupt autonomous activity
            self.brain.set_in_dialogue(True, player_id)
            self._in_dialogue_with = player_id
            self._idle_countdown = 600  # Reset 10-minute countdown
            self._auto_action = None
            self._auto_action_remaining = 0

            # Detect action commands (/action)
            action_name, _ = DialogueHandler._parse_action(content)
            if action_name:
                logger.info(f"NPC {self.npc_data['name']} received action '{action_name}' from {player_name}")
                from src.npc.action_rules import parse_attributes
                player_attrs = parse_attributes(self._decode_field(fields, "player_attrs", "{}"))
                npc_attrs = parse_attributes(self.npc_data.get("attributes", "{}"))
                result = await self.dialogue_handler.respond_to_action(
                    player_name, player_id, action_name,
                    scene_name=self._scene_name,
                    game_time=game_time,
                    scene_type=self._scene_type or "indoor",
                    player_attrs=player_attrs,
                    npc_attrs=npc_attrs,
                    player_data=player_data,
                )
            else:
                logger.info(f"NPC {self.npc_data['name']} received dialogue from {player_name}: {content[:50]}...")
                result = await self.dialogue_handler.respond_to_player(
                    player_name, player_id, content,
                    scene_name=self._scene_name,
                    game_time=game_time,
                    player_context=player_context,
                    player_data=player_data,
                )

        # Save dialogue to database
        self._save_dialogue(player_id, content, result["content"],
                            result["favorability_change"], game_time)

        # Send response via pub/sub so WebSocket picks it up
        await self.broker.publish("dialogue:response", {
            "npc_id": self.npc_id,
            "npc_name": self.npc_data["name"],
            "player_id": player_id,
            "content": result["content"],
            "favorability_change": str(result.get("favorability_change", 0)),
            "favorability_before": int(result.get("favorability_before", 0)),
            "favorability_after": int(result.get("favorability_after", 0)),
            "familiarity_after": int(result.get("familiarity_after", 0)),
            "mood_before": result.get("mood_before", ""),
            "new_mood": result.get("new_mood", ""),
            "relationship_type": result.get("relationship_type", "stranger"),
            "game_time": game_time,
        })
        logger.info(f"NPC {self.npc_data['name']} response sent: {result['content'][:60]}... fav={result['favorability_change']}")

        # Fire-and-forget TTS request (non-blocking, text already sent)
        if result.get("content"):
            asyncio.create_task(self._request_tts(result["content"]))

        # Publish state update
        await self._publish_state()

        # Dialogue complete, but keep in_dialogue for idle timeout
        self.brain._in_dialogue = True  # Still in dialogue mode

    async def _request_tts(self, text: str):
        """Submit TTS request to TTS Gateway. Fire-and-forget, non-blocking.
        
        Parses text into stage direction and dialogue segments, sending them
        as a structured TTS request. Stage directions use a standard narrator voice,
        dialogue uses the NPC's voice-cloned voice.
        """
        # Strip metadata tags like [[FAVORABILITY: +3]] before TTS
        clean_text = re.sub(r"\[\[.*?\]\]", "", text).strip()
        if not clean_text:
            return
        # Prepend narrator intro: "（XXX说：）"
        npc_name = self.npc_data.get("name", "")
        if npc_name:
            clean_text = f"（{npc_name}说：）{clean_text}"
        # Parse into segments
        segments = parse_stage_and_dialogue(clean_text)
        if not segments:
            return
        try:
            await self.broker.stream_add("stream:tts:requests", {
                "request_id": str(uuid.uuid4()),
                "npc_id": self.npc_id,
                "text": clean_text,
                "segments": json.dumps(segments),
                "mood": self.npc_data.get("current_mood", "neutral"),
                "reply_to": "tts:chunk",
                "player_id": "player_001",
            })
        except Exception as e:
            logger.warning(f"TTS request failed (non-critical): {e}")

    def _save_dialogue(self, player_id: str, player_msg: str,
                       npc_response: str, fav_change: int, game_time: str):
        """Persist dialogue to database."""
        from src.common.models import gen_id
        conn = get_connection()
        try:
            # Player message
            conn.execute("""INSERT INTO dialogue(id, speaker_id, speaker_type, listener_id, listener_type,
                         content, scene_id, game_time, favorability_change)
                         VALUES(?, ?, 'player', ?, 'npc', ?, ?, ?, 0)""",
                         (gen_id(), player_id, self.npc_id, player_msg,
                          self.npc_data.get("current_scene_id"), game_time))
            # NPC response
            conn.execute("""INSERT INTO dialogue(id, speaker_id, speaker_type, listener_id, listener_type,
                         content, scene_id, game_time, favorability_change)
                         VALUES(?, ?, 'npc', ?, 'player', ?, ?, ?, ?)""",
                         (gen_id(), self.npc_id, player_id, npc_response,
                          self.npc_data.get("current_scene_id"), game_time, fav_change))
            conn.commit()
        finally:
            conn.close()

    def _extract_room_from_activity(self, activity: str) -> str:
        """Extract room name from activity text like '在卧室床上睡觉' → '卧室'."""
        if activity.startswith("在") and ("床" in activity or "沙发" in activity or
                "做饭" in activity or "洗澡" in activity or "看电视" in activity):
            # Pattern: 在XX房间/区域 + action
            inner = activity[1:]  # strip leading 在
            for kw in ["床上", "沙发", "做饭", "洗澡", "看电视", "喝水", "吃饭", "书桌"]:
                if kw in inner:
                    room = inner.split(kw)[0]
                    return room if room else ""
        return ""

    @staticmethod
    def _rel_type_cn(rel_type: str) -> str:
        mapping = {
            "parent": "父母", "sibling": "兄弟姐妹", "child": "子女",
            "stranger": "陌生人", "acquaintance": "认识的人",
            "friend": "朋友", "best_friend": "好朋友",
            "boyfriend": "男朋友", "girlfriend": "女朋友",
            "spouse": "配偶", "dislike": "讨厌的人", "enemy": "仇敌",
        }
        return mapping.get(rel_type, rel_type)

    async def _catch_up_schedule(self):
        """On startup, check current game time from DB and apply the most recent schedule entry.
        This prevents NPCs from being stuck in daytime locations after a restart."""
        if not self.movement_mgr:
            return
        # Read game time from DB
        try:
            from src.common.database import get_connection, fetch_one
            import json
            conn = get_connection()
            try:
                row = fetch_one(conn, "SELECT value FROM game_state WHERE key = 'game_time'")
                gt = json.loads(row["value"]) if row else {}
            finally:
                conn.close()
        except Exception:
            gt = {}
        hour = gt.get("hour", 8)
        minute = gt.get("minute", 0)
        day = gt.get("day", 1)
        scheduled = self.movement_mgr.get_schedule_for_time(hour, minute, day)
        if scheduled and scheduled.get("scene"):
            target = scheduled["scene"]
            current = self.npc_data.get("current_scene_id", "")
            if target and target != current:
                logger.info(f"NPC {self.npc_data['name']}: schedule catch-up: {current} → {target} "
                           f"(game time {hour:02d}:{minute:02d} Day {day})")
                room_name = "客厅"
                if target == self._home_scene_id:
                    room_name = "客厅"
                # For catch-up on startup, arrive instantly (already "should" be there)
                self._update_scene(target, room_name)
                try:
                    await self.broker.publish("npc_movement", {
                        "npc_id": self.npc_id,
                        "scene_id": target,
                        "room_name": room_name,
                        "activity": scheduled.get("activity", "闲逛"),
                        "reason": "schedule_catchup",
                    })
                    await self._publish_state()
                except Exception:
                    pass

    def _update_scene(self, new_scene_id: str, room_name: str = ""):
        """Update NPC's current scene and room in npc_data and local fields.
        Must be called when the NPC moves to a new scene or room."""
        old_scene = self.npc_data.get("current_scene_id", "")
        old_room = self.npc_data.get("current_room", "")
        if new_scene_id == old_scene and room_name == old_room:
            return  # No change
        self.npc_data["current_scene_id"] = new_scene_id
        self.npc_data["current_scene_name"] = ""
        self.npc_data["current_room"] = room_name
        # Keep brain in sync so movement decisions use the correct scene
        if hasattr(self, "brain") and self.brain:
            self.brain._current_scene = new_scene_id
            self.brain._greeted_player = False
        # Look up scene name and type from DB
        conn = get_connection()
        try:
            row = fetch_one(conn, "SELECT name, scene_type FROM scene WHERE id = ?", (new_scene_id,))
            if row:
                self._scene_name = row["name"]
                self._scene_type = row.get("scene_type", "indoor")
                self.npc_data["current_scene_name"] = row["name"]
            else:
                self._scene_name = "未知"
                self._scene_type = "indoor"
        finally:
            conn.close()
        if room_name and room_name != old_room:
            logger.info(f"NPC {self.npc_data['name']}: entered room '{room_name}' in {new_scene_id}")
        elif new_scene_id != old_scene:
            logger.info(f"NPC {self.npc_data['name']}: moved from {old_scene} to {new_scene_id}")

    def _persist_death(self):
        """Save NPC death state to database."""
        try:
            conn = get_connection()
            execute(conn,
                "UPDATE npc SET is_dead = 1, death_cause = ?, updated_at = datetime('now') WHERE id = ?",
                (self.physiology.death_cause, self.npc_id))
            conn.commit()
            conn.close()
            logger.info(f"NPC {self.npc_data['name']}: death persisted to DB")
        except Exception as e:
            logger.error(f"NPC {self.npc_data['name']}: failed to persist death: {e}")

    async def _publish_state(self):
        """Publish NPC state to Redis."""
        current_scene_id = self.npc_data.get("current_scene_id", "")
        activity = self.npc_data.get("current_activity", "")

        # Use current_room from npc_data if set, otherwise derive from activity
        room_name = self.npc_data.get("current_room", "") or ""
        if not room_name and self._scene_type == "home" and activity:
            room_name = self._extract_room_from_activity(activity)

        state = {
            "npc_id": self.npc_id,
            "name": self.npc_data["name"],
            "mood": self.mood_mgr.current,
            "mood_intensity": self.mood_mgr._intensity,
            "physiology": {
                "hunger": round(self.physiology.hunger, 1) if self.physiology else 0,
                "thirst": round(self.physiology.thirst, 1) if self.physiology else 0,
                "energy": round(self.physiology.energy, 1) if self.physiology else 0,
                "social": round(self.physiology.social, 1) if self.physiology else 0,
                "hp": round(self.physiology.hp, 1) if self.physiology else 0,
            } if self.physiology else None,
            "current_scene": current_scene_id,
            "current_scene_name": self._scene_name,
            "scene_type": self._scene_type,
            "current_activity": activity,
            "current_room": room_name,
            "home_scene_id": self._home_scene_id,
            "home_scene_name": self._home_scene_name,
            "in_dialogue": bool(self._in_dialogue_with),
            "is_dead": self.physiology.is_dead if self.physiology else False,
            "death_cause": self.physiology.death_cause if self.physiology else "",
            "is_traveling": self._is_traveling,
            "travel_target": self._travel_target,
            "travel_remaining": round(self._travel_remaining, 1) if self._is_traveling else 0,
        }
        if self.physiology:
            state["physiology"] = {
                "hunger": round(self.physiology.hunger, 1),
                "thirst": round(self.physiology.thirst, 1),
                "energy": round(self.physiology.energy, 1),
                "social": round(self.physiology.social, 1),
                "hp": round(self.physiology.hp, 1),
                "age": self.physiology._age,
                "age_stage": str(self.physiology._stage),
            }
        if self._auto_action:
            state["auto_action"] = {
                "action_name": self._auto_action.action_name,
                "display_text": self._auto_action.display_text,
                "icon": self._auto_action.icon,
                "animation": self._auto_action.animation,
                "category": self._auto_action.category,
                "target_id": self._auto_action.target_id,
                "target_name": self._auto_action.target_name,
            }
        await self.broker.publish(f"npc:{self.npc_id}:state", state)
        await self.broker.kv_set(f"state:npc:{self.npc_id}", state)

    async def run(self):
        """Main NPC loop."""
        await self.start()
        _health_tick = 0
        while self._running:
            await asyncio.sleep(1.0)
            _health_tick += 1
            if _health_tick % 15 == 0:  # every 15 seconds
                try:
                    scene_id = self.npc_data.get("current_scene_id", "")
                    await self.broker.report_health(
                        f"npc:{self.npc_id}",
                        status="alive",
                        extra={
                            "scene": scene_id,
                            "dialogue": self._in_dialogue_with or "",
                            "mood": self.npc_data.get("current_mood", "neutral"),
                        },
                    )
                except Exception as e:
                    logger.warning(f"NPC health report failed: {e}")

    async def shutdown(self):
        logger.info(f"NPC {self.npc_data.get('name', self.npc_id)} shutting down...")
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=5)
        await self.broker.disconnect()


def main():
    npc_id = None
    args = sys.argv[1:]
    # Handle both positional and --npc-id format
    for i, arg in enumerate(args):
        if arg == "--npc-id" and i + 1 < len(args):
            npc_id = args[i + 1]
        elif not arg.startswith("--"):
            npc_id = arg
    if not npc_id:
        npc_id = os.environ.get("NPC_ID", "npc_li_ming")
    proc = NpcProcess(npc_id)
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
