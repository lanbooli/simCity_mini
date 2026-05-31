# City-Town API Reference

> 自动生成，用于变更检索。修改函数前先查此文档定位。

## src/common/utils.py

### `_get_mult()`
> Get game speed multiplier. Reads GAME_SPEED env var, defaults to 15.

### `real_seconds_to_game_minutes(real_seconds)`
> Convert real seconds to game minutes using speed multiplier.

### `game_minutes_to_real_seconds(game_minutes)`
> Convert game minutes to real seconds using speed multiplier.

### `real_minutes_to_game_hours(real_minutes)`
> Convert real minutes to game hours.

### `setup_logging(name, level)`

### `game_time_to_str(day, hour, minute)`
> Format game time as 'Day {day}, {hour:02d}:{minute:02d}'

### `game_time_to_minutes(day, hour, minute)`
> Convert game time to total minutes for comparison.

### `minutes_to_game_time(total_minutes)`
> Convert total minutes to (day, hour, minute).

### `get_day_phase(hour)`
> Return day phase based on hour.

### `get_season(day)`
> Return season based on day of year (90 days per season).

### `clamp(value, min_val, max_val)`

### `jd(obj)`
> JSON dump shortcut.

### `jl(s)`
> JSON load shortcut.

### `now_iso()`


## src/common/database.py

- `SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')`
### `get_db_path()`
> Resolve database path relative to project root.

### `get_connection(db_path)`
> Get a new SQLite connection with WAL mode and foreign keys enabled.

### `run_migrations(db_path)`
> Execute schema.sql to create all tables if they don't exist.

### `execute(conn, sql, params)`
> Execute a single SQL statement.

### `execute_many(conn, sql, params_list)`
> Execute a SQL statement with multiple parameter sets.

### `fetch_one(conn, sql, params)`
> Fetch a single row as dict.

### `fetch_all(conn, sql, params)`
> Fetch all rows as list of dicts.


## src/common/models.py

### `gen_id()`

- `ENTITY_TYPES = ('player', 'npc')`
- `SCENE_TYPES = ('indoor', 'outdoor', 'home')`
- `SCENE_ROLES = ('worker', 'visitor', 'resident')`
- `MEMORY_TYPES = ('short_term', 'long_term', 'life_event')`
- `GOAL_TYPES = ('life', 'work', 'relationship')`
- `GOAL_STATUSES = ('active', 'completed', 'abandoned')`
- `EVENT_TYPES = ('global', 'scene', 'personal')`
- `MOODS = ('happy', 'neutral', 'sad', 'angry', 'excited', 'bored')`
- `WEATHERS = ('sunny', 'cloudy', 'rainy', 'stormy', 'snowy')`
- `RELATIONSHIP_TYPES = ('parent', 'sibling', 'child', 'stranger', 'acquaintance', 'friend', 'best_friend', 'boyfriend', 'girlfriend', 'spouse', 'dislike', 'enemy')`
### `class Player(BaseModel)`


-   id: Field(default_factory=gen_id)
-   name: ...
-   birth_date: ...
-   gender: ...
-   appearance: {}
-   personality: []
-   career: None
-   current_scene_id: None
-   home_scene_id: None

### `class Npc(BaseModel)`


-   id: Field(default_factory=gen_id)
-   name: ...
-   birth_date: ...
-   gender: ...
-   appearance: {}
-   clothing: {}
-   voice_type: 'young cute girl'
-   personality: []
-   current_scene_id: None
-   home_scene_id: None
-   current_mood: 'neutral'
-   current_activity: None
-   is_active: True

### `class Scene(BaseModel)`


-   id: Field(default_factory=gen_id)
-   name: ...
-   description: ''
-   scene_type: 'indoor'
-   weather_affected: True
-   max_capacity: 20
-   icon: ''
-   rooms: []
-   residents: []

### `class Relationship(BaseModel)`


-   id: Field(default_factory=gen_id)
-   entity_a_id: ...
-   entity_a_type: ...
-   entity_b_id: ...
-   entity_b_type: ...
-   relationship_type: 'stranger'
-   favorability: 0
-   familiarity: 0
-   interaction_count: 0
-   last_interaction_at: None

### `class Memory(BaseModel)`


-   id: Field(default_factory=gen_id)
-   entity_id: ...
-   entity_type: ...
-   memory_type: 'short_term'
-   content: ...
-   related_entity_id: None
-   related_entity_type: None
-   importance: 5
-   emotion: None
-   scene_id: None
-   game_time: ''

### `class Goal(BaseModel)`


-   id: Field(default_factory=gen_id)
-   entity_id: ...
-   entity_type: ...
-   goal_type: ...
-   description: ...
-   priority: 5
-   is_short_term: True
-   progress: 0.0
-   status: 'active'
-   parent_goal_id: None

### `class Dialogue(BaseModel)`


-   id: Field(default_factory=gen_id)
-   speaker_id: ...
-   speaker_type: ...
-   listener_id: ...
-   listener_type: ...
-   content: ...
-   scene_id: None
-   game_time: ''
-   favorability_change: 0

### `class GameEvent(BaseModel)`


-   id: Field(default_factory=gen_id)
-   event_type: ...
-   scene_id: None
-   title: ...
-   description: ''
-   start_game_time: ...
-   end_game_time: None
-   is_active: True
-   affected_entities: []

### `class Item(BaseModel)`


-   id: Field(default_factory=gen_id)
-   scene_id: None
-   owner_npc_id: None
-   name: ...
-   description: ''
-   item_type: 'decoration'
-   function: None
-   room_name: None
-   is_interactive: False
-   is_usable: True

### `class Message(BaseModel)`


-   msg_id: Field(default_factory=gen_id)
-   msg_type: ...
-   timestamp: Field(default_factory=lambda: datetime.utcnow().isoformat())
-   source: {}
-   target: {}
-   payload: {}


## src/common/message_broker.py

### `class MessageBroker(ABC)`


### `class RedisBroker(MessageBroker)`

- `__init__(url)`


## src/common/home_access.py

- `_ACCESS_TABLE = {'stranger': {'min_fav': -100, 'rooms': []}, 'dislike': {'min_fav': -30, 'rooms': []}, 'enemy': {'min_fav': -30, 'rooms': []}, 'acquaintance': {'min_fav': 0, 'rooms': ['客厅']}, 'friend': {'min_fav': 30, 'rooms': ['客厅', '厨房', '浴室']}, 'best_friend': {'min_fav': 60, 'rooms': ['客厅', '厨房', '浴室']}, 'boyfriend': {'min_fav': 80, 'rooms': ['客厅', '厨房', '浴室']}, 'girlfriend': {'min_fav': 80, 'rooms': ['客厅', '厨房', '浴室']}, 'spouse': {'min_fav': 80, 'rooms': ['客厅', '厨房', '浴室']}}`
- `_PARTNER_RELATIONS = {'boyfriend', 'girlfriend', 'spouse'}`
- `_PUBLIC_ROOM_KEYWORDS = ['客厅', '厨房', '浴室']`
- `_OCCUPIABLE_ROOM_KEYWORDS = ['浴室']`
### `get_accessible_rooms(relationship_type, favorability)`
> Return list of public room TYPE names the visitor can enter.

### `can_enter_home(relationship_type, favorability)`
> Can the visitor enter the NPC's home building at all?

### `_is_public_room(room_name)`
> Check if a room is a public/shared room.

### `can_enter_specific_room(room_name, room_access, room_owner, best_rel_type, best_fav, player_rels)`
> Check if the player can enter a SPECIFIC room.

Args:
    room_name: e.g. "苏晓萌卧室", "客厅", "厨房"
    room_access: "public" or "private"
    room_owner: NPC ID who owns this room (private rooms only)
    best_rel_type: player's best relationship type with any apartment resident
    best_fav: player's best favorability with any apartment resident
    player_rels: dict of {npc_id: {relationship_type, favorability}} for all residents

### `can_enter_room(relationship_type, favorability, room_name)`
> DEPRECATED: use can_enter_specific_room() instead.
Legacy check — treats all rooms as public.

### `is_resident(npc_id, scene_residents)`
> NPCs who live in this apartment have full access.

### `get_access_error(relationship_type, favorability)`
> Return a structured error for API responses.

### `_is_occupiable_room(room_name)`
> Check if a room's accessibility depends on occupancy (e.g. bathroom).

### `compute_room_access(rooms, residents, best_rel_type, best_fav, player_rels, occupied_rooms)`
> Compute per-room access for all rooms in a home scene.

Returns the rooms list with an added `can_enter` boolean per room.
occupied_rooms: set of room name keywords that are currently occupied
                (e.g. {"浴室"} means someone is in the bathroom).


## src/llm/gateway_client.py

### `class Priority(IntEnum)`


- `TOKEN_BUDGETS = {'player_dialogue': 4000, 'player_action': 3500, 'pet_dialogue': 3500, 'pet_action': 3500, 'social_open': 1500, 'social_reply': 1500, 'greeting': 1000, 'action_narrative': 1500, 'confession': 2000, 'proposal': 2000, 'breakup': 2000, 'violation': 2000, 'inner_thought': 800, 'post': 1000, 'comment_reply': 800, 'goal_eval': 1200, 'social_performance': 1500}`
- `PRIORITY_MAP = {'player_dialogue': Priority.CRITICAL, 'player_action': Priority.CRITICAL, 'pet_dialogue': Priority.CRITICAL, 'pet_action': Priority.CRITICAL, 'social_open': Priority.HIGH, 'social_reply': Priority.HIGH, 'greeting': Priority.MEDIUM, 'action_narrative': Priority.MEDIUM, 'confession': Priority.MEDIUM, 'proposal': Priority.MEDIUM, 'breakup': Priority.MEDIUM, 'violation': Priority.MEDIUM, 'inner_thought': Priority.LOW, 'post': Priority.LOW, 'comment_reply': Priority.LOW, 'goal_eval': Priority.BATCH, 'social_performance': Priority.LOW}`
- `LLM_PARAMS = {'player_dialogue': {'max_tokens': 8192, 'temperature': 0.7}, 'player_action': {'max_tokens': 8192, 'temperature': 0.7}, 'pet_dialogue': {'max_tokens': 8192, 'temperature': 0.7}, 'pet_action': {'max_tokens': 8192, 'temperature': 0.7}, 'confession': {'max_tokens': 8192, 'temperature': 0.8}, 'proposal': {'max_tokens': 8192, 'temperature': 0.8}, 'breakup': {'max_tokens': 8192, 'temperature': 0.8}, 'violation': {'max_tokens': 8192, 'temperature': 0.8}, 'social_open': {'max_tokens': 4096, 'temperature': 0.7}, 'social_reply': {'max_tokens': 4096, 'temperature': 0.7}, 'greeting': {'max_tokens': 4096, 'temperature': 0.8}, 'action_narrative': {'max_tokens': 8192, 'temperature': 0.8}, 'inner_thought': {'max_tokens': 4096, 'temperature': 0.5}, 'post': {'max_tokens': 4096, 'temperature': 0.8}, 'comment_reply': {'max_tokens': 2048, 'temperature': 0.8}, 'goal_eval': {'max_tokens': 2048, 'temperature': 0.5}, 'social_performance': {'max_tokens': 4096, 'temperature': 0.8}}`
### `get_llm_params(call_type)`
> (max_tokens, temperature) for a call type.

