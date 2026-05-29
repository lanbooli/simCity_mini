"""
NPC→Player intimate action decision engine.

Per-tick probability check for NPC-initiated intimate actions
(feeding, hugging, cooking for player, leaning on shoulder, etc.).

Uses the 39-set personality system for probability modifiers and
the 3 master rules for behavior evolution over time.
"""

import json
import os
import random
from dataclasses import dataclass
from typing import Optional

from src.npc.personality import PersonalityEngine, calculate_intimacy_probability


# ── Intimate action definitions ──────────────────────

@dataclass
class IntimateAction:
    name: str           # internal key
    label: str          # display label with emoji
    rel_threshold: str  # min relationship type
    fav_min: int        # min favorability
    allowed_scenes: list[str]  # scene types: indoor/outdoor/home
    room_keywords: list[str]   # room name keywords (empty = any)
    time_condition: str  # "meal" | "evening" | "daytime" | "morning" | "any" | "night"
    context_condition: str  # "eating" | "after_eat" | "cooking" | "before_out" | "after_shower" | "tired" | "any"
    base_prob: float     # per-tick probability (0.0-1.0)
    cooldown_minutes: int  # cooldown in game minutes
    personality_affinity: list[int]  # personality IDs that boost this action


INTIMATE_ACTIONS: list[IntimateAction] = [
    IntimateAction(
        name="feed_partner", label="喂饭 🥢",
        rel_threshold="boyfriend", fav_min=70,
        allowed_scenes=["home", "indoor"], room_keywords=["厨房", "餐厅", "餐桌"],
        time_condition="meal", context_condition="eating",
        base_prob=0.08, cooldown_minutes=60,
        personality_affinity=[2, 10, 17],
    ),
    IntimateAction(
        name="wipe_mouth", label="帮忙擦嘴 🧻",
        rel_threshold="boyfriend", fav_min=60,
        allowed_scenes=["home", "indoor"], room_keywords=["厨房", "餐厅", "餐桌"],
        time_condition="any", context_condition="after_eat",
        base_prob=0.12, cooldown_minutes=60,
        personality_affinity=[2, 11],
    ),
    IntimateAction(
        name="fix_collar", label="整理衣领 👔",
        rel_threshold="boyfriend", fav_min=50,
        allowed_scenes=["home"], room_keywords=["客厅", "卧室"],
        time_condition="morning", context_condition="before_out",
        base_prob=0.06, cooldown_minutes=90,
        personality_affinity=[2, 14, 16],
    ),
    IntimateAction(
        name="tie_apron", label="帮系围裙 👗",
        rel_threshold="boyfriend", fav_min=60,
        allowed_scenes=["home"], room_keywords=["厨房"],
        time_condition="meal", context_condition="cooking",
        base_prob=0.10, cooldown_minutes=60,
        personality_affinity=[10, 17, 2],
    ),
    IntimateAction(
        name="lean_on_shoulder", label="靠肩膀上 😴",
        rel_threshold="friend", fav_min=50,
        allowed_scenes=["home", "indoor", "outdoor"], room_keywords=["客厅", "沙发"],
        time_condition="evening", context_condition="tired",
        base_prob=0.10, cooldown_minutes=90,
        personality_affinity=[13, 17, 19, 11],
    ),
    IntimateAction(
        name="hold_hands_walk", label="牵手散步 🚶",
        rel_threshold="friend", fav_min=50,
        allowed_scenes=["outdoor"], room_keywords=[],
        time_condition="daytime", context_condition="any",
        base_prob=0.08, cooldown_minutes=60,
        personality_affinity=[10, 15, 17],
    ),
    IntimateAction(
        name="sudden_hug", label="突然拥抱 🫂",
        rel_threshold="friend", fav_min=55,
        allowed_scenes=["home", "indoor", "outdoor"], room_keywords=[],
        time_condition="any", context_condition="any",
        base_prob=0.08, cooldown_minutes=120,
        personality_affinity=[10, 15, 17],
    ),
    IntimateAction(
        name="ask_for_hug", label="撒娇要抱抱 🥺",
        rel_threshold="friend", fav_min=60,
        allowed_scenes=["home"], room_keywords=["客厅"],
        time_condition="any", context_condition="tired",
        base_prob=0.10, cooldown_minutes=120,
        personality_affinity=[10, 13, 17, 19],
    ),
    IntimateAction(
        name="cook_for_player", label="做饭给你吃 🍳",
        rel_threshold="boyfriend", fav_min=60,
        allowed_scenes=["home"], room_keywords=["厨房"],
        time_condition="meal", context_condition="any",
        base_prob=0.10, cooldown_minutes=120,
        personality_affinity=[2, 10, 14, 17, 32],
    ),
    IntimateAction(
        name="give_gift", label="送小礼物 🎁",
        rel_threshold="friend", fav_min=50,
        allowed_scenes=["home", "indoor", "outdoor"], room_keywords=[],
        time_condition="any", context_condition="any",
        base_prob=0.02, cooldown_minutes=480,  # once per day
        personality_affinity=[2, 12, 17, 19, 32],
    ),
    IntimateAction(
        name="blow_dry_hair", label="帮吹头发 💨",
        rel_threshold="boyfriend", fav_min=80,
        allowed_scenes=["home"], room_keywords=["浴室"],
        time_condition="any", context_condition="after_shower",
        base_prob=0.15, cooldown_minutes=120,
        personality_affinity=[2, 14, 17],
    ),
    IntimateAction(
        name="watch_tv_together", label="一起看电视 📺",
        rel_threshold="friend", fav_min=50,
        allowed_scenes=["home"], room_keywords=["客厅"],
        time_condition="evening", context_condition="any",
        base_prob=0.08, cooldown_minutes=90,
        personality_affinity=[5, 10, 16, 32],
    ),
    # ── Physical intimacy actions (merged from brain.py) ──
    IntimateAction(
        name="stand_close", label="靠近你 🚶",
        rel_threshold="friend", fav_min=30,
        allowed_scenes=["home", "indoor", "outdoor"], room_keywords=[],
        time_condition="any", context_condition="any",
        base_prob=0.15, cooldown_minutes=40,
        personality_affinity=[10, 15, 17],
    ),
    IntimateAction(
        name="cheek_kiss", label="亲你脸颊 😚",
        rel_threshold="best_friend", fav_min=65,
        allowed_scenes=["home", "indoor"], room_keywords=[],
        time_condition="any", context_condition="any",
        base_prob=0.06, cooldown_minutes=180,
        personality_affinity=[10, 15, 17, 11],
    ),
    IntimateAction(
        name="kiss", label="亲吻你 💋",
        rel_threshold="boyfriend", fav_min=75,
        allowed_scenes=["home", "indoor"], room_keywords=["客厅", "卧室"],
        time_condition="any", context_condition="any",
        base_prob=0.05, cooldown_minutes=240,
        personality_affinity=[10, 15, 17, 11],
    ),
    IntimateAction(
        name="sweet_talk", label="对你说情话 💕",
        rel_threshold="boyfriend", fav_min=60,
        allowed_scenes=["home", "indoor", "outdoor"], room_keywords=[],
        time_condition="any", context_condition="any",
        base_prob=0.10, cooldown_minutes=60,
        personality_affinity=[10, 15, 17, 32],
    ),
    IntimateAction(
        name="goodbye_kiss", label="告别亲吻 💋",
        rel_threshold="boyfriend", fav_min=70,
        allowed_scenes=["home", "indoor"], room_keywords=["门口", "客厅"],
        time_condition="morning", context_condition="before_out",
        base_prob=0.12, cooldown_minutes=120,
        personality_affinity=[10, 15, 17, 11],
    ),
    # ── New affectionate/romantic actions ──
    IntimateAction(
        name="head_pat", label="摸头杀 ✋",
        rel_threshold="friend", fav_min=40,
        allowed_scenes=["home", "indoor", "outdoor"], room_keywords=[],
        time_condition="any", context_condition="any",
        base_prob=0.12, cooldown_minutes=60,
        personality_affinity=[10, 15, 17, 13],
    ),
    IntimateAction(
        name="back_hug", label="从背后抱你 🤗",
        rel_threshold="best_friend", fav_min=65,
        allowed_scenes=["home", "indoor"], room_keywords=["厨房", "客厅", "卧室"],
        time_condition="any", context_condition="any",
        base_prob=0.06, cooldown_minutes=150,
        personality_affinity=[10, 15, 17, 11],
    ),
    IntimateAction(
        name="forehead_kiss", label="轻吻额头 💋",
        rel_threshold="boyfriend", fav_min=80,
        allowed_scenes=["home", "indoor"], room_keywords=["卧室", "客厅"],
        time_condition="night", context_condition="tired",
        base_prob=0.07, cooldown_minutes=200,
        personality_affinity=[2, 10, 11, 17, 14],
    ),
    IntimateAction(
        name="playful_punch", label="轻捶你一下 💢",
        rel_threshold="friend", fav_min=40,
        allowed_scenes=["home", "indoor", "outdoor"], room_keywords=[],
        time_condition="any", context_condition="any",
        base_prob=0.10, cooldown_minutes=45,
        personality_affinity=[10, 15, 16, 19],
    ),
    IntimateAction(
        name="pull_sleeve", label="拉你衣角 🥺",
        rel_threshold="friend", fav_min=35,
        allowed_scenes=["home", "indoor", "outdoor"], room_keywords=[],
        time_condition="any", context_condition="any",
        base_prob=0.08, cooldown_minutes=50,
        personality_affinity=[13, 17, 19, 11],
    ),
    IntimateAction(
        name="fix_hair", label="帮你整理头发 ✨",
        rel_threshold="best_friend", fav_min=60,
        allowed_scenes=["home", "indoor"], room_keywords=[],
        time_condition="any", context_condition="any",
        base_prob=0.08, cooldown_minutes=90,
        personality_affinity=[2, 14, 17, 32],
    ),
    IntimateAction(
        name="arm_in_arm", label="挽起你手臂 💑",
        rel_threshold="friend", fav_min=55,
        allowed_scenes=["outdoor", "indoor"], room_keywords=[],
        time_condition="daytime", context_condition="any",
        base_prob=0.10, cooldown_minutes=80,
        personality_affinity=[10, 15, 17, 11],
    ),
    IntimateAction(
        name="whisper", label="在你耳边低语 😳",
        rel_threshold="best_friend", fav_min=70,
        allowed_scenes=["home", "indoor"], room_keywords=["客厅", "卧室"],
        time_condition="evening", context_condition="any",
        base_prob=0.06, cooldown_minutes=120,
        personality_affinity=[15, 17, 11, 10],
    ),
    IntimateAction(
        name="cover_blanket", label="帮你盖好毯子 🛌",
        rel_threshold="friend", fav_min=50,
        allowed_scenes=["home"], room_keywords=["卧室", "客厅"],
        time_condition="night", context_condition="tired",
        base_prob=0.12, cooldown_minutes=120,
        personality_affinity=[2, 13, 17, 14, 32],
    ),
    IntimateAction(
        name="bring_tea", label="端茶给你 ☕",
        rel_threshold="friend", fav_min=35,
        allowed_scenes=["home", "indoor"], room_keywords=["厨房", "客厅"],
        time_condition="daytime", context_condition="tired",
        base_prob=0.12, cooldown_minutes=80,
        personality_affinity=[2, 13, 14, 32],
    ),
    IntimateAction(
        name="share_snack", label="分享零食 🍪",
        rel_threshold="friend", fav_min=30,
        allowed_scenes=["home", "indoor"], room_keywords=["客厅", "厨房"],
        time_condition="daytime", context_condition="eating",
        base_prob=0.10, cooldown_minutes=60,
        personality_affinity=[10, 15, 16, 19, 32],
    ),
    IntimateAction(
        name="cuddle", label="依偎在你身边 🥰",
        rel_threshold="boyfriend", fav_min=75,
        allowed_scenes=["home"], room_keywords=["客厅", "卧室"],
        time_condition="evening", context_condition="any",
        base_prob=0.08, cooldown_minutes=150,
        personality_affinity=[10, 11, 17, 13],
    ),
]

