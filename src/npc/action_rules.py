"""
Action interaction rules for player→NPC social actions and NPC autonomous actions.
Unified data source — one ACTION_RULES dict for both execution paths.
"""

import json
from enum import Enum
from src.common.utils import clamp


# ── Animation type enum (abstract, not CSS-specific) ──

class AnimType(str, Enum):
    NONE = "none"
    PULSE = "pulse"
    BOUNCE = "bounce"
    SWING = "swing"
    SHAKE = "shake"
    FLOAT = "float"
    SPIN = "spin"
    FADE = "fade"


# ── Helper: build solo action (no player version) ──

def _solo(name_cn, icon, animation, display_text, weight=10,
          duration=3, cooldown=20, sprite_key="", **kw):
    """Factory for NPC-only solo actions."""
    return {
        "name_cn": name_cn,
        "category": "solo",
        "icon": icon,
        "animation": animation,
        "sprite_key": sprite_key or name_cn,
        "frame_count": kw.get("frame_count", 4),
        "loop": kw.get("loop", True),
        # Player-side fields (not applicable)
        "base_delta": None,
        "min_relation": None,
        "desc": "",
        # NPC autonomous fields
        "npc_auto": True,
        "display_text": display_text,
        "display_variants": kw.get("display_variants", [display_text]),
        "duration_ticks": duration,
        "cooldown_ticks": cooldown,
        "base_weight": weight,
        "requirements": {
            "min_favorability": None,
            "max_favorability": None,
            "needs_target": False,
            "scene_types": None,
            "time_range": None,
            "allowed_moods": None,
            "personality_boost": kw.get("personality_boost"),
            "personality_penalty": kw.get("personality_penalty"),
        },
    }


# ── Helper: shared action (both player + NPC) ──

def _shared(name_cn, icon, category, base_delta, min_relation, desc,
            animation, display_text, weight=8, duration=2, cooldown=20,
            sprite_key="", frame_count=4, loop=True,
            min_fav=0, max_fav=None, needs_target=True,
            personality_boost=None, personality_penalty=None, **kw):
    """Factory for shared player+NPC actions."""
    return {
        "name_cn": name_cn,
        "category": category,
        "icon": icon,
        "animation": animation,
        "sprite_key": sprite_key or name_cn,
        "frame_count": frame_count,
        "loop": loop,
        # Player-side fields
        "base_delta": base_delta,
        "min_relation": min_relation,
        "desc": desc,
        # NPC autonomous fields
        "npc_auto": True,
        "display_text": display_text,
        "display_variants": kw.get("display_variants", [display_text]),
        "duration_ticks": duration,
        "cooldown_ticks": cooldown,
        "base_weight": weight,
        "requirements": {
            "min_favorability": min_fav,
            "max_favorability": max_fav,
            "needs_target": needs_target,
            "scene_types": None,
            "time_range": None,
            "allowed_moods": None,
            "personality_boost": personality_boost,
            "personality_penalty": personality_penalty,
        },
    }


# ── Helper: NPC-only negative action ──

def _negative_auto(name_cn, icon, animation, display_text, weight=6,
                   min_fav=None, max_fav=None, duration=2, cooldown=30, **kw):
    """Factory for NPC-only negative actions (no player version)."""
    return {
        "name_cn": name_cn,
        "category": "negative",
        "icon": icon,
        "animation": animation,
        "sprite_key": name_cn,
        "frame_count": kw.get("frame_count", 4),
        "loop": kw.get("loop", False),
        "base_delta": None,
        "min_relation": None,
        "desc": "",
        "npc_auto": True,
        "display_text": display_text,
        "display_variants": kw.get("display_variants", [display_text]),
        "duration_ticks": duration,
        "cooldown_ticks": cooldown,
        "base_weight": weight,
        "requirements": {
            "min_favorability": min_fav,
            "max_favorability": max_fav,
            "needs_target": kw.get("needs_target", True),
            "scene_types": None,
            "time_range": None,
            "allowed_moods": None,
            "personality_boost": kw.get("personality_boost"),
            "personality_penalty": kw.get("personality_penalty"),
        },
    }


# ═══════════════════════════════════════════════════════════
#  UNIFIED ACTION RULES  (~130 actions)
# ═══════════════════════════════════════════════════════════

