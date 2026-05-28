"""
Social Handshake Protocol: 3-phase rules engine for NPC↔NPC social negotiation.

Phase 1: A sends invitation (rules decide who/what/where, no LLM)
Phase 2: B responds (accept / counter-offer / reject, pure rules)
Phase 3: A confirms (confirm / re-counter / abort)

LLM is only invoked AFTER successful handshake, for content performance.
"""
import logging
import random
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger("npc.handshake")


class HandshakeDecision(StrEnum):
    ACCEPT = "accept"
    COUNTER = "counter"
    REJECT = "reject"


class Activity(StrEnum):
    EAT_TOGETHER = "一起吃饭"
    CHAT = "闲聊"
    INTIMATE = "亲密互动"
    GATHER = "一起采集"
    VISIT = "拜访探望"


# Scene facility lookup by scene_type
SCENE_FACILITIES = {
    "restaurant":  {"has_food": True,  "has_water": True,  "safe_sleep": False},
    "cafe":        {"has_food": True,  "has_water": True,  "safe_sleep": False},
    "home":        {"has_food": True,  "has_water": True,  "safe_sleep": True},
    "hotel":       {"has_food": False, "has_water": True,  "safe_sleep": True},
    "park":        {"has_food": False, "has_water": False, "safe_sleep": False},
    "market":      {"has_food": True,  "has_water": True,  "safe_sleep": False},
    "office":      {"has_food": False, "has_water": True,  "safe_sleep": False},
    "hospital":    {"has_food": True,  "has_water": True,  "safe_sleep": True},
    "school":      {"has_food": False, "has_water": True,  "safe_sleep": False},
    "bar":         {"has_food": True,  "has_water": True,  "safe_sleep": False},
    "gym":         {"has_food": False, "has_water": True,  "safe_sleep": False},
    "library":     {"has_food": False, "has_water": True,  "safe_sleep": False},
    "indoor":      {"has_food": False, "has_water": True,  "safe_sleep": False},
    "outdoor":     {"has_food": False, "has_water": False, "safe_sleep": False},
    "shop":        {"has_food": False, "has_water": False, "safe_sleep": False},
}


def scene_has(scene_type: str, facility: str) -> bool:
    return SCENE_FACILITIES.get(scene_type, {}).get(facility, False)


# ── Phase 1: Intent Decision ────────────────────────

@dataclass
class SocialIntent:
    target_id: str
    target_name: str
    activity: str
    proposed_location: str = ""   # scene_id where activity should happen
    reason: str = ""


def decide_social_intent(
    my_id: str,
    my_scene_id: str,
    my_scene_type: str,
    my_phys,           # PhysiologyManager
    my_rels,           # RelationshipManager
    candidates: list[dict],  # [{"id":..., "name":..., "scene_id":..., "scene_type":..., "in_dialogue":bool}]
) -> SocialIntent | None:
    """
    Pure rules: decide who to socialize with and what to do.
    Returns None if no suitable target or no social need.
    """
    if not my_phys.can_socialize() or not my_phys.wants_social():
        return None

    # Filter: must be nearby (same scene or reachable), not in dialogue, has relationship
    viable = []
    for c in candidates:
        if c["id"] == my_id:
            continue
        if c.get("in_dialogue", False):
            continue
        rel = my_rels.get_relation(c["id"])
        if not rel or rel.get("favorability", 0) < -30:
            continue
        # Must be in same scene or my scene (reachable simplification)
        if c.get("scene_id") != my_scene_id:
            continue
        viable.append((c, rel))

    if not viable:
        return None

    # Pick target: highest favorability
    viable.sort(key=lambda x: x[1].get("favorability", 0), reverse=True)
    target, rel = viable[0]

    fav = rel.get("favorability", 0)
    rel_type = rel.get("relationship_type", "stranger")

    # Determine activity based on needs + relationship
    my_hungry = my_phys.needs_food()
    target_has_food = scene_has(target.get("scene_type", "indoor"), "has_food")
    my_has_food = scene_has(my_scene_type, "has_food")

    activity = Activity.CHAT  # default

    if my_hungry and (target_has_food or my_has_food):
        activity = Activity.EAT_TOGETHER
    elif fav >= 80 and rel_type in ("boyfriend", "girlfriend", "spouse"):
        activity = Activity.INTIMATE
    elif rel_type in ("friend", "best_friend") and fav >= 60:
        activity = Activity.CHAT

    # Determine location: who has food? who is less mobile?
    loc = my_scene_id
    if activity == Activity.EAT_TOGETHER:
        loc = my_scene_id if my_has_food else target["scene_id"]
    elif activity == Activity.INTIMATE:
        # Go to the less public place (prefer home/hotel)
        if scene_has(my_scene_type, "safe_sleep"):
            loc = my_scene_id
        elif scene_has(target.get("scene_type", ""), "safe_sleep"):
            loc = target["scene_id"]
        else:
            loc = my_scene_id

    logger.debug(
        f"Social intent: {my_id} → {target['id']} "
        f"activity={activity.value} loc={loc} reason=fav={fav}"
    )

    return SocialIntent(
        target_id=target["id"],
        target_name=target.get("name", ""),
        activity=activity.value,
        proposed_location=loc,
        reason=f"fav={fav} hungry={my_hungry}",
    )


# ── Phase 2: B's Response ───────────────────────────

