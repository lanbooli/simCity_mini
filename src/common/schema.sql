-- ============================================================
-- City Town - 城市小镇 数据库 Schema
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- 玩家
-- ============================================================
CREATE TABLE IF NOT EXISTS player (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    birth_date      TEXT NOT NULL,
    gender          TEXT NOT NULL CHECK(gender IN ('male','female','other')),
    appearance      TEXT NOT NULL DEFAULT '{}',
    personality     TEXT NOT NULL DEFAULT '[]',
    career          TEXT,
    current_scene_id TEXT,
    home_scene_id   TEXT,
    attributes      TEXT NOT NULL DEFAULT '{"stamina":5,"speed":5,"strength":5}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (current_scene_id) REFERENCES scene(id),
    FOREIGN KEY (home_scene_id) REFERENCES scene(id)
);

-- ============================================================
-- 场景
-- ============================================================
CREATE TABLE IF NOT EXISTS scene (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    scene_type      TEXT NOT NULL DEFAULT 'indoor' ,
    weather_affected INTEGER NOT NULL DEFAULT 1,
    max_capacity    INTEGER NOT NULL DEFAULT 20,
    icon            TEXT NOT NULL DEFAULT '',
    rooms           TEXT NOT NULL DEFAULT '[]',
    residents       TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- NPC
-- ============================================================
CREATE TABLE IF NOT EXISTS npc (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    birth_date      TEXT NOT NULL,
    gender          TEXT NOT NULL CHECK(gender IN ('male','female','other')),
    appearance      TEXT NOT NULL DEFAULT '{}',
    clothing        TEXT NOT NULL DEFAULT '{}',
    voice_type      TEXT NOT NULL DEFAULT '',
    career          TEXT,
    personality     TEXT NOT NULL DEFAULT '[]',
    current_scene_id TEXT,
    home_scene_id   TEXT,
    current_mood    TEXT NOT NULL DEFAULT 'neutral',
    current_activity TEXT,
    schedule        TEXT NOT NULL DEFAULT '{}',
    attributes      TEXT NOT NULL DEFAULT '{"stamina":5,"speed":5,"strength":5}',
    is_active       INTEGER NOT NULL DEFAULT 1,
    is_dead         INTEGER NOT NULL DEFAULT 0,
    death_cause     TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (current_scene_id) REFERENCES scene(id),
    FOREIGN KEY (home_scene_id) REFERENCES scene(id)
);

-- ============================================================
-- 场景-NPC 关联 (含角色: worker/visitor/resident)
-- ============================================================
CREATE TABLE IF NOT EXISTS scene_npc (
    scene_id        TEXT NOT NULL,
    npc_id          TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'visitor' CHECK(role IN ('worker','visitor','resident')),
    joined_at       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (scene_id, npc_id),
    FOREIGN KEY (scene_id) REFERENCES scene(id),
    FOREIGN KEY (npc_id) REFERENCES npc(id)
);

-- ============================================================
-- 道具/物品
-- ============================================================
CREATE TABLE IF NOT EXISTS item (
    id              TEXT PRIMARY KEY,
    scene_id        TEXT,
    owner_npc_id    TEXT,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    item_type       TEXT NOT NULL DEFAULT 'decoration',
    function        TEXT,
    room_name       TEXT,
    is_interactive  INTEGER NOT NULL DEFAULT 0,
    is_usable       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (scene_id) REFERENCES scene(id),
    FOREIGN KEY (owner_npc_id) REFERENCES npc(id)
);

-- ============================================================
-- 关系 (有向边)
-- entity_a = 主体, entity_b = 客体
-- Alice 对 Bob 的看法和 Bob 对 Alice 的看法是两行
-- ============================================================
CREATE TABLE IF NOT EXISTS relationship (
    id              TEXT PRIMARY KEY,
    entity_a_id     TEXT NOT NULL,
    entity_a_type   TEXT NOT NULL CHECK(entity_a_type IN ('player','npc')),
    entity_b_id     TEXT NOT NULL,
    entity_b_type   TEXT NOT NULL CHECK(entity_b_type IN ('player','npc')),
    relationship_type TEXT NOT NULL DEFAULT 'stranger',
    favorability    INTEGER NOT NULL DEFAULT 0,
    familiarity     INTEGER NOT NULL DEFAULT 0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_interaction_at TEXT,
    -- Phase 4.0: intimacy comfort (directed A→B)
    intimacy_comfort INTEGER NOT NULL DEFAULT 0,
    -- Phase 8: romance system
    love_eligible    INTEGER NOT NULL DEFAULT 0,
    committed_since  TEXT,
    married_since    TEXT,
    jealousy_level   INTEGER NOT NULL DEFAULT 0,
    breakup_count    INTEGER NOT NULL DEFAULT 0,
    divorced         INTEGER NOT NULL DEFAULT 0,
    -- Phase 9: boundary violation tracking
    violation_count  INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_a_id, entity_a_type, entity_b_id, entity_b_type)
);
CREATE INDEX IF NOT EXISTS idx_relationship_a ON relationship(entity_a_id, entity_a_type);
CREATE INDEX IF NOT EXISTS idx_relationship_b ON relationship(entity_b_id, entity_b_type);