ACTION_RULES: dict[str, dict] = {
    # ────────────────────────────────────────────
    #  😊 Friendly (5) — shared
    # ────────────────────────────────────────────
    "微笑": _shared("微笑", "😊", "friendly", 1, None, "对NPC露出友善的微笑",
                    AnimType.SWING, "朝{target}露出友善的微笑", weight=10, duration=2, cooldown=12),
    "挥手": _shared("挥手", "👋", "friendly", 1, None, "向NPC挥手致意",
                    AnimType.SWING, "朝{target}挥了挥手", weight=10, duration=2, cooldown=12),
    "鼓掌": _shared("鼓掌", "👏", "friendly", 1, None, "为NPC鼓掌喝彩",
                    AnimType.BOUNCE, "为{target}鼓掌", weight=6, duration=2, cooldown=20),
    "赞美": _shared("赞美", "👍", "friendly", 2, None, "真诚地赞美NPC",
                    AnimType.PULSE, "对{target}表达了赞美", weight=6, duration=2, cooldown=25),
    "道歉": _shared("道歉", "🙏", "friendly", 2, None, "诚恳地向NPC道歉",
                    AnimType.PULSE, "向{target}诚恳道歉", weight=4, duration=2, cooldown=30),

    # ────────────────────────────────────────────
    #  💕 Intimate · Acquaintance (5)
    # ────────────────────────────────────────────
    "摸摸头": _shared("摸摸头", "🤚", "intimate", 2, "acquaintance", "轻轻摸摸NPC的头",
                      AnimType.SWING, "轻轻摸了摸{target}的头", weight=8, min_fav=10),
    "送礼": _shared("送礼", "🎁", "intimate", 3, "acquaintance", "送给NPC一份精心准备的礼物",
                    AnimType.BOUNCE, "送给{target}一份礼物", weight=6, duration=2, cooldown=30, min_fav=10),
    "搭肩": _shared("搭肩", "🤝", "intimate", 2, "acquaintance", "轻轻拍了拍NPC的肩膀",
                    AnimType.PULSE, "拍了拍{target}的肩膀", weight=7, min_fav=15),
    "眨眼": _shared("眨眼", "😉", "intimate", 2, "acquaintance", "调皮地对NPC眨眨眼",
                    AnimType.PULSE, "对{target}调皮地眨了眨眼", weight=7, min_fav=15),
    "勾肩": _shared("勾肩", "🫂", "intimate", 2, "acquaintance", "自然地勾住NPC的肩膀",
                    AnimType.SWING, "勾住{target}的肩膀", weight=6, min_fav=20),

    # ────────────────────────────────────────────
    #  💕 Intimate · Friend (7)
    # ────────────────────────────────────────────
    "拥抱": _shared("拥抱", "🫂", "intimate", 3, "friend", "热情地拥抱NPC",
                    AnimType.SWING, "热情地拥抱了{target}", weight=7, min_fav=25),
    "牵手": _shared("牵手", "👫", "intimate", 3, "friend", "轻轻牵起NPC的手",
                    AnimType.FLOAT, "牵起{target}的手", weight=6, min_fav=30),
    "捏脸": _shared("捏脸", "🤏", "intimate", 3, "friend", "宠溺地捏捏NPC的脸颊",
                    AnimType.PULSE, "宠溺地捏了捏{target}的脸颊", weight=5, min_fav=35),
    "摸脸": _shared("摸脸", "🖐️", "intimate", 3, "friend", "温柔地抚摸NPC的脸庞",
                    AnimType.FLOAT, "温柔地抚摸{target}的脸庞", weight=5, min_fav=35),
    "暖手": _shared("暖手", "🔥", "intimate", 3, "friend", "温柔地握住NPC的手搓暖",
                    AnimType.PULSE, "握住{target}的手暖了暖", weight=5, min_fav=30),
    "头碰头": _shared("头碰头", "🫣", "intimate", 3, "friend", "额头轻轻碰在一起",
                      AnimType.SWING, "和{target}额头碰在一起", weight=5, min_fav=35),
    "鼻尖轻碰": _shared("鼻尖轻碰", "👃", "intimate", 4, "friend", "鼻尖与NPC轻轻触碰",
                        AnimType.FLOAT, "鼻尖与{target}轻轻触碰", weight=4, min_fav=40),

    # ────────────────────────────────────────────
    #  💕 Intimate · Best Friend (8)
    # ────────────────────────────────────────────
    "靠肩": _shared("靠肩", "💆", "intimate", 3, "best_friend", "温柔地把头靠在NPC的肩膀上",
                    AnimType.FLOAT, "把头靠在{target}的肩膀上", weight=5, min_fav=40),
    "亲吻": _shared("亲吻", "💋", "intimate", 4, "best_friend", "温柔地亲吻NPC",
                    AnimType.FLOAT, "温柔地亲吻了{target}", weight=6, min_fav=50),
    "枕膝": _shared("枕膝", "🦵", "intimate", 5, "best_friend", "温柔地让NPC枕在自己膝上",
                    AnimType.FLOAT, "让{target}枕在自己膝上", weight=3, min_fav=55),
    "深情对视": _shared("深情对视", "👀", "intimate", 4, "best_friend", "含情脉脉地凝视NPC的双眼",
                        AnimType.FADE, "与{target}深情对视", weight=5, min_fav=45),
    "双人比心": _shared("双人比心", "🫶", "intimate", 4, "best_friend", "与NPC一起用手比出一个心形",
                        AnimType.BOUNCE, "和{target}一起比了个心", weight=5, min_fav=40),
    "耳旁低语": _shared("耳旁低语", "🗣️", "intimate", 4, "best_friend", "贴近NPC耳边轻声细语",
                        AnimType.FADE, "贴近{target}耳边轻声细语", weight=5, min_fav=45),
    "十指相扣": _shared("十指相扣", "🤞", "intimate", 4, "best_friend", "与NPC十指紧紧相扣",
                        AnimType.FLOAT, "与{target}十指紧紧相扣", weight=5, min_fav=50),
    "牵手散步": _shared("牵手散步", "🚶", "intimate", 3, "best_friend", "牵着NPC的手一起漫步",
                        AnimType.SWING, "牵着{target}的手一起漫步", weight=4, min_fav=40, duration=4),

    # ────────────────────────────────────────────
    #  ❤️ Couple · Boyfriend/Girlfriend (12)
    # ────────────────────────────────────────────
    "依偎": _shared("依偎", "💑", "couple", 5, "boyfriend", "亲密地依偎在NPC身边",
                    AnimType.FLOAT, "依偎在{target}身边", weight=6, min_fav=55, duration=3),
    "公主抱": _shared("公主抱", "👸", "couple", 5, "boyfriend", "一把将NPC公主抱起",
                      AnimType.BOUNCE, "一把将{target}公主抱起", weight=4, min_fav=60),
    "举高高": _shared("举高高", "🙌", "couple", 5, "boyfriend", "开心地把NPC举起来转圈",
                      AnimType.SPIN, "把{target}举起来转圈", weight=3, min_fav=60),
    "背后抱": _shared("背后抱", "🤗", "couple", 5, "boyfriend", "从背后温柔地环抱住NPC",
                      AnimType.FLOAT, "从背后温柔地环抱住{target}", weight=5, min_fav=55),
    "壁咚": _shared("壁咚", "🧱", "couple", 6, "boyfriend", "帅气地将NPC壁咚在墙上",
                    AnimType.SHAKE, "将{target}壁咚在墙上", weight=3, min_fav=60),
    "吻手礼": _shared("吻手礼", "🫡", "couple", 4, "boyfriend", "优雅地单膝跪下亲吻NPC手背",
                      AnimType.FADE, "单膝跪下亲吻{target}的手背", weight=3, min_fav=50),
    "脸颊吻": _shared("脸颊吻", "😘", "couple", 5, "boyfriend", "温柔地在NPC脸颊上亲了一下",
                      AnimType.FLOAT, "在{target}脸颊上亲了一下", weight=5, min_fav=55),
    "额头吻": _shared("额头吻", "😚", "couple", 5, "boyfriend", "温柔地在NPC额头上印下一吻",
                      AnimType.FLOAT, "在{target}额头上印下一吻", weight=5, min_fav=55),
    "双人共舞": _shared("双人共舞", "💃", "couple", 6, "boyfriend", "搂着NPC的腰一起慢舞",
                        AnimType.SPIN, "搂着{target}的腰一起慢舞", weight=3, min_fav=60, duration=4),
    "同坐依偎": _shared("同坐依偎", "🛋️", "couple", 5, "boyfriend", "和NPC坐在一起紧紧依偎",
                        AnimType.FLOAT, "和{target}坐在一起紧紧依偎", weight=4, min_fav=55, duration=3),
    "枕胸口": _shared("枕胸口", "💓", "couple", 6, "boyfriend", "让NPC温柔地靠在自己胸口",
                      AnimType.FLOAT, "让{target}温柔地靠在自己胸口", weight=3, min_fav=65, duration=3),
    "膝上坐": _shared("膝上坐", "💺", "couple", 7, "boyfriend", "将NPC轻轻拉到自己膝上坐着",
                      AnimType.SWING, "将{target}轻轻拉到膝上坐着", weight=2, min_fav=70, duration=3),

    # ────────────────────────────────────────────
    #  ❤️ Couple · Spouse (6)
    # ────────────────────────────────────────────
    "浪漫深吻": _shared("浪漫深吻", "❤️", "couple", 8, "spouse", "深情地拥吻NPC",
                        AnimType.FLOAT, "深情地拥吻{target}", weight=5, min_fav=75, duration=3),
    "求婚": _shared("求婚", "💍", "couple", 10, "spouse", "单膝跪地向NPC求婚",
                    AnimType.BOUNCE, "单膝跪地向{target}求婚", weight=1, min_fav=90, cooldown=120),
    "婚礼拥抱": _shared("婚礼拥抱", "💒", "couple", 8, "spouse", "在婚礼上紧紧拥抱NPC",
                        AnimType.SWING, "在婚礼上紧紧拥抱{target}", weight=1, min_fav=85),
    "抱怀转圈": _shared("抱怀转圈", "🎠", "couple", 7, "spouse", "公主抱起NPC幸福地转圈",
                        AnimType.SPIN, "公主抱起{target}幸福地转圈", weight=2, min_fav=80),
    "坐腿": _shared("坐腿", "🪑", "couple", 7, "spouse", "让NPC撒娇地坐在自己腿上",
                    AnimType.SWING, "让{target}撒娇地坐在自己腿上", weight=2, min_fav=75, duration=3),
    "共枕": _shared("共枕", "🛏️", "couple", 8, "spouse", "与NPC同床共枕温情相拥",
                    AnimType.FLOAT, "与{target}同床共枕温情相拥", weight=2, min_fav=85, duration=4),

    # ────────────────────────────────────────────
    #  😠 Negative — emotional (3, shared)
    # ────────────────────────────────────────────
    "生气": _shared("生气", "😤", "negative", -2, None, "对NPC表现出明显的愤怒",
                    AnimType.SHAKE, "对{target}表现出明显的愤怒", weight=4, min_fav=-10, max_fav=None),
    "哭泣": _shared("哭泣", "😢", "negative", -1, None, "在NPC面前伤心地哭泣",
                    AnimType.PULSE, "在{target}面前伤心地哭泣", weight=3, min_fav=None, max_fav=None),
    "嘲笑": _shared("嘲笑", "😏", "negative", -3, None, "嘲笑挖苦NPC",
                    AnimType.SHAKE, "嘲笑挖苦{target}", weight=3, min_fav=-20, max_fav=None),
}


