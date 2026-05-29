"""
Initialize the database: create tables and seed with game data.
"""

import json
import os
import sys

# Ensure city-town/ is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.database import get_db_path, get_connection, run_migrations, execute, fetch_all
from src.common.models import gen_id
from src.common.utils import jd


def seed_data(conn):
    """Insert initial scenes, NPCs, relationships, and goals from config files."""
    config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
    c = conn  # shortcut

    # ── Load config files ─────────────────────────
    with open(os.path.join(config_dir, "game_config.yaml"), "r", encoding="utf-8") as f:
        import yaml
        config = yaml.safe_load(f)

    with open(os.path.join(config_dir, "npc_templates.json"), "r", encoding="utf-8") as f:
        npc_templates = json.load(f)

    # ── Initial game state ────────────────────────
    execute(c, "INSERT OR IGNORE INTO game_state(key, value) VALUES(?, ?)",
            ("game_time", jd({"day": config["game"]["start_day"],
                              "hour": config["game"]["start_hour"],
                              "minute": config["game"]["start_minute"]})))
    execute(c, "INSERT OR IGNORE INTO game_state(key, value) VALUES(?, ?)",
            ("weather", jd({"type": config["weather"]["initial"]})))

    # ── Insert scenes ─────────────────────────────
    scene_ids = []
    for s in config["scenes"]:
        rooms_json = jd(s.get("rooms", []))
        residents_json = jd(s.get("residents", []))
        execute(c, """INSERT OR REPLACE INTO scene(id, name, description, scene_type, weather_affected, max_capacity, icon, rooms, residents)
                      VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s["id"], s["name"], s["description"], s["scene_type"],
                 int(s["weather_affected"]), s["max_capacity"], s["icon"],
                 rooms_json, residents_json))
        scene_ids.append(s["id"])

    # ── NPC attributes (stamina, speed, strength) ─
    _npc_attrs = {
        "npc_li_ming":    {"stamina": 6, "speed": 5, "strength": 4},   # lean barista, moderate
        "npc_wang_fang":  {"stamina": 4, "speed": 6, "strength": 3},   # petite student, agile
        "npc_zhang_wei":  {"stamina": 8, "speed": 6, "strength": 9},   # muscular fitness coach
        "npc_chen_xue":   {"stamina": 4, "speed": 4, "strength": 3},   # elegant librarian
        "npc_liu_jie":    {"stamina": 5, "speed": 3, "strength": 4},   # older store owner
    }

    # ── NPC → home scene mapping ─────────────────
    _npc_homes = {
        "npc_li_ming": "apt_a", "npc_photo_01": "apt_a", "npc_photo_07": "apt_a", "npc_photo_09": "apt_a",
        "npc_wang_fang": "apt_b", "npc_photo_02": "apt_b", "npc_photo_06": "apt_b", "npc_photo_10": "apt_b",
        "npc_zhang_wei": "apt_c", "npc_photo_03": "apt_c", "npc_photo_05": "apt_c", "npc_photo_11": "apt_c", "npc_photo_12": "apt_c",
        "npc_chen_xue": "apt_d", "npc_liu_jie": "apt_d", "npc_photo_04": "apt_d", "npc_photo_08": "apt_d", "npc_photo_13": "apt_d",
    }

    # ── Insert NPCs ───────────────────────────────
    npc_ids = []
    for t in npc_templates:
        attrs = jd(_npc_attrs.get(t["id"], {"stamina": 5, "speed": 5, "strength": 5}))
        home_id = _npc_homes.get(t["id"])
        execute(c, """INSERT OR IGNORE INTO npc(id, name, birth_date, gender, appearance, clothing,
                      voice_type, career, personality, current_scene_id, home_scene_id, current_mood, current_activity, schedule, attributes)
                      VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (t["id"], t["name"], t["birth_date"], t["gender"],
                 jd(t["appearance"]), jd(t["clothing"]), t["voice_type"],
                 t.get("career", ""), jd(t["personality"]), t["default_scene"], home_id,
                 "neutral", t["default_activity"],
                 jd(t.get("schedule", {})), attrs))
        npc_ids.append(t["id"])

        # Scene-NPC association (public scene)
        execute(c, """INSERT OR IGNORE INTO scene_npc(scene_id, npc_id, role) VALUES(?, ?, ?)""",
                (t["default_scene"], t["id"], t.get("scene_role", "visitor")))

        # Scene-NPC association (home scene as resident)
        if home_id:
            execute(c, """INSERT OR IGNORE INTO scene_npc(scene_id, npc_id, role) VALUES(?, ?, 'resident')""",
                    (home_id, t["id"]))

        # Goals
        for g in t.get("goals", []):
            execute(c, """INSERT OR IGNORE INTO goal(id, entity_id, entity_type, goal_type, description,
                          priority, is_short_term, status)
                          VALUES(?, ?, 'npc', ?, ?, ?, ?, 'active')""",
                    (gen_id(), t["id"], g["goal_type"], g["description"],
                     g["priority"], int(g["is_short_term"])))

    # ── Insert NPC-to-NPC initial relationships ──
    # 李明-王芳: 熟人
    _insert_rel(c, "npc_li_ming", "npc", "npc_wang_fang", "npc",
                "acquaintance", 25, 30, 15)
    _insert_rel(c, "npc_wang_fang", "npc", "npc_li_ming", "npc",
                "acquaintance", 40, 35, 20)

    # 李明-张伟: 朋友
    _insert_rel(c, "npc_li_ming", "npc", "npc_zhang_wei", "npc",
                "friend", 45, 50, 30)
    _insert_rel(c, "npc_zhang_wei", "npc", "npc_li_ming", "npc",
                "friend", 50, 55, 35)

    # 王芳-陈雪: 认识
    _insert_rel(c, "npc_wang_fang", "npc", "npc_chen_xue", "npc",
                "acquaintance", 15, 20, 8)
    _insert_rel(c, "npc_chen_xue", "npc", "npc_wang_fang", "npc",
                "acquaintance", 20, 15, 10)

    # 刘姐-李明: 熟人
    _insert_rel(c, "npc_liu_jie", "npc", "npc_li_ming", "npc",
                "acquaintance", 35, 40, 25)
    _insert_rel(c, "npc_li_ming", "npc", "npc_liu_jie", "npc",
                "acquaintance", 30, 35, 20)

    # 刘姐-王芳: 熟人
    _insert_rel(c, "npc_liu_jie", "npc", "npc_wang_fang", "npc",
                "acquaintance", 30, 25, 12)
    _insert_rel(c, "npc_wang_fang", "npc", "npc_liu_jie", "npc",
                "acquaintance", 25, 20, 10)

    # ── Insert items ──────────────────────────────
    # Format: (id, scene_id, owner_npc_id, name, description, item_type, function, room_name, is_interactive, is_usable)
    items = [
        # Public scene items
        ("item_coffee_machine", "scene_coffee_shop", None, "咖啡机", "一台意式浓缩咖啡机", "tool", "cook", None, True, True),
        ("item_menu", "scene_coffee_shop", None, "菜单", "手写风格的饮品菜单", "decoration", None, None, True, False),
        ("item_bench", "scene_park", None, "长椅", "一张木制公园长椅", "furniture", "rest", None, True, True),
        ("item_bookshelf", "scene_library", None, "书架", "高及天花板的橡木书架", "furniture", "decorate", None, False, False),
        ("item_counter", "scene_market", None, "收银台", "老式的收银台", "furniture", None, None, True, False),
        ("item_blackboard", "scene_school", None, "黑板", "教室前面的黑板", "tool", None, None, False, False),
        # ── Public scene food/water items ──
        ("item_school_canteen", "scene_school", None, "食堂", "学校食堂，提供午餐", "furniture", "eat,cook", None, True, True),
        ("item_school_water", "scene_school", None, "饮水机", "走廊里的饮水机", "furniture", "drink", None, True, True),
        ("item_park_food", "scene_park", None, "小吃摊", "路边小吃摊，有简单食物", "furniture", "eat,cook,drink", None, True, True),
        ("item_market_snacks", "scene_market", None, "零食货架", "摆满各种零食和方便食品", "furniture", "eat", None, True, True),
        ("item_market_drinks", "scene_market", None, "饮料冰柜", "各种饮料和矿泉水", "furniture", "drink", None, True, True),
        ("item_market_veggies", "scene_market", None, "蔬菜水果区", "新鲜蔬菜水果", "furniture", "cook", None, True, True),
        ("item_hospital_vending", "scene_hospital", None, "自动售货机", "有零食和饮料", "furniture", "eat,drink", None, True, True),
        ("item_hospital_water", "scene_hospital", None, "饮水机", "提供热水和冷水", "furniture", "drink", None, True, True),
        ("item_library_vending", "scene_library", None, "自动售货机", "有饮料和零食", "furniture", "eat,drink", None, True, True),
        # New scene items (Phase: town expansion)
        ("item_restaurant_table", "scene_restaurant", None, "餐桌", "铺着格子桌布的木餐桌", "furniture", "eat", None, True, True),
        ("item_restaurant_kitchen", "scene_restaurant", None, "厨房", "忙碌的餐厅厨房，飘出诱人的香味", "furniture", "cook", None, True, True),
        ("item_restaurant_bar", "scene_restaurant", None, "吧台", "提供各种饮品", "furniture", "drink", None, True, True),
        ("item_bar_counter", "scene_bar", None, "吧台", "供应鸡尾酒和啤酒的长吧台", "furniture", "drink", None, True, True),
        ("item_bar_booth", "scene_bar", None, "卡座", "舒适的皮质卡座", "furniture", "rest", None, True, True),
        ("item_bar_jukebox", "scene_bar", None, "点唱机", "老式的点唱机，可以选歌", "electronics", "entertain", None, True, True),
        ("item_gym_treadmill", "scene_gym", None, "跑步机", "进口的电动跑步机", "equipment", "exercise", None, True, True),
        ("item_gym_dumbbell", "scene_gym", None, "哑铃区", "整套哑铃和杠铃", "equipment", "exercise", None, True, True),
        ("item_gym_water", "scene_gym", None, "饮水机", "健身房的饮水机", "furniture", "drink", None, True, True),
        ("item_cinema_screen", "scene_cinema", None, "放映厅", "大银幕放映厅，环绕音响", "furniture", "entertain", None, True, True),
        ("item_cinema_snacks", "scene_cinema", None, "零食柜台", "爆米花和可乐", "furniture", "eat", None, True, True),
        ("item_clothing_rack", "scene_clothing", None, "服装展示架", "挂着当季新款", "furniture", "store", None, True, False),
        ("item_clothing_mirror", "scene_clothing", None, "试衣镜", "落地试衣镜", "furniture", "decorate", None, True, False),
        ("item_station_bench", "scene_station", None, "候车长椅", "遮阳棚下的金属长椅", "furniture", "rest", None, True, True),
        ("item_station_vending", "scene_station", None, "自动售货机", "卖饮料和零食", "furniture", "eat,drink", None, True, True),
        ("item_riverside_bench", "scene_riverside", None, "河边长椅", "面对河景的木质长椅", "furniture", "rest", None, True, True),
        ("item_riverside_vendor", "scene_riverside", None, "小吃摊", "卖烤红薯和糖葫芦", "furniture", "eat,cook,drink", None, True, True),
        ("item_office_desk", "scene_office", None, "办公桌", "政府工作人员的办公位", "furniture", "work", None, True, True),
        ("item_office_water", "scene_office", None, "饮水机", "公共饮水机", "furniture", "drink", None, True, True),
        ("item_arcade_cabinet", "scene_arcade", None, "街机", "经典格斗游戏街机", "electronics", "entertain", None, True, True),
        ("item_arcade_snacks", "scene_arcade", None, "零食柜", "薯片和汽水", "furniture", "eat", None, True, True),
    ]
    for item in items:
        execute(c, """INSERT OR REPLACE INTO item(id, scene_id, owner_npc_id, name, description, item_type, function, room_name, is_interactive, is_usable)
                      VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", item)

    # ── Home scene items ──────────────────────────
    # Note: owner_npc_id is set to NULL for all items. Ownership is determined
    # by the room's "owner" field in the scene rooms JSON.
    _home_items = []
    _home_configs = [
        ("apt_a", ["npc_li_ming", "npc_photo_01", "npc_photo_07", "npc_photo_09"]),
        ("apt_b", ["npc_wang_fang", "npc_photo_02", "npc_photo_06", "npc_photo_10"]),
        ("apt_c", ["npc_zhang_wei", "npc_photo_03", "npc_photo_05", "npc_photo_11", "npc_photo_12"]),
        ("apt_d", ["npc_chen_xue", "npc_liu_jie", "npc_photo_04", "npc_photo_08", "npc_photo_13"]),
        ("home_player", ["player_001"]),
    ]
    _npc_name_lookup = {
        "npc_li_ming": "李明", "npc_wang_fang": "王芳", "npc_zhang_wei": "张伟",
        "npc_chen_xue": "陈雪", "npc_liu_jie": "刘姐",
        "npc_photo_01": "苏晓萌", "npc_photo_02": "林雨桐", "npc_photo_03": "赵小美",
        "npc_photo_04": "周若兰", "npc_photo_05": "吴佳琪", "npc_photo_06": "郑诗涵",
        "npc_photo_07": "钱晓雪", "npc_photo_08": "孙婉清", "npc_photo_09": "李若溪",
        "npc_photo_10": "冯小曼", "npc_photo_11": "陈思怡", "npc_photo_12": "褚云熙",
        "npc_photo_13": "卫小薇",
    }

    for home_id, residents in _home_configs:
        base = f"item_{home_id}"
        # Living room (shared)
        _home_items.append((f"{base}_sofa", home_id, None, "沙发", "柔软的布艺沙发", "furniture", "rest", "客厅"))
        _home_items.append((f"{base}_tv", home_id, None, "电视", "一台液晶电视", "electronics", "entertain", "客厅"))
        _home_items.append((f"{base}_tea_table", home_id, None, "茶几", "木质茶几", "furniture", "decorate", "客厅"))
        # Kitchen (shared)
        _home_items.append((f"{base}_fridge", home_id, None, "冰箱", "储存食物的冰箱", "appliance", "eat", "厨房"))
        _home_items.append((f"{base}_stove", home_id, None, "灶台", "做饭用的燃气灶台", "appliance", "cook", "厨房"))
        _home_items.append((f"{base}_sink", home_id, None, "水槽", "厨房水槽，可以喝水洗漱", "fixture", "drink", "厨房"))
        _home_items.append((f"{base}_dining_table", home_id, None, "餐桌", "吃饭用的餐桌", "furniture", "eat", "厨房"))
        # Bathroom (shared)
        _home_items.append((f"{base}_shower", home_id, None, "淋浴", "热水淋浴", "fixture", "wash", "浴室"))
        _home_items.append((f"{base}_mirror", home_id, None, "镜子", "浴室镜子", "fixture", "decorate", "浴室"))
        # Bedrooms (private per resident)
        for resident_id in residents:
            if home_id == "home_player":
                rn = "卧室"
                owner = None  # Player's own bedroom
            else:
                name_part = _npc_name_lookup.get(resident_id, resident_id)
                rn = f"{name_part}卧室"
                owner = resident_id  # NPC's private bedroom
            _home_items.append((f"{base}_bed_{resident_id}", home_id, owner, "床", "舒适的床", "furniture", "sleep,couple_intimate", rn))
            _home_items.append((f"{base}_wardrobe_{resident_id}", home_id, owner, "衣柜", "存放衣物的衣柜", "furniture", "store", rn))
            _home_items.append((f"{base}_desk_{resident_id}", home_id, owner, "书桌", "学习和工作的书桌", "furniture", "rest", rn))

    for item in _home_items:
        execute(c, """INSERT OR REPLACE INTO item(id, scene_id, owner_npc_id, name, description, item_type, function, room_name, is_interactive, is_usable)
                      VALUES(?, ?, ?, ?, ?, ?, ?, ?, 1, 1)""", item)

    print(f"  Home items seeded: {len(_home_items)}")

    # ── Insert a default player ───────────────────
    player_id = "player_001"
    execute(c, """INSERT OR IGNORE INTO player(id, name, birth_date, gender, appearance, personality, career, current_scene_id, home_scene_id, attributes)
                  VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (player_id, "新居民", "2000-01-01", "other",
             jd({"height": "170cm", "build": "普通"}),
             jd(["友好", "好奇"]), "小镇新居民", "scene_coffee_shop", "home_player",
             jd({"stamina": 5, "speed": 5, "strength": 5})))

    # Player relationships with all NPCs (stranger by default)
    for npc_id in npc_ids:
        _insert_rel(c, player_id, "player", npc_id, "npc", "stranger", 0, 0, 0)
        _insert_rel(c, npc_id, "npc", player_id, "player", "stranger", 0, 0, 0)

    conn.commit()
    print(f"Seeded: {len(scene_ids)} scenes, {len(npc_ids)} NPCs, {len(items)} items, 1 player")


