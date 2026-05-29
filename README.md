# 城市小镇 (City Town)

城市生活模拟游戏。19 个 NPC 各自拥有独立的 AI 进程，具备性格、记忆、心情和关系系统。NPC 之间可以自主社交，也能与玩家进行丰富的互动——从日常寒暄到恋爱结婚。

## 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.14 |
| 通信 | Redis (pub/sub + streams + KV store) |
| 持久化 | SQLite + ChromaDB (向量记忆) |
| LLM | LM Studio (OpenAI 兼容 API) |
| 后端 | FastAPI + WebSocket |
| 前端 | Vanilla JS + CSS (SPA) |
| 进程管理 | 自定义 Supervisor (多进程架构) |

## 目录结构

```
city-town/
├── src/
│   ├── supervisor.py          # 进程管理器（启动/停止/状态）
│   ├── api/                   # FastAPI 服务 + WebSocket
│   │   ├── server.py          # 应用入口
│   │   ├── websocket_manager.py
│   │   ├── schemas.py
│   │   └── routes/            # REST 端点
│   │       ├── admin.py       # 管理面板 API
│   │       ├── dialogue.py
│   │       ├── npc.py
│   │       ├── player.py
│   │       ├── scene.py
│   │       └── system.py
│   ├── common/                # 共享基础设施
│   │   ├── database.py        # SQLite 连接池
│   │   ├── message_broker.py  # Redis 抽象层
│   │   ├── models.py          # 数据模型
│   │   ├── schema.sql         # 数据库 DDL
│   │   └── utils.py           # 工具函数
│   ├── config/                # 配置
│   │   ├── settings.py           # Pydantic Settings (.env)
│   │   ├── game_config.yaml      # 场景+NPC数据
│   │   ├── scene_distances.json  # 场所间步行距离矩阵
│   │   └── npc_personality_map.json # NPC→39型性格映射
│   ├── llm/                   # LLM 客户端
│   │   ├── lmstudio_client.py
│   │   └── prompts.py         # 所有提示词模板
│   ├── npc/                   # NPC 系统（核心）
│   │   ├── process.py         # NPC 进程主循环 + 危机处理 + 通勤
│   │   ├── brain.py           # 决策引擎（意图生成）
│   │   ├── dialogue.py        # 对话处理器 + InteractionContext
│   │   ├── relationship.py    # 关系管理器
│   │   ├── action_rules.py    # 动作规则/越界检测
│   │   ├── action_selector.py # 自动动作选择器
│   │   ├── intimacy_engine.py # 亲密度引擎（29种互动）
│   │   ├── physiology.py      # 生理系统（4维需求）
│   │   ├── personality.py     # 39型性格引擎
│   │   ├── social_handshake.py # NPC↔NPC社交握手协议
│   │   ├── perception.py      # 环境感知
│   │   ├── memory.py          # 记忆管理
│   │   ├── mood.py            # 心情管理
│   │   ├── movement.py        # 场景移动 + 排程
│   │   └── social_feed.py     # 朋友圈
│   ├── player/                # 玩家系统
│   │   ├── process.py         # 玩家进程
│   │   ├── dialogue_manager.py
│   │   └── memory.py
│   ├── rag/                   # 向量检索
│   │   ├── embeddings.py
│   │   ├── retriever.py
│   │   └── vector_store.py
│   └── system/                # 系统进程
│       ├── process.py         # 时间/天气主循环
│       ├── time_manager.py
│       ├── weather_manager.py
│       ├── scene_manager.py
│       └── event_manager.py
├── frontend/                  # 前端 SPA
│   ├── index.html
│   ├── css/
│   │   ├── main.css
│   │   ├── reset.css
│   │   ├── components.css
│   │   └── admin.css
│   └── js/
│       ├── main.js
│       ├── store.js           # 响应式状态管理
│       ├── websocket.js       # WebSocket 客户端
│       ├── api.js             # REST API 客户端
│       ├── components/
│       │   ├── npcCard.js
│       │   └── relationshipBar.js
│       └── panels/
│           ├── topBar.js
│           ├── sidebar.js
│           ├── sceneView.js
│           ├── dialogue.js
│           └── adminPanel.js
├── data/                      # 运行时数据
│   ├── city_town.db           # SQLite 数据库
│   └── chromadb/              # 向量存储
├── scripts/                   # 工具脚本
│   └── migrate_social.py
└── config/                    # 配置文件
    └── game_config.yaml
```

## 快速启动

### 前置条件

- Python 3.14+
- Redis (localhost:6379)
- LM Studio 运行中 (或兼容的 OpenAI API)

### 安装

```bash
cd city-town
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 配置

编辑 `.env` 文件（可选，所有配置均有默认值）：

```env
REDIS_URL=redis://localhost:6379
LMSTUDIO_BASE_URL=http://localhost:1234
LMSTUDIO_MODEL=qwen3.6-35b-a3b-uncensored-hauhaucs-aggressive
DATABASE_PATH=data/city_town.db
API_HOST=0.0.0.0
API_PORT=8000
```

游戏参数（关系阈值、天气概率、越界判定等）在 `config/game_config.yaml` 中配置。

### 启动

```bash
# 启动全部进程（系统 + 19 NPC + 玩家 + API）
python -m src.supervisor start

