"""
Add photo-based NPCs from the avatars directory.
Idempotent - skips NPCs that already exist.
"""

import json
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.database import get_connection, get_db_path, fetch_one, execute
from src.common.models import gen_id
from src.common.utils import jd

# 13 female NPCs with varied personalities and roles
NEW_NPCS = [
    {
        "name": "苏晓萌", "birth_date": "2001-03-21", "gender": "female",
        "appearance": {"height": "160cm", "build": "娇小可爱", "hair": "棕色短发", "eyes": "大眼灵动", "face": "娃娃脸"},
        "clothing": {"default": "卫衣配百褶裙", "casual": "宽松毛衣和牛仔裤"},
        "voice_type": "年轻女孩可爱型",
        "personality": ["活泼", "天真", "爱笑", "有点健忘"],
        "default_scene": "scene_coffee_shop", "scene_role": "visitor",
        "default_activity": "在窗边喝奶茶自拍",
        "goals": [{"goal_type": "work", "description": "通过期末考试", "is_short_term": True, "priority": 2},
                  {"goal_type": "life", "description": "学会做甜点", "is_short_term": True, "priority": 4}],
    },
    {
        "name": "林雨桐", "birth_date": "1999-08-15", "gender": "female",
        "appearance": {"height": "167cm", "build": "苗条高挑", "hair": "黑色长直发", "eyes": "丹凤眼", "face": "瓜子脸精致"},
        "clothing": {"default": "白色衬衫配长裙", "casual": "风衣和窄脚裤"},
        "voice_type": "温柔知性女声",
        "personality": ["温柔", "细心", "学霸型", "有点完美主义"],
        "default_scene": "scene_library", "scene_role": "visitor",
        "default_activity": "在书架间安静阅读",
        "goals": [{"goal_type": "work", "description": "考上研究生", "is_short_term": True, "priority": 1},
                  {"goal_type": "life", "description": "写一篇学术论文", "is_short_term": True, "priority": 3}],
    },
    {
        "name": "赵小美", "birth_date": "2000-06-08", "gender": "female",
        "appearance": {"height": "158cm", "build": "微胖可爱", "hair": "栗色卷发", "eyes": "圆眼明亮", "face": "圆脸苹果肌"},
        "clothing": {"default": "碎花连衣裙", "casual": "粉色T恤和短裤"},
        "voice_type": "甜美可爱女声",
        "personality": ["开朗", "八卦", "爱撒娇", "热心肠"],
        "default_scene": "scene_market", "scene_role": "visitor",
        "default_activity": "在货架前挑选零食",
        "goals": [{"goal_type": "relationship", "description": "找到男朋友", "is_short_term": True, "priority": 3},
                  {"goal_type": "life", "description": "减肥5斤", "is_short_term": True, "priority": 4}],
    },
    {
        "name": "周若兰", "birth_date": "1997-11-30", "gender": "female",
        "appearance": {"height": "170cm", "build": "高挑气质", "hair": "大波浪卷发", "eyes": "深邃眼眸", "face": "成熟御姐脸"},
        "clothing": {"default": "职业套装", "casual": "丝绸衬衫和阔腿裤"},
        "voice_type": "成熟磁性女声",
        "personality": ["成熟", "独立", "事业心强", "外冷内热"],
        "default_scene": "scene_coffee_shop", "scene_role": "visitor",
        "default_activity": "用笔记本电脑工作",
        "goals": [{"goal_type": "work", "description": "升职为部门经理", "is_short_term": True, "priority": 1},
                  {"goal_type": "life", "description": "买一套公寓", "is_short_term": False, "priority": 2}],
    },
    {
        "name": "吴佳琪", "birth_date": "2002-02-14", "gender": "female",
        "appearance": {"height": "163cm", "build": "青春活力", "hair": "马尾辫", "eyes": "大眼睛双眼皮", "face": "鹅蛋脸清纯"},
        "clothing": {"default": "运动装束", "casual": "卫衣和运动裤"},
        "voice_type": "青春活泼女声",
        "personality": ["阳光", "运动型", "开朗", "有点粗心"],
        "default_scene": "scene_park", "scene_role": "visitor",
        "default_activity": "在公园跑道晨跑",
        "goals": [{"goal_type": "work", "description": "考上体育学院", "is_short_term": True, "priority": 2},
                  {"goal_type": "life", "description": "跑完一次马拉松", "is_short_term": True, "priority": 3}],
    },
    {
        "name": "郑诗涵", "birth_date": "1998-09-05", "gender": "female",
        "appearance": {"height": "165cm", "build": "匀称优雅", "hair": "及腰黑发", "eyes": "柔和杏眼", "face": "古典鹅蛋脸"},
        "clothing": {"default": "汉服改良连衣裙", "casual": "素色针织衫"},
        "voice_type": "温柔文静女声",
        "personality": ["文静", "有书卷气", "喜欢古典文化", "内向"],
        "default_scene": "scene_library", "scene_role": "visitor",
        "default_activity": "在角落写毛笔字",
        "goals": [{"goal_type": "life", "description": "完成一幅水墨画作品", "is_short_term": True, "priority": 3},
                  {"goal_type": "relationship", "description": "找到志同道合的朋友", "is_short_term": False, "priority": 4}],
    },
    {
        "name": "钱晓雪", "birth_date": "2001-12-25", "gender": "female",
        "appearance": {"height": "159cm", "build": "娇小玲珑", "hair": "银色短卷发", "eyes": "蓝色美瞳", "face": "小脸精致"},
        "clothing": {"default": "日系学院风", "casual": "格子裙和白色袜套"},
        "voice_type": "软萌少女音",
        "personality": ["害羞", "二次元爱好者", "善良", "容易脸红"],
        "default_scene": "scene_school", "scene_role": "visitor",
        "default_activity": "坐在座位上画画",
        "goals": [{"goal_type": "life", "description": "参加漫展cosplay", "is_short_term": True, "priority": 2},
                  {"goal_type": "work", "description": "考进美术院校", "is_short_term": True, "priority": 1}],
    },
    {
        "name": "孙婉清", "birth_date": "1996-05-18", "gender": "female",
        "appearance": {"height": "168cm", "build": "曲线优美", "hair": "棕色中长发", "eyes": "媚眼如丝", "face": "高级脸"},
        "clothing": {"default": "黑色修身长裙", "casual": "皮夹克和紧身裤"},
        "voice_type": "磁性低音女声",
        "personality": ["高冷", "独立", "神秘", "内心温柔"],
        "default_scene": "scene_coffee_shop", "scene_role": "visitor",
        "default_activity": "独坐角落品黑咖啡",
        "goals": [{"goal_type": "work", "description": "开一家个人设计工作室", "is_short_term": False, "priority": 2},
                  {"goal_type": "life", "description": "去冰岛旅行", "is_short_term": True, "priority": 3}],
    },
    {
        "name": "李若溪", "birth_date": "2000-10-10", "gender": "female",
        "appearance": {"height": "162cm", "build": "健康阳光", "hair": "短发清爽", "eyes": "笑眼弯弯", "face": "干净清新"},
        "clothing": {"default": "休闲衬衫配短裤", "casual": "棉麻宽松装"},
        "voice_type": "清新自然女声",
        "personality": ["随和", "乐观", "喜欢自然", "有点佛系"],
        "default_scene": "scene_park", "scene_role": "visitor",
        "default_activity": "在湖边喂鸽子",
        "goals": [{"goal_type": "life", "description": "种一个小花园", "is_short_term": True, "priority": 3},
                  {"goal_type": "relationship", "description": "多参加社交活动", "is_short_term": True, "priority": 4}],
    },
    {
        "name": "冯小曼", "birth_date": "1999-04-01", "gender": "female",
        "appearance": {"height": "164cm", "build": "纤细柔弱", "hair": "黑长直齐刘海", "eyes": "无辜大眼", "face": "楚楚可怜"},
        "clothing": {"default": "白色连衣裙", "casual": "开衫和长裙"},
        "voice_type": "轻柔细语女声",
        "personality": ["敏感", "细腻", "有艺术细胞", "容易多想"],
        "default_scene": "scene_library", "scene_role": "visitor",
        "default_activity": "翻看艺术画册",
        "goals": [{"goal_type": "work", "description": "举办个人画展", "is_short_term": False, "priority": 2},
                  {"goal_type": "relationship", "description": "克服社交恐惧", "is_short_term": True, "priority": 3}],
    },
    {
        "name": "陈思怡", "birth_date": "2001-07-07", "gender": "female",
        "appearance": {"height": "161cm", "build": "娃娃脸可爱", "hair": "双马尾", "eyes": "猫眼灵动", "face": "小圆脸"},
        "clothing": {"default": "背带裤配条纹衫", "casual": "卡通T恤和短裙"},
        "voice_type": "元气少女音",
        "personality": ["元气", "话痨", "好奇心旺盛", "不怕生"],
        "default_scene": "scene_school", "scene_role": "visitor",
        "default_activity": "和同学打闹聊天",
        "goals": [{"goal_type": "work", "description": "数学考到90分", "is_short_term": True, "priority": 1},
                  {"goal_type": "life", "description": "学会弹尤克里里", "is_short_term": True, "priority": 3}],
    },
    {
        "name": "褚云熙", "birth_date": "1997-01-28", "gender": "female",
        "appearance": {"height": "169cm", "build": "御姐身材", "hair": "酒红色长发", "eyes": "锐利眼神", "face": "高级御姐脸"},
        "clothing": {"default": "西装短裙", "casual": "皮衣皮靴"},
        "voice_type": "冷艳女王音",
        "personality": ["强势", "果断", "目标明确", "护短"],
        "default_scene": "scene_market", "scene_role": "visitor",
        "default_activity": "在特产区挑选进口商品",
        "goals": [{"goal_type": "work", "description": "创业开连锁店", "is_short_term": False, "priority": 1},
                  {"goal_type": "life", "description": "参加企业家论坛", "is_short_term": True, "priority": 2}],
    },
    {
        "name": "卫小薇", "birth_date": "2002-09-16", "gender": "female",
        "appearance": {"height": "156cm", "build": "萝莉身形", "hair": "粉色挑染bob头", "eyes": "瞳色异色", "face": "混血感"},
        "clothing": {"default": "洛丽塔风格裙", "casual": "oversize卫衣"},
        "voice_type": "萝莉音",
        "personality": ["古灵精怪", "任性", "爱美", "有点小虚荣"],
        "default_scene": "scene_coffee_shop", "scene_role": "visitor",
        "default_activity": "点了一杯独角兽星冰乐拍照",
        "goals": [{"goal_type": "life", "description": "成为网红博主", "is_short_term": True, "priority": 2},
                  {"goal_type": "work", "description": "接第一个商业推广", "is_short_term": True, "priority": 3}],
    },
]

