"""
39-set complete personality judgment system.

Three layers:
  1. Master rules (3) — universal, highest priority
  2. Base personalities (24) — normal personality types
  3. Extreme personalities (12) — special/plot-driven types

Conflict priority: situation > emotion > instinct > personality > morality
"""

from __future__ import annotations
from typing import Optional

# ── Master Rules ──────────────────────────────────────────

MASTER_RULE_1 = "人性本能底层规则"
MASTER_RULE_1_DESC = "自保、避痛、求生、趋利优先。生理需求 > 社交需求。信任难建易崩。"

MASTER_RULE_2 = "情绪触发演变规则"
MASTER_RULE_2_DESC = (
    "持续温柔→依赖→交付软肋；持续冷漠→消耗爱意→彻底抽离；"
    "持续压迫→反抗→麻木→绝望→黑化；持续被偏爱→安全感爆棚；持续被否定→自卑封闭。"
)

MASTER_RULE_3 = "环境人格可变规则"
MASTER_RULE_3_DESC = (
    "顺境温和松弛，逆境冷漠多疑。长期善待则柔软，长期伤害则坚硬。"
    "重大创伤后人格永久偏移，无法恢复纯白状态。"
)

CONFLICT_PRIORITY = "处境状态 > 当下情绪 > 底层本能 > 性格人格 > 道德约束"

# ── Base Personalities (24) ───────────────────────────────

PERSONALITIES = {
    # --- Normal (1-6) ---
    1: {
        "name": "普通中庸人格",
        "intimacy_mod": 1.0,
        "home_style": "简单实用",
        "description": "不主动作恶，也不主动牺牲。绝对中立利己。怕麻烦、随大流。",
    },
    2: {
        "name": "善良温柔人格",
        "intimacy_mod": 1.5,
        "home_style": "整洁温馨",
        "description": "共情极强，习惯性体谅别人、委屈自己。生气快、原谅快。",
    },
    3: {
        "name": "自私利己人格",
        "intimacy_mod": 0.3,
        "home_style": "实用至上",
        "description": "一切以我不吃亏为核心。有利配合，无利抽身。内心清醒自私。",
    },
    4: {
        "name": "世俗现实人格",
        "intimacy_mod": 0.6,
        "home_style": "体面实用",
        "description": "情绪稳定、看人看价值。懂得人情世故，不相信无条件的爱。",
    },
    5: {
        "name": "佛系淡漠人格",
        "intimacy_mod": 0.2,
        "home_style": "极简清冷",
        "description": "不争不抢不怨不恨。情绪极低波动。底线极高，触碰即永久远离。",
    },
    6: {
        "name": "圆滑世故人格",
        "intimacy_mod": 1.0,
        "home_style": "表面热情",
        "description": "不得罪人、说话留三分。表面谁都好，内心谁不信。看似温柔，实则清醒薄情。",
    },
    # --- Temperament (7-12) ---
    7: {
        "name": "刚烈叛逆人格",
        "intimacy_mod": 1.0,
        "home_style": "个性化强",
        "description": "吃软不吃硬，越压迫越反抗。自尊心极高，宁折不弯。",
    },
    8: {
        "name": "懦弱自卑人格",
        "intimacy_mod": 0.1,
        "home_style": "暗淡封闭",
        "description": "极度自我否定。害怕冲突、不敢拒绝。极易被操控。",
    },
    9: {
        "name": "高冷禁欲人格",
        "intimacy_mod": 0.2,
        "home_style": "一尘不染",
        "description": "情绪极少波动。不爱社交。温柔极其稀缺，只给唯一特定的人。",
    },
    10: {
        "name": "活泼乐天人格",
        "intimacy_mod": 1.8,
        "home_style": "热闹欢快",
        "description": "情绪外放、爱笑爱热闹。自愈速度快。看似开朗，受伤后快速变冷。",
    },
    11: {
        "name": "敏感内向人格",
        "intimacy_mod": 0.4,
        "home_style": "安静私密",
        "description": "极度在意细节和态度。容易胡思乱想。积累失望后安静离开。",
    },
    12: {
        "name": "偏执执拗人格",
        "intimacy_mod": 1.3,
        "home_style": "专注沉溺",
        "description": "认定的事绝不放手。爱恨浓烈百倍。温柔可无限容忍，背叛永久记恨。",
    },
    # --- Life Stage (13-16) ---
    13: {
        "name": "青涩少女人格",
        "intimacy_mod": 0.6,
        "home_style": "可爱温馨",
        "description": "心思干净单纯。极易害羞脸皮薄。依赖心强，信任谁就全身心依附。",
    },
    14: {
        "name": "成熟御姐人格",
        "intimacy_mod": 0.5,
        "home_style": "优雅大气",
        "description": "情绪稳定、戒备心重。独立果断不依附。温柔专属，对外清冷。",
    },
    15: {
        "name": "少年意气人格",
        "intimacy_mod": 1.2,
        "home_style": "随性自由",
        "description": "重情义轻利益。热血冲动嫉恶如仇。被辜负后迅速成熟冷硬。",
    },
    16: {
        "name": "中年沉稳人格",
        "intimacy_mod": 0.5,
        "home_style": "稳重实用",
        "description": "情绪藏深、克制隐忍。责任优先。底线坚定，触碰绝不原谅。",
    },
    # --- Romance (17-20) ---
    17: {
        "name": "深情依恋恋爱人格",
        "intimacy_mod": 2.0,
        "home_style": "甜蜜温馨",
        "description": "爱上即卸下所有防备。极度敏感在意。攒够失望彻底绝情。",
    },
    18: {
        "name": "冷淡薄情恋爱人格",
        "intimacy_mod": 0.2,
        "home_style": "清冷疏离",
        "description": "不主动不黏人。爱意克制内敛。爱可随时抽身，不拖泥带水。",
    },
    19: {
        "name": "缺爱依恋恋爱人格",
        "intimacy_mod": 1.5,
        "home_style": "渴望温暖",
        "description": "极度渴望被偏爱。别人一点点好就加倍依赖。被好好爱会极度温柔。",
    },
    20: {
        "name": "理智绝情恋爱人格",
        "intimacy_mod": 0.3,
        "home_style": "冷静克制",
        "description": "感情排自我之后。不合则止，不内耗不回头。爱意消失即彻底冷漠。",
    },
    # --- Position (21-24) ---
    21: {
        "name": "弱势受害者人格",
        "intimacy_mod": 0.0,
        "home_style": "灰暗压抑",
        "description": "恐惧压制理智。不敢反抗不敢顶嘴。内心极度抵触，表面被迫配合。",
    },
    22: {
        "name": "强势掌控者人格",
        "intimacy_mod": 1.2,
        "home_style": "浮华讲究",
        "description": "极强掌控欲，享受支配快感。视顺从为理所应当。温柔+霸道混合。",
    },
    23: {
        "name": "落魄自卑人格",
        "intimacy_mod": 0.1,
        "home_style": "消沉暗淡",
        "description": "自我价值感极低。对善意极度感恩，对恶意极度记恨。",
    },
    24: {
        "name": "得志傲慢人格",
        "intimacy_mod": 0.4,
        "home_style": "浮华炫耀",
        "description": "自信心爆棚优越感强。轻视弱者。顺境嚣张，逆境易崩溃。",
    },
}

