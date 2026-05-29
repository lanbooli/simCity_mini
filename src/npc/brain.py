"""
NPC autonomous decision engine.
Each cycle: perceive → generate intention → decide action.
"""

import random
from typing import Optional


class Brain:
    def __init__(self, npc_id: str, movement_mgr, mood_mgr, relationship_mgr, memory_mgr,
                 npc_data: dict, all_scene_ids: list[str]):
        self.npc_id = npc_id
        self.npc_data = npc_data
        self.movement_mgr = movement_mgr
        self.mood_mgr = mood_mgr
        self.relationship_mgr = relationship_mgr
        self.memory_mgr = memory_mgr
        self.all_scene_ids = all_scene_ids
        self._current_scene = npc_data.get("current_scene_id", "")
        self._current_activity = npc_data.get("current_activity", "")
        self._in_dialogue = False
        self._dialogue_target: Optional[str] = None
        self._greeted_player = False  # Only greet once per scene entry

    @property
    def current_scene(self) -> str:
        return self._current_scene

    @property
    def current_activity(self) -> str:
        return self._current_activity

    def set_in_dialogue(self, in_dialogue: bool, target_id: str = ""):
        self._in_dialogue = in_dialogue
        self._dialogue_target = target_id if in_dialogue else None
        if in_dialogue:
            self._current_activity = f"与{'玩家' if (target_id or '').startswith('player') else '某人'}对话中"

    def decide(self, game_time: dict, perception=None) -> dict:
        """Main decision cycle with perception data."""
        if self._in_dialogue:
            return {"action": "idle", "scene_id": None, "activity": self._current_activity,
                    "social_target": None, "reason": "in_dialogue"}

        hour = game_time["hour"]
        minute = game_time["minute"]

        # 1. Check schedule for movement
        day = game_time.get("day", 1)
        move_decision = self.movement_mgr.decide_movement(
            hour, minute, self._current_scene, day)
        if move_decision and move_decision.get("scene_id") != self._current_scene:
            self._current_scene = move_decision["scene_id"]
            self._current_activity = move_decision.get("activity", "")
            self._greeted_player = False
            return {
                "action": "move",
                "scene_id": self._current_scene,
                "activity": self._current_activity,
                "social_target": None,
                "reason": move_decision.get("reason", "schedule"),
            }

        # 2. Update activity from schedule if changed
        if move_decision and move_decision.get("reason") == "schedule_activity":
            new_activity = move_decision.get("activity", "")
            if new_activity != self._current_activity:
                self._current_activity = new_activity
                return {
                    "action": "change_activity",
                    "scene_id": self._current_scene,
                    "activity": self._current_activity,
                    "social_target": None,
                    "reason": "schedule",
                }

        # 3. Player interaction decisions (requires perception)
        if perception and perception.players_present:
            player_intent = self._generate_player_intent(perception)
            if player_intent:
                return player_intent

        # 4. NPC social desire check
        if perception and perception.npcs_present and self.mood_mgr.current not in ("sad", "angry"):
            if random.random() < 0.30:
                social_target = self._pick_social_target(perception)
                if social_target:
                    return {
                        "action": "socialize",
                        "scene_id": self._current_scene,
                        "activity": "社交互动",
                        "social_target": social_target,
                        "reason": "social_desire",
                    }

        # 5. Idle
        return {
            "action": "idle",
            "scene_id": None,
            "activity": self._current_activity,
            "social_target": None,
            "reason": "idle",
        }

    def _generate_player_intent(self, perception) -> dict | None:
        """Phase 4: Generate intent toward the player based on relationship and context."""
        player = perception.players_present[0]
        player_id = player.id
        rel = self.relationship_mgr.get_relation(player_id)
        if not rel:
            return None

        fav = rel.get("favorability", 0)
        personality = self.npc_data.get("personality", "[]")
        if isinstance(personality, str):
            import json
            personality = json.loads(personality)

        # Negative: avoid player
        if fav <= -50 and random.random() < 0.15:
            return {
                "action": "avoid_player",
                "scene_id": None,
                "activity": "避开玩家",
                "social_target": None,
                "reason": f"对{player.name}好感过低({fav})",
            }

        # Positive: greet player on first encounter this scene visit
        if not self._greeted_player and fav >= 0:
            self._greeted_player = True
            if random.random() < 0.50:
                return {
                    "action": "greet_player",
                    "scene_id": None,
                    "activity": "打招呼",
                    "social_target": None,
                    "reason": "greet",
                }

        # High favorability: approach or initiate action
        if fav >= 50:
            action = self._pick_player_action(rel, personality, perception)
            if action:
                return action

        return None

    def _pick_player_action(self, rel: dict, personality: list, perception) -> dict | None:
        """Pick a conversational action toward the player. 
        Physical/intimate actions are now handled by IntimacyEngine."""
        fav = rel.get("favorability", 0)
        is_shy = "害羞" in personality or "内向" in personality
        is_outgoing = "外向" in personality or "开朗" in personality
        is_romantic = "浪漫" in personality
        mood = self.mood_mgr.current

        candidates = []

        # Chat up
        weight = 15
        if is_outgoing: weight *= 1.5
        if mood == "happy": weight *= 1.3
        elif mood == "sad": weight *= 0.3
        candidates.append({"action_name": "chat_up", "desc": "主动搭话闲聊", "cooldown": 45, "weight": weight})

        # Compliment
        if fav >= 10:
            weight = 8
            if is_shy: weight *= 0.5
            if is_romantic: weight *= 1.5
            candidates.append({"action_name": "compliment", "desc": "赞美对方", "cooldown": 90, "weight": weight})

        # Mood adjustments
        for c in candidates:
            if mood in ("happy", "excited"):
                c["weight"] *= 1.3
            elif mood == "angry":
                c["weight"] *= 0.2

        if not candidates:
            return None

        total = sum(c["weight"] for c in candidates)
        r = random.random() * total
        cumulative = 0
        for c in candidates:
            cumulative += c["weight"]
            if r <= cumulative:
                return {
                    "action": "npc_initiated_action",
                    "scene_id": None,
                    "activity": f"对玩家{c['action_name']}",
                    "social_target": None,
                    "reason": f"主动互动: {c['action_name']}",
                    "action_name": c["action_name"],
                    "action_desc": c["desc"],
                    "cooldown": c["cooldown"],
                }

        return None

    def _pick_social_target(self, perception=None) -> Optional[str]:
        """Pick an NPC to interact with, preferring same-scene NPCs."""
        relations = self.relationship_mgr.get_all_relations()
        if perception:
            same_scene_ids = perception.other_npc_ids
            candidates = [
                r for r in relations
                if r["entity_b_type"] == "npc"
                and r["entity_b_id"] in same_scene_ids
                and r["favorability"] > 10
                and r["familiarity"] > 5
            ]
        else:
            candidates = [
                r for r in relations
                if r["entity_b_type"] == "npc"
                and r["favorability"] > 10
                and r["familiarity"] > 5
            ]

        if not candidates:
            return None

        weights = [max(1, r["favorability"]) for r in candidates]
        total = sum(weights)
        r = random.random() * total
        cumulative = 0
        for candidate, weight in zip(candidates, weights):
            cumulative += weight
            if r <= cumulative:
                return candidate["entity_b_id"]

        return candidates[0]["entity_b_id"] if candidates else None

    def update_from_scene(self, scene_id: str, activity: str = ""):
        self._current_scene = scene_id
        self._greeted_player = False
        if activity:
            self._current_activity = activity