-- ============================================================
-- 记忆 (玩家和NPC通用)
-- ============================================================
CREATE TABLE IF NOT EXISTS memory (
    id              TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL CHECK(entity_type IN ('player','npc')),
    memory_type     TEXT NOT NULL DEFAULT 'short_term' CHECK(memory_type IN ('short_term','long_term','life_event')),
    content         TEXT NOT NULL,
    related_entity_id TEXT,
    related_entity_type TEXT CHECK(related_entity_type IN ('player','npc')),
    importance      INTEGER NOT NULL DEFAULT 5,
    emotion         TEXT,
    scene_id        TEXT,
    game_time       TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (scene_id) REFERENCES scene(id)
);
CREATE INDEX IF NOT EXISTS idx_memory_entity ON memory(entity_id, entity_type);
CREATE INDEX IF NOT EXISTS idx_memory_time ON memory(game_time);

-- ============================================================
-- 记忆-向量桥接 (SQLite <-> ChromaDB)
-- ============================================================
CREATE TABLE IF NOT EXISTS memory_embedding (
    id              TEXT PRIMARY KEY,
    memory_id       TEXT NOT NULL UNIQUE,
    chroma_id       TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (memory_id) REFERENCES memory(id)
);

-- ============================================================
-- 目标
-- ============================================================
CREATE TABLE IF NOT EXISTS goal (
    id              TEXT PRIMARY KEY,
    entity_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL CHECK(entity_type IN ('player','npc')),
    goal_type       TEXT NOT NULL CHECK(goal_type IN ('life','work','relationship')),
    description     TEXT NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 5,
    is_short_term   INTEGER NOT NULL DEFAULT 1,
    progress        REAL NOT NULL DEFAULT 0.0,
    status          TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','abandoned')),
    parent_goal_id  TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT,
    FOREIGN KEY (parent_goal_id) REFERENCES goal(id)
);
CREATE INDEX IF NOT EXISTS idx_goal_entity ON goal(entity_id, entity_type);

-- ============================================================
-- 对话历史
-- ============================================================
CREATE TABLE IF NOT EXISTS dialogue (
    id              TEXT PRIMARY KEY,
    speaker_id      TEXT NOT NULL,
    speaker_type    TEXT NOT NULL CHECK(speaker_type IN ('player','npc')),
    listener_id     TEXT NOT NULL,
    listener_type   TEXT NOT NULL CHECK(listener_type IN ('player','npc')),
    content         TEXT NOT NULL,
    scene_id        TEXT,
    game_time       TEXT NOT NULL DEFAULT '',
    favorability_change INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (scene_id) REFERENCES scene(id)
);
CREATE INDEX IF NOT EXISTS idx_dialogue_pair ON dialogue(speaker_id, listener_id);
CREATE INDEX IF NOT EXISTS idx_dialogue_time ON dialogue(game_time);

-- ============================================================
-- 游戏事件
-- ============================================================
CREATE TABLE IF NOT EXISTS game_event (
    id              TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL CHECK(event_type IN ('global','scene','personal')),
    scene_id        TEXT,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    start_game_time TEXT NOT NULL,
    end_game_time   TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    affected_entities TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (scene_id) REFERENCES scene(id)
);

-- ============================================================
-- 游戏状态 (KV 持久化)
-- ============================================================
CREATE TABLE IF NOT EXISTS game_state (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================================
-- 朋友圈 (Phase 10)
-- ============================================================
CREATE TABLE IF NOT EXISTS social_post (
    id              TEXT PRIMARY KEY,
    author_id       TEXT NOT NULL,
    author_type     TEXT NOT NULL CHECK(author_type IN ('player','npc')),
    content         TEXT NOT NULL,
    post_type       TEXT NOT NULL DEFAULT 'general',
    visibility      TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','friends','close_friends','lover','private')),
    scene_id        TEXT,
    mood            TEXT,
    related_entity_id TEXT,
    game_time       TEXT NOT NULL DEFAULT '',
    like_count      INTEGER NOT NULL DEFAULT 0,
    comment_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_post_author ON social_post(author_id);
CREATE INDEX IF NOT EXISTS idx_post_time ON social_post(created_at);

CREATE TABLE IF NOT EXISTS social_like (
    id              TEXT PRIMARY KEY,
    post_id         TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    user_type       TEXT NOT NULL CHECK(user_type IN ('player','npc')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(post_id, user_id, user_type),
    FOREIGN KEY (post_id) REFERENCES social_post(id)
);

CREATE TABLE IF NOT EXISTS social_comment (
    id              TEXT PRIMARY KEY,
    post_id         TEXT NOT NULL,
    author_id       TEXT NOT NULL,
    author_type     TEXT NOT NULL CHECK(author_type IN ('player','npc')),
    content         TEXT NOT NULL,
    game_time       TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (post_id) REFERENCES social_post(id)
);

