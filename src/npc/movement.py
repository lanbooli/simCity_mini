"""
NPC movement system. Schedule-driven with random free-time movement.
"""

import json
import random
from typing import Optional

# Public scene pools for photo NPCs who need auto-generated schedules.
# Excludes home-type scenes so photo NPCs randomly pick a public place.
_PUBLIC_SCENE_POOLS = {
    "young": ["scene_coffee_shop", "scene_park", "scene_school", "scene_library"],
    "adult": ["scene_coffee_shop", "scene_park", "scene_market", "scene_library"],
}


def generate_default_schedule(
    home_scene_id: str,
    public_scenes: list[str],
    career: str = "",
    career_workplace: dict | None = None,
) -> dict:
    """Auto-generate a basic daily schedule for NPCs without one.

    Returns {"weekday": {...}, "weekend": {...}} with day-type-aware schedules.
    Career-aware: NPCs with a workplace go there on weekdays, free-roam on weekends.
    """
    if not home_scene_id:
        return {}

    pool = [s for s in public_scenes if s != home_scene_id and not s.startswith("apt_") and s != "home_player"]
    if not pool:
        return {}

    workplace_id = ""
    if career and career_workplace:
        workplace_id = career_workplace.get(career, "")

    leave_hour = random.randint(7, 9)
    leave_min = random.choice([0, 15, 30, 45])

    if workplace_id:
        # ── Weekday: work day ──
        lunch_scene = random.choice(pool)
        evening_scene = random.choice(pool)
        weekday = {
            f"{leave_hour:02d}:{leave_min:02d}": {
                "activity": "出门上班",
                "scene": workplace_id,
            },
            "12:00": {
                "activity": "午休吃饭",
                "scene": lunch_scene,
            },
            "13:00": {
                "activity": "继续工作",
                "scene": workplace_id,
            },
            "17:00": {
                "activity": "下班后散步",
                "scene": evening_scene,
            },
            "20:00": {
                "activity": "回家休息",
                "scene": home_scene_id,
            },
        }
        # ── Weekend: free day ──
        weekend_leave = random.randint(9, 11)
        weekend = {
            f"{weekend_leave:02d}:00": {
                "activity": "出门逛逛",
                "scene": random.choice(pool),
            },
            "12:00": {
                "activity": "吃午饭",
                "scene": random.choice(pool),
            },
            "15:00": {
                "activity": "休闲时光",
                "scene": random.choice(pool),
            },
            "20:00": {
                "activity": "回家休息",
                "scene": home_scene_id,
            },
        }
        return {"weekday": weekday, "weekend": weekend}
    else:
        # ── No workplace: same schedule every day ──
        morning_scene = random.choice(pool)
        afternoon_scene = random.choice(pool)
        day_schedule = {
            f"{leave_hour:02d}:{leave_min:02d}": {
                "activity": "出门",
                "scene": morning_scene,
            },
            "12:00": {
                "activity": "吃午饭",
                "scene": random.choice(pool),
            },
            "15:00": {
                "activity": "闲逛",
                "scene": afternoon_scene,
            },
            "20:00": {
                "activity": "回家休息",
                "scene": home_scene_id,
            },
        }
        return {"weekday": day_schedule, "weekend": day_schedule}


class MovementManager:
    def __init__(self, npc_id: str, schedule: dict, current_scene: str):
        self.npc_id = npc_id
        self.schedule = schedule  # {"weekday": {HH:MM: ...}, "weekend": {HH:MM: ...}} or flat {HH:MM: ...}
        self.current_scene = current_scene
        self._available_scenes: list[str] = []
        self._schedule_cache: dict[str, list[tuple[int, dict]]] = {}  # "weekday"/"weekend" → sorted entries
        self._has_day_types = False

    def set_available_scenes(self, scene_ids: list[str]):
        self._available_scenes = scene_ids
        self._build_schedule_cache()

    def _build_schedule_cache(self):
        """Parse schedule into sortable (minutes, entry) tuples. Supports day-type-aware format."""
        # Detect day-type format: {"weekday": {...}, "weekend": {...}}
        if "weekday" in self.schedule or "weekend" in self.schedule:
            self._has_day_types = True
            for day_type in ("weekday", "weekend"):
                entries = self.schedule.get(day_type, {})
                cache = []
                for time_str, entry in entries.items():
                    try:
                        h, m = time_str.split(":")
                        total_mins = int(h) * 60 + int(m)
                        cache.append((total_mins, entry))
                    except (ValueError, KeyError):
                        pass
                cache.sort(key=lambda x: x[0])
                self._schedule_cache[day_type] = cache
        else:
            # Legacy flat format: treat as every-day schedule
            self._has_day_types = False
            cache = []
            for time_str, entry in self.schedule.items():
                try:
                    h, m = time_str.split(":")
                    total_mins = int(h) * 60 + int(m)
                    cache.append((total_mins, entry))
                except (ValueError, KeyError):
                    pass
            cache.sort(key=lambda x: x[0])
            self._schedule_cache["all"] = cache

    @staticmethod
    def _is_weekend(day: int) -> bool:
        """Day 6 (Saturday) and Day 7/0 (Sunday) are weekends."""
        return day % 7 in (6, 0)

    def get_schedule_for_time(self, hour: int, minute: int, day: int = 1) -> Optional[dict]:
        """Get the scheduled activity for a given game time and day."""
        current_mins = hour * 60 + minute

        if self._has_day_types:
            day_type = "weekend" if self._is_weekend(day) else "weekday"
            cache = self._schedule_cache.get(day_type, [])
        else:
            cache = self._schedule_cache.get("all", [])

        best_entry = None
        for total_mins, entry in cache:
            if total_mins <= current_mins:
                best_entry = entry
            else:
                break
        return best_entry

    def decide_movement(self, hour: int, minute: int, current_scene: str, day: int = 1) -> Optional[dict]:
        """
        Decide if NPC should move. Returns movement action dict or None.

        Returns: {"scene_id": "...", "activity": "...", "reason": "schedule"|"random"}
        """
        # Priority 1: Schedule
        scheduled = self.get_schedule_for_time(hour, minute, day)
        if scheduled and scheduled.get("scene"):
            target_scene = scheduled["scene"]
            if target_scene != current_scene:
                return {
                    "scene_id": target_scene,
                    "activity": scheduled.get("activity", ""),
                    "reason": "schedule",
                }
            elif scheduled.get("activity") and scheduled["activity"] != "":
                return {
                    "scene_id": current_scene,
                    "activity": scheduled["activity"],
                    "reason": "schedule_activity",
                }

        # Priority 2: Random exploration (10% chance per decision cycle)
        if random.random() < 0.10 and self._available_scenes:
            target = random.choice(self._available_scenes)
            if target != current_scene:
                return {
                    "scene_id": target,
                    "activity": "闲逛",
                    "reason": "random",
                }

        return None

    def get_current_activity(self, hour: int, minute: int, day: int = 1, default: str = "") -> str:
        """Get NPC's current activity based on schedule."""
        scheduled = self.get_schedule_for_time(hour, minute, day)
        if scheduled:
            return scheduled.get("activity", default)
        return default