# Character-appropriate attribute generation based on profile
def _gen_attrs(npc: dict) -> dict:
    """Generate stamina/speed/strength based on NPC appearance and personality."""
    h = int(npc["appearance"].get("height", "165cm").rstrip("cm")) if "cm" in npc["appearance"].get("height", "165cm") else 165
    build = npc["appearance"].get("build", "")
    pers = " ".join(npc.get("personality", []))

    # Base scaling from height
    stamina = 4 + (h - 155) // 10
    speed = 4 + (h - 165) // 15
    strength = 3 + (h - 155) // 10

    # Build modifiers
    if any(w in build for w in ["健壮", "肌肉", "运动", "阳光", "活力"]):
        stamina += 2; strength += 2
    if any(w in build for w in ["娇小", "纤细", "柔弱", "萝莉"]):
        strength -= 1; stamina -= 1
    if any(w in build for w in ["苗条", "高挑", "匀称", "曲线"]):
        speed += 1
    if any(w in build for w in ["微胖", "圆润"]):
        stamina -= 1; speed -= 1
    if "御姐" in build:
        strength += 2; stamina += 1

    # Personality modifiers
    if any(w in pers for w in ["运动", "活泼", "元气", "阳光"]):
        speed += 1; stamina += 1
    if any(w in pers for w in ["强势", "果断"]):
        strength += 1
    if any(w in pers for w in ["文静", "内向", "害羞", "敏感"]):
        strength -= 1; speed -= 1

    return {
        "stamina": max(1, min(10, stamina)),
        "speed": max(1, min(10, speed)),
        "strength": max(1, min(10, strength)),
    }