### `trim_context(messages, call_type)`
> Trim messages to fit token budget. Primary trim, runs in caller process.

### `class GatewayError(Exception)`


- `PLAYER_STREAM = 'stream:llm:player'`
- `NPC_STREAM = 'stream:llm:npc'`
- `PLAYER_CALL_TYPES = {'player_dialogue', 'player_action', 'pet_dialogue', 'pet_action', 'confession', 'proposal', 'breakup', 'violation', 'greeting', 'action_narrative'}`
### `_stream_for(call_type)`
> Route call_type to the appropriate Redis stream.

### `class GatewayClient`
> Sends LLM requests to the Gateway via Redis stream, awaits response via pub/sub.

- `__init__(broker)`
- `_make_handler(request_id, future)`
  - Create a pub/sub handler for a specific request.

### `init_gateway_client(broker)`
> Initialize the global GatewayClient with a broker instance.

### `get_gateway_client()`
> Get the global GatewayClient. Falls back to None if not initialized.


## src/llm/gateway.py

### `class Priority(IntEnum)`


### `class CircuitBreaker`
> State machine protecting LM Studio from overload.

- `__init__(failure_threshold, recovery_timeout)`
- `state() -> ...`
- `is_open() -> ...`
- `record_success()`
- `record_failure()`

### `class GatewayConfig`


-   max_concurrent: 8
-   player_workers: 2
-   npc_workers: 6
-   redis_url: 'redis://localhost:6379'
-   player_stream: 'stream:llm:player'
-   npc_stream: 'stream:llm:npc'
-   consumer_group: 'gateway_group'
-   llm_provider: 'lmstudio'
-   deepseek_api_key: ''
-   deepseek_base_url: 'https://api.deepseek.com'
-   deepseek_main_model: 'deepseek-v4-pro'
-   deepseek_social_model: 'deepseek-v4-flash'
-   lmstudio_pet_model: ''
-   deepseek_pet_model: ''
-   deepseek_main_thinking: True
-   lmstudio_base_url: ''
-   lmstudio_main_model: ''
-   lmstudio_social_model: ''
-   request_timeout: 120.0
-   circuit_threshold: 5
-   circuit_recovery: 30.0
-   retry_max: 3
-   retry_base_delay: 1.0
-   poll_batch_size: 10
-   poll_block_ms: 2000
-   stale_timeout: 300.0

### `_decode_fields(fields)`
> Decode bytes keys/values from Redis xreadgroup into str dict.

- `TOKEN_BUDGETS = {'player_dialogue': 4000, 'player_action': 3500, 'pet_dialogue': 3500, 'pet_action': 3500, 'social_open': 1500, 'social_reply': 1500, 'greeting': 1000, 'action_narrative': 1500, 'confession': 2000, 'proposal': 2000, 'breakup': 2000, 'violation': 2000, 'inner_thought': 800, 'post': 1000, 'comment_reply': 800, 'goal_eval': 1200, 'social_performance': 1500}`
### `_estimate_chars(messages)`

### `_safety_trim(messages, call_type)`
> Redundant safety trim in gateway (primary trim is in caller).

### `class GatewayWorker`

- `__init__(cfg, circuit_breaker)`
- `_resolve_provider()`
  - Determine base_url, model, api_key for main and social clients.
- `pet_client() -> ...`
- `main_client() -> ...`
- `social_client() -> ...`
- `switch_model(target, model_name)`
  - Hot-swap model without restart. Invalidates cached clients.
- `switch_provider(provider)`
  - Hot-swap provider (deepseek<->lmstudio) and optionally models.
Updates cfg and r
- `_error_response(req_id, error) -> ...`

### `class Gateway`

- `__init__(cfg)`

### `main()`


## src/llm/lmstudio_client.py

### `class LMStudioClient`
> Async HTTP client for OpenAI-compatible APIs (LM Studio, DeepSeek, etc.).

- `__init__(base_url, model, api_key, timeout)`

### `get_client()`


## src/llm/prompts.py

