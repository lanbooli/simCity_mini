from __future__ import annotations

import logging
import json
from datetime import datetime
from typing import Optional


def setup_logging(name: str, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def game_time_to_str(day: int, hour: int, minute: int) -> str:
    """Format game time as 'Day {day}, {hour:02d}:{minute:02d}'"""
    return f"Day {day}, {hour:02d}:{minute:02d}"


def game_time_to_minutes(day: int, hour: int, minute: int) -> int:
    """Convert game time to total minutes for comparison."""
    return day * 24 * 60 + hour * 60 + minute


def minutes_to_game_time(total_minutes: int) -> tuple[int, int, int]:
    """Convert total minutes to (day, hour, minute)."""
    day = total_minutes // (24 * 60)
    remaining = total_minutes % (24 * 60)
    hour = remaining // 60
    minute = remaining % 60
    return day, hour, minute


def get_day_phase(hour: int) -> str:
    """Return day phase based on hour."""
    if 5 <= hour < 8:
        return "dawn"
    elif 8 <= hour < 12:
        return "morning"
    elif 12 <= hour < 14:
        return "noon"
    elif 14 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 21:
        return "evening"
    elif 21 <= hour < 24:
        return "night"
    else:
        return "late_night"


def get_season(day: int) -> str:
    """Return season based on day of year (90 days per season)."""
    year_day = day % 360
    if year_day < 90:
        return "spring"
    elif year_day < 180:
        return "summer"
    elif year_day < 270:
        return "autumn"
    else:
        return "winter"


def clamp(value: int, min_val: int, max_val: int) -> int:
    return max(min_val, min(value, max_val))


def jd(obj) -> str:
    """JSON dump shortcut."""
    return json.dumps(obj, ensure_ascii=False)


def jl(s: str) -> any:
    """JSON load shortcut."""
    return json.loads(s)


def now_iso() -> str:
    return datetime.utcnow().isoformat()
