# 生育系统设计文档

## 一、嘿咻检测与处理

### 1.1 `/H` 前缀识别

```
玩家发送格式:
  /[H]动作内容    (标准格式)
  /H动作内容      (简化格式)

路由规则:
  content.startswith("/H") 或 content.startswith("/[H]")
  → 提取动作内容 (去掉前缀)
  → dialogue.py: _handle_sex_interaction()
```

### 1.2 专属 Prompt

```
NPC_SEX_INTERACTION_SYSTEM:

你是一个角色扮演AI。玩家正在与你进行亲密互动。

描写要求:
1. 不少于300字，细致入微地描述每一个感官细节
2. 感官变化: 体温的微妙上升、心跳的节奏变化、呼吸深浅、皮肤触感的细腻反馈
3. 外貌变化: 脸颊绯红的蔓延、细密汗珠的渗出、眼神从清澈到迷离的过渡、
   衣物的褶皱与凌乱、发丝的散落
4. 声音描写: 用拟声词表现喘息、轻哼、低语、呜咽
5. 使用比喻和拟人手法增强画面感:
   - 比喻: "像春日融雪般酥软" "如琴弦被轻拨时的颤栗"
   - 拟人: "每一寸肌肤都在低语" "指尖仿佛有自己的记忆"
6. 动作描写使用（），对话使用「」
7. 根据两人关系和动作程度做出合理反应
8. 以 [[FAVORABILITY: ±N]] 结尾（范围-5到+10）
9. 如果互动达到高潮，在回复末尾包含 [ORGASM] 标记

当前互动阶段提示：
{interaction_stage}
```

### 1.3 互动阶段追踪

```python
self._sex_stage = {
    "count": 0,           # 本次会话累计次数
    "intensity": 0,       # 累积强度 (0-100)
    "last_action": "",    # 上一个动作
}
```

### 1.4 模型路由

| 特性 | 普通动作 `/xxx` | 嘿咻 `/Hxxx` |
|------|----------------|-------------|
| Prompt | NPC_ACTION_SYSTEM | NPC_SEX_INTERACTION |
| 回复字数 | 30-60字 | ≥300字 |
| 描写手法 | 一般叙事 | 感官+比喻+拟人 |
| 好感度 | -5 ~ +5 | -5 ~ +10 |
| [ORGASM] | 无 | 有 |
| 调用模型 | 35B | 35B |
| max_tokens | 8192 | 8192 |

## 二、怀孕系统

### 2.1 触发条件

```
触发: LLM 回复包含 [ORGASM] 标记
概率: 5% (基础) + 3% × 本次会话嘿咻次数 (累计, 上限30%)
条件: 双方异性 + NPC 存活 + NPC 未怀孕
限制: 同一天内多次不叠加 (按游戏日去重)
```

### 2.2 数据库

```sql
CREATE TABLE pregnancy (
    id TEXT PRIMARY KEY,
    mother_id TEXT NOT NULL,           -- NPC id
    father_id TEXT NOT NULL,           -- 玩家 id
    father_name TEXT NOT NULL,         -- 冗余，方便查询
    conceived_day INTEGER NOT NULL,    -- 受孕游戏日
    due_day INTEGER NOT NULL,          -- 预产期 = conceived_day + 280
    status TEXT DEFAULT 'pregnant',    -- pregnant | delivered
    created_at TEXT
);
```

### 2.3 怀孕期间 (280 游戏日)

```
每天 midnight 检查:
  ├─ 是否到达 due_day → 触发分娩
  └─ 未到达:
       ├─ mood 波动 (±5)
       ├─ personality 含 "外向"/"分享型" → 朋友圈发状态
       ├─ 移动速度 -50% (travel 时间 ×2)
       └─ 不参与剧烈动作 (action_rules 合并判断)

NPC 信息:
  - 管理面板显示: "怀孕中 | 父亲: XXX | 预产期: Day NNN"
  - 对话 prompt 注入怀孕状态
```

### 2.4 分娩