# ── Physical actions (attribute check required) ──

PHYSICAL_ACTIONS: dict[str, dict] = {
    "殴打": {
        "attr": "strength",
        "success_delta": -5, "fail_delta": -3,
        "success_desc": "挥拳击中了NPC",
        "fail_desc": "挥拳打向NPC但被躲开/格挡了",
        "category": "force",
        "icon": "👊", "animation": AnimType.SHAKE, "sprite_key": "punch",
        "frame_count": 4, "loop": False,
        "npc_auto": True, "display_text": "愤怒地对{target}挥舞拳头",
        "display_variants": ["对{target}动粗", "与{target}发生了肢体冲突"],
        "duration_ticks": 2, "cooldown_ticks": 40, "base_weight": 3,
        "requirements": {"min_favorability": -60, "max_favorability": None,
                         "needs_target": True, "scene_types": None, "time_range": None,
                         "allowed_moods": None, "personality_boost": "强势",
                         "personality_penalty": "温柔"},
    },
    "推搡": {
        "attr": "strength",
        "success_delta": -3, "fail_delta": -2,
        "success_desc": "用力推了NPC一把，NPC踉跄后退",
        "fail_desc": "试图推搡NPC但被对方稳住身形挡了回来",
        "category": "force",
        "icon": "🤛", "animation": AnimType.SHAKE, "sprite_key": "push",
        "frame_count": 3, "loop": False,
        "npc_auto": True, "display_text": "用力推了{target}一把",
        "display_variants": ["推搡了{target}一下"],
        "duration_ticks": 2, "cooldown_ticks": 35, "base_weight": 4,
        "requirements": {"min_favorability": -40, "max_favorability": None,
                         "needs_target": True, "scene_types": None, "time_range": None,
                         "allowed_moods": None, "personality_boost": "强势",
                         "personality_penalty": "温柔"},
    },
    "绊倒": {
        "attr": "speed",
        "success_delta": -3, "fail_delta": -2,
        "success_desc": "趁NPC不备将其绊倒在地",
        "fail_desc": "试图绊倒NPC但被对方敏捷地跳开了",
        "category": "agility",
        "icon": "🦵", "animation": AnimType.SHAKE, "sprite_key": "trip",
        "frame_count": 3, "loop": False,
        "npc_auto": True, "display_text": "趁{target}不备将其绊倒",
        "display_variants": ["伸腿绊了{target}一下"],
        "duration_ticks": 2, "cooldown_ticks": 40, "base_weight": 3,
        "requirements": {"min_favorability": -50, "max_favorability": None,
                         "needs_target": True, "scene_types": None, "time_range": None,
                         "allowed_moods": None, "personality_boost": None,
                         "personality_penalty": "善良"},
    },
    "捉弄": {
        "attr": "speed",
        "success_delta": -1, "fail_delta": 0,
        "success_desc": "突然从背后跳出来吓了NPC一大跳",
        "fail_desc": "想捉弄NPC但被提前发现，对方一脸无语地看着你",
        "category": "agility",
        "icon": "😜", "animation": AnimType.BOUNCE, "sprite_key": "prank",
        "frame_count": 4, "loop": False,
        "npc_auto": True, "display_text": "突然从背后跳出来吓了{target}一大跳",
        "display_variants": ["恶作剧地捉弄了{target}"],
        "duration_ticks": 2, "cooldown_ticks": 30, "base_weight": 5,
        "requirements": {"min_favorability": -20, "max_favorability": 30,
                         "needs_target": True, "scene_types": None, "time_range": None,
                         "allowed_moods": None, "personality_boost": "开朗",
                         "personality_penalty": None},
    },
}


