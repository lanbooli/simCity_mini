# 系统架构

## 多进程架构

```
┌──────────────────────────────────────────────────┐
│                  Supervisor                       │
│         (src/supervisor.py)                       │
│  启动/停止/监控所有子进程                            │
└────┬───────┬────────┬────────┬──────────────────┘
     │       │        │        │
     ▼       ▼        ▼        ▼
┌─────────┐ ┌──────┐ ┌──────┐ ┌──────────────────┐
│ System  │ │Player│ │ API  │ │ NPC × 19         │
│ Process │ │Process│ │Server│ │ (独立进程)        │
└────┬────┘ └──┬───┘ └──┬───┘ └───────┬──────────┘
     │         │        │             │
     └─────────┴────────┴─────────────┘
                      │
              ┌───────▼───────┐
              │    Redis      │
              │ ┌───────────┐ │
              │ │ Pub/Sub   │ │  ← 广播: 时间/天气/社交事件
              │ │ Streams   │ │  ← 消息: 对话/社交/移动
              │ │ KV Store  │ │  ← 状态: NPC/玩家/场景
              │ └───────────┘ │
              └───────┬───────┘
                      │
              ┌───────▼───────┐
              │   SQLite      │  ← 持久化数据
              │   ChromaDB    │  ← 向量记忆 (RAG)
              └───────────────┘
```

## 通信机制

### Redis 频道分工

| 机制 | 用途 | 示例 |
|------|------|------|
| **Pub/Sub** | 广播事件（一对多） | `system:time_tick`, `system:weather`, `system:social_event` |
| **Streams** | 消息队列（点对点+消费组） | `stream:dialogue:{npc_id}`, `stream:social:{npc_id}` |
| **KV Store** | 状态存储（读写） | `state:npc:{id}`, `state:scene:{id}:npcs`, `state:game_time` |

### 进程间通信流程

#### NPC 自主决策循环
```
1. System 发布 time_tick → Pub/Sub channel
2. NPC Process 收到 tick → _on_time_update()
3. Perception 查询 Redis KV (同场景实体)
4. Brain.decide() → 生成意图
5. 执行意图 (对话/社交/移动)
6. 更新 Redis KV (NPC 自身状态)
7. 写入 SQLite (记忆/关系/对话历史)
```

#### 玩家对话流程
```
1. 前端 WebSocket → API Server
2. API → stream:dialogue:inbound
3. Player Process 消费 → 添加 RAG 上下文
4. Player → stream:dialogue:{npc_id}
5. NPC Process 消费 → LLM 生成回复
6. NPC → stream:dialogue:outbound
7. API WebSocket → 前端显示
```

#### NPC↔NPC 社交流程
```
1. NPC A 决策 socialize → 选中同场景 NPC B
2. NPC A LLM 生成开场白
3. 更新 A→B 关系，创建记忆
4. 广播 system:social_event (phase: "open")
5. 发送消息到 stream:social:{npc_b_id}
6. NPC B _social_consumer 消费
7. NPC B LLM 生成回复
8. 更新 B→A 关系，创建记忆
9. 广播 system:social_event (phase: "reply")
10. 双写 dialogue 表
```

## 数据模型

### 有向关系 (Directed Relationship)

```
Alice → Bob:  favorability=85, familiarity=60, type=friend
Bob → Alice:  favorability=70, familiarity=50, type=acquaintance
```

两个方向独立存储。`relationship` 表的 `entity_a` 为主体，`entity_b` 为客体。

### 记忆层级

| 类型 | importance | 说明 |
|------|-----------|------|
| short_term | 1-5 | 日常琐事，容量 20 条 |
| long_term | 6-8 | LLM 每日总结生成，持久保留 |
| life_event | 9-10 | 告白/结婚/重大事件，永久保留 |

### 关系类型层级

```
stranger(0) → acquaintance(1) → friend(2) → best_friend(3)
                                              ↓
                                    boyfriend/girlfriend(4)
                                              ↓
                                        spouse(5)

dislike(-1) → enemy(-2)   (负面路径)
```

## 数据库表

| 表 | 说明 |
|----|------|
| `player` | 玩家基础信息 |
| `npc` | NPC 基础信息 (性格/属性/日程) |
| `scene` | 场景定义 |
| `scene_npc` | NPC 在场景中的角色 (worker/visitor/resident) |
| `relationship` | 有向关系边 (好感/熟悉/舒适/恋爱状态) |
| `memory` | 通用记忆 (玩家+NPC) |
| `memory_embedding` | SQLite ↔ ChromaDB 桥接 |
| `dialogue` | 对话历史 (支持 player↔npc 和 npc↔npc) |
| `goal` | 目标 (life/work/relationship) |
| `game_event` | 游戏事件 (global/scene/personal) |
| `game_state` | KV 持久化 |
| `item` | 道具/物品 |
| `social_post` | 朋友圈动态 |
| `social_like` | 点赞记录 |
| `social_comment` | 评论记录 |

## LLM 集成

- 通过 LM Studio 的 OpenAI 兼容 API 调用
- 模型: `qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive` / `qwen3.5-4b-uncensored-hauhaucs-aggressive` (按调用类型路由)
- 提示词模板集中在 `src/llm/prompts.py`
- NPC 对话使用 `temperature=0.8`，内心独白 `temperature=0.9`
- 越界叙事 `temperature=0.6`（确保严肃性）
- 支持重试 (max 2 retries, 5s timeout)

## 前端

- 纯静态 SPA，由 FastAPI 直接 serve
- 响应式状态管理 (`Store` 模式，发布/订阅)
- WebSocket 实时接收时间/天气/NPC 状态/社交事件
- 管理面板 (`Ctrl+Shift+M`) 用于调试


## 新增系统（v0.3.0）

### 生理系统
```
PhysiologyManager (纯规则,不消耗LLM)
├── tick(delta_hours) → 4属性衰减
├── crisis() → 返回优先级最高的危机 (thirst > hunger > energy)
├── recover(stat, amount) → 恢复属性
├── daily_check() → 年龄+1, 老人死亡概率
└── 死亡 → _persist_death() → SQLite
```

### 互动系统
```
玩家动作 → respond_to_action()
           ├── InteractionContext.add_action() → 记录状态
           ├── NPC_ACTION_SYSTEM prompt ← interaction_context
           └── LLM生成回复（知道当前肢体状态）

NPC主动亲密 → IntimacyEngine.check_actions()
              ├── 29种动作 × 概率（状态驱动）
              ├── _STATE_BOOST/_STATE_SUPPRESS → 链式触发
              └── _execute_intimate_action()
                  ├── LLM叙事
                  └── InteractionContext.add_action()
```

### 通勤系统
```
_start_travel(target, room)
  → 查 config/scene_distances.json
  → _is_traveling = True
  → _travel_remaining = N game minutes
  → 每游戏分钟递减
  → 通勤中: 不社交/不互动/不显示
  → _on_arrive() → 正常恢复
```

### 场所20个（最新）
```
☕ cafe | 🌳 outdoor | 🏫 school | 📚 library | 🛒 market | 🏥 hospital
🍽️ restaurant | 🍺 bar | 💪 gym | 🎬 cinema | 👗 shop | 🚉 outdoor
🌊 outdoor | 🏛️ office | 🎮 arcade | 🏠 home×5
```
