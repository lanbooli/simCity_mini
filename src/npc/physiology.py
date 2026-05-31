"""
PhysiologyManager: rules-based physiological needs system.

Four stats (0-100): hunger, thirst, energy, social.
Crisis interrupt priority: thirst > hunger > energy.
Age stages affect stat caps; personality modifies decay rates.
"""
import json
import logging
import random
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger("npc.physiology")


class AgeStage(StrEnum):
    INFANT = "infant"
    CHILD = "child"
    ADULT = "adult"
    ELDER = "elder"


class Crisis(StrEnum):
    THIRST = "thirst"
    HUNGER = "hunger"
    ENERGY = "energy"


# Age stage thresholds and stat cap modifiers
AGE_CONFIG = {
    AgeStage.INFANT: {"max_age": 3, "stat_cap": 0.6, "can_socialize": False, "decay_mult": 2.0},
    AgeStage.CHILD:  {"max_age": 12, "stat_cap": 0.8, "can_socialize": True, "decay_mult": 1.2},
    AgeStage.ADULT:  {"max_age": 60, "stat_cap": 1.0, "can_socialize": True, "decay_mult": 1.0},
    AgeStage.ELDER:  {"max_age": 120, "stat_cap": 0.7, "can_socialize": True, "decay_mult": 1.3},
}

# Base decay per game hour (before personality/age modifiers)
# game_speed_multiplier=15 → 1 game hour = 4 real minutes
BASE_DECAY = {
    "hunger": 1.5,   # ~67 game hours from full → ~4.5 real hours
    "thirst": 2.0,   # ~50 game hours → ~3.3 real hours
    "energy": 1.0,   # ~100 game hours → ~6.7 real hours
    "social": 0.8,   # ~125 game hours → ~8.3 real hours
}

# Personality modifiers (multiply base decay)
PERSONALITY_MODIFIERS = {
    "外向": {"social": 1.5},
    "内向": {"social": 0.5},
    "贪吃": {"hunger": 1.3},
    "养生": {"hunger": 0.7, "thirst": 0.7},
    "懒惰": {"energy": 0.7},
    "精力旺盛": {"energy": 1.3},
}

# Crisis thresholds
CRISIS_THIRST = 20.0
CRISIS_HUNGER = 20.0
CRISIS_ENERGY = 10.0

# HP drain per hour when critical stat is 0
HP_DRAIN_RATE = 5.0  # hp per hour when starving/dehydrated

# Death probability per week for elders (daily_check triggers weekly)
ELDER_DEATH_BASE_AGE = 70
ELDER_DEATH_BASE_PROB = 0.007  # 0.7% per week at age 70 (was 0.1%/day)
ELDER_DEATH_MAX_PROB = 0.14    # 14% per week at age 90+


@dataclass
class PhysiologyState:
    hunger: float = 80.0
    thirst: float = 80.0
    energy: float = 80.0
    social: float = 80.0
    hp: float = 100.0
    age: int = 25
    age_stage: AgeStage = AgeStage.ADULT
    is_dead: bool = False
    death_cause: str = ""