# 查看状态
python -m src.supervisor status

# 停止
python -m src.supervisor stop
```

启动后访问 `http://localhost:8000` 进入游戏。

### 管理面板

开发调试时，在浏览器中按 `Ctrl+Shift+M` 或访问 `?admin=true` 打开管理面板。可修改 NPC 属性、关系数值、游戏状态，以及触发快速测试事件。

## 进程架构

```
Supervisor (管理者)
├── System Process     # 时间推进 + 天气变化
├── API Server         # FastAPI + WebSocket (端口 8000)
├── Player Process     # 玩家状态 + 对话路由
├── NPC × 18           # 每个 NPC 独立进程
└── (LLM via HTTP)     # 非进程，按需调用
```

所有进程通过 Redis 通信，无直接内存共享。

## 核心系统

- **关系系统**：有向好感度 (-100~100)、熟悉度 (0~100)、亲密舒适度 (0~100)
- **恋爱系统**：告白→恋人→求婚→结婚→分手/离婚，完整的恋爱生命周期
- **越界系统**：动作门槛 vs 关系等级差异判定，NPC 性格化反应，舆论传播
- **朋友圈**：NPC 自主发帖，玩家/NPC 点赞评论，可见性控制
- **动作系统**：递减收益、上下文敏感度、4 级物理动作判定
- **记忆系统**：短期/长期/人生事件三级，RAG 向量检索

## 开发指南

- 新增 NPC：在 `scripts/init_db.py` 添加数据，重启 supervisor
- 新增动作：在 `src/npc/action_rules.py` 的 `ACTION_RULES` 字典注册
- 新增提示词模板：在 `src/llm/prompts.py` 添加新模板
- 调试：使用管理面板 (`Ctrl+Shift+M`) 快速操控游戏状态


## 最新系统（Phase 2+）

### 生理系统 (`src/npc/physiology.py`)

NPC拥有4维生理需求，纯规则引擎（不消耗LLM）：

| 属性 | 衰减速率 | 危机阈值 | 恢复方式 |
|------|---------|---------|---------|
| 🍽️ hunger | -1.5/h | <20 | 厨房做饭 +60 |
| 💧 thirst | -2.0/h | <20 | 喝水 +60 |
| ⚡ energy | -1.0/h | <10 | 卧室睡觉 +70 |
| 👥 social | -0.8/h | <40触发社交欲 | 社交互动恢复 |

- 危机优先级：thirst > hunger > energy
- 饥饿/脱水为0时扣HP（5HP/h），HP=0则死亡
- 死亡写入数据库持久化（重启不复活）
- 年龄阶段影响属性上限和衰减倍率
- 老年人每天有自然死亡概率（70岁+）

### 亲密度引擎 (`src/npc/intimacy_engine.py`)

NPC根据关系自动发起29种亲密互动：

| 层级 | 条件 | 示例动作 |
|------|------|---------|
| 🟢 朋友 | fav≥30 | 分享零食、端茶、靠近、拉衣角、挽手臂 |
| 🟡 好友 | fav≥50 | 摸头杀、拥抱、靠肩膀、牵手散步、盖毯子 |
| 🟠 密友 | fav≥65 | 背后抱、亲脸颊、耳边低语 |
| 🔴 情侣 | fav≥75 | 亲吻、依偎、亲额头、情话、告别亲吻 |

状态驱动逻辑：拥抱中→亲吻概率×3，挽手臂×0.1。动作按逻辑链触发，不重复。

### 互动连续性 (`src/npc/dialogue.py:InteractionContext`)

跨动作的状态记忆：

- 跟踪最近5次互动记录 + 当前肢体状态
- 状态自动衰减（hugging保持6游戏分钟）
- 注入LLM prompt → NPC知道"被抱着时被亲"
- 合并兼容状态（hugging+kissing → hugging while kissing）

### 房间级定位

NPC移动精确到具体房间（客厅/厨房/卧室/浴室），而非仅场景级别。

### 通勤系统

- NPC从A到B需要行走时间（`config/scene_distances.json`，210对距离）
- 有自行车属性的NPC速度×2
- 通勤中的NPC不显示在任何场所、不互动、不社交
- 到达后自动恢复正常行为
- 玩家不受此限制

### 20个场所地图

☕ 咖啡店 · 🌳 公园 · 🏫 高中 · 📚 图书馆 · 🛒 超市 · 🏥 医院 · 🍽️ 餐厅 · 🍺 酒吧 · 💪 健身房 · 🎬 影院 · 👗 服装店 · 🚉 车站 · 🌊 河边 · 🏛️ 镇政府 · 🎮 游戏厅 · 🏠 公寓×4 · 🏠 玩家公寓

### 进程守护

- Supervisor管理所有进程（system/API/player/19 NPC），健康检查+自动重启
- NPC死亡后进程不重启
- 部分NPC为"照片NPC"（无预设深度性格）

## 许可证


MIT