# ═══════════════════════════════════════════════════════════
#  NPC-ONLY AUTONOMOUS ACTIONS
# ═══════════════════════════════════════════════════════════

# ── Solo actions (~22) — NPC idle daily behaviors ──

AUTO_SOLO_ACTIONS = {
    "发呆": _solo("发呆", "😶", AnimType.FADE, "望着远处发呆...", weight=15, duration=5, cooldown=10),
    "散步": _solo("散步", "🚶", AnimType.SWING, "悠闲地散着步", weight=10, duration=5, cooldown=15),
    "看手机": _solo("看手机", "📱", AnimType.NONE, "低头刷着手机", weight=18, duration=5, cooldown=8,
                    personality_boost=None, personality_penalty="高冷"),
    "喝水": _solo("喝水", "🥤", AnimType.PULSE, "喝了一口水", weight=12, duration=2, cooldown=15),
    "伸懒腰": _solo("伸懒腰", "🙆", AnimType.SWING, "舒服地伸了个懒腰", weight=8, duration=2, cooldown=30),
    "打哈欠": _solo("打哈欠", "🥱", AnimType.PULSE, "打了个哈欠", weight=6, duration=2, cooldown=30),
    "整理衣服": _solo("整理衣服", "👔", AnimType.PULSE, "低头整理了一下衣服", weight=6, duration=2, cooldown=25),
    "照镜子": _solo("照镜子", "🪞", AnimType.FADE, "对着镜子端详自己", weight=5, duration=3, cooldown=40),
    "哼歌": _solo("哼歌", "🎵", AnimType.SWING, "愉快地哼着小曲", weight=7, duration=4, cooldown=25,
                  personality_boost="开朗"),
    "看书": _solo("看书", "📖", AnimType.NONE, "安静地看着书", weight=6, duration=6, cooldown=35,
                  personality_boost="内向"),
    "写字": _solo("写字", "✍️", AnimType.NONE, "在本子上写着什么", weight=4, duration=5, cooldown=40),
    "打扫": _solo("打扫", "🧹", AnimType.SWING, "认真地打扫着周围", weight=5, duration=5, cooldown=35),
    "望窗外": _solo("望窗外", "🪟", AnimType.FADE, "静静地望着窗外", weight=10, duration=4, cooldown=20,
                    display_variants=["望着窗外发呆", "透过窗户看向外面"]),
    "打盹": _solo("打盹", "😴", AnimType.FLOAT, "歪着头打起了盹...", weight=5, duration=6, cooldown=50),
    "揉眼睛": _solo("揉眼睛", "👁️", AnimType.PULSE, "揉了揉眼睛", weight=6, duration=2, cooldown=25),
    "托腮": _solo("托腮", "🤔", AnimType.NONE, "托着腮帮子想事情", weight=8, duration=4, cooldown=20),
    "整理头发": _solo("整理头发", "💇", AnimType.SWING, "用手理了理头发", weight=6, duration=2, cooldown=25,
                      personality_boost=None),
    "搓手": _solo("搓手", "🤲", AnimType.SHAKE, "来回搓着双手", weight=4, duration=2, cooldown=30),
    "数钱": _solo("数钱", "💰", AnimType.NONE, "偷偷数着钱包里的钱", weight=3, duration=3, cooldown=45),
    "吃东西": _solo("吃东西", "🍞", AnimType.PULSE, "在吃东西", weight=8, duration=4, cooldown=25),
    "浇花": _solo("浇花", "🌱", AnimType.SWING, "细心地给花浇水", weight=4, duration=3, cooldown=40),
    "踢石子": _solo("踢石子", "🦶", AnimType.BOUNCE, "无聊地踢着地上的小石子", weight=4, duration=3, cooldown=30),
}