def _insert_rel(conn, a_id, a_type, b_id, b_type, rel_type, fav, fam, count):
    # Use deterministic ID so re-running doesn't create duplicates
    rel_id = f"rel_{a_id}_{b_id}"
    existing = conn.execute(
        "SELECT favorability, familiarity, interaction_count FROM relationship WHERE id = ?",
        (rel_id,)
    ).fetchone()
    if existing:
        # Don't overwrite existing progress — only insert if missing
        return
    execute(conn, """INSERT OR IGNORE INTO relationship(id, entity_a_id, entity_a_type, entity_b_id, entity_b_type,
                      relationship_type, favorability, familiarity, interaction_count)
                      VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rel_id, a_id, a_type, b_id, b_type, rel_type, fav, fam, count))


if __name__ == "__main__":
    db_path = get_db_path()
    print(f"Initializing database at: {db_path}")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    run_migrations(db_path)

    conn = get_connection(db_path)
    try:
        seed_data(conn)
        # Verify
        scenes = fetch_all(conn, "SELECT id, name FROM scene")
        npcs = fetch_all(conn, "SELECT id, name FROM npc")
        rels = fetch_all(conn, "SELECT COUNT(*) as cnt FROM relationship")
        players = fetch_all(conn, "SELECT id, name FROM player")
        print(f"Database ready: {len(scenes)} scenes, {len(npcs)} NPCs, "
              f"{rels[0]['cnt']} relationships, {len(players)} players")
    finally:
        conn.close()
