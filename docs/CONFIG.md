# 配置说明书

`config/game_config.yaml` 包含所有游戏参数。修改后重启服务即生效。

## 游戏基础设定 (`game`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `name` | 城市小镇 | 游戏名称 |
| `start_day` | 1 | 初始天数 |
| `start_hour` | 8 | 初始小时 (0-23) |
| `start_minute` | 0 | 初始分钟 (0-59) |
| `game_speed_multiplier` | 120 | 1 真秒 = 120 游戏秒 = 2 游戏分钟 |

## 天气系统 (`weather`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `initial` | sunny | 初始天气 |
| `transition_weights.*` | 见文件 | 天气间转移概率 (每游戏小时判定) |

可用天气：`sunny` / `cloudy` / `rainy` / `stormy` / `snowy`

## 亲密舒适度 (`intimacy_comfort`)

控制 NPC 与玩家/其他 NPC 之间的身体接触舒适程度 (0-100)。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `growth_per_hour_same_scene` | 1 | 同场景每小时自然增长量 |
| `growth_personality_extrovert` | 1.5 | 外向性格增速倍率 |
| `decay_per_day_absent` | 2 | 玩家长时间未出现每天衰减 |
| `decay_witness_intimacy` | 5 | NPC 目睹玩家与他人亲密时的衰减 |

## 恋爱系统 (`romance`)

### 心动阈值 (`love_eligible`)

同时满足以下条件触发"心动时刻"：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `favorability_min` | 80 | 最低好感度 |
| `intimacy_comfort_min` | 70 | 最低亲密舒适度 |
| `familiarity_min` | 35 | 最低熟悉度 |

### 告白判定 (`confession_acceptance`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `base_rate` | 0.60 | 基础接受率 |
| `fav_85_plus` | 0.40 | 好感 >= 85 加成 |
| `comfort_80_plus` | 0.30 | 舒适 >= 80 加成 |
| `personality_romantic` | 0.20 | 浪漫性格加成 |
| `personality_shy` | -0.15 | 害羞性格减成 |

### NPC 主动告白 (`npc_confession_probability`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `base_per_tick` | 0.05 | 每个决策周期基础概率 |
| `personality_romantic` | 4.0 | 浪漫性格倍率 |
| `personality_extrovert` | 2.5 | 外向性格倍率 |
| `personality_shy` | 0.2 | 害羞性格倍率 |

### 求婚条件 (`proposal`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `favorability_min` | 90 | 最低好感度 |
| `intimacy_comfort_min` | 90 | 最低亲密舒适度 |
| `familiarity_min` | 60 | 最低熟悉度 |
| `min_ticks_as_lovers` | 1440 | 成为恋人后的最小 tick 数 |

## 越界行为 (`boundary_violation`)

### 判定

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `violation_threshold` | 3 | 动作门槛等级 - 当前关系等级 >= 此值触发越界 |

### 关系等级映射 (`relation_levels`)

```
stranger: 0, acquaintance: 1, friend: 2, best_friend: 3
boyfriend/girlfriend: 4, spouse: 5, parent/sibling/child: 5
dislike: -1, enemy: -2
```

### 惩罚 (`favorability_penalty` / `comfort_penalty`)

| 严重度 | 好感惩罚 | 舒适惩罚 |
|--------|---------|---------|
| minor (轻微冒犯) | -20 | -10 |
| moderate (中度骚扰) | -50 | -50 |
| severe (严重侵犯) | -80 | -100 (归零) |
| violent (暴力侵犯) | -100 | -100 (永久锁定) |

### 舆论传播 (`gossip`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `witness_count_1` | 0.8 | 1人目击传播概率 |
| `witness_count_3plus` | 1.0 | 3+人目击传播概率 |
| `spread_tick_single` | 24 | 单一目击者传播所需 tick |
| `spread_tick_multiple` | 12 | 多人目击传播所需 tick |
| `reputation_drop.minor` | 5 | 轻微事件声望下降 |
| `reputation_drop.moderate` | 15 | 中度事件声望下降 |
| `reputation_drop.severe` | 30 | 严重事件声望下降 |
| `reputation_drop.violent` | 40 | 暴力事件声望下降 |

### 创伤恢复 (`recovery_ticks`)

| 等级 | tick 数 | 说明 |
|------|---------|------|
| minor | 240 | 自动恢复 |
| moderate | 720 | 自动恢复 |
| severe | 2880 | 需玩家公开道歉 |
| violent | -1 | 不可恢复 |

### 反击 (`counter_attack`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | true | 是否启用 NPC 反击 |
| `attribute_diff_for_npc_win` | 2 | NPC 属性高于玩家此值时反击成功 |

## 朋友圈 (`social_feed`)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `post_probability_base` | 0.03 | 每个决策周期基础发帖概率 |
| `post_cooldown_ticks` | 480 | 发帖冷却 (tick) |
| `personality_extrovert_mult` | 2.5 | 外向性格发帖倍率 |
| `personality_talkative_mult` | 3.0 | 话痨性格发帖倍率 |
| `personality_shy_mult` | 0.3 | 害羞性格发帖倍率 |
| `npc_browse_interval_ticks` | 30 | NPC 浏览朋友圈间隔 |
| `npc_like_acquaintance_prob` | 0.6 | 点赞熟人帖的概率 |
| `npc_comment_acquaintance_prob` | 0.2 | 评论熟人帖的概率 |
| `player_like_daily_cap` | 3 | 玩家点赞每日上限 |
| `post_retention_game_days` | 7 | 动态保留天数 |

## 场景定义 (`scenes`)

每个场景的字段：

| 字段 | 说明 |
|------|------|
| `id` | 唯一标识符 (如 `scene_coffee_shop`) |
| `name` | 显示名称 |
| `description` | 场景描述文本 |
| `scene_type` | `indoor` / `outdoor` |
| `weather_affected` | 是否受天气影响 |
| `max_capacity` | 最大容纳人数 |
| `icon` | 前端显示图标 (emoji) |

默认场景：阳光咖啡店、中心公园、小镇高中、公共图书馆、便民超市