# ── NPC-only negative actions (~25, 4 favorability tiers) ──

AUTO_NEGATIVE_ACTIONS = {
    # ── Cold (好感 -1 ~ -30) ──
    "翻白眼": _negative_auto("翻白眼", "🙄", AnimType.SHAKE, "对{target}翻了个白眼",
                             max_fav=-1, min_fav=-30, weight=6),
    "冷眼": _negative_auto("冷眼", "😒", AnimType.NONE, "冷眼看了{target}一眼",
                           max_fav=-1, min_fav=-30, weight=7),
    "无视": _negative_auto("无视", "😐", AnimType.NONE, "无视了{target}的存在",
                           max_fav=-5, min_fav=-30, weight=8),
    "撇嘴": _negative_auto("撇嘴", "😕", AnimType.PULSE, "对{target}撇了撇嘴",
                           max_fav=-1, min_fav=-30, weight=5),
    "扭头": _negative_auto("扭头", "🙅", AnimType.SWING, "看见{target}扭头就走",
                           max_fav=-10, min_fav=-30, weight=6),
    "避开": _negative_auto("避开", "🚶", AnimType.SWING, "远远看到{target}就绕道避开",
                           max_fav=-10, min_fav=-30, weight=5),

    # ── Disgust (好感 -30 ~ -60) ──
    "瞪眼": _negative_auto("瞪眼", "👿", AnimType.SHAKE, "狠狠瞪了{target}一眼",
                           max_fav=-30, min_fav=-60, weight=7),
    "嘲讽": _negative_auto("嘲讽", "😏", AnimType.SHAKE, "对{target}冷嘲热讽",
                           max_fav=-30, min_fav=-60, weight=6),
    "冷笑": _negative_auto("冷笑", "😤", AnimType.SHAKE, "冲{target}冷笑了一声",
                           max_fav=-30, min_fav=-60, weight=6),
    "指责": _negative_auto("指责", "👉", AnimType.SHAKE, "指着{target}大声指责",
                           max_fav=-30, min_fav=-60, weight=5, personality_boost="强势"),
    "甩手": _negative_auto("甩手", "🖐️", AnimType.SWING, "不耐烦地朝{target}甩了甩手",
                           max_fav=-30, min_fav=-60, weight=6),
    "砸东西": _negative_auto("砸东西", "💢", AnimType.SHAKE, "气得把手边的东西砸在地上",
                             max_fav=-30, min_fav=-60, weight=3, personality_boost="强势",
                             personality_penalty="温柔"),

    # ── Hostile (好感 -60 ~ -90) ──
    "怒骂": _negative_auto("怒骂", "🤬", AnimType.SHAKE, "指着{target}破口大骂",
                           max_fav=-60, min_fav=-90, weight=5, personality_boost="强势"),
    "摔东西": _negative_auto("摔东西", "💥", AnimType.SHAKE, "拿起东西朝{target}方向狠狠摔去",
                             max_fav=-60, min_fav=-90, weight=4, personality_boost="强势"),
    "拍桌子": _negative_auto("拍桌子", "🪑", AnimType.SHAKE, "狠狠一拍桌子，怒视{target}",
                             max_fav=-60, min_fav=-90, weight=4),
    "拉扯": _negative_auto("拉扯", "👊", AnimType.SHAKE, "冲上去和{target}拉扯起来",
                           max_fav=-60, min_fav=-90, weight=3),
    "威胁": _negative_auto("威胁", "😠", AnimType.SHAKE, "咬牙切齿地威胁{target}",
                           max_fav=-60, min_fav=-90, weight=4, personality_boost="强势"),

    # ── Hate (好感 ≤ -90) ──
    "追打": _negative_auto("追打", "🏃", AnimType.SHAKE, "追着{target}满街打",
                           max_fav=-90, min_fav=None, weight=2, personality_boost="强势"),
    "掐脖子": _negative_auto("掐脖子", "🫲", AnimType.SHAKE, "一把掐住{target}的脖子",
                             max_fav=-90, min_fav=None, weight=1),
    "踢打": _negative_auto("踢打", "👟", AnimType.SHAKE, "对着{target}一顿拳打脚踢",
                           max_fav=-90, min_fav=None, weight=1),
    "搏斗": _negative_auto("搏斗", "⚔️", AnimType.SHAKE, "与{target}激烈地扭打在一起",
                           max_fav=-90, min_fav=None, weight=1, personality_boost="强势"),
    "呼救": _negative_auto("呼救", "🆘", AnimType.SHAKE, "看到{target}就大声呼救",
                           max_fav=-90, min_fav=None, weight=2,
                           personality_penalty="强势"),
}