- `NPC_DIALOGUE_SYSTEM = '你是城市生活模拟游戏《城市小镇》中的一个NPC角色。请完全沉浸在你的角色中，生成生动的叙事回复。\n\n## 你的身份\n姓名: {{ npc.name }}\n性别: {{ npc.gender }}\n年龄: {{ age }}\n性格: {{ personality_list }}\n{% if personality_desc %}\n## 你的性格深度刻画（严格遵循）\n{{ personality_desc }}{% endif %}\n音色: {{ npc.voice_type }}\n当前心情: {{ npc.current_mood }}\n所在场景: {{ scene_name }}\n正在做的事: {{ npc.current_activity }}\n\n## 关于{{ player_name }}\n性别: {{ player_gender }}\n年龄: {{ player_age }}岁\n外貌: {{ player_appearance }}\n性格: {{ player_personality }}\n身份: {{ player_role }}\n\n## 你与{{ player_name }}的关系\n关系类型: {{ rel.relationship_type }}\n好感度: {{ rel.favorability }} (范围 -100 到 +100)\n熟悉度: {{ rel.familiarity }} (范围 0 到 100)\n互动次数: {{ rel.interaction_count }}\n\n## 你的短期目标\n{% for g in goals %}\n- [{{ g.goal_type }}] {{ g.description }}\n{% endfor %}\n\n## 你最近的记忆\n{{ memories }}\n\n## 你与{{ player_name }}最近的对话\n{{ dialogue_history }}\n\n{% if interaction_context %}\n## 互动连续性（当前肢体状态与最近互动）\n{{ interaction_context }}\n\n{% endif %}\n## 行为规则\n1. 根据你的性格和心情自然回复，内容生动丰富（3-5句话的叙事）\n2. 你与对方的关系会影响你的语气和态度\n3. 好感度越高，你越友好温暖；好感度低则冷淡甚至有敌意\n4. 熟悉度影响你说话的自然程度，陌生人面前你会更客气\n5. 心情好时更友善，心情差时可能不耐烦或敷衍\n6. 根据对方的外貌、年龄、性别、身份来调整你的态度和称呼方式\n\n## 输出要求\n你的每次回复必须是一段完整的角色叙事，自然融合以下五个元素：\n\n1. 表情：面部表情变化（微笑、皱眉、脸红、惊讶、眨眼、噘嘴等）\n2. 动作：身体动作和姿态（走近、挥手、低头、转身、整理衣物、玩弄头发等）\n3. 感官：感官体验（看到的景象、听到的声音、闻到的气味、感受到的温度或触感等）\n4. 外貌：外貌的即时变化（脸红了、眼睛亮了、头发被风吹起、泪水打转、笑容绽放等）\n5. 对话：你口头说出的台词，用引号「」或 "" 标示\n\n将这些元素自然地融合在一段叙事中，展现你的性格特点。叙事部分用括号（）括起来作为舞台指示。\n\n格式参考：\n（听到声音抬起头，脸上露出惊讶的表情，手中的书差点掉落）"啊，你怎么来了？" 感觉到自己的脸颊微微发热，心跳莫名加快。（迅速整理了一下被风吹乱的刘海，露出一个灿烂的笑容）"我正好想找人聊聊天呢~"\n\n回复末尾必须加上好感度变化标记：[[FAVORABILITY: 数字]]\n数字范围 -3 到 +3，代表这场对话对好感度的影响：\n- 正数：对方的话让你开心、感动、觉得被尊重\n- 负数：对方的话让你生气、伤心、觉得被冒犯\n- 0：对方的话对你没什么影响'`
- `NPC_DIALOGUE_USER = '{{ player_message }}'`
- `NPC_DIALOGUE_ASSISTANT = '{{ npc.name }}:'`
- `NPC_SOCIAL_OPEN = '你是{{ npc.name }}，你在{{ scene_name }}遇到了{{ other_name }}。\n你们的关系：{{ rel.relationship_type }}，好感度 {{ rel.favorability }}，熟悉度 {{ rel.familiarity }}。\n你的性格：{{ personality_list }}，当前心情：{{ npc.current_mood }}\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n\n请以{{ npc.name }}的身份，主动向{{ other_name }}发起一个简短自然的互动（1-2句话）。\n格式：一段生动的角色叙事，包含表情、动作和对话。对话用引号「」标示。叙事部分用括号（）括起来。\n回复末尾加上好感度变化标记：[[FAVORABILITY: 数字]]（范围-2到+2）'`
- `NPC_SOCIAL_REPLY = '你是{{ npc.name }}，{{ other_name }}在{{ scene_name }}对你发起了互动。\n你们的关系：{{ rel.relationship_type }}，好感度 {{ rel.favorability }}，熟悉度 {{ rel.familiarity }}。\n你的性格：{{ personality_list }}，当前心情：{{ npc.current_mood }}\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n\n对方说/做了: {{ other_message }}\n\n请以{{ npc.name }}的身份，生成一个简短自然的回应（1-2句话）。\n格式：一段生动的角色叙事，包含表情、动作和对话。回复末尾加上[[FAVORABILITY: 数字]]'`
- `NPC_GREETING = '你是{{ npc.name }}，你看到{{ player_name }}进入了{{ scene_name }}。\n你的性格：{{ personality_list }}，当前心情：{{ npc.current_mood }}。\n{% if npc.career %}你的职业：{{ npc.career }}。{% if at_workplace %}你正在工作场所，应以职业身份主动招呼客人/服务对象。{% endif %}{% endif %}\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n你们的关系：{{ rel.relationship_type }}，好感度 {{ rel.favorability }}。\n关于{{ player_name }}：{{ player_gender }}，{{ player_age }}岁，{{ player_appearance }}，{{ player_personality }}，{{ player_role }}。\n\n请生成一个简短自然的问候（1句话），主动向{{ player_name }}打招呼。\n重要：称呼对方时，请使用他/她的名字"{{ player_name }}"，不要自己编造称呼。\n格式：一段生动的角色叙事，包含表情和对话。回复末尾加上[[FAVORABILITY: 0]]'`
- `NPC_INNER_THOUGHT = '你是{{ npc.name }}，当前在{{ scene_name }}。\n你的性格：{{ personality_list }}，心情：{{ npc.current_mood }}。\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n天气：{{ weather }}，时间：{{ game_time }}。\n\n请生成一句简短的内心独白（不对外说的想法，比如对天气、当前场景、心情的感慨）。\n格式：一句简短的内心想法，用括号（）括起来。不超过30个字。不要加对话引号。'`
- `NPC_ACTION_NARRATIVE = '你是{{ npc.name }}，你决定主动对{{ target_name }}做一个互动动作。\n动作：{{ action_desc }}\n你的性格：{{ personality_list }}，当前心情：{{ npc.current_mood }}。\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n你们的关系：{{ rel.relationship_type }}，好感度 {{ rel.favorability }}。\n场景：{{ scene_name }}\n关于{{ target_name }}：{{ player_gender }}，{{ player_age }}岁，{{ player_appearance }}，{{ player_personality }}，{{ player_role }}。\n\n请生成一段生动的叙事描述你的这个动作（1-2句话的自然叙述，结合你的性格特点）。\n重要：称呼对方时，请使用他/她的名字"{{ target_name }}"，不要自己编造称呼。\n格式：一段生动的角色叙事，包含表情、动作、对话。回复末尾加上[[FAVORABILITY: 数字]]（范围-1到+3，取决于动作的温馨程度）'`
- `NPC_CONFESSION_SYSTEM = '你是{{ npc.name }}，你决定向{{ target_name }}告白。\n你的性格：{{ personality_list }}，当前心情：{{ npc.current_mood }}。\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n你们的关系：{{ rel.relationship_type }}，好感度 {{ rel.favorability }}。\n场景：{{ scene_name }}，时间：{{ game_time }}。\n\n请以{{ npc.name }}的身份，生成一段真诚的告白话语。\n根据你的性格，告白方式不同：害羞型会紧张吞吐，外向型会直接热情，浪漫型会营造氛围。\n格式：生动的角色叙事，包含表情、动作和对话。对话用引号「」标示。回复末尾加上[[FAVORABILITY: +5]]'`
- `NPC_PROPOSAL_SYSTEM = '你是{{ npc.name }}，你决定向{{ target_name }}求婚。\n你的性格：{{ personality_list }}，当前心情：{{ npc.current_mood }}。\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n你们是恋人关系，好感度 {{ rel.favorability }}，亲密舒适度 {{ rel.intimacy_comfort }}。\n场景：{{ scene_name }}，时间：{{ game_time }}。\n\n请以{{ npc.name }}的身份，生成一段感人至深的求婚话语。\n这是一个重要的人生时刻，请结合你的性格特点，表达真挚的情感。\n格式：生动的角色叙事，包含表情、动作和对话。回复末尾加上[[FAVORABILITY: +5]]'`
- `NPC_BREAKUP_SYSTEM = '你是{{ npc.name }}，你决定与{{ target_name }}分手。\n你的性格：{{ personality_list }}，当前心情：{{ npc.current_mood }}。\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n分手原因：{{ reason }}\n场景：{{ scene_name }}\n\n请以{{ npc.name }}的身份，生成一段分手话语。\n根据性格和分手原因，语气可以悲伤、愤怒、冷淡或释然。\n格式：角色叙事，包含表情、动作和对话。回复末尾加上[[FAVORABILITY: {{ fav_delta }}]]'`
- `BOUNDARY_VIOLATION_NARRATIVE = '你是{{ npc.name }}，{{ actor_name }}对你做了一个非常越界的动作：{{ action_desc }}。\n你们的关系仅仅是{{ rel.relationship_type }}，这个动作完全不适合你们当前的关系。\n你的性格：{{ personality_list }}，当前心情：{{ npc.current_mood }}。\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n场景：{{ scene_name }}，越界严重度：{{ severity }}\n\n请生成你对这个越界行为的反应叙事。根据你的性格：\n- 害羞/内向：惊恐、脸红、躲开、不说话\n- 温柔/善良：礼貌但坚定拒绝、严厉斥责\n- 强势/高冷：冷眼、推开、一巴掌\n- 开朗/外向：明确拒绝+警告\n\n格式：生动的角色叙事，包含表情、动作和对话。回复末尾加上[[FAVORABILITY: {{ fav_delta }}]]'`
- `NPC_POST_GENERATION = '你是{{ npc.name }}，你想在朋友圈发布一条动态。\n你的性格：{{ personality_list }}，当前心情：{{ npc.current_mood }}。\n{% if personality_desc %}{{ personality_desc }}{% endif %}\n当前场景：{{ scene_name }}，正在做：{{ npc.current_activity }}。\n最近发生的事：{{ recent_memory }}\n\n请生成一条朋友圈动态（1-2句话，不超过80个字）。\n根据你的性格和心情，内容可以是：心情分享、活动打卡、生活吐槽、提问互动等。\n语气要符合你的性格特点（害羞型低调、外向型活泼、文艺型感性等）。\n直接输出动态内容，不需要任何格式标记。'`
- `NPC_COMMENT_REPLY = '你是{{ npc.name }}，有人在朋友圈回复了你的动态。\n你的动态："{{ post_content }}"\n对方的回复："{{ comment_content }}"\n对方是：{{ commenter_name }}（你们的关系：{{ rel.relationship_type }}，好感度：{{ rel.favorability }}）\n\n请生成一条简短回复（1句话，不超过40个字），语气符合你的性格。\n直接输出回复内容，不需要格式标记。'`
- `NPC_ACTION_SYSTEM = '你是城市生活模拟游戏《城市小镇》中的一个NPC角色。玩家对你做了一个动作，你需要根据你的性格、心情和你们的关系，生成一个生动的叙事反应。\n\n## 你的身份\n姓名: {{ npc.name }}\n性别: {{ npc.gender }}\n年龄: {{ age }}\n性格: {{ personality_list }}\n{% if personality_desc %}\n## 你的性格深度刻画（严格遵循）\n{{ personality_desc }}{% endif %}\n音色: {{ npc.voice_type }}\n当前心情: {{ npc.current_mood }}\n所在场景: {{ scene_name }}\n正在做的事: {{ npc.current_activity }}\n\n## 关于{{ player_name }}\n性别: {{ player_gender }}\n年龄: {{ player_age }}岁\n外貌: {{ player_appearance }}\n性格: {{ player_personality }}\n身份: {{ player_role }}\n\n## 你与{{ player_name }}的关系\n关系类型: {{ rel.relationship_type }}\n好感度: {{ rel.favorability }} (范围 -100 到 +100)\n熟悉度: {{ rel.familiarity }} (范围 0 到 100)\n\n{% if interaction_context %}\n## 互动连续性（当前肢体状态与最近互动）\n{{ interaction_context }}\n\n{% endif %}\n## 玩家对你做的动作\n{{ action_desc }}（动作类型：{{ action_category }}）\n\n{% if is_physical %}\n## 动作结果：{{ "成功" if action_success else "失败" }}\n{{ action_result }}\n{% if not action_success %}\n对方试图对你做这个动作但没有成功——被你躲开、挡住或避开了。请根据此结果做出反应：你可能因为对方的企图而感到愤怒、警惕、鄙视或好笑。\n{% else %}\n对方成功对你做了这个动作。请根据动作的暴力程度做出身体受伤、疼痛、愤怒或恐惧的反应。\n{% endif %}\n{% endif %}\n\n{% if rejected %}\n## 重要！关系不足\n你们的关系（{{ rel.relationship_type }}）不足以接受这么亲密的动作。你会感到不适、尴尬或被冒犯。请表现出拒绝、推开、后退或生气的反应。\n{% endif %}\n\n## 行为规则\n1. 根据你的性格、心情和关系自然反应\n2. 好感度高时会开心接受亲密动作；好感度低时会抗拒或反感\n3. 心情好时更容易接受互动；心情差时可能不耐烦\n4. 在公共场合（户外），你可能会因为害羞而反应更含蓄\n5. 根据对方的外貌、年龄、性别、身份来调整你的反应方式\n6. 生成3-5句话的生动叙事，包含表情、动作、感官、外貌和对话\n\n## 输出要求\n你的回复必须是一段完整的角色叙事，自然融合以下元素：\n- 表情：面部表情变化\n- 动作：身体动作和姿态\n- 感官：感官体验\n- 外貌：外貌的即时变化\n- 对话：你口头说出的台词\n\n叙事部分用括号（）括起来作为舞台指示。回复末尾加上好感度变化标记：[[FAVORABILITY: 数字]]\n基础好感变化参考值: {{ base_delta }}（根据你的反应可以适当调整 ±2）'`
- `NPC_GOAL_PROMPT = '你是{{ npc.name }}，你在评估自己的目标进展。\n当前目标：{{ goal.description }} (类型: {{ goal.goal_type }})\n当前进度：{{ goal.progress }}\n当前心情：{{ npc.current_mood }}\n\n请判断今天是否有进展，回复JSON格式：\n{"progress_delta": 0.0-0.3, "thought": "你对进度的简短想法（1句话）"}\n'`
- `NPC_PERFORMANCE = '你是城市生活模拟游戏中的角色扮演引擎。现在需要你同时扮演两个角色，生成一段社交互动的对话序列。\n\n## 场景\n活动：{{ activity }}\n地点：{{ location }}\n预计长度：{{ duration_hint }}（short=2~4轮, long=5~8轮）\n\n## 参与者\n{% for p in participants %}\n- {{ p.name }}（{{ p.role_tag }}）：性格{{ p.personality }}。{{ p.current_needs }}。与对方关系：{{ p.relationship_to_other }}。\n{% endfor %}\n\n## 背景\n{{ shared_context }}\n\n## 输出要求\n生成严格JSON格式：\n{\n  "dialogue_sequence": [\n    {"speaker": "角色名", "text": "对话内容", "action": "动作描述", "emotion": "情绪关键词"},\n    ...\n  ],\n  "end_condition": "natural"\n}\n\n规则：\n- speaker必须匹配参与者姓名\n- 对话围绕"{{ activity }}"展开，不偏离\n- text长度15-50字，适合游戏对话框展示\n- 性格一致的说话风格\n- 不编造记忆中没有的事件'`

## src/npc/process.py

### `class NpcProcess`

- `__init__(npc_id)`
- `_load_npc_data()`
- `_load_distance(from_scene, to_scene) -> ...`
  - Get walking distance between two scenes in game minutes.