# ── Extreme Personalities (12) ────────────────────────────

EXTREME_PERSONALITIES = {
    25: {"name": "讨好型依附人格", "intimacy_mod": 1.8, "home_style": "过度整洁",
         "description": "习惯性迁就所有人。害怕被讨厌。内心长期压抑，最终爆发绝情。"},
    26: {"name": "病娇偏执人格", "intimacy_mod": 2.5, "home_style": "爱恨浓烈",
         "description": "爱即是占有。可以温柔极致也可极端疯狂。极致深情=极致疯狂。"},
    27: {"name": "自闭社恐人格", "intimacy_mod": 0.0, "home_style": "绝对封闭",
         "description": "惧怕社交。信任的人面前才展露真实情绪。"},
    28: {"name": "高傲自负人格", "intimacy_mod": 0.1, "home_style": "奢华张扬",
         "description": "自我认知极高。看不起平庸弱者。极强好胜心。"},
    29: {"name": "隐忍伪装人格", "intimacy_mod": 0.5, "home_style": "表面温和",
         "description": "表面温顺无害。所有情绪藏底。爆发即彻底决裂。"},
    30: {"name": "单纯天真人格", "intimacy_mod": 1.0, "home_style": "纯白洁净",
         "description": "相信人性本善。不懂套路伪装。纯真崩塌后黑化最快。"},
    31: {"name": "阴郁孤僻人格", "intimacy_mod": 0.1, "home_style": "昏暗封闭",
         "description": "不爱社交极度独处。防备心拉满。接纳某人后会极其专一。"},
    32: {"name": "温柔救赎人格", "intimacy_mod": 1.5, "home_style": "温暖治愈",
         "description": "天生温柔包容。擅长治愈他人。治愈别人的同时自己极易内耗。"},
    33: {"name": "报复黑化人格", "intimacy_mod": 0.0, "home_style": "冷硬灰暗",
         "description": "曾经善良被重伤后变冷。一寸伤害百倍奉还。黑化不可逆。"},
    34: {"name": "顺从奴性人格", "intimacy_mod": 1.0, "home_style": "卑微简陋",
         "description": "长期被掌控丧失反抗意识。自我价值极低，默认只配服从。"},
    35: {"name": "清醒旁观者人格", "intimacy_mod": 0.2, "home_style": "理性有序",
         "description": "不入局不深情不站队。看透所有人心理。温柔是礼貌，冷漠是本质。"},
    36: {"name": "善恶摇摆中立人格", "intimacy_mod": 0.8, "home_style": "随境而变",
         "description": "无绝对善恶随境遇切换。顺则为善，逆则生恶。最贴近真实人性。"},
}