@dataclass
class HandshakeResponse:
    decision: str          # accept / counter / reject
    activity: str = ""     # accepted or counter-proposed activity
    location: str = ""     # accepted or counter-proposed location
    reason: str = ""       # human-readable reason
    message: str = ""      # short template message


def evaluate_invitation(
    intent: SocialIntent,
    target_id: str,
    target_phys,           # PhysiologyManager
    target_rels,           # RelationshipManager
    target_scene_id: str,
    target_scene_type: str,
    target_in_dialogue: bool = False,
) -> HandshakeResponse:
    """
    B receives A's invitation. Returns accept, counter, or reject.
    Pure rules — no LLM.
    """
    # ── Force reject conditions ──
    if target_in_dialogue:
        return HandshakeResponse(HandshakeDecision.REJECT, reason="busy_in_dialogue",
                                 message="我现在正忙着呢。")
    if target_phys.is_dead:
        return HandshakeResponse(HandshakeDecision.REJECT, reason="dead",
                                 message="")
    crisis = target_phys.crisis()
    if crisis:
        return HandshakeResponse(HandshakeDecision.REJECT, reason=f"crisis_{crisis}",
                                 message="我现在有点不舒服，改天吧。")

    rel = target_rels.get_relation(intent.target_id) or {}
    fav = rel.get("favorability", 0)

    # Hostile relationship → reject
    if fav < -50:
        return HandshakeResponse(HandshakeDecision.REJECT, reason="hostile",
                                 message="我不想和你说话。")

    # ── Need matching ──
    activity = intent.activity

    if activity == Activity.EAT_TOGETHER.value:
        if target_phys.hunger > 80:
            # B is not hungry → counter-offer to chat
            return HandshakeResponse(
                HandshakeDecision.COUNTER,
                activity=Activity.CHAT.value,
                location=target_scene_id,
                reason="not_hungry",
                message="我不太饿，不过可以陪你聊会儿。",
            )
        # Both hungry → accept
        return HandshakeResponse(
            HandshakeDecision.ACCEPT,
            activity=activity,
            location=intent.proposed_location,
            reason="both_hungry",
            message="好，我这就来。",
        )

    elif activity == Activity.INTIMATE.value:
        if fav < 70:
            return HandshakeResponse(HandshakeDecision.REJECT, reason="insufficient_intimacy",
                                     message="我们还没到那个地步吧...")
        return HandshakeResponse(
            HandshakeDecision.ACCEPT,
            activity=activity,
            location=intent.proposed_location,
            reason="mutual_affection",
            message="嗯...好啊。",
        )

    elif activity in (Activity.CHAT.value, Activity.VISIT.value):
        # Check social needs
        if target_phys.social < 40:
            return HandshakeResponse(
                HandshakeDecision.ACCEPT, activity=activity,
                location=intent.proposed_location,
                reason="social_need",
                message="正好，我也想找人聊聊天。",
            )
        elif fav >= 30:
            return HandshakeResponse(
                HandshakeDecision.ACCEPT, activity=activity,
                location=intent.proposed_location,
                reason="friendship",
                message="好啊，聊会儿。",
            )
        else:
            return HandshakeResponse(HandshakeDecision.REJECT, reason="low_interest",
                                     message="改天吧。")

    # Default: accept if favorability is non-negative
    if fav >= 0:
        return HandshakeResponse(
            HandshakeDecision.ACCEPT, activity=activity,
            location=intent.proposed_location,
            reason="default_accept",
            message="好。",
        )
    return HandshakeResponse(HandshakeDecision.REJECT, reason="low_favorability",
                             message="下次吧。")


# ── Phase 3: A Confirms ─────────────────────────────

@dataclass
class ConfirmedActivity:
    confirmed: bool
    activity: str = ""
    location: str = ""       # scene_id
    duration_hint: str = "short"  # short / long
    participants: list[dict] = field(default_factory=list)


def confirm_handshake(
    intent: SocialIntent,
    response: HandshakeResponse,
    initiator_phys,        # PhysiologyManager
    initiator_scene_id: str,
    initiator_scene_type: str,
    target_name: str = "",
) -> ConfirmedActivity:
    """A receives B's response. Returns final confirmed activity or rejected."""
    if response.decision == HandshakeDecision.REJECT:
        return ConfirmedActivity(confirmed=False)

    if response.decision == HandshakeDecision.ACCEPT:
        # Determine duration hint
        duration = "short"
        if initiator_phys.energy > 50 and initiator_phys.hunger > 40:
            duration = "long"
        return ConfirmedActivity(
            confirmed=True,
            activity=response.activity or intent.activity,
            location=response.location or intent.proposed_location,
            duration_hint=duration,
        )

    if response.decision == HandshakeDecision.COUNTER:
        # Can I accept the counter?
        counter_activity = response.activity
        if counter_activity == Activity.CHAT.value:
            # Always accept chat counter-offer if I wanted to socialize
            duration = "short"
            if initiator_phys.energy > 50:
                duration = "long"
            return ConfirmedActivity(
                confirmed=True,
                activity=counter_activity,
                location=response.location or initiator_scene_id,
                duration_hint=duration,
            )

        # Other counters: accept if not in crisis
        if initiator_phys.crisis() is None:
            return ConfirmedActivity(
                confirmed=True,
                activity=counter_activity,
                location=response.location or initiator_scene_id,
                duration_hint="short",
            )

        return ConfirmedActivity(confirmed=False)

    return ConfirmedActivity(confirmed=False)
