# Changelog

## v0.2.0 (2026-05-24) — NPC 自主行为系统

### 新增

#### NPC 感知系统
- NPC 每决策周期查询 Redis KV，感知同场景实体（NPC + 玩家）
- 感知数据包括：场景类型/时间/天气/实体心情和活动状态

#### NPC↔NPC 社交
- NPC 之间可自主发起社交（LLM 生成开场白 → 目标 NPC 回复）
- 社交动作：打招呼/闲聊/拥抱/赠送礼物/一起喝咖啡/抱怨天气/争吵
- 双向关系更新（A→B 和 B→A 独立计算）
- 对话历史写入 dialogue 表（speaker_type=listener_type="npc"）
- 前端显示社交气泡（黄色浮动气泡，5秒消失）

#### NPC→玩家丰富互动
- NPC 基于关系+性格+心情+场景主动对玩家发起互动
- 动作类型：打招呼/搭话/赞美/送礼/靠近/请咖啡/邀请散步/倾诉/回避
- 亲密动作递进（牵手→拥抱→亲脸颊→亲吻→依偎）
- 玩家忽略 NPC 主动互动 3 次后该 NPC 不再主动互动
- NPC 回避行为（好感 <= -50 时主动离开场景）

#### 内心独白与记忆巩固
- NPC 约每 30 游戏分钟概率触发内心独白（灰色斜体气泡）
- 每天结束时记忆巩固：高重要性记忆升级为长期，低重要性删除

#### 亲密舒适度系统
- 新增 intimacy_comfort 数值 (0-100)，有向（A→B 和 B→A 独立）
- 同场景共处自然增长，亲密互动大幅增长
- 被拒绝/被忽略衰减
- 性格修正：外向 ×1.5，害羞 ×0.3

#### 动作系统优化
- **递减收益**：同一动作连续使用效果递减（×0.7 → ×0.4 → ×0.15）
- **非线性好感度曲线**：极端值更难提升（80-100 区间 ×0.3）
- **上下文敏感度**：时间/场景/心情/性格修正动作效果
- **4 级物理判定**：critical_success / success / narrow_fail / failure
- **动作冷却**：两次动作间隔 >= 20 游戏分钟

#### 恋爱关系系统
- 心动阈值判定（好感 >= 80, 舒适 >= 70, 熟悉 >= 35）
- 玩家告白（/告白）和 NPC 主动告白
- 恋人专属动作：亲吻/深吻/依偎/说情话/牵手散步/约会
- 恋人期对话风格变化（更亲密，更长）
- 玩家求婚（/求婚）和 NPC 主动求婚
- 结婚/离婚完整生命周期
- 吃醋系统（亲眼目睹或第三方告知才触发）
- 分手/冷静期/复合机制

#### 越界行为与后果系统
- 动作门槛 vs 关系等级差异判定（gap >= 3 触发越界）
- 4 级严重度：轻微/中度/严重/暴力
- NPC 性格化反应表（害羞→逃跑，强势→反击+报警）
- 目击者 gossip 传播 + 全镇声望下降
- 属性反击判定（NPC strength+speed vs 玩家）
- 受害者创伤恢复（轻微 240 tick → 暴力永久不可逆）

#### NPC 朋友圈系统
- NPC 每个决策周期概率发帖（基础 3%，性格修正）
- 内容类型：心情分享/活动打卡/社交感慨/恋爱官宣/提问互动
- LLM 生成帖子内容（个性+心情+场景作为上下文）
- 可见性控制：公开/好友/密友/仅恋人
- 玩家/NPC 点赞评论互动
- NPC 之间互相浏览/点赞/评论朋友圈
- 动态保留 7 游戏天

#### 管理面板
- `Ctrl+Shift+M` 或 `?admin=true` 开启
- NPC 属性/关系/游戏状态修改
- 快捷测试触发器（强制决策/告白/求婚/吃醋/越界）
- 仅在 DEBUG 模式下启用

### 修复
- WebSocket `_on_*` 处理器死代码 bug（缩进错误导致永不执行）
- NPC↔NPC 关系更新硬编码 `other_type="player"`
- RAG 检索硬编码 `entity_type: "player"` 过滤条件
- 前端 NPC 状态变化不触发重渲染
- 动作规则参数名 `player_attrs`/`npc_attrs` → `actor_attrs`/`target_attrs`

### 数据库变更
- relationship 表新增 8 字段：intimacy_comfort, love_eligible, committed_since, married_since, jealousy_level, breakup_count, divorced, violation_count
- 新增 social_post / social_like / social_comment 三张表

### 配置变更
- config/game_config.yaml 新增 4 节：intimacy_comfort, romance, boundary_violation, social_feed

---

## v0.1.0 (2026-05-23) — 初始版本

- 多进程架构（System + Player + NPC × 18 + API）
- Redis 通信（Pub/Sub + Streams + KV Store）
- SQLite 持久化 + ChromaDB 向量存储
- FastAPI REST API + WebSocket 实时推送
- 玩家 ↔ NPC 对话系统（LLM 生成 + RAG 记忆检索）
- 基础关系系统（好感度/熟悉度/关系类型转换）
- NPC 心情系统（happy/sad/angry/fear/neutral/excited）
- NPC 日程表和场景移动
- 时间系统（游戏日/小时/分钟，120x 倍速）
- 天气系统（晴天/阴天/雨天/暴风雨/雪天转换）
- 动作系统（微笑/拥抱/殴打等）
- 前端 SPA（场景视图/NPC 卡片/对话面板）
