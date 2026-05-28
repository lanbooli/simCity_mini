"""
NPC relationship manager. Handles favorability, familiarity, and relationship type transitions.
"""

from typing import Optional
from src.common.database import get_connection, execute, fetch_one
from src.common.utils import clamp, now_iso


class RelationshipManager:
    def __init__(self, npc_id: str):
        self.npc_id = npc_id
        self._cache: dict[str, dict] = {}  # other_id -> relationship dict

    def load_relationships(self, db_path: str = ""):
        """Load all relationships where this NPC is entity_a."""
        conn = get_connection(db_path)
        try:
            rows = conn.execute(
                "SELECT * FROM relationship WHERE entity_a_id = ? AND entity_a_type = 'npc'",
                (self.npc_id,)
            ).fetchall()
            for r in rows:
                d = dict(r)
                self._cache[d["entity_b_id"]] = d
        finally:
            conn.close()

    def get_relation(self, other_id: str) -> Optional[dict]:
        return self._cache.get(other_id)

    def get_or_create_relation(self, other_id: str, other_type: str = "player",
                               db_path: str = "") -> dict:
        """Get existing relationship or create a default stranger one."""
        rel = self._cache.get(other_id)
        if rel:
            return rel

        # Create default stranger relationship
        from src.common.models import gen_id
        rel = {
            "id": gen_id(),
            "entity_a_id": self.npc_id,
            "entity_a_type": "npc",
            "entity_b_id": other_id,
            "entity_b_type": other_type,
            "relationship_type": "stranger",
            "favorability": 0,
            "familiarity": 0,
            "intimacy_comfort": 0,
            "love_eligible": 0,
            "jealousy_level": 0,
            "breakup_count": 0,
            "divorced": 0,
            "violation_count": 0,
            "interaction_count": 0,
            "last_interaction_at": None,
        }
        self._save_relation(rel, db_path)
        self._cache[other_id] = rel
        return rel

    def update_interaction(self, other_id: str, favorability_delta: int,
                           other_type: str = "player", db_path: str = "") -> dict:
        """Process an interaction: update favorability, familiarity, and check transitions."""
        rel = self.get_or_create_relation(other_id, other_type, db_path)

        # Apply favorability change rules
        adjusted_delta = self._adjust_favorability(rel, favorability_delta)

        rel["favorability"] = clamp(rel["favorability"] + adjusted_delta, -100, 100)
        rel["familiarity"] = clamp(rel["familiarity"] + 1, 0, 100)
        rel["interaction_count"] = rel["interaction_count"] + 1
        rel["last_interaction_at"] = now_iso()

        # Check relationship type transition
        new_type = self._check_type_transition(rel)
        if new_type != rel["relationship_type"]:
            rel["relationship_type"] = new_type

        self._save_relation(rel, db_path)
        self._cache[other_id] = rel
        return rel

    def _adjust_favorability(self, rel: dict, delta: int) -> int:
        """Apply post-processing rules to favorability delta."""
        # Rule: strangers are less affected, but every interaction counts
        if rel["familiarity"] < 10:
            delta = max(delta // 2, 1) if delta > 0 else (min(delta // 2, -1) if delta < 0 else 0)

        # Rule: close friends are more forgiving
        if rel["favorability"] >= 80 and delta < 0:
            delta = min(delta + 1, 0)

        # Rule: deep grudges are hard to overcome
        if rel["favorability"] <= -80 and delta > 0:
            delta = max(delta - 1, 0)

        # Curve scale: harder to increase at extremes
        delta = self._curve_scale(rel["favorability"], delta)

        return clamp(delta, -3, 3)

    def _curve_scale(self, favorability: int, delta: int) -> int:
        """Nonlinear scaling: harder to improve at extremes."""
        abs_fav = abs(favorability)
        if abs_fav < 30:
            return delta
        elif abs_fav < 60:
            return int(delta * 0.8)
        elif abs_fav < 80:
            return int(delta * 0.55)
        else:
            return int(delta * 0.3)

    def _check_type_transition(self, rel: dict) -> str:
        """Check if relationship type should change based on favorability thresholds."""
        fav = rel["favorability"]
        fam = rel["familiarity"]
        current = rel["relationship_type"]

        # Fixed relationships don't change
        if current in ("parent", "sibling", "child"):
            return current

        # Positive progression (requires minimum familiarity)
        if fam >= 5 and fav >= 10 and current == "stranger":
            return "acquaintance"
        if fam >= 15 and fav >= 30 and current == "acquaintance":
            return "friend"
        if fam >= 30 and fav >= 70 and current == "friend":
            return "best_friend"

        # Negative progression
        if fav <= -10 and current in ("stranger", "acquaintance"):
            return "dislike"
        if fav <= -50 and current == "dislike":
            return "enemy"

        # Recovery from negative
        if fav >= 0 and current == "enemy":
            return "dislike"
        if fav >= 15 and current == "dislike":
            return "stranger"

        # Check love eligibility
        if fav >= 80 and fam >= 35 and rel.get("intimacy_comfort", 0) >= 70:
            if current in ("friend", "best_friend", "acquaintance"):
                rel["love_eligible"] = 1

        return current

    # ── Romance / Intimacy methods ──────────────────

    def update_intimacy_comfort(self, other_id: str, delta: int, other_type: str = "player"):
        """Adjust intimacy comfort level."""
        rel = self.get_or_create_relation(other_id, other_type)
        rel["intimacy_comfort"] = clamp(
            rel.get("intimacy_comfort", 0) + delta, 0, 100)
        self._save_relation(rel)
        self._cache[other_id] = rel
        return rel

    def check_love_eligible(self, other_id: str) -> bool:
        """Check if love confession threshold is met."""
        rel = self.get_relation(other_id)
        if not rel:
            return False
        return (rel.get("love_eligible", 0) == 1 and
                rel.get("favorability", 0) >= 80 and
                rel.get("intimacy_comfort", 0) >= 70 and
                rel.get("familiarity", 0) >= 35)

    def set_romantic_committed(self, other_id: str, relationship_type: str,
                                game_time: str, other_type: str = "player"):
        """Set relationship to romantic committed."""
        rel = self.get_or_create_relation(other_id, other_type)
        rel["relationship_type"] = relationship_type
        rel["committed_since"] = game_time
        rel["intimacy_comfort"] = min(100, rel.get("intimacy_comfort", 0) + 15)
        rel["favorability"] = clamp(rel.get("favorability", 0) + 5, -100, 100)
        rel["love_eligible"] = 0
        self._save_relation(rel)
        self._cache[other_id] = rel
        return rel

    def marry(self, other_id: str, game_time: str, other_type: str = "player"):
        """Set relationship to spouse."""
        rel = self.get_or_create_relation(other_id, other_type)
        if rel["relationship_type"] not in ("boyfriend", "girlfriend"):
            return rel
        rel["relationship_type"] = "spouse"
        rel["married_since"] = game_time
        rel["favorability"] = clamp(rel.get("favorability", 0) + 10, -100, 100)
        rel["intimacy_comfort"] = 100
        self._save_relation(rel)
        self._cache[other_id] = rel
        return rel

    def breakup(self, other_id: str, game_time: str, other_type: str = "player"):
        """End a romantic relationship."""
        rel = self.get_or_create_relation(other_id, other_type)
        rel["relationship_type"] = "acquaintance"
        rel["intimacy_comfort"] = 0
        rel["love_eligible"] = 0
        rel["jealousy_level"] = 0
        rel["favorability"] = clamp(rel.get("favorability", 0) - 30, -100, 100)
        rel["breakup_count"] = rel.get("breakup_count", 0) + 1
        rel["committed_since"] = None
        self._save_relation(rel)
        self._cache[other_id] = rel
        return rel

    def divorce(self, other_id: str, game_time: str, other_type: str = "player"):
        """End a marriage."""
        rel = self.get_or_create_relation(other_id, other_type)
        rel["relationship_type"] = "stranger"
        rel["intimacy_comfort"] = 0
        rel["love_eligible"] = 0
        rel["jealousy_level"] = 0
        rel["favorability"] = clamp(rel.get("favorability", 0) - 50, -100, 100)
        rel["divorced"] = 1
        rel["married_since"] = None
        rel["committed_since"] = None
        self._save_relation(rel)
        self._cache[other_id] = rel
        return rel

    def add_jealousy(self, other_id: str, amount: int, other_type: str = "player"):
        """Increase jealousy level."""
        rel = self.get_or_create_relation(other_id, other_type)
        rel["jealousy_level"] = clamp(
            rel.get("jealousy_level", 0) + amount, 0, 100)
        self._save_relation(rel)
        self._cache[other_id] = rel
        return rel

    def record_violation(self, other_id: str, other_type: str = "player"):
        """Record a boundary violation."""
        rel = self.get_or_create_relation(other_id, other_type)
        rel["violation_count"] = rel.get("violation_count", 0) + 1
        self._save_relation(rel)
        self._cache[other_id] = rel
        return rel

    def _save_relation(self, rel: dict, db_path: str = ""):
        conn = get_connection(db_path)
        try:
            execute(conn, """INSERT OR REPLACE INTO relationship
                           (id, entity_a_id, entity_a_type, entity_b_id, entity_b_type,
                            relationship_type, favorability, familiarity,
                            intimacy_comfort, love_eligible, jealousy_level,
                            breakup_count, divorced, violation_count,
                            interaction_count, last_interaction_at,
                            committed_since, married_since, updated_at)
                           VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (rel["id"], rel["entity_a_id"], rel["entity_a_type"],
                     rel["entity_b_id"], rel["entity_b_type"],
                     rel["relationship_type"], rel["favorability"], rel["familiarity"],
                     rel.get("intimacy_comfort", 0), rel.get("love_eligible", 0),
                     rel.get("jealousy_level", 0), rel.get("breakup_count", 0),
                     rel.get("divorced", 0), rel.get("violation_count", 0),
                     rel["interaction_count"], rel["last_interaction_at"],
                     rel.get("committed_since", None), rel.get("married_since", None)))
            conn.commit()
        finally:
            conn.close()

    def get_all_relations(self) -> list[dict]:
        return list(self._cache.values())