# ═══════════════════════════════════════════════════════════
#  Category descriptions
# ═══════════════════════════════════════════════════════════

ACTION_CATEGORY_DESC = {
    "friendly": "友善的互动",
    "intimate": "亲密的肢体接触或赠礼",
    "couple": "情侣专属互动",
    "negative": "负面的情绪表达或冒犯",
    "solo": "NPC独处行为",
    "special": "特殊的情感表达",
    "force": "攻击性的身体接触",
    "agility": "敏捷型的互动",
}


# ═══════════════════════════════════════════════════════════
#  Helper: get all NPC-autonomous actions
# ═══════════════════════════════════════════════════════════

def get_auto_actions() -> dict[str, dict]:
    """Return all actions where npc_auto=True (shared + NPC-only)."""
    result = {}
    for name, info in ACTION_RULES.items():
        if info.get("npc_auto"):
            result[name] = info
    for name, info in PHYSICAL_ACTIONS.items():
        if info.get("npc_auto"):
            result[name] = info
    for name, info in AUTO_SOLO_ACTIONS.items():
        result[name] = info
    for name, info in AUTO_NEGATIVE_ACTIONS.items():
        result[name] = info
    return result


def get_all_actions() -> dict[str, dict]:
    """Return ALL actions across all dictionaries."""
    result = {}
    result.update(ACTION_RULES)
    result.update(PHYSICAL_ACTIONS)
    result.update(AUTO_SOLO_ACTIONS)
    result.update(AUTO_NEGATIVE_ACTIONS)
    return result