ALL_PERSONALITIES = {**PERSONALITIES, **EXTREME_PERSONALITIES}


# ── Personality Engine ────────────────────────────────────

class PersonalityEngine:
    """Computes behavior modifiers for NPCs based on their personality type tags."""

    def __init__(self, personality_ids: list[int]):
        self.ids = personality_ids
        self._entries = [ALL_PERSONALITIES[pid] for pid in personality_ids if pid in ALL_PERSONALITIES]

    @property
    def intimacy_mod(self) -> float:
        """Average intimacy modifier across all personality types."""
        if not self._entries:
            return 1.0
        return sum(e["intimacy_mod"] for e in self._entries) / len(self._entries)

    @property
    def home_style(self) -> str:
        if not self._entries:
            return "普通"
        return " + ".join(e["home_style"] for e in self._entries)

    @property
    def primary_name(self) -> str:
        if not self._entries:
            return "普通中庸人格"
        return self._entries[0]["name"]

    def get_action_bonus(self, action_type: str) -> float:
        """Get personality flavor bonus for specific action types.

        action_type: 'feed' | 'wipe' | 'tidy' | 'apron' | 'lean' |
                     'walk' | 'hug' | 'cling' | 'cook' | 'gift' | 'hair' | 'tv'
        """
        flavor_map = {
            # 温柔/贤惠倾向
            "feed":  [2, 10, 17],
            "wipe":  [2, 11],
            "tidy":  [2, 14, 16],
            "apron": [2, 10, 17],
            "cook":  [2, 10, 14, 17, 32],
            "hair":  [2, 14, 17],
            # 依赖/撒娇倾向
            "lean":  [10, 13, 17, 19],
            "cling": [10, 13, 17, 19],
            # 外向/浪漫倾向
            "walk":  [10, 15, 17],
            "hug":   [10, 15, 17],
            "gift":  [2, 12, 17, 19, 32],
            # 随和
            "tv":    [5, 10, 16, 32],
        }

        relevant = flavor_map.get(action_type, [])
        if not relevant:
            return 1.0

        # Each matching personality type adds 30% boost
        matches = sum(1 for pid in self.ids if pid in relevant)
        return 1.0 + matches * 0.3


def calculate_intimacy_probability(
    base_prob: float,
    personality_engine: PersonalityEngine,
    mood: str,
    game_hour: int,
    is_home: bool = False,
    is_weekend: bool = False,
    together_minutes: float = 10.0,
) -> float:
    """Calculate final probability for an NPC to initiate an intimate action.

    Args:
        base_prob: Base probability per tick (0.0-1.0)
        personality_engine: PersonalityEngine with the NPC's personality ids
        mood: NPC current mood (happy/excited/neutral/sad/angry/bored)
        game_hour: Current game hour (0-23)
        is_home: Is NPC at home?
        is_weekend: Is it a weekend/holiday?
        together_minutes: Minutes player and NPC have been in same scene
    """
    prob = base_prob

    # Mood modifier
    mood_mods = {
        "happy": 1.5, "excited": 2.0, "neutral": 1.0,
        "sad": 0.3, "angry": 0.1, "bored": 0.5,
    }
    prob *= mood_mods.get(mood, 1.0)

    # Personality modifier (from 39-set system)
    prob *= personality_engine.intimacy_mod

    # Time modifier
    if 7 <= game_hour <= 9 or 12 <= game_hour <= 13 or 18 <= game_hour <= 20:
        prob *= 1.5  # mealtime boost
    if 22 <= game_hour or game_hour < 6:
        prob *= 0.2  # sleeping
    if is_weekend:
        prob *= 1.3
    if 8 <= game_hour <= 17 and not is_weekend:
        prob *= 0.7  # work hours

    # Home safety bonus
    if is_home:
        prob *= 1.2

    # Together time modifier
    if together_minutes < 5:
        prob *= 0.5
    elif together_minutes > 30:
        prob *= 0.6

    return min(prob, 0.50)  # cap at 50% per tick to prevent spamming
