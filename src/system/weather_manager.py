"""
Weather state machine.
Transitions: sunny ↔ cloudy → rainy → stormy → rainy → cloudy → sunny
Winter can add snowy weather.
"""

import random
from typing import Optional


WEATHER_TRANSITIONS = {
    "sunny":  ["cloudy"],
    "cloudy": ["sunny", "rainy", "snowy"],
    "rainy":  ["cloudy", "stormy"],
    "stormy": ["rainy"],
    "snowy":  ["cloudy"],
}

WEATHER_WEIGHTS = {
    ("sunny", "cloudy"):  0.15,
    ("cloudy", "sunny"):  0.25,
    ("cloudy", "rainy"):  0.20,
    ("cloudy", "snowy"):  0.05,
    ("rainy", "stormy"):  0.10,
    ("rainy", "cloudy"):  0.30,
    ("stormy", "rainy"):  0.40,
    ("snowy", "cloudy"):  0.25,
}

WEATHER_EMOJI = {
    "sunny":  "☀️",
    "cloudy": "☁️",
    "rainy":  "🌧️",
    "stormy": "⛈️",
    "snowy":  "❄️",
}


class WeatherManager:
    def __init__(self, broker, initial: str = "sunny"):
        self.broker = broker
        self.current = initial

    def state_dict(self) -> dict:
        return {
            "type": self.current,
            "emoji": WEATHER_EMOJI.get(self.current, "❓"),
            "intensity": "heavy" if self.current == "stormy" else "light",
        }

    def transition(self, season: str) -> Optional[str]:
        """Attempt a weather transition. Returns new weather if changed, None otherwise."""
        candidates = WEATHER_TRANSITIONS.get(self.current, [])
        if not candidates:
            return None

        # Filter out snowy if not winter
        if season != "winter":
            candidates = [c for c in candidates if c != "snowy"]

        if not candidates:
            return None

        # Weighted random choice
        weights = []
        for c in candidates:
            w = WEATHER_WEIGHTS.get((self.current, c), 0.1)
            weights.append(w)

        total = sum(weights)
        if total == 0:
            return None

        # Normalize and pick
        r = random.random() * total
        cumulative = 0
        for c, w in zip(candidates, weights):
            cumulative += w
            if r <= cumulative:
                self.current = c
                return c

        return None

    async def try_transition(self, season: str):
        """Attempt transition and publish if changed."""
        result = self.transition(season)
        if result:
            await self.broker.publish("system:weather", self.state_dict())
            await self.broker.kv_set("state:weather", self.state_dict())