# ═══════════════════════════════════════════════════════════
#  Physical action check (unchanged logic)
# ═══════════════════════════════════════════════════════════

def check_physical_action(action_name: str, player_attrs: dict,
                          npc_attrs: dict) -> dict:
    """Check if a physical action succeeds based on attribute comparison."""
    action = PHYSICAL_ACTIONS.get(action_name)
    if not action:
        return {"success": True, "tier": "success", "action_desc": "", "base_delta": 0, "delta_multiplier": 1.0}

    attr = action["attr"]
    player_val = player_attrs.get(attr, 5)
    npc_val = npc_attrs.get(attr, 5)
    diff = player_val - npc_val

    if diff >= 3:
        return {"tier": "critical_success", "success": True,
                "action_desc": action.get("critical_desc", action["success_desc"]),
                "base_delta": action["success_delta"], "delta_multiplier": 1.5}
    elif diff >= 1:
        return {"tier": "success", "success": True,
                "action_desc": action["success_desc"],
                "base_delta": action["success_delta"], "delta_multiplier": 1.0}
    elif diff == 0:
        return {"tier": "narrow_fail", "success": False,
                "action_desc": action.get("narrow_fail_desc", action["fail_desc"]),
                "base_delta": action["fail_delta"], "delta_multiplier": 0.7}
    else:
        return {"tier": "failure", "success": False,
                "action_desc": action["fail_desc"],
                "base_delta": action["fail_delta"], "delta_multiplier": 0.5}


# ═══════════════════════════════════════════════════════════
#  Diminishing Returns Tracker
# ═══════════════════════════════════════════════════════════

class DiminishingTracker:
    """Track repeated actions between actor-target pairs to prevent grinding."""
    def __init__(self, window_ticks: int = 480):
        self._history: dict[str, list[int]] = {}
        self._window = window_ticks

    def record_action(self, actor_id: str, target_id: str, action_name: str, tick: int):
        key = f"{actor_id}_{target_id}_{action_name}"
        self._history.setdefault(key, []).append(tick)
        self._history[key] = [t for t in self._history[key]
                              if tick - t < self._window]

    def get_multiplier(self, actor_id: str, target_id: str, action_name: str, tick: int) -> float:
        key = f"{actor_id}_{target_id}_{action_name}"
        count = len(self._history.get(key, []))
        if count <= 1: return 1.0
        elif count == 2: return 0.7
        elif count == 3: return 0.4
        else: return 0.15

    def clear(self):
        self._history.clear()


_diminishing_tracker = DiminishingTracker()


def get_diminishing_tracker() -> DiminishingTracker:
    return _diminishing_tracker


# ═══════════════════════════════════════════════════════════
#  Context Multipliers
# ═══════════════════════════════════════════════════════════

def calculate_context_multipliers(action_name: str, rel: dict, mood: str,
                                   scene_type: str, game_hour: int = 12) -> float:
    """Calculate context sensitivity multipliers for a favorability delta."""
    all_actions = get_all_actions()
    action = all_actions.get(action_name) or {}
    category = action.get("category", "friendly")
    multiplier = 1.0

    if game_hour >= 21 or game_hour < 6:
        if category in ("intimate", "couple"): multiplier *= 1.3
        elif category == "friendly": multiplier *= 0.9

    if category in ("intimate", "couple"):
        if scene_type == "outdoor": multiplier *= 0.8
        elif scene_type == "indoor": multiplier *= 1.0

    if mood in ("happy", "excited") and category in ("friendly", "intimate", "couple"):
        multiplier *= 1.25
    elif mood == "sad" and action_name in ("安慰", "道歉"):
        multiplier *= 1.3
    elif mood == "sad" and category == "friendly":
        multiplier *= 0.8
    elif mood == "angry":
        multiplier *= 0.6

    return multiplier


# ═══════════════════════════════════════════════════════════
#  Action-specific favorability modifiers
# ═══════════════════════════════════════════════════════════

def apply_action_rules(action_name: str, rel: dict, delta: int,
                       mood: str, scene_type: str,
                       action_success: bool = True) -> int:
    """Apply action-specific post-processing rules."""
    all_actions = get_all_actions()
    action = all_actions.get(action_name) or {}
    category = action.get("category", "friendly")
    min_rel = action.get("min_relation")
    current_type = rel.get("relationship_type", "stranger")

    if min_rel and not _meets_relation(current_type, min_rel):
        if category in ("intimate", "couple"):
            return -abs(delta)
        return delta

    if category in ("intimate", "couple") and scene_type == "outdoor":
        delta = delta // 2

    if mood in ("happy", "excited") and delta > 0:
        delta += 1
    elif mood in ("sad", "angry") and delta > 0:
        delta = max(delta - 1, 0)

    if action_name == "道歉" and rel.get("favorability", 0) < 0:
        delta += 1

    if action_name == "嘲笑" and rel.get("favorability", 0) < -20:
        delta = max(delta - 1, -3)

    if category in ("force", "agility") and not action_success:
        delta = -abs(delta)

    if category == "couple":
        return clamp(delta, -10, 10)
    return clamp(delta, -3, 3)


