"""
NPC autonomous action selector. Weighted random selection with requirements filtering.
No LLM involved — pure rules engine operating on the unified action_rules data.
"""

import random
import json
from dataclasses import dataclass
from typing import Optional

from src.npc.action_rules import get_auto_actions, AnimType


@dataclass
class AutoActionResult:
    """Result of autonomous action selection."""
    action_name: str
    action_info: dict
    target_id: str = ""
    target_name: str = ""
    display_text: str = ""
    icon: str = ""
    animation: str = ""
    category: str = ""
    duration_ticks: int = 3
    cooldown_ticks: int = 20


class ActionSelector:
    """Weighted random selector for NPC autonomous actions.

    Filters candidates by requirements (favorability range, scene type, time,
    mood, personality), adjusts weights, then picks via roulette-wheel selection.
    """

    def __init__(self, npc_data: dict, relationship_mgr, mood: str,
                 scene_type: str = "indoor", scene_name: str = "",
                 game_hour: int = 12):
        self.npc_id = npc_data.get("id", "")
        self.npc_name = npc_data.get("name", "")
        self.relationship_mgr = relationship_mgr
        self.mood = mood
        self.scene_type = scene_type
        self.scene_name = scene_name
        self.game_hour = game_hour

        raw = npc_data.get("personality", "[]")
        self.personality: list[str] = json.loads(raw) if isinstance(raw, str) else (raw or [])

        self._all_actions = get_auto_actions()

    def select_action(self, cooldowns: dict,
                      nearby_npcs: list[dict] | None = None,
                      tick_counter: int = 0) -> Optional[AutoActionResult]:
        """Select an autonomous action. Returns None if no valid candidate."""
        nearby_npcs = nearby_npcs or []
        candidates: list[tuple[str, dict, float, dict | None]] = []

        for name, info in self._all_actions.items():
            if name in cooldowns:
                continue

            req = info.get("requirements", {})
            needs_target = req.get("needs_target", False)

            if needs_target:
                for npc in nearby_npcs:
                    if npc.get("id") == self.npc_id:
                        continue
                    if self._meets_requirements(info, npc):
                        w = self._calculate_weight(info, npc)
                        if w > 0:
                            candidates.append((name, info, w, npc))
            else:
                if self._meets_requirements(info):
                    w = self._calculate_weight(info)
                    if w > 0:
                        candidates.append((name, info, w, None))

        if not candidates:
            return None

        total = sum(w for _, _, w, _ in candidates)
        if total <= 0:
            return None

        r = random.uniform(0, total)
        cumulative = 0.0
        for name, info, weight, target in candidates:
            cumulative += weight
            if r <= cumulative:
                return self._build_result(name, info, target)

        # Floating-point safety: return last
        name, info, weight, target = candidates[-1]
        return self._build_result(name, info, target)

    def _meets_requirements(self, info: dict, target_npc: dict | None = None) -> bool:
        """Check whether the action's requirements are satisfied."""
        req = info.get("requirements", {})

        # Scene type filter
        scene_types = req.get("scene_types")
        if scene_types and self.scene_type not in scene_types:
            return False

        # Time-of-day filter
        time_range = req.get("time_range")
        if time_range:
            start, end = time_range
            if start <= end:
                if not (start <= self.game_hour <= end):
                    return False
            else:
                if not (self.game_hour >= start or self.game_hour <= end):
                    return False

        # Mood filter
        allowed_moods = req.get("allowed_moods")
        if allowed_moods and self.mood not in allowed_moods:
            return False

        # Personality penalty (hard block)
        penalty = req.get("personality_penalty")
        if penalty and penalty in self.personality:
            return False

        # Favorability range (only when targeting another NPC)
        if target_npc:
            rel = self.relationship_mgr.get_relation(target_npc.get("id"))
            fav = rel.get("favorability", 0) if rel else 0

            min_fav = req.get("min_favorability")
            max_fav = req.get("max_favorability")

            if min_fav is not None and fav < min_fav:
                return False
            if max_fav is not None and fav > max_fav:
                return False

        return True

    def _calculate_weight(self, info: dict, target_npc: dict | None = None) -> float:
        """Calculate adjusted selection weight."""
        weight = float(info.get("base_weight", 5))
        req = info.get("requirements", {})
        category = info.get("category", "solo")

        # Personality boost
        boost = req.get("personality_boost")
        if boost and boost in self.personality:
            weight *= 1.5

        # Mood modifiers
        if self.mood == "happy" and category in ("friendly", "intimate", "couple"):
            weight *= 1.2
        elif self.mood == "sad" and category == "solo":
            weight *= 1.3
        elif self.mood == "angry" and category == "negative":
            weight *= 2.0

        # Late-night: less active, more naps
        if self.game_hour >= 22 or self.game_hour < 6:
            if category == "solo":
                weight *= 0.7
            if info.get("name_cn") == "打盹":
                weight *= 2.0

        # Target in dialogue → very unlikely to interact
        if target_npc and target_npc.get("in_dialogue"):
            weight *= 0.1

        return max(weight, 0.1)

    def _build_result(self, name: str, info: dict,
                      target: dict | None) -> AutoActionResult:
        """Build the result with substituted display text."""
        variants = info.get("display_variants", [info.get("display_text", "")])
        chosen = random.choice(variants) if variants else ""

        # Substitute placeholders
        if target:
            chosen = chosen.replace("{target}", target.get("name", "某人"))
        chosen = chosen.replace("{actor}", self.npc_name)

        return AutoActionResult(
            action_name=name,
            action_info=info,
            target_id=target.get("id", "") if target else "",
            target_name=target.get("name", "") if target else "",
            display_text=chosen,
            icon=info.get("icon", ""),
            animation=info.get("animation", AnimType.NONE),
            category=info.get("category", "solo"),
            duration_ticks=info.get("duration_ticks", 3),
            cooldown_ticks=info.get("cooldown_ticks", 20),
        )