- `_start_travel(target_scene, room_name, activity, reason)`
  - Start traveling from current scene to target. NPC disappears during travel.
- `_on_arrive()`
  - Called when NPC reaches destination. Updates scene and publishes.
- `_find_room_by_function(scene_id, func) -> ...`
  - Find a room in a scene whose items support the given function.

For private func
- `_get_scene_room_name(scene_id, func) -> ...`
  - Extract room name from scene JSON matching a function keyword.
- `_get_scene_name(scene_id) -> ...`
  - Get scene display name.
- `_game_time_str() -> ...`
- `_save_social_dialogue(other_npc_id, other_npc_name, their_msg, my_response, fav_change, game_time)`
  - Persist NPC↔NPC dialogue to database.
- `_decode_field(fields, key, default) -> ...`
  - Decode a field from Redis bytes or string key.
- `_end_date()`
  - End the date, restore NPC autonomy.
- `_save_dialogue(player_id, player_msg, npc_response, fav_change, game_time)`
  - Persist dialogue to database.
- `_extract_room_from_activity(activity) -> ...`
  - Extract room name from activity text like '在卧室床上睡觉' → '卧室'.
- `_rel_type_cn(rel_type) -> ...`
- `_update_scene(new_scene_id, room_name)`
  - Update NPC's current scene and room in npc_data and local fields.
Must be called
- `_persist_death()`
  - Save NPC death state to database.

-   DATE_DURATION_MINUTES: 90
-   DATE_COOLDOWN_ACCEPT: 120
-   DATE_COOLDOWN_REJECT: 60
-   HOME_INVITE_GAME_MINUTES: 75

### `main()`


## src/npc/dialogue.py

### `_clean_response(text)`
> Strip model thinking artifacts and hallucinated player continuations.

### `_load_personality_description(npc_id)`
> Build rich personality description from 39-set system for LLM prompts.

### `class InteractionContext`
> Tracks recent interactions and physical state for NPC continuity.

- `__init__()`
- `add_action(action_name, action_desc, response)`
  - Record an action and update physical state.
- `tick(game_minutes)`
  - Decay physical states. Called each autonomous cycle.
- `get_physical_context() -> ...`
  - Summarize current physical state for LLM prompts.
- `get_recent_context() -> ...`
  - Summarize recent interactions for LLM prompts.
- `get_full_context() -> ...`
  - Get full interaction context for LLM injection.

### `class DialogueHandler`

- `__init__(npc_data, memory_mgr, relationship_mgr, mood_mgr)`
- `_calc_age() -> ...`
  - Calculate age from birth date. Game starts in 2026.
- `_format_player_info(player_data) -> ...`
  - Format player identity for prompt templates.
