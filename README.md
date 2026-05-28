# 城市小镇 (City Town)

城市生活模拟游戏。18 个 NPC 各自拥有独立的 AI 进程，具备性格、记忆、心情和关系系统。NPC 之间可以自主社交，也能与玩家进行丰富的互动——从日常寒暄到恋爱结婚。

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
│   │   ├── settings.py        # Pydantic Settings (.env)
│   │   └── game_config.yaml   # 游戏参数（天气/关系/恋爱/越界/朋友圈）
│   ├── llm/                   # LLM 客户端
│   │   ├── lmstudio_client.py
│   │   └── prompts.py         # 所有提示词模板
│   ├── npc/                   # NPC 系统（核心）
│   │   ├── process.py         # NPC 进程主循环
│   │   ├── brain.py           # 决策引擎（意图生成）
│   │   ├── dialogue.py        # 对话处理器
│   │   ├── relationship.py    # 关系管理器
│   │   ├── action_rules.py    # 动作规则/越界检测
│   │   ├── perception.py      # 环境感知
│   │   ├── memory.py          # 记忆管理
│   │   ├── mood.py            # 心情管理
│   │   ├── movement.py        # 场景移动
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
# 启动全部进程（系统 + 18 NPC + 玩家 + API）
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

## 许可证

MIT