class PhysiologyManager:
    """Manages physiological needs for one NPC. Pure rules, no LLM."""

    def __init__(self, npc_data: dict):
        self.npc_id = npc_data.get("id", "")
        self.npc_name = npc_data.get("name", "")
        self._personality = self._parse_personality(npc_data.get("personality", "[]"))
        self._age = self._calc_age(npc_data.get("birth_date", "2001-01-01"))
        self._stage = self._determine_stage(self._age)

        cap = AGE_CONFIG[self._stage]["stat_cap"]
        self.hunger = min(80.0, 100.0 * cap)
        self.thirst = min(80.0, 100.0 * cap)
        self.energy = min(80.0, 100.0 * cap)
        self.social = min(80.0, 100.0 * cap)
        self.hp = 100.0
        self.is_dead = False
        self.death_cause = ""

        self._hours_since_social = 0.0

    # ── public API ──────────────────────────────────

    def tick(self, delta_hours: float):
        """Advance physiology by delta_hours game hours."""
        if self.is_dead:
            return

        cap = AGE_CONFIG[self._stage]["stat_cap"] * 100.0
        age_mult = AGE_CONFIG[self._stage]["decay_mult"]

        # Apply decay
        for stat in ("hunger", "thirst", "energy", "social"):
            base = BASE_DECAY[stat]
            pers_mult = self._get_personality_mult(stat)
            decay = base * age_mult * pers_mult * delta_hours
            current = getattr(self, stat)
            setattr(self, stat, max(0.0, current - decay))

        self._hours_since_social += delta_hours
        self.hunger = min(self.hunger, cap)
        self.thirst = min(self.thirst, cap)
        self.energy = min(self.energy, cap)
        self.social = min(self.social, cap)

        # HP drain when starving or dehydrated
        if self.hunger <= 0 or self.thirst <= 0:
            self.hp -= HP_DRAIN_RATE * delta_hours
            if self.hp <= 0:
                self.is_dead = True
                self.death_cause = "starved" if self.hunger <= 0 else "dehydrated"
                logger.info(f"NPC {self.npc_name} died: {self.death_cause}")

        # Elder death check (run once per day via daily_check)
        if self.hp <= 0:
            self.is_dead = True
            if not self.death_cause:
                self.death_cause = "health_failure"

    def age_one_year(self):
        """Called ~once per 20 real days. Advances age by 1 year."""
        if self.is_dead:
            return

        self._age += 1
        old_stage = self._stage
        self._stage = self._determine_stage(self._age)

        if self._stage != old_stage:
            logger.info(f"NPC {self.npc_name} aged to {self._age}: {old_stage} → {self._stage}")
            cap = AGE_CONFIG[self._stage]["stat_cap"] * 100.0
            self.hunger = min(self.hunger, cap)
            self.thirst = min(self.thirst, cap)
            self.energy = min(self.energy, cap)
            self.social = min(self.social, cap)

    def elder_death_check(self):
        """Called every game midnight. Rolls for natural death if elderly."""
        if self.is_dead:
            return
        if self._stage != AgeStage.ELDER or self._age < ELDER_DEATH_BASE_AGE:
            return

        prob = ELDER_DEATH_BASE_PROB + (self._age - ELDER_DEATH_BASE_AGE) * 0.001
        prob = min(prob, ELDER_DEATH_MAX_PROB)
        if random.random() < prob:
            self.is_dead = True
            self.death_cause = "old_age"
            logger.info(f"NPC {self.npc_name} died of old age at {self._age}")

    def recover(self, stat: str, amount: float):
        """Recover a stat by amount. Used when NPC eats/drinks/sleeps/socializes."""
        if self.is_dead:
            return
        cap = AGE_CONFIG[self._stage]["stat_cap"] * 100.0
        current = getattr(self, stat)
        setattr(self, stat, min(cap, current + amount))
        if stat == "social":
            self._hours_since_social = 0.0

    def recover_tick(self, rates: dict):
        """Recover stats per tick based on rates dict {stat: amount_per_minute}."""
        if self.is_dead:
            return
        cap = AGE_CONFIG[self._stage]["stat_cap"] * 100.0
        for stat, amount in rates.items():
            if stat == "social":
                self._hours_since_social = 0.0
            current = getattr(self, stat)
            setattr(self, stat, min(cap, current + amount))

    def crisis(self) -> str | None:
        """Return current crisis type, or None. Thirst > hunger > energy priority."""
        if self.is_dead:
            return None
        if self.thirst < CRISIS_THIRST:
            return Crisis.THIRST
        if self.hunger < CRISIS_HUNGER:
            return Crisis.HUNGER
        if self.energy < CRISIS_ENERGY:
            return Crisis.ENERGY
        return None

    def can_socialize(self) -> bool:
        """True if no crisis and social need is present."""
        if self.is_dead:
            return False
        if not AGE_CONFIG[self._stage]["can_socialize"]:
            return False
        if self.crisis() is not None:
            return False
        return True

    def wants_social(self) -> bool:
        """True if social need is low enough to trigger social intent."""
        return self.social < 40.0

    def needs_food(self) -> bool:
        return self.hunger < 50.0

    def needs_drink(self) -> bool:
        return self.thirst < 50.0

    def needs_rest(self) -> bool:
        return self.energy < 30.0

    def snapshot(self) -> PhysiologyState:
        return PhysiologyState(
            hunger=self.hunger, thirst=self.thirst,
            energy=self.energy, social=self.social,
            hp=self.hp, age=self._age,
            age_stage=self._stage,
            is_dead=self.is_dead,
            death_cause=self.death_cause,
        )

    def summary(self) -> str:
        """One-line Chinese summary for LLM context."""
        if self.is_dead:
            return "已死亡"
        parts = []
        if self.hunger < 30:
            parts.append("饥饿")
        elif self.hunger < 60:
            parts.append("有点饿")
        if self.thirst < 20:
            parts.append("口渴")
        if self.energy < 20:
            parts.append("疲惫")
        if self.social < 30:
            parts.append("孤独")
        return "、".join(parts) if parts else "状态良好"

    # ── internal helpers ─────────────────────────────

    @staticmethod
    def _parse_personality(raw) -> list[str]:
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return [t.strip() for t in raw.split(",") if t.strip()]
        return []

    @staticmethod
    def _calc_age(birth_date: str) -> int:
        try:
            birth_year = int(birth_date.split("-")[0])
            return max(1, 2026 - birth_year)
        except (ValueError, IndexError):
            return 25

    @staticmethod
    def _determine_stage(age: int) -> AgeStage:
        for stage in (AgeStage.INFANT, AgeStage.CHILD, AgeStage.ADULT, AgeStage.ELDER):
            if age <= AGE_CONFIG[stage]["max_age"]:
                return stage
        return AgeStage.ELDER

    def _get_personality_mult(self, stat: str) -> float:
        m = 1.0
        for trait in self._personality:
            mods = PERSONALITY_MODIFIERS.get(trait, {})
            m *= mods.get(stat, 1.0)
        return m