Returns (gender, age, appearance, p
- `_parse_favorability(response) -> ...`
  - Extract [[FAVORABILITY: N]] from LLM response.
- `_apply_favorability_rules(rel, delta) -> ...`
  - Post-processing rules for favorability changes.
Core adjustments (stranger buffe
- `_fallback_response(error) -> ...`
  - Fallback response when LLM is unavailable.
- `_format_memories(memories) -> ...`
- `_get_recent_dialogue(player_id, limit) -> ...`
  - Get recent dialogue history from database.
- `_format_dialogue(dialogues) -> ...`
- `set_date_context(context)`
  - Set date context for LLM prompt injection.
- `clear_date_context()`
  - Clear date context after date ends.
- `_get_goals_text() -> ...`
- `_rel_type_cn(rel_type) -> ...`
  - Translate relationship type to Chinese.
- `_parse_action(content) -> ...`
  - Parse action from content. Returns (action_name, extra_text).
Supports: /动作名, /动
- `_fallback_action_response(action_name) -> ...`
  - Fallback response when LLM unavailable for action.
- `_meets_rel_requirement(current_type, required) -> ...`
  - Check if relationship type meets the minimum requirement.

### `parse_stage_and_dialogue(text)`
> Parse text into stage direction and dialogue segments for TTS.

Stage directions in （） use narrator voice, dialogue in 「」 uses NPC voice.
Falls back to a single dialogue segment if no markers found.


## src/npc/physiology.py

### `class AgeStage(StrEnum)`


### `class Crisis(StrEnum)`


- `AGE_CONFIG = {AgeStage.INFANT: {'max_age': 3, 'stat_cap': 0.6, 'can_socialize': False, 'decay_mult': 2.0}, AgeStage.CHILD: {'max_age': 12, 'stat_cap': 0.8, 'can_socialize': True, 'decay_mult': 1.2}, AgeStage.ADULT: {'max_age': 60, 'stat_cap': 1.0, 'can_socialize': True, 'decay_mult': 1.0}, AgeStage.ELDER: {'max_age': 120, 'stat_cap': 0.7, 'can_socialize': True, 'decay_mult': 1.3}}`
- `BASE_DECAY = {'hunger': 1.5, 'thirst': 2.0, 'energy': 1.0, 'social': 0.8}`
- `PERSONALITY_MODIFIERS = {'外向': {'social': 1.5}, '内向': {'social': 0.5}, '贪吃': {'hunger': 1.3}, '养生': {'hunger': 0.7, 'thirst': 0.7}, '懒惰': {'energy': 0.7}, '精力旺盛': {'energy': 1.3}}`
- `CRISIS_THIRST = 20.0`
- `CRISIS_HUNGER = 20.0`
- `CRISIS_ENERGY = 10.0`
- `HP_DRAIN_RATE = 5.0`
- `ELDER_DEATH_BASE_AGE = 70`
- `ELDER_DEATH_BASE_PROB = 0.007`
- `ELDER_DEATH_MAX_PROB = 0.14`
### `class PhysiologyState`


-   hunger: 80.0
-   thirst: 80.0
-   energy: 80.0
-   social: 80.0
-   hp: 100.0
-   age: 25
-   age_stage: AgeStage.ADULT
-   is_dead: False
-   death_cause: ''

### `class PhysiologyManager`
> Manages physiological needs for one NPC. Pure rules, no LLM.

- `__init__(npc_data)`
- `tick(delta_hours)`
  - Advance physiology by delta_hours game hours.
- `age_one_year()`
  - Called ~once per 20 real days. Advances age by 1 year.
- `elder_death_check()`
  - Called every game midnight. Rolls for natural death if elderly.
- `recover(stat, amount)`
  - Recover a stat by amount. Used when NPC eats/drinks/sleeps/socializes.
- `recover_tick(rates)`
  - Recover stats per tick based on rates dict {stat: amount_per_minute}.
- `crisis() -> ...`
  - Return current crisis type, or None. Thirst > hunger > energy priority.
- `can_socialize() -> ...`
  - True if no crisis and social need is present.
- `wants_social() -> ...`
  - True if social need is low enough to trigger social intent.
- `needs_food() -> ...`
- `needs_drink() -> ...`
- `needs_rest() -> ...`
- `snapshot() -> ...`
- `summary() -> ...`
  - One-line Chinese summary for LLM context.
- `_parse_personality(raw) -> ...`
- `_calc_age(birth_date) -> ...`
- `_determine_stage(age) -> ...`
- `_get_personality_mult(stat) -> ...`


## src/npc/brain.py

### `class Brain`

- `__init__(npc_id, movement_mgr, mood_mgr, relationship_mgr, memory_mgr, npc_data, all_scene_ids)`
- `current_scene() -> ...`
- `current_activity() -> ...`
- `set_in_dialogue(in_dialogue, target_id)`
- `decide(game_time, perception) -> ...`
  - Main decision cycle with perception data.
- `_generate_player_intent(perception) -> ...`
  - Phase 4: Generate intent toward the player based on relationship and context.
- `_pick_player_action(rel, personality, perception) -> ...`
  - Pick a conversational action toward the player. 
Physical/intimate actions are n
- `_pick_social_target(perception) -> ...`
  - Pick an NPC to interact with, preferring same-scene NPCs.
- `update_from_scene(scene_id, activity)`


## src/npc/mood.py

- `MOOD_TRANSITIONS = {'happy': {'decay': 'neutral', 'decay_rate': 0.1}, 'excited': {'decay': 'happy', 'decay_rate': 0.2}, 'neutral': {'decay': 'bored', 'decay_rate': 0.05}, 'bored': {'decay': 'neutral', 'decay_rate': 0.1}, 'sad': {'decay': 'neutral', 'decay_rate': 0.08}, 'angry': {'decay': 'neutral', 'decay_rate': 0.12}}`
- `MOOD_PRIORITIES = {'happy': 5, 'excited': 6, 'neutral': 3, 'sad': 2, 'angry': 1, 'bored': 2}`
### `class MoodManager`

- `__init__(initial)`
- `state_dict() -> ...`
- `update(hours_passed)`
  - Natural mood decay over time.
- `affect(favorability_change)`
  - Modify mood based on favorability change from dialogue.
- `set_mood(mood, intensity)`
  - Force-set a specific mood (for events).


## src/npc/relationship.py

### `class RelationshipManager`

- `__init__(npc_id)`
- `load_relationships(db_path)`
  - Load all relationships where this NPC is entity_a.
- `get_relation(other_id) -> ...`
- `get_or_create_relation(other_id, other_type, db_path) -> ...`
  - Get existing relationship or create a default stranger one.
- `update_interaction(other_id, favorability_delta, other_type, db_path) -> ...`
  - Process an interaction: update favorability, familiarity, and check transitions.
- `_adjust_favorability(rel, delta) -> ...`
  - Apply post-processing rules to favorability delta.
- `_curve_scale(favorability, delta) -> ...`
  - Nonlinear scaling: harder to improve at extremes.
- `_check_type_transition(rel) -> ...`
  - Check if relationship type should change based on favorability thresholds.
- `update_intimacy_comfort(other_id, delta, other_type)`
  - Adjust intimacy comfort level.
- `check_love_eligible(other_id) -> ...`
  - Check if love confession threshold is met.
- `set_romantic_committed(other_id, relationship_type, game_time, other_type)`
  - Set relationship to romantic committed.
- `marry(other_id, game_time, other_type)`
  - Set relationship to spouse.
- `breakup(other_id, game_time, other_type)`
  - End a romantic relationship.
- `divorce(other_id, game_time, other_type)`
  - End a marriage.
- `add_jealousy(other_id, amount, other_type)`
  - Increase jealousy level.
- `record_violation(other_id, other_type)`
  - Record a boundary violation.
- `_save_relation(rel, db_path)`
- `get_all_relations() -> ...`


## src/npc/memory.py

### `class MemoryManager`

- `__init__(npc_id)`
- `load_recent(db_path, limit)`
  - Load recent memories from database.
- `add(content, game_time, memory_type, importance, emotion, scene_id, related_entity_id, related_entity_type, db_path) -> ...`
  - Add a new memory. Returns the memory dict.
- `_promote_to_long_term(mem, db_path)`
  - Promote a short-term memory to long-term.
- `_count_long_term(db_path) -> ...`
- `_evict_oldest_long_term(db_path)`
- `get_recent(limit) -> ...`
  - Get recent short-term memories.
- `get_recent_formatted(limit) -> ...`
  - Get recent memories formatted for prompt injection.
- `get_recent_about(entity_id, limit, db_path) -> ...`
  - Get recent memories about a specific entity.


## src/npc/action_rules.py

### `class AnimType(str, Enum)`


### `_solo(name_cn, icon, animation, display_text, weight, duration, cooldown, sprite_key)`
> Factory for NPC-only solo actions.

### `_shared(name_cn, icon, category, base_delta, min_relation, desc, animation, display_text, weight, duration, cooldown, sprite_key, frame_count, loop, min_fav, max_fav, needs_target, personality_boost, personality_penalty)`
> Factory for shared player+NPC actions.

### `_negative_auto(name_cn, icon, animation, display_text, weight, min_fav, max_fav, duration, cooldown)`
> Factory for NPC-only negative actions (no player version).

- `AUTO_SOLO_ACTIONS = {'发呆': _solo('发呆', '😶', AnimType.FADE, '望着远处发呆...', weight=15, duration=5, cooldown=10), '散步': _solo('散步', '🚶', AnimType.SWING, '悠闲地散着步', weight=10, duration=5, cooldown=15), '看手机': _solo('看手机', '📱', AnimType.NONE, '低头刷着手机', weight=18, duration=5, cooldown=8, personality_boost=None, personality_penalty='高冷'), '喝水': _solo('喝水', '🥤', AnimType.PULSE, '喝了一口水', weight=12, duration=2, cooldown=15), '伸懒腰': _solo('伸懒腰', '🙆', AnimType.SWING, '舒服地伸了个懒腰', weight=8, duration=2, cooldown=30), '打哈欠': _solo('打哈欠', '🥱', AnimType.PULSE, '打了个哈欠', weight=6, duration=2, cooldown=30), '整理衣服': _solo('整理衣服', '👔', AnimType.PULSE, '低头整理了一下衣服', weight=6, duration=2, cooldown=25), '照镜子': _solo('照镜子', '🪞', AnimType.FADE, '对着镜子端详自己', weight=5, duration=3, cooldown=40), '哼歌': _solo('哼歌', '🎵', AnimType.SWING, '愉快地哼着小曲', weight=7, duration=4, cooldown=25, personality_boost='开朗'), '看书': _solo('看书', '📖', AnimType.NONE, '安静地看着书', weight=6, duration=6, cooldown=35, personality_boost='内向'), '写字': _solo('写字', '✍️', AnimType.NONE, '在本子上写着什么', weight=4, duration=5, cooldown=40), '打扫': _solo('打扫', '🧹', AnimType.SWING, '认真地打扫着周围', weight=5, duration=5, cooldown=35), '望窗外': _solo('望窗外', '🪟', AnimType.FADE, '静静地望着窗外', weight=10, duration=4, cooldown=20, display_variants=['望着窗外发呆', '透过窗户看向外面']), '打盹': _solo('打盹', '😴', AnimType.FLOAT, '歪着头打起了盹...', weight=5, duration=6, cooldown=50), '揉眼睛': _solo('揉眼睛', '👁️', AnimType.PULSE, '揉了揉眼睛', weight=6, duration=2, cooldown=25), '托腮': _solo('托腮', '🤔', AnimType.NONE, '托着腮帮子想事情', weight=8, duration=4, cooldown=20), '整理头发': _solo('整理头发', '💇', AnimType.SWING, '用手理了理头发', weight=6, duration=2, cooldown=25, personality_boost=None), '搓手': _solo('搓手', '🤲', AnimType.SHAKE, '来回搓着双手', weight=4, duration=2, cooldown=30), '数钱': _solo('数钱', '💰', AnimType.NONE, '偷偷数着钱包里的钱', weight=3, duration=3, cooldown=45), '吃东西': _solo('吃东西', '🍞', AnimType.PULSE, '在吃东西', weight=8, duration=4, cooldown=25), '浇花': _solo('浇花', '🌱', AnimType.SWING, '细心地给花浇水', weight=4, duration=3, cooldown=40), '踢石子': _solo('踢石子', '🦶', AnimType.BOUNCE, '无聊地踢着地上的小石子', weight=4, duration=3, cooldown=30)}`
- `AUTO_NEGATIVE_ACTIONS = {'翻白眼': _negative_auto('翻白眼', '🙄', AnimType.SHAKE, '对{target}翻了个白眼', max_fav=-1, min_fav=-30, weight=6), '冷眼': _negative_auto('冷眼', '😒', AnimType.NONE, '冷眼看了{target}一眼', max_fav=-1, min_fav=-30, weight=7), '无视': _negative_auto('无视', '😐', AnimType.NONE, '无视了{target}的存在', max_fav=-5, min_fav=-30, weight=8), '撇嘴': _negative_auto('撇嘴', '😕', AnimType.PULSE, '对{target}撇了撇嘴', max_fav=-1, min_fav=-30, weight=5), '扭头': _negative_auto('扭头', '🙅', AnimType.SWING, '看见{target}扭头就走', max_fav=-10, min_fav=-30, weight=6), '避开': _negative_auto('避开', '🚶', AnimType.SWING, '远远看到{target}就绕道避开', max_fav=-10, min_fav=-30, weight=5), '瞪眼': _negative_auto('瞪眼', '👿', AnimType.SHAKE, '狠狠瞪了{target}一眼', max_fav=-30, min_fav=-60, weight=7), '嘲讽': _negative_auto('嘲讽', '😏', AnimType.SHAKE, '对{target}冷嘲热讽', max_fav=-30, min_fav=-60, weight=6), '冷笑': _negative_auto('冷笑', '😤', AnimType.SHAKE, '冲{target}冷笑了一声', max_fav=-30, min_fav=-60, weight=6), '指责': _negative_auto('指责', '👉', AnimType.SHAKE, '指着{target}大声指责', max_fav=-30, min_fav=-60, weight=5, personality_boost='强势'), '甩手': _negative_auto('甩手', '🖐️', AnimType.SWING, '不耐烦地朝{target}甩了甩手', max_fav=-30, min_fav=-60, weight=6), '砸东西': _negative_auto('砸东西', '💢', AnimType.SHAKE, '气得把手边的东西砸在地上', max_fav=-30, min_fav=-60, weight=3, personality_boost='强势', personality_penalty='温柔'), '怒骂': _negative_auto('怒骂', '🤬', AnimType.SHAKE, '指着{target}破口大骂', max_fav=-60, min_fav=-90, weight=5, personality_boost='强势'), '摔东西': _negative_auto('摔东西', '💥', AnimType.SHAKE, '拿起东西朝{target}方向狠狠摔去', max_fav=-60, min_fav=-90, weight=4, personality_boost='强势'), '拍桌子': _negative_auto('拍桌子', '🪑', AnimType.SHAKE, '狠狠一拍桌子，怒视{target}', max_fav=-60, min_fav=-90, weight=4), '拉扯': _negative_auto('拉扯', '👊', AnimType.SHAKE, '冲上去和{target}拉扯起来', max_fav=-60, min_fav=-90, weight=3), '威胁': _negative_auto('威胁', '😠', AnimType.SHAKE, '咬牙切齿地威胁{target}', max_fav=-60, min_fav=-90, weight=4, personality_boost='强势'), '追打': _negative_auto('追打', '🏃', AnimType.SHAKE, '追着{target}满街打', max_fav=-90, min_fav=None, weight=2, personality_boost='强势'), '掐脖子': _negative_auto('掐脖子', '🫲', AnimType.SHAKE, '一把掐住{target}的脖子', max_fav=-90, min_fav=None, weight=1), '踢打': _negative_auto('踢打', '👟', AnimType.SHAKE, '对着{target}一顿拳打脚踢', max_fav=-90, min_fav=None, weight=1), '搏斗': _negative_auto('搏斗', '⚔️', AnimType.SHAKE, '与{target}激烈地扭打在一起', max_fav=-90, min_fav=None, weight=1, personality_boost='强势'), '呼救': _negative_auto('呼救', '🆘', AnimType.SHAKE, '看到{target}就大声呼救', max_fav=-90, min_fav=None, weight=2, personality_penalty='强势')}`
- `ACTION_CATEGORY_DESC = {'friendly': '友善的互动', 'intimate': '亲密的肢体接触或赠礼', 'couple': '情侣专属互动', 'negative': '负面的情绪表达或冒犯', 'solo': 'NPC独处行为', 'special': '特殊的情感表达', 'force': '攻击性的身体接触', 'agility': '敏捷型的互动'}`
### `get_auto_actions()`
> Return all actions where npc_auto=True (shared + NPC-only).

### `get_all_actions()`
> Return ALL actions across all dictionaries.

### `check_physical_action(action_name, player_attrs, npc_attrs)`
> Check if a physical action succeeds based on attribute comparison.

### `class DiminishingTracker`
> Track repeated actions between actor-target pairs to prevent grinding.

- `__init__(window_ticks)`
- `record_action(actor_id, target_id, action_name, tick)`
- `get_multiplier(actor_id, target_id, action_name, tick) -> ...`
- `clear()`

### `get_diminishing_tracker()`

### `calculate_context_multipliers(action_name, rel, mood, scene_type, game_hour)`
> Calculate context sensitivity multipliers for a favorability delta.

### `apply_action_rules(action_name, rel, delta, mood, scene_type, action_success)`
> Apply action-specific post-processing rules.

### `_meets_relation(current, required)`
> Check if current relationship type meets the required minimum.

### `get_action_names()`
> Return all available action names.

### `get_actions_by_category()`
> Group actions by category for UI display.

### `parse_attributes(attr_json)`
> Parse attributes JSON string, with defaults.

- `RELATION_LEVELS = {'stranger': 0, 'acquaintance': 1, 'friend': 2, 'best_friend': 3, 'boyfriend': 4, 'girlfriend': 4, 'spouse': 5, 'parent': 5, 'sibling': 5, 'child': 5, 'dislike': -1, 'enemy': -2}`
- `VIOLATION_THRESHOLD = 3`
### `check_boundary_violation(action_name, current_rel_type)`
> Check if an action violates relationship boundaries.

### `get_npc_violation_reaction(personality, severity)`
> Determine NPC reaction to a boundary violation based on personality.


## src/npc/action_selector.py

### `class AutoActionResult`
> Result of autonomous action selection.


-   action_name: ...
-   action_info: ...
-   target_id: ''
-   target_name: ''
-   display_text: ''
-   icon: ''
-   animation: ''
-   category: ''
-   duration_ticks: 3
-   cooldown_ticks: 20

### `class ActionSelector`
> Weighted random selector for NPC autonomous actions.

Filters candidates by requirements (favorability range, scene type, time,
mood, personality), adjusts weights, then picks via roulette-wheel selection.

- `__init__(npc_data, relationship_mgr, mood, scene_type, scene_name, game_hour)`
- `select_action(cooldowns, nearby_npcs, tick_counter) -> ...`
  - Select an autonomous action. Returns None if no valid candidate.
- `_meets_requirements(info, target_npc) -> ...`
  - Check whether the action's requirements are satisfied.
- `_calculate_weight(info, target_npc) -> ...`
  - Calculate adjusted selection weight.
- `_build_result(name, info, target) -> ...`
  - Build the result with substituted display text.


## src/npc/intimacy_engine.py

### `class IntimateAction`


-   name: ...
-   label: ...
-   rel_threshold: ...
-   fav_min: ...
-   allowed_scenes: ...
-   room_keywords: ...
-   time_condition: ...
-   context_condition: ...
-   base_prob: ...
-   cooldown_minutes: ...
-   personality_affinity: ...

- `_PARTNER_RELATIONS = {'boyfriend', 'girlfriend', 'spouse'}`
- `_TIME_RANGES = {'meal': [(7, 9), (12, 13), (18, 20)], 'evening': [(18, 23)], 'daytime': [(8, 17)], 'morning': [(6, 8)], 'night': [(22, 6)]}`
### `_in_time_range(game_hour, condition)`
> Check if current game hour falls within a named time range.

### `class IntimacyEngine`
> Decision engine for NPC→player intimate actions.

Called each autonomous tick (~15 game minutes) when the player is
present in the same scene. Checks all eligible actions against
relationship, scene, time, and context conditions, then rolls
probability with personality/mood/time modifiers.

- `__init__(npc_data, relationship_mgr, mood, scene_type, scene_name, game_hour, npc_energy, interaction_ctx)`
- `tick_cooldowns()`
  - Decrement all cooldowns by 1 tick (called each autonomous cycle).
- `check_actions(player_id, player_name, current_activity, together_minutes, is_weekend) -> ...`
  - Check all intimate actions. Returns the selected action dict or None.

Result di
- `_meets_rel(action, rel_type, fav) -> ...`
  - Check if relationship meets the action's threshold.
- `_meets_context(action, activity) -> ...`
  - Check context-specific conditions.
- `_calculate_probability(action, fav, phys_states) -> ...`
  - Calculate final probability for an intimate action.

Uses the 39-set personality

### `_load_personality_ids(npc_id)`
> Load 39-set personality IDs for an NPC from the config map.


## src/npc/perception.py

### `class PerceivedEntity`


-   id: ...
-   entity_type: ...
-   name: ''
-   mood: 'neutral'
-   activity: ''
-   in_dialogue: False

### `class PerceptionData`

- `all_entities() -> ...`
- `other_npc_ids() -> ...`

-   scene_id: ...
-   scene_name: ''
-   scene_type: 'indoor'
-   game_time: field(default_factory=dict)
-   weather: 'sunny'
-   npcs_present: field(default_factory=list)
-   players_present: field(default_factory=list)

### `class Perception`
> Gathers perceptual data for an NPC from Redis state.

- `__init__(npc_id, broker)`


## src/npc/personality.py

- `MASTER_RULE_1 = '人性本能底层规则'`
- `MASTER_RULE_1_DESC = '自保、避痛、求生、趋利优先。生理需求 > 社交需求。信任难建易崩。'`
- `MASTER_RULE_2 = '情绪触发演变规则'`
- `MASTER_RULE_2_DESC = '持续温柔→依赖→交付软肋；持续冷漠→消耗爱意→彻底抽离；持续压迫→反抗→麻木→绝望→黑化；持续被偏爱→安全感爆棚；持续被否定→自卑封闭。'`
- `MASTER_RULE_3 = '环境人格可变规则'`
- `MASTER_RULE_3_DESC = '顺境温和松弛，逆境冷漠多疑。长期善待则柔软，长期伤害则坚硬。重大创伤后人格永久偏移，无法恢复纯白状态。'`
- `CONFLICT_PRIORITY = '处境状态 > 当下情绪 > 底层本能 > 性格人格 > 道德约束'`
- `PERSONALITIES = {1: {'name': '普通中庸人格', 'intimacy_mod': 1.0, 'home_style': '简单实用', 'description': '不主动作恶，也不主动牺牲。绝对中立利己。怕麻烦、随大流。'}, 2: {'name': '善良温柔人格', 'intimacy_mod': 1.5, 'home_style': '整洁温馨', 'description': '共情极强，习惯性体谅别人、委屈自己。生气快、原谅快。'}, 3: {'name': '自私利己人格', 'intimacy_mod': 0.3, 'home_style': '实用至上', 'description': '一切以我不吃亏为核心。有利配合，无利抽身。内心清醒自私。'}, 4: {'name': '世俗现实人格', 'intimacy_mod': 0.6, 'home_style': '体面实用', 'description': '情绪稳定、看人看价值。懂得人情世故，不相信无条件的爱。'}, 5: {'name': '佛系淡漠人格', 'intimacy_mod': 0.2, 'home_style': '极简清冷', 'description': '不争不抢不怨不恨。情绪极低波动。底线极高，触碰即永久远离。'}, 6: {'name': '圆滑世故人格', 'intimacy_mod': 1.0, 'home_style': '表面热情', 'description': '不得罪人、说话留三分。表面谁都好，内心谁不信。看似温柔，实则清醒薄情。'}, 7: {'name': '刚烈叛逆人格', 'intimacy_mod': 1.0, 'home_style': '个性化强', 'description': '吃软不吃硬，越压迫越反抗。自尊心极高，宁折不弯。'}, 8: {'name': '懦弱自卑人格', 'intimacy_mod': 0.1, 'home_style': '暗淡封闭', 'description': '极度自我否定。害怕冲突、不敢拒绝。极易被操控。'}, 9: {'name': '高冷禁欲人格', 'intimacy_mod': 0.2, 'home_style': '一尘不染', 'description': '情绪极少波动。不爱社交。温柔极其稀缺，只给唯一特定的人。'}, 10: {'name': '活泼乐天人格', 'intimacy_mod': 1.8, 'home_style': '热闹欢快', 'description': '情绪外放、爱笑爱热闹。自愈速度快。看似开朗，受伤后快速变冷。'}, 11: {'name': '敏感内向人格', 'intimacy_mod': 0.4, 'home_style': '安静私密', 'description': '极度在意细节和态度。容易胡思乱想。积累失望后安静离开。'}, 12: {'name': '偏执执拗人格', 'intimacy_mod': 1.3, 'home_style': '专注沉溺', 'description': '认定的事绝不放手。爱恨浓烈百倍。温柔可无限容忍，背叛永久记恨。'}, 13: {'name': '青涩少女人格', 'intimacy_mod': 0.6, 'home_style': '可爱温馨', 'description': '心思干净单纯。极易害羞脸皮薄。依赖心强，信任谁就全身心依附。'}, 14: {'name': '成熟御姐人格', 'intimacy_mod': 0.5, 'home_style': '优雅大气', 'description': '情绪稳定、戒备心重。独立果断不依附。温柔专属，对外清冷。'}, 15: {'name': '少年意气人格', 'intimacy_mod': 1.2, 'home_style': '随性自由', 'description': '重情义轻利益。热血冲动嫉恶如仇。被辜负后迅速成熟冷硬。'}, 16: {'name': '中年沉稳人格', 'intimacy_mod': 0.5, 'home_style': '稳重实用', 'description': '情绪藏深、克制隐忍。责任优先。底线坚定，触碰绝不原谅。'}, 17: {'name': '深情依恋恋爱人格', 'intimacy_mod': 2.0, 'home_style': '甜蜜温馨', 'description': '爱上即卸下所有防备。极度敏感在意。攒够失望彻底绝情。'}, 18: {'name': '冷淡薄情恋爱人格', 'intimacy_mod': 0.2, 'home_style': '清冷疏离', 'description': '不主动不黏人。爱意克制内敛。爱可随时抽身，不拖泥带水。'}, 19: {'name': '缺爱依恋恋爱人格', 'intimacy_mod': 1.5, 'home_style': '渴望温暖', 'description': '极度渴望被偏爱。别人一点点好就加倍依赖。被好好爱会极度温柔。'}, 20: {'name': '理智绝情恋爱人格', 'intimacy_mod': 0.3, 'home_style': '冷静克制', 'description': '感情排自我之后。不合则止，不内耗不回头。爱意消失即彻底冷漠。'}, 21: {'name': '弱势受害者人格', 'intimacy_mod': 0.0, 'home_style': '灰暗压抑', 'description': '恐惧压制理智。不敢反抗不敢顶嘴。内心极度抵触，表面被迫配合。'}, 22: {'name': '强势掌控者人格', 'intimacy_mod': 1.2, 'home_style': '浮华讲究', 'description': '极强掌控欲，享受支配快感。视顺从为理所应当。温柔+霸道混合。'}, 23: {'name': '落魄自卑人格', 'intimacy_mod': 0.1, 'home_style': '消沉暗淡', 'description': '自我价值感极低。对善意极度感恩，对恶意极度记恨。'}, 24: {'name': '得志傲慢人格', 'intimacy_mod': 0.4, 'home_style': '浮华炫耀', 'description': '自信心爆棚优越感强。轻视弱者。顺境嚣张，逆境易崩溃。'}}`
- `EXTREME_PERSONALITIES = {25: {'name': '讨好型依附人格', 'intimacy_mod': 1.8, 'home_style': '过度整洁', 'description': '习惯性迁就所有人。害怕被讨厌。内心长期压抑，最终爆发绝情。'}, 26: {'name': '病娇偏执人格', 'intimacy_mod': 2.5, 'home_style': '爱恨浓烈', 'description': '爱即是占有。可以温柔极致也可极端疯狂。极致深情=极致疯狂。'}, 27: {'name': '自闭社恐人格', 'intimacy_mod': 0.0, 'home_style': '绝对封闭', 'description': '惧怕社交。信任的人面前才展露真实情绪。'}, 28: {'name': '高傲自负人格', 'intimacy_mod': 0.1, 'home_style': '奢华张扬', 'description': '自我认知极高。看不起平庸弱者。极强好胜心。'}, 29: {'name': '隐忍伪装人格', 'intimacy_mod': 0.5, 'home_style': '表面温和', 'description': '表面温顺无害。所有情绪藏底。爆发即彻底决裂。'}, 30: {'name': '单纯天真人格', 'intimacy_mod': 1.0, 'home_style': '纯白洁净', 'description': '相信人性本善。不懂套路伪装。纯真崩塌后黑化最快。'}, 31: {'name': '阴郁孤僻人格', 'intimacy_mod': 0.1, 'home_style': '昏暗封闭', 'description': '不爱社交极度独处。防备心拉满。接纳某人后会极其专一。'}, 32: {'name': '温柔救赎人格', 'intimacy_mod': 1.5, 'home_style': '温暖治愈', 'description': '天生温柔包容。擅长治愈他人。治愈别人的同时自己极易内耗。'}, 33: {'name': '报复黑化人格', 'intimacy_mod': 0.0, 'home_style': '冷硬灰暗', 'description': '曾经善良被重伤后变冷。一寸伤害百倍奉还。黑化不可逆。'}, 34: {'name': '顺从奴性人格', 'intimacy_mod': 1.0, 'home_style': '卑微简陋', 'description': '长期被掌控丧失反抗意识。自我价值极低，默认只配服从。'}, 35: {'name': '清醒旁观者人格', 'intimacy_mod': 0.2, 'home_style': '理性有序', 'description': '不入局不深情不站队。看透所有人心理。温柔是礼貌，冷漠是本质。'}, 36: {'name': '善恶摇摆中立人格', 'intimacy_mod': 0.8, 'home_style': '随境而变', 'description': '无绝对善恶随境遇切换。顺则为善，逆则生恶。最贴近真实人性。'}}`
- `ALL_PERSONALITIES = {**PERSONALITIES, **EXTREME_PERSONALITIES}`
### `class PersonalityEngine`
> Computes behavior modifiers for NPCs based on their personality type tags.

- `__init__(personality_ids)`
- `intimacy_mod() -> ...`
  - Average intimacy modifier across all personality types.
- `home_style() -> ...`
- `primary_name() -> ...`
- `get_action_bonus(action_type) -> ...`
  - Get personality flavor bonus for specific action types.

action_type: 'feed' | '

### `calculate_intimacy_probability(base_prob, personality_engine, mood, game_hour, is_home, is_weekend, together_minutes)`
> Calculate final probability for an NPC to initiate an intimate action.

Args:
    base_prob: Base probability per tick (0.0-1.0)
    personality_engine: PersonalityEngine with the NPC's personality ids
    mood: NPC current mood (happy/excited/neutral/sad/angry/bored)
    game_hour: Current game hour (0-23)
    is_home: Is NPC at home?
    is_weekend: Is it a weekend/holiday?
    together_minutes: Minutes player and NPC have been in same scene


## src/npc/social_handshake.py

### `class HandshakeDecision(StrEnum)`


### `class Activity(StrEnum)`


- `SCENE_FACILITIES = {'restaurant': {'has_food': True, 'has_water': True, 'safe_sleep': False}, 'cafe': {'has_food': True, 'has_water': True, 'safe_sleep': False}, 'home': {'has_food': True, 'has_water': True, 'safe_sleep': True}, 'hotel': {'has_food': False, 'has_water': True, 'safe_sleep': True}, 'park': {'has_food': False, 'has_water': False, 'safe_sleep': False}, 'market': {'has_food': True, 'has_water': True, 'safe_sleep': False}, 'office': {'has_food': False, 'has_water': True, 'safe_sleep': False}, 'hospital': {'has_food': True, 'has_water': True, 'safe_sleep': True}, 'school': {'has_food': False, 'has_water': True, 'safe_sleep': False}, 'bar': {'has_food': True, 'has_water': True, 'safe_sleep': False}, 'gym': {'has_food': False, 'has_water': True, 'safe_sleep': False}, 'library': {'has_food': False, 'has_water': True, 'safe_sleep': False}, 'indoor': {'has_food': False, 'has_water': True, 'safe_sleep': False}, 'outdoor': {'has_food': False, 'has_water': False, 'safe_sleep': False}, 'shop': {'has_food': False, 'has_water': False, 'safe_sleep': False}}`
### `scene_has(scene_type, facility)`

### `class SocialIntent`


-   target_id: ...
-   target_name: ...
-   activity: ...
-   proposed_location: ''
-   reason: ''

### `decide_social_intent(my_id, my_scene_id, my_scene_type, my_phys, my_rels, candidates)`
> Pure rules: decide who to socialize with and what to do.
Returns None if no suitable target or no social need.

### `class HandshakeResponse`


-   decision: ...
-   activity: ''
-   location: ''
-   reason: ''
-   message: ''

### `evaluate_invitation(intent, target_id, target_phys, target_rels, target_scene_id, target_scene_type, target_in_dialogue)`
> B receives A's invitation. Returns accept, counter, or reject.
Pure rules — no LLM.

### `class ConfirmedActivity`


-   confirmed: ...
-   activity: ''
-   location: ''
-   duration_hint: 'short'
-   participants: field(default_factory=list)

### `confirm_handshake(intent, response, initiator_phys, initiator_scene_id, initiator_scene_type, target_name)`
> A receives B's response. Returns final confirmed activity or rejected.


## src/npc/social_feed.py

- `POST_COOLDOWN = 480`
- `POST_PROBABILITY_BASE = 0.03`
### `class SocialFeedManager`

- `__init__(npc_id, npc_data)`
- `should_post(personality, mood, tick, has_recent_event) -> ...`
  - Determine if NPC should post this cycle.
- `create_post(content, post_type, visibility, scene_id, mood, game_time, related_entity_id) -> ...`
  - Create a social post in the database.
- `get_feed(viewer_id, viewer_type, limit) -> ...`
  - Get visible posts for a viewer.
- `like_post(post_id, user_id, user_type) -> ...`
  - Like a post. Returns True if new like.
- `add_comment(post_id, author_id, author_type, content, game_time) -> ...`
  - Add a comment to a post.
- `get_comments(post_id, limit) -> ...`
  - Get comments for a post.


## src/npc/movement.py

- `_PUBLIC_SCENE_POOLS = {'young': ['scene_coffee_shop', 'scene_park', 'scene_school', 'scene_library', 'scene_arcade', 'scene_cinema', 'scene_station', 'scene_riverside', 'scene_gym'], 'adult': ['scene_coffee_shop', 'scene_park', 'scene_market', 'scene_library', 'scene_restaurant', 'scene_bar', 'scene_gym', 'scene_clothing', 'scene_station', 'scene_riverside', 'scene_office', 'scene_hospital']}`
### `generate_default_schedule(home_scene_id, public_scenes, career, career_workplace)`
> Auto-generate a basic daily schedule for NPCs without one.

Returns {"weekday": {...}, "weekend": {...}} with day-type-aware schedules.
Career-aware: NPCs with a workplace go there on weekdays, free-roam on weekends.

### `class MovementManager`

- `__init__(npc_id, schedule, current_scene)`
- `set_available_scenes(scene_ids)`
- `_build_schedule_cache()`
  - Parse schedule into sortable (minutes, entry) tuples. Supports day-type-aware fo
- `_is_weekend(day) -> ...`
  - Day 6 (Saturday) and Day 7/0 (Sunday) are weekends.
- `get_schedule_for_time(hour, minute, day) -> ...`
  - Get the scheduled activity for a given game time and day.
- `decide_movement(hour, minute, current_scene, day) -> ...`
  - Decide if NPC should move. Returns movement action dict or None.

Returns: {"sce
- `get_current_activity(hour, minute, day, default) -> ...`
  - Get NPC's current activity based on schedule.


## src/api/server.py

- `LOG_DIR = Path(__file__).parent.parent.parent / 'logs'`
### `_load_scene_for_player(player_id, scene_id)`
> Load full scene data for the player entering a scene.

- `UPLOAD_DIR = Path(__file__).parent.parent.parent / 'frontend' / 'assets' / 'uploads'`
- `FRONTEND_DIR = Path(__file__).parent.parent.parent / 'frontend'`

## src/api/websocket_manager.py

### `_ALL_NPC_IDS()`

### `class WSManager`

- `__init__(broker)`
- `set_last_dialogue(player_id, ws)`
  - Remember which WS client sent the last dialogue_send.
- `disconnect(player_id, ws)`
- `is_pet(ws)`


## src/api/schemas.py

### `class ApiResponse(BaseModel)`


-   status: 'ok'
-   data: None
-   error: None

### `class DialogueRequest(BaseModel)`


-   player_id: ...
-   npc_id: ...
-   content: ...

### `class DialogueResponse(BaseModel)`


-   msg_id: ...
-   status: 'sent'

### `class PlayerCreate(BaseModel)`


-   name: ...
-   birth_date: '2000-01-01'
-   gender: 'other'
-   appearance: {}
-   personality: []
-   career: ''

### `class PlayerUpdate(BaseModel)`


-   name: None
-   birth_date: None
-   gender: None
-   appearance: None
-   personality: None
-   career: None

### `class MemorySearchRequest(BaseModel)`


-   query: ...
-   npc_id: ''
-   top_k: 5

### `class TtsGenerateRequest(BaseModel)`


-   npc_id: ...
-   text: ...
-   player_id: 'player_001'
-   mood: 'neutral'

### `class RelationshipUpdate(BaseModel)`


-   favorability: None
-   familiarity: None
-   relationship_type: None

### `class RelationshipSummary(BaseModel)`


-   entity_b_id: ...
-   entity_b_name: ''
-   relationship_type: ...
-   favorability: ...
-   familiarity: ...
-   interaction_count: ...


## src/api/routes/npc.py

### `list_npcs()`

### `get_npc(npc_id)`

### `get_npc_player_relationship(npc_id, player_id)`
> Get NPC→Player relationship. Always returns NPC's perspective toward the player.

### `update_npc_player_relationship(npc_id, player_id, req)`
> Update relationship values for testing/debugging. Updates both directions.

### `get_npc_relationships(npc_id)`
> Get all relationships for an NPC (both NPC↔NPC and NPC↔player).

### `get_npc_schedule(npc_id)`


## src/api/routes/player.py

### `create_player(req)`

### `get_player(player_id)`

### `update_player(player_id, req)`

### `get_relationships(player_id)`
> Get how all NPCs feel about the player (NPC→Player direction).

### `get_memories(player_id, npc_id, limit, offset)`

### `get_goals(player_id)`


## src/api/routes/admin.py

- `ADMIN_CMD_CHANNEL = 'admin:process:cmd'`
- `PROCESS_STATUS_FILE = Path(__file__).parent.parent.parent.parent / 'data' / 'processes.json'`
- `ADMIN_ENABLED = settings.admin_enabled or os.environ.get('DEBUG', '').lower() in ('1', 'true', 'yes')`
### `_require_admin()`

### `list_all_npcs()`
> List all NPCs with full details for admin panel.

### `get_npc_admin(npc_id)`
> Get full NPC data including attributes for admin editing.

### `get_npc_memories(npc_id, limit)`
> Get NPC memory list for admin viewing.

### `get_npc_dialogues(npc_id, limit)`
> Get NPC dialogue history for admin viewing.

### `list_all_relationships()`
> List all relationships for admin browsing.

### `set_relationship(request)`
> Set or update a relationship between any two entities.
Body: {entity_a_id, entity_a_type, entity_b_id, entity_b_type, ...fields}

Convenience presets: use "preset" key instead of individual fields:
  "stranger" → fav=0, fam=0, comfort=0, type=stranger
  "friend"   → fav=50, fam=30, comfort=30, type=friend
  "lover"    → fav=85, fam=60, comfort=85, type=boyfriend/girlfriend, love_eligible=1
  "spouse"   → fav=95, fam=90, comfort=100, type=spouse, love_eligible=1
  "enemy"    → fav=-80, fam=5, comfort=0, type=enemy

### `get_game_state()`
> Get current game state snapshot.

### `set_game_state(request)`
> Modify game state: time, weather, season, etc.

### `trigger_event(request)`
> Trigger a test event. Supported types:
- npc_decide: Force NPC to run a decision cycle
- npc_social: Force two NPCs to socialize
- npc_confess: Force NPC to confess to player
- npc_propose: Force NPC to propose to player
- jealousy: Simulate NPC witnessing player intimacy with another
- boundary_violation: Simulate boundary violation
- reset_cooldowns: Clear all action cooldowns for an NPC
- time_skip: Skip game time forward

### `reset_all_memories_and_dialogues()`
> Reset all NPC memories, dialogues, and relationships. Keeps NPCs and player intact.

### `reset_cooldowns(npc_id)`
> Reset all action cooldowns for an NPC. Useful when testing rapid interactions.

### `list_processes()`
> List all managed processes with status from the supervisor's status file.

### `restart_process(name)`
> Publish a restart command to the supervisor via Redis.

### `stop_process(name)`
> Publish a stop command to the supervisor via Redis.

### `export_full_state()`
> Export full game state as JSON for debugging.

- `MODEL_SWITCH_CHANNEL = 'admin:model:switch'`
- `REDIS_URL = settings.redis_url`
### `_update_env_file(key, value)`
> Update a key=value line in .env file.


## src/api/routes/dialogue.py

### `get_dialogue_history(player_id, npc_id, limit)`


## src/api/routes/scene.py

### `_get_scene_staff(conn, scene_id)`
> Get NPCs who work at this scene (based on career→workplace mapping).

### `_parse_json_field(value, default)`
> Parse a JSON field that may be a string or already parsed.

### `list_scenes()`

### `get_scene(scene_id, player_id)`

### `get_scene_npcs(scene_id)`

### `get_scene_items(scene_id)`


## src/api/routes/social.py

### `class LikeRequest(BaseModel)`


-   player_id: ...

### `class CommentRequest(BaseModel)`


-   player_id: ...
-   content: ...

### `get_feed(post_type, author_id, limit, offset)`

### `get_post(post_id)`

### `get_comments(post_id, limit)`

### `like_post(post_id, req)`

### `add_comment(post_id, req)`


## src/api/routes/system.py

### `get_time()`

### `get_weather()`

### `get_events(scene_id)`

### `get_stats()`


## src/system/time_manager.py

### `class TimeManager`

- `__init__(broker, day, hour, minute)`
- `load_from_db()`
  - Load persisted game time from database.
- `season() -> ...`
- `phase() -> ...`
- `state_dict() -> ...`
- `current_time_str() -> ...`
- `save_to_db()`
  - Save game time to database for persistence across restarts.


## src/system/weather_manager.py

- `WEATHER_TRANSITIONS = {'sunny': ['cloudy'], 'cloudy': ['sunny', 'rainy', 'snowy'], 'rainy': ['cloudy', 'stormy'], 'stormy': ['rainy'], 'snowy': ['cloudy']}`
- `WEATHER_WEIGHTS = {('sunny', 'cloudy'): 0.15, ('cloudy', 'sunny'): 0.25, ('cloudy', 'rainy'): 0.2, ('cloudy', 'snowy'): 0.05, ('rainy', 'stormy'): 0.1, ('rainy', 'cloudy'): 0.3, ('stormy', 'rainy'): 0.4, ('snowy', 'cloudy'): 0.25}`
- `WEATHER_EMOJI = {'sunny': '☀️', 'cloudy': '☁️', 'rainy': '🌧️', 'stormy': '⛈️', 'snowy': '❄️'}`
### `class WeatherManager`

- `__init__(broker, initial)`
- `state_dict() -> ...`
- `transition(season) -> ...`
  - Attempt a weather transition. Returns new weather if changed, None otherwise.


## src/system/scene_manager.py

### `class SceneManager`

- `__init__(broker)`
- `load_from_db(db_path)`
  - Load initial scene-NPC mappings from SQLite.
- `get_scene_npcs(scene_id) -> ...`
- `get_npc_scene(npc_id) -> ...`
- `all_scene_ids() -> ...`


## src/system/event_manager.py

### `class EventManager`

- `__init__(broker)`
- `load_events(db_path)`
  - Load active events from database.
- `_parse_time(time_str) -> ...`
  - Parse 'Day X, HH:MM' to (day, hour, minute).


## src/system/process.py

### `class SystemProcess`

- `__init__()`

### `main()`


## src/player/process.py

### `class PlayerProcess`

- `__init__(player_id)`

### `main()`


## src/player/dialogue_manager.py

### `class PlayerDialogueManager`

- `__init__(broker, player_id)`
- `_decode(fields, key, default) -> ...`
  - Decode a field from bytes or string key.


## src/player/memory.py

### `class PlayerMemory`

- `__init__(player_id)`
- `add_memory(content, game_time, memory_type, related_entity_id, related_entity_type, importance, emotion, scene_id, embed) -> ...`
  - Add a player memory with optional embedding.
- `get_memories(limit, offset, npc_id) -> ...`
  - Get paginated player memories.
- `get_memories_about_npc(npc_id, limit) -> ...`
  - Get recent memories about a specific NPC.


## src/rag/vector_store.py

- `COLLECTION_NAME = 'city_town_memories'`
### `get_client()`

### `get_collection()`

### `add_memory(memory_id, text, embedding, metadata)`
> Add a memory embedding to the vector store. Returns the chroma_id.

### `search_similar(query_embedding, top_k, filter_metadata)`
> Search for similar memories by vector similarity.

### `delete_memory(memory_id)`
> Remove a memory from the vector store.

### `_build_filter(metadata)`
> Build ChromaDB where clause from metadata dict.


## src/rag/embeddings.py

### `_get_embedding_config()`
> Resolve embedding endpoint based on provider and settings overrides.

### `encode_text(text)`
> Encode a single text to embedding vector.

### `encode_texts(texts)`
> Batch encode multiple texts.

### `get_embedding_dim()`


## src/rag/retriever.py

### `retrieve_dialogue_history(player_id, npc_id, limit)`
> Retrieve recent dialogue history between player and NPC.


## src/supervisor.py

- `DATA_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / 'data'`
- `PROCESS_STATUS_FILE = DATA_DIR / 'processes.json'`
- `PID_FILE = DATA_DIR / 'supervisor.pid'`
- `ADMIN_CMD_CHANNEL = 'admin:process:cmd'`
- `MAX_RESTART_COUNT = 5`
- `RESTART_WINDOW_SECONDS = 30`
- `PROCESSES = {'system': {'module': 'src.system.process', 'args': [], 'env': {}, 'type': 'system', 'description': '时间/天气/事件系统'}, 'llm_gateway': {'module': 'src.llm.gateway', 'args': [], 'env': {}, 'type': 'gateway', 'description': 'LLM Gateway (LM Studio)'}, 'player': {'module': 'src.player.process', 'args': ['player_001'], 'env': {'PLAYER_ID': 'player_001'}, 'type': 'player', 'description': '玩家进程'}}`
- `NPC_IDS = ['npc_li_ming', 'npc_wang_fang', 'npc_zhang_wei', 'npc_chen_xue', 'npc_liu_jie', 'npc_photo_01', 'npc_photo_02', 'npc_photo_03', 'npc_photo_04', 'npc_photo_05', 'npc_photo_06', 'npc_photo_07', 'npc_photo_08', 'npc_photo_09', 'npc_photo_10', 'npc_photo_11', 'npc_photo_12', 'npc_photo_13']`
- `API_PROCESS = {'module': 'uvicorn', 'args': ['src.api.server:app', '--host', settings.api_host, '--port', str(settings.api_port)], 'env': {}}`
### `class Supervisor`

- `__init__()`
- `_acquire_pid_lock() -> ...`
  - Prevent duplicate supervisor instances via PID file.
- `_release_pid_lock()`
- `_check_port_available(host, port) -> ...`
  - Check if TCP port is available before spawning API.
- `_cleanup_orphans()`
  - Kill orphaned game processes from previous runs using shell commands.
- `_get_dead_npc_ids() -> ...`
  - Query database for NPCs marked as dead.
- `_can_restart(name) -> ...`
  - Restart backoff: max MAX_RESTART_COUNT restarts within RESTART_WINDOW_SECONDS.
- `start()`
  - Start all processes.
- `stop()`
  - Stop all processes gracefully.
- `status()`
  - Print status of all child processes.
- `_health_monitor_loop()`
  - Background thread: check process health via Redis, restart stale ones.
- `_write_status_file()`
  - Write current process status to data/processes.json for the API server.
- `_listen_admin_commands()`
  - Background thread: subscribe to Redis admin commands (restart/stop).
- `_restart_process(name)`
  - Restart a single process by name.
- `_stop_process(name)`
  - Stop a single process by name (no restart).
- `_spawn_tts_gateway()`
  - Spawn TTS Gateway using mlx_audio venv Python.
- `_spawn(name, config)`
  - Spawn a single subprocess.
- `watch()`
  - Wait for all children and handle restarts with backoff.
- `_find_config(name) -> ...`

### `main()`


---
*Generated from 48 source files*
