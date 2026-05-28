# 前端说明

## 技术栈

- Vanilla JavaScript (无框架)
- CSS3 (CSS 变量 / Flexbox / Grid)
- 自定义响应式 Store 模式
- WebSocket 实时通信

## 文件结构

```
frontend/
├── index.html              # SPA 入口
├── css/
│   ├── reset.css           # CSS Reset
│   ├── main.css            # 布局和全局样式
│   ├── components.css      # 组件样式 (NPC卡片/气泡/按钮)
│   └── admin.css           # 管理面板样式
├── js/
│   ├── main.js             # 应用初始化 + 面板协调
│   ├── store.js            # 响应式状态管理
│   ├── websocket.js        # WebSocket 客户端
│   ├── api.js              # REST API 调用封装
│   ├── components/
│   │   ├── npcCard.js      # NPC 卡片渲染 (含社交气泡)
│   │   └── relationshipBar.js  # 关系数值可视化
│   └── panels/
│       ├── topBar.js       # 顶部栏 (时间/天气/场景名)
│       ├── sidebar.js      # 侧边栏 (场景列表/NPC列表/朋友圈入口)
│       ├── sceneView.js    # 场景视图 (NPC卡片 + 社交气泡)
│       ├── dialogue.js     # 对话面板 (聊天界面)
│       └── adminPanel.js   # 管理面板 (调试工具)
└── assets/
    └── avatars/            # NPC 头像图片
```

## 面板布局

```
┌─────────────────────────────────────────────────┐
│  TopBar: 时间 | 天气 | 场景名                     │
├──────────┬──────────────────────────────────────┤
│ Sidebar  │  SceneView (主视图)                  │
│          │  ┌──────┐ ┌──────┐ ┌──────┐         │
│ 📍场景   │  │ NPC  │ │ NPC  │ │ NPC  │         │
│  ☕咖啡店│  │ 卡片 │ │ 卡片 │ │ 卡片 │         │
│  🌳公园  │  └──────┘ └──────┘ └──────┘         │
│  🏫学校  │  ┌──────┐ ┌──────┐                  │
│  ...     │  │ NPC  │ │ NPC  │                  │
│          │  │ 卡片 │ │ 卡片 │                  │
│ 👥 NPC   │  └──────┘ └──────┘                  │
│  · 李明  │                                      │
│  · 王芳  │  Dialogue Panel (底部弹出)            │
│  · ...   │  ┌──────────────────────────┐       │
│          │  │ NPC: 你好呀~             │       │
│ 💬 朋友圈│  │ You: 今天天气真好        │       │
│          │  │ [输入框........] [发送]   │       │
│          │  └──────────────────────────┘       │
└──────────┴──────────────────────────────────────┘
```

## 状态管理 (Store)

`store.js` 实现发布/订阅模式：

```javascript
// 读取
Store.get('gameTime')      // → {day, hour, minute, time_str}
Store.get('weather')       // → "sunny"
Store.get('npcs')          // → {npc_id: {mood, activity, ...}}

// 订阅变化
Store.on('gameTime', (newTime) => { ... })
Store.on('npcs', (npcs) => { ... })
Store.on('socialBubbles', (bubbles) => { ... })

// 更新
Store.set('gameTime', {day: 2, hour: 10, minute: 30})
```

### Store 数据键

| Key | 类型 | 说明 |
|-----|------|------|
| `gameTime` | object | 当前游戏时间 |
| `weather` | string | 当前天气 |
| `currentScene` | object | 当前焦点场景 |
| `npcs` | object | 所有 NPC 状态 (按 ID 索引) |
| `scenes` | array | 场景列表 |
| `socialBubbles` | object | 社交气泡 (按 NPC ID 索引) |
| `dialogues` | object | 对话历史 (按 NPC ID 索引) |
| `relationships` | object | 关系数据 |
| `playerState` | object | 玩家状态 |

## WebSocket 事件流

`websocket.js` 维护与 `ws://localhost:8000/ws/game` 的长连接。

收到服务端消息后的路由：

| 消息类型 | 处理 |
|---------|------|
| `time_update` | `Store.set('gameTime', data)` → TopBar 重渲染 |
| `weather_update` | `Store.set('weather', data.weather)` → TopBar 重渲染 |
| `dialogue_response` | `Store.addDialogue(data.npc_id, data)` → Dialogue 面板更新 |
| `npc_state_update` | `Store.updateNpc(data.npc_id, data)` → NPC 卡片更新 |
| `social_event` | `Store.addSocialEvent(data)` → 社交气泡渲染 |
| `npc_moved` | `Store.updateNpc(data.npc_id, {scene_id: data.to_scene})` → 场景视图刷新 |
| `scene_update` | `Store.set('currentScene', data)` → SceneView 重渲染 |

## 社交气泡系统

`sceneView.js` 管理 NPC 卡片上的浮动气泡。4 种类型：

| 类型 | CSS 类 | 颜色 | 触发事件 |
|------|--------|------|---------|
| 社交对话 | `.social-bubble` | 黄色 | NPC↔NPC 交谈 |
| 亲密互动 | `.intimate-bubble` | 粉色 | 拥抱/亲吻等 |
| 动作 | `.action-bubble` | 绿色 | 打招呼/送礼等 |
| 内心独白 | `.thought-bubble` | 灰色斜体 | NPC 内心想法 |

气泡在 NPC 卡片上方显示，5 秒后自动消失。

## 主题

使用 CSS 变量定义在 `main.css` 中。修改 `:root` 下的变量值可全局换肤。