AVATAR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "assets", "avatars",
)


def add_npcs():
    conn = get_connection()
    avatar_files = sorted(glob.glob(os.path.join(AVATAR_DIR, "*")))
    avatar_files = [f for f in avatar_files
                    if os.path.splitext(f)[1].lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp")]

    print(f"Found {len(avatar_files)} avatar photos, {len(NEW_NPCS)} NPC templates")

    added = 0
    for i, npc_tmpl in enumerate(NEW_NPCS):
        npc_id = f"npc_photo_{i + 1:02d}"

        # Check if already exists
        existing = fetch_one(conn, "SELECT id FROM npc WHERE id = ?", (npc_id,))
        if existing:
            print(f"  SKIP {npc_tmpl['name']} ({npc_id}) - already exists")
            continue

        # Assign avatar
        avatar = os.path.basename(avatar_files[i]) if i < len(avatar_files) else ""
        avatar_path = f"assets/avatars/{avatar}" if avatar else ""

        # Insert NPC
        attrs = jd(_gen_attrs(npc_tmpl))
        execute(conn, """INSERT INTO npc(id, name, birth_date, gender, appearance, clothing,
                       voice_type, personality, current_scene_id, current_mood, current_activity, schedule, attributes)
                       VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (npc_id, npc_tmpl["name"], npc_tmpl["birth_date"], npc_tmpl["gender"],
                 jd(npc_tmpl["appearance"] | {"avatar": avatar_path}),
                 jd(npc_tmpl["clothing"]), npc_tmpl["voice_type"],
                 jd(npc_tmpl["personality"]),
                 npc_tmpl["default_scene"], "neutral", npc_tmpl["default_activity"],
                 "{}", attrs))

        # Scene-NPC association
        execute(conn, "INSERT OR REPLACE INTO scene_npc(scene_id, npc_id, role) VALUES(?, ?, ?)",
                (npc_tmpl["default_scene"], npc_id, npc_tmpl.get("scene_role", "visitor")))

        # Goals
        for g in npc_tmpl.get("goals", []):
            execute(conn, """INSERT INTO goal(id, entity_id, entity_type, goal_type, description,
                          priority, is_short_term, status)
                          VALUES(?, ?, 'npc', ?, ?, ?, ?, 'active')""",
                    (gen_id(), npc_id, g["goal_type"], g["description"],
                     g["priority"], int(g["is_short_term"])))

        # NPC-to-NPC relationships with some existing NPCs
        _add_sample_rel(conn, npc_id, "npc_li_ming", "stranger", 0, 5)
        _add_sample_rel(conn, npc_id, "npc_wang_fang", "acquaintance", 20, 15)

        # Player relationships
        _add_sample_rel_player(conn, "player_001", npc_id, "stranger", 0, 0)
        _add_sample_rel_player(conn, npc_id, "player_001", "stranger", 0, 0)

        added += 1
        print(f"  ADDED {npc_tmpl['name']} ({npc_id}) with avatar {avatar}")

    conn.commit()
    # Verify
    count = conn.execute("SELECT COUNT(*) as c FROM npc WHERE id LIKE 'npc_photo_%'").fetchone()
    print(f"\nDone. {added} NPCs added. Photo NPCs in DB: {count['c']}")
    conn.close()


def _add_sample_rel(conn, a_id, b_id, rel_type, fav, fam):
    execute(conn, """INSERT OR REPLACE INTO relationship(id, entity_a_id, entity_a_type, entity_b_id, entity_b_type,
                  relationship_type, favorability, familiarity, interaction_count)
                  VALUES(?, ?, 'npc', ?, 'npc', ?, ?, ?, 0)""",
            (gen_id(), a_id, b_id, rel_type, fav, fam))


def _add_sample_rel_player(conn, a_id, b_id, rel_type, fav, fam):
    a_type = "player" if a_id.startswith("player") else "npc"
    b_type = "player" if b_id.startswith("player") else "npc"
    execute(conn, """INSERT OR REPLACE INTO relationship(id, entity_a_id, entity_a_type, entity_b_id, entity_b_type,
                  relationship_type, favorability, familiarity, interaction_count)
                  VALUES(?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (gen_id(), a_id, a_type, b_id, b_type, rel_type, fav, fam))


if __name__ == "__main__":
    add_npcs()