# Partner-level relations that unlock intimate actions
_PARTNER_RELATIONS = {"boyfriend", "girlfriend", "spouse"}

# Time condition ranges (game hour)
_TIME_RANGES = {
    "meal": [(7, 9), (12, 13), (18, 20)],
    "evening": [(18, 23)],
    "daytime": [(8, 17)],
    "morning": [(6, 8)],
    "night": [(22, 6)],  # wraps around
}


def _in_time_range(game_hour: int, condition: str) -> bool:
    """Check if current game hour falls within a named time range."""
    ranges = _TIME_RANGES.get(condition, [])
    for start, end in ranges:
        if start <= end:
            if start <= game_hour <= end:
                return True
        else:  # wraps midnight
            if game_hour >= start or game_hour <= end:
                return True
    return condition == "any"


class IntimacyEngine:
    """Decision engine for NPC→player intimate actions.

    Called each autonomous tick (~15 game minutes) when the player is
    present in the same scene. Checks all eligible actions against
    relationship, scene, time, and context conditions, then rolls
    probability with personality/mood/time modifiers.
    """

    def __init__(self, npc_data: dict, relationship_mgr, mood: str,
                 scene_type: str = "indoor", scene_name: str = "",
                 game_hour: int = 12, npc_energy: float = 50.0,
                 interaction_ctx=None):
        self.npc_id = npc_data.get("id", "")
        self.npc_name = npc_data.get("name", "")
        self.relationship_mgr = relationship_mgr
        self.mood = mood
        self.scene_type = scene_type
        self.scene_name = scene_name
        self.game_hour = game_hour
        self.npc_energy = npc_energy
        self.interaction_ctx = interaction_ctx

        # Load 39-set personality engine
        personality_ids = _load_personality_ids(self.npc_id)
        self.personality_engine = PersonalityEngine(personality_ids)

        # Cooldowns: action_name -> ticks remaining
        self._cooldowns: dict[str, int] = {}

    def tick_cooldowns(self):
        """Decrement all cooldowns by 1 tick (called each autonomous cycle)."""
        for k in list(self._cooldowns):
            self._cooldowns[k] -= 1
            if self._cooldowns[k] <= 0:
                del self._cooldowns[k]

    def check_actions(self, player_id: str, player_name: str,
                      current_activity: str = "",
                      together_minutes: float = 15.0,
                      is_weekend: bool = False,
                      ) -> Optional[dict]:
        """Check all intimate actions. Returns the selected action dict or None.

        Result dict contains: action_name, label, display_text for frontend.
        """
        # Get player relationship
        rel = self.relationship_mgr.get_relation(player_id)
        if not rel:
            return None

        fav = rel.get("favorability", 0)
        rel_type = rel.get("relationship_type", "stranger")

        candidates: list[tuple[IntimateAction, float]] = []

        for action in INTIMATE_ACTIONS:
            if action.name in self._cooldowns:
                continue

            # Relation check
            if not self._meets_rel(action, rel_type, fav):
                continue

            # Scene type check
            # Map new scene types (cafe/market/school/etc.) to legacy categories
            scene_cat = self.scene_type
            if scene_cat in ("cafe", "market", "school", "library", "hospital", "bar", "gym", "restaurant", "shop", "cinema", "arcade", "office"):
                scene_cat = "indoor"
            if action.allowed_scenes and scene_cat not in action.allowed_scenes:
                continue

            # Time condition
            if not _in_time_range(self.game_hour, action.time_condition):
                continue

            # Context condition
            if not self._meets_context(action, current_activity):
                continue

            # Calculate final probability with interaction context
            phys_states = set(self.interaction_ctx.physical_states.keys()) if self.interaction_ctx else set()
            prob = self._calculate_probability(action, fav, phys_states)
            if prob <= 0:
                continue

            candidates.append((action, prob))

        if not candidates:
            return None

        # Pick highest probability (not weighted random — highest prob wins)
        # This ensures actions with matching context always beat generic ones
        best_action, best_prob = max(candidates, key=lambda x: x[1])

        if random.random() < best_prob:
            # Set cooldown
            self._cooldowns[best_action.name] = best_action.cooldown_minutes // 15
            return {
                "action_name": best_action.name,
                "label": best_action.label,
                "display_text": f"{best_action.label}",
                "fav_min": best_action.fav_min,
            }

        return None

    def _meets_rel(self, action: IntimateAction, rel_type: str, fav: int) -> bool:
        """Check if relationship meets the action's threshold."""
        if fav < action.fav_min:
            return False

        if action.rel_threshold in _PARTNER_RELATIONS:
            return rel_type in _PARTNER_RELATIONS
        elif action.rel_threshold == "friend":
            return rel_type in ("friend", "best_friend", *list(_PARTNER_RELATIONS))
        elif action.rel_threshold == "best_friend":
            return rel_type in ("best_friend", *list(_PARTNER_RELATIONS))

        return rel_type == action.rel_threshold

    def _meets_context(self, action: IntimateAction, activity: str) -> bool:
        """Check context-specific conditions."""
        cond = action.context_condition
        if cond == "any":
            return True
        if cond == "tired":
            return self.npc_energy < 50 or self.mood in ("sad", "tired")
        if cond == "eating":
            return "吃" in activity or "饭" in activity or "餐" in activity
        if cond == "after_eat":
            return True  # hard to detect precisely, allow
        if cond == "cooking":
            return "做" in activity or "厨" in activity or "煮" in activity
        if cond == "before_out":
            return 6 <= self.game_hour <= 8
        if cond == "after_shower":
            return "洗" in activity or "浴" in activity
        return True

    # State → boosted actions: when in physical state X, boost Y actions
    _STATE_BOOST = {
        "hugging": {"kiss": 3.0, "cheek_kiss": 2.5, "forehead_kiss": 2.0, "sweet_talk": 2.0, "cuddle": 2.5, "whisper": 2.0},
        "hugging while kissing": {"cuddle": 3.0, "forehead_kiss": 2.5, "sweet_talk": 2.5},
        "holding hands": {"arm_in_arm": 3.0, "cheek_kiss": 2.0, "sudden_hug": 2.0},
        "standing very close": {"head_pat": 2.5, "cheek_kiss": 3.0, "fix_hair": 2.5, "pull_sleeve": 1.5},
        "kissing": {"hug": 2.5, "cuddle": 3.0, "sweet_talk": 2.5},
        "kissing on the cheek": {"whisper": 2.5, "head_pat": 2.0},
        "whispering sweet words": {"cheek_kiss": 3.0, "cuddle": 2.0},
    }
    
    # State → suppressed actions: when in state X, suppress Y actions (they don't make sense)
    _STATE_SUPPRESS = {
        "hugging": {"stand_close": -0.9, "arm_in_arm": -0.9, "head_pat": -0.7, "pull_sleeve": -0.9, "fix_hair": -0.5, "hold_hands_walk": -0.9},
        "hugging while kissing": {"stand_close": -0.9, "arm_in_arm": -0.9, "head_pat": -0.8, "pull_sleeve": -0.9},
        "holding hands": {"stand_close": -0.5},
        "kissing": {"stand_close": -0.9, "arm_in_arm": -0.9, "pull_sleeve": -0.9, "head_pat": -0.7},
    }

    def _calculate_probability(self, action: IntimateAction, fav: int, phys_states: set | None = None) -> float:
        """Calculate final probability for an intimate action.

        Uses the 39-set personality engine and the probability formula:
        base_prob × mood_mod × personality_mod × time_mod × state_mod
        """
        # Personality affinity boost
        personality_mod = 1.0
        for pid in action.personality_affinity:
            if pid in self.personality_engine.ids:
                personality_mod += 0.3

        # Use the engine's intimacy_mod as overall multiplier
        personality_mod *= self.personality_engine.intimacy_mod

        # Mood modifier
        mood_mods = {
            "happy": 1.5, "excited": 2.0, "neutral": 1.0,
            "sad": 0.3, "angry": 0.1, "bored": 0.5,
        }
        # Boost for tired/sad actions when those moods match
        if action.context_condition == "tired" and self.mood in ("sad", "tired"):
            mood_mods["sad"] = 2.0

        mood_mod = mood_mods.get(self.mood, 1.0)

        # Time modifier
        time_mod = 1.0
        if action.time_condition == "meal":
            time_mod = 1.5
        elif action.time_condition == "night":
            time_mod = 0.2
        elif action.time_condition == "daytime" and not (8 <= self.game_hour <= 17):
            time_mod = 0.7

        # Home safety bonus
        if self.scene_type in ("home", "apt_a", "apt_b", "apt_c", "apt_d", "home_player"):
            time_mod *= 1.2

        prob = action.base_prob * mood_mod * personality_mod * time_mod

        # State-aware modifier: boost logical next actions, suppress impossible ones
        state_mod = 1.0
        if phys_states:
            for state in phys_states:
                boosts = self._STATE_BOOST.get(state, {})
                if action.name in boosts:
                    state_mod *= boosts[action.name]
                supps = self._STATE_SUPPRESS.get(state, {})
                if action.name in supps:
                    state_mod *= (1.0 + supps[action.name])
            state_mod = max(0.05, min(state_mod, 5.0))  # clamp

        prob *= state_mod

        # High favorability bonus
        if fav >= 85:
            prob *= 1.3

        return min(prob, 0.60)  # cap at 60%


def _load_personality_ids(npc_id: str) -> list[int]:
    """Load 39-set personality IDs for an NPC from the config map."""
    try:
        config_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")
        map_path = os.path.join(config_dir, "npc_personality_map.json")
        with open(map_path, "r", encoding="utf-8") as f:
            pmap = json.load(f)
        entry = pmap.get(npc_id)
        if not entry:
            return []
        ids_ = [entry["primary"]] + entry.get("secondary", []) + [entry.get("romance")]
        return [i for i in ids_ if i]
    except Exception:
        return []
