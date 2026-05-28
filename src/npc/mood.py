"""
NPC mood state machine.
Moods: happy, neutral, sad, angry, excited, bored
"""

import random

MOOD_TRANSITIONS = {
    "happy":   {"decay": "neutral", "decay_rate": 0.1},
    "excited": {"decay": "happy",   "decay_rate": 0.2},
    "neutral": {"decay": "bored",   "decay_rate": 0.05},
    "bored":   {"decay": "neutral", "decay_rate": 0.1},
    "sad":     {"decay": "neutral", "decay_rate": 0.08},
    "angry":   {"decay": "neutral", "decay_rate": 0.12},
}

MOOD_PRIORITIES = {
    "happy": 5, "excited": 6, "neutral": 3,
    "sad": 2, "angry": 1, "bored": 2,
}


class MoodManager:
    def __init__(self, initial: str = "neutral"):
        self.current = initial
        self._intensity = 1.0  # 0.0-1.0
        self._hours_in_mood = 0

    def state_dict(self) -> dict:
        return {
            "mood": self.current,
            "intensity": round(self._intensity, 2),
            "hours_in_mood": self._hours_in_mood,
        }

    def update(self, hours_passed: float = 1.0):
        """Natural mood decay over time."""
        self._hours_in_mood += hours_passed
        decay_info = MOOD_TRANSITIONS.get(self.current, {})
        decay_rate = decay_info.get("decay_rate", 0.05)

        # Check if mood should decay
        if self.current != "neutral" and random.random() < decay_rate * hours_passed:
            self.current = decay_info.get("decay", "neutral")
            self._hours_in_mood = 0
            self._intensity = 0.5
        elif self.current == "neutral" and random.random() < decay_rate * hours_passed:
            self.current = "bored"
            self._hours_in_mood = 0

    def affect(self, favorability_change: int):
        """Modify mood based on favorability change from dialogue."""
        if favorability_change >= 2:
            self.current = "happy"
            self._intensity = min(1.0, self._intensity + 0.3)
            self._hours_in_mood = 0
        elif favorability_change == 1:
            if self.current in ("neutral", "bored", "sad"):
                self.current = "happy"
                self._intensity = 0.6
        elif favorability_change <= -2:
            self.current = "angry"
            self._intensity = min(1.0, self._intensity + 0.4)
            self._hours_in_mood = 0
        elif favorability_change == -1:
            if self.current in ("happy", "excited"):
                self.current = "neutral"
            elif self.current == "neutral":
                self.current = "sad"
                self._intensity = 0.4

    def set_mood(self, mood: str, intensity: float = 0.5):
        """Force-set a specific mood (for events)."""
        if mood in MOOD_TRANSITIONS:
            self.current = mood
            self._intensity = max(0.1, min(1.0, intensity))
            self._hours_in_mood = 0