def _meets_relation(current: str, required: str) -> bool:
    """Check if current relationship type meets the required minimum."""
    hierarchy = ["stranger", "acquaintance", "friend", "best_friend",
                  "boyfriend", "girlfriend", "spouse",
                  "parent", "sibling", "child"]
    romantic_pairs = {"boyfriend", "girlfriend"}
    if current in romantic_pairs and required in romantic_pairs:
        return True
    if current == "spouse" and required in romantic_pairs:
        return True
    if current in hierarchy and required in hierarchy:
        return hierarchy.index(current) >= hierarchy.index(required)
    return False


# ═══════════════════════════════════════════════════════════
#  Utility functions
# ═══════════════════════════════════════════════════════════

def get_action_names() -> list[str]:
    """Return all available action names."""
    return list(get_all_actions().keys())


def get_actions_by_category() -> dict[str, list[str]]:
    """Group actions by category for UI display."""
    groups: dict[str, list[str]] = {}
    for name, info in get_all_actions().items():
        cat = info.get("category", "other")
        groups.setdefault(cat, []).append(name)
    return groups


def parse_attributes(attr_json: str) -> dict:
    """Parse attributes JSON string, with defaults."""
    defaults = {"stamina": 5, "speed": 5, "strength": 5}
    try:
        parsed = json.loads(attr_json) if attr_json else {}
        return {**defaults, **parsed}
    except (json.JSONDecodeError, TypeError):
        return defaults


# ═══════════════════════════════════════════════════════════
#  Boundary Violation (uses inline min_relation now)
# ═══════════════════════════════════════════════════════════

RELATION_LEVELS = {
    "stranger": 0, "acquaintance": 1, "friend": 2, "best_friend": 3,
    "boyfriend": 4, "girlfriend": 4, "spouse": 5,
    "parent": 5, "sibling": 5, "child": 5,
    "dislike": -1, "enemy": -2,
}

VIOLATION_THRESHOLD = 3


def check_boundary_violation(action_name: str, current_rel_type: str) -> dict | None:
    """Check if an action violates relationship boundaries."""
    all_actions = get_all_actions()
    action = all_actions.get(action_name, {})
    required = action.get("min_relation")
    if not required:
        return None

    current_level = RELATION_LEVELS.get(current_rel_type, 0)
    required_level = RELATION_LEVELS.get(required, 0)

    gap = required_level - current_level
    if gap < VIOLATION_THRESHOLD:
        return None

    if gap >= 5:
        severity = "violent"
        fav_delta = -100
    elif gap >= 4:
        severity = "severe"
        fav_delta = -80
    elif gap >= 3:
        severity = "moderate"
        fav_delta = -50
    else:
        severity = "minor"
        fav_delta = -20

    return {"violation": True, "severity": severity, "fav_delta": fav_delta, "gap": gap}


def get_npc_violation_reaction(personality: list, severity: str) -> dict:
    """Determine NPC reaction to a boundary violation based on personality."""
    reactions = {
        "minor": {
            "害羞": "脸红躲开", "内向": "低头不说话",
            "温柔": "礼貌但坚定地拒绝", "善良": "礼貌拒绝",
            "强势": "冷眼推开", "高冷": "冷眼不说话",
            "开朗": "尴尬笑笑躲开", "外向": "尴尬走开",
        },
        "moderate": {
            "害羞": "惊恐逃跑", "内向": "惊慌失措",
            "温柔": "严厉斥责", "善良": "严肃警告",
            "强势": "一巴掌打过去", "高冷": "一巴掌推开",
            "开朗": "明确拒绝+警告", "外向": "大喊别碰我",
        },
        "severe": {
            "害羞": "尖叫逃跑", "内向": "崩溃大哭",
            "温柔": "大声呼救", "善良": "大声呼救",
            "强势": "强力反击+报警", "高冷": "反击+呼救",
            "开朗": "大喊+推开", "外向": "大声呼救",
        },
        "violent": {
            "害羞": "冻结/崩溃大哭", "内向": "崩溃痛哭",
            "温柔": "呼救+报警", "善良": "反击+报警",
            "强势": "全力反击", "高冷": "致命反击",
            "开朗": "反击+报警", "外向": "强力反击",
        },
    }

    level_reactions = reactions.get(severity, reactions["minor"])
    for trait, reaction in level_reactions.items():
        if trait in personality:
            return {"reaction": reaction, "will_flee": severity in ("moderate", "severe"),
                    "will_call_help": severity in ("severe", "violent"),
                    "will_counter_attack": severity == "violent"}
    return {"reaction": "惊恐地看着对方", "will_flee": True, "will_call_help": False,
            "will_counter_attack": False}
