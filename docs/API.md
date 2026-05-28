# API 文档

Base URL: `http://localhost:8000/api/v1`

## REST 端点

### 健康检查

```
GET /health
```
Response: `{"status":"ok","service":"city-town-api","version":"0.1.0"}`

### 场景

```
GET /api/v1/scenes
```
返回所有场景列表，含各场景当前 NPC 数量。

```
GET /api/v1/scenes/{scene_id}
```
返回指定场景详情，含当前在场的 NPC 列表。

### NPC

```
GET /api/v1/npcs
```
返回所有 NPC 列表（基础信息：名称/性别/性格/心情/活动/场景）。

```
GET /api/v1/npcs/{npc_id}
```
返回指定 NPC 详情。

### 对话

```
GET /api/v1/dialogue/history?entity_id={id}&other_id={id}
```
查询两个实体之间的对话历史。

### 玩家

```
GET /api/v1/player/{player_id}
```
返回玩家状态。

```
POST /api/v1/player/{player_id}/move
```
移动玩家到指定场景。Body: `{"scene_id": "scene_park"}`

### 系统

```
GET /api/v1/system/time
```
返回当前游戏时间 (day/hour/minute)。

```
GET /api/v1/system/weather
```
返回当前天气。

### 管理面板

仅在 DEBUG 模式下可用。

```
GET  /api/v1/admin/state              # 导出完整游戏状态快照
POST /api/v1/admin/npc/{npc_id}       # 修改 NPC 属性
POST /api/v1/admin/relationship       # 修改关系数值
POST /api/v1/admin/game_state         # 修改游戏状态 (时间/天气)
POST /api/v1/admin/trigger            # 触发快速测试事件
POST /api/v1/admin/npc/{npc_id}/decide         # 强制 NPC 决策
POST /api/v1/admin/reset_cooldowns/{npc_id}    # 重置 NPC 冷却
```

## WebSocket

```
ws://localhost:8000/ws/game?player_id=player_001
```

### 客户端 → 服务端

| type | data | 说明 |
|------|------|------|
| `dialogue_send` | `{npc_id, content}` | 发送对话消息 |
| `scene_focus` | `{scene_id}` | 切换焦点场景 |
| `ping` | `{}` | 心跳 |

### 服务端 → 客户端

| type | data | 说明 |
|------|------|------|
| `time_update` | `{day, hour, minute, time_str}` | 时间更新 (每 tick) |
| `weather_update` | `{weather}` | 天气变化 |
| `dialogue_response` | `{npc_id, content, favorability_change, new_mood, game_time}` | NPC 对话回复 |
| `npc_state_update` | `{npc_id, mood, activity, scene_id}` | NPC 状态变化 |
| `social_event` | `{interaction_id, phase, npc_id, target_id, action_name, content, scene_id}` | NPC↔NPC 社交事件 |
| `npc_moved` | `{npc_id, from_scene, to_scene}` | NPC 移动 |
| `scene_update` | `{scene_id, npcs_present}` | 场景在场实体更新 |

## Redis 频道 (内部)

### Pub/Sub

| 频道 | 消息格式 | 说明 |
|------|---------|------|
| `system:time_tick` | `{day, hour, minute}` | 游戏时间滴答 |
| `system:weather` | `{type}` | 天气变化 |
| `system:social_event` | `{interaction_id, phase, npc_id, target_type, target_id, action_name, content}` | 社交事件广播 |
| `npc_movement` | `{npc_id, scene_id, activity, reason}` | NPC 移动请求 |

### Streams

| Stream | 用途 |
|--------|------|
| `stream:dialogue:inbound` | 玩家 → Player Process |
| `stream:dialogue:outbound` | NPC → API → 前端 |
| `stream:dialogue:{npc_id}` | Player → 特定 NPC |
| `stream:social:{npc_id}` | NPC A → NPC B 社交消息 |

### KV Store

| Key | 值 |
|-----|-----|
| `state:game_time` | `{day, hour, minute, time_str}` |
| `state:weather` | 天气字符串 |
| `state:npc:{id}` | NPC 完整状态 (mood/activity/scene/attributes) |
| `state:player:{id}` | 玩家状态 |
| `state:player:{id}:location` | `{scene_id, scene_name}` |
| `state:scene:{id}:npcs` | `{npcs: [{id, name, mood, activity}]}` |
| `state:scene:{id}:info` | `{name, description, scene_type, icon}` |