```
到达 due_day:
  1. 创建新生儿 NPC
     姓 = father_name 第一个字
     名 = 从名字池随机
     性别 = 50/50 随机
     career = "婴儿"
     personality = ["天真","好奇","依赖"]
     home_scene_id = mother.home_scene_id
     birth_date = 当前游戏日

  2. 写入数据库
     npc 表 + scene_npc 表

  3. 创建关系
     mother → baby: "child"
     baby → mother: "mother" + 高 favorability
     father → baby: "child"
     baby → father: "father" + 高 favorability

  4. pregnancy.status → "delivered"

  5. 发送玩家消息: "XXX 生下了一个男/女孩, 取名 YYY"

  6. 广播 social_event
```

## 三、婴儿成长

### 3.1 年龄阶段

```python
AGE_CONFIG 修改:
  INFANT (0-7岁):
    stat_cap=0.4
    decay_mult=0.0  ← 饥饿/口渴/精力不下降, 保证存活
    can_socialize=False

  CHILD (7-12岁): 现有配置不变
  ADULT (12-60岁): 现有配置不变
  ELDER (60+): 现有配置不变
```

### 3.2 睡眠状态

```
game hour 22:00 ~ 06:00 → sleeping (所有 NPC)
婴儿 (0-3): 20:00 ~ 08:00 → sleeping (更长时间)

sleeping 期间:
  - 拒绝互动, 返回 "XXX 正在睡觉"
  - energy 满格时自然醒来
  - 不触发自主行为
```

### 3.3 成长里程碑

```
5岁: 开始自主行动 (autonomous_cycle)
7岁: 进入 CHILD 阶段, 可上学
12岁: 进入 ADULT 阶段
```

## 四、玩家消息系统

### 4.1 数据库

```sql
CREATE TABLE player_messages (
    id TEXT PRIMARY KEY,
    player_id TEXT NOT NULL,
    from_npc_id TEXT NOT NULL,
    from_npc_name TEXT NOT NULL,
    msg_type TEXT NOT NULL,          -- pregnancy_announce|birth_announce|baby_milestone
    content TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    game_time TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### 4.2 消息类型

| 类型 | 触发时机 | 示例内容 |
|------|---------|---------|
| `pregnancy_announce` | 检测到怀孕 | "我怀孕了，孩子是你的" |
| `birth_announce` | 分娩完成 | "我生了，是个女孩，取名林思雨" |
| `baby_milestone` | 关键年龄 | "小明今天会走路了" (3岁) |

### 4.3 API

```
GET  /api/v1/player/{player_id}/messages     → 消息列表
POST /api/v1/player/{player_id}/messages/read → 标记已读
GET  /api/v1/player/{player_id}/messages/unread_count → 未读数
```

### 4.4 前端

```
管理面板: 📬 消息图标 + 未读 badge
  ├─ 点击展开消息列表
  ├─ 未读消息高亮
  └─ 点击标记已读
```

## 五、NPC 信息展示

```
管理面板 NPC 详情新增:
  ├─ 怀孕状态: 怀孕中 | 父亲: 李怡鸣 | 预产期: Day 320
  ├─ 子女列表: [林小明 (男, 3岁), 林小华 (女, 1岁)]
  └─ 是否睡眠: 正在睡觉 (22:00-06:00)
```

## 六、涉及文件

| 文件 | 变更内容 |
|------|---------|
| `scripts/init_db.py` | 建 pregnancy + player_messages 表 |
| `common/models.py` | Pregnancy + PlayerMessage 模型 |
| `npc/dialogue.py` | /H 检测 + 专属 prompt + 怀孕概率 |
| `npc/process.py` | 怀孕追踪 + 分娩 + 睡眠 + 消息发送 |
| `npc/physiology.py` | INFANT decay_mult=0, 睡眠逻辑 |
| `api/routes/admin.py` | 玩家消息 API + NPC 怀孕/子女信息 |
| `api/routes/player.py` | 新增玩家消息路由 |
| `frontend/js/panels/adminPanel.js` | 消息面板 + NPC 详情展示 |
| `frontend/css/admin.css` | 样式 |

## 七、开始游戏年龄调整

```
新生儿 age = 0
玩家首次互动: 婴儿 0-7 岁不降饥饿值
7-12 岁: CHILD 阶段, 可社交
12 岁+: ADULT 阶段 (可生育的最小年龄)
```
