"""
NPC dialogue handler. Builds prompts, calls LLM, parses responses.
Reserved: voice interface hooks for future audio input/output.
"""

import asyncio
import logging
import random
import re
import json
from collections import deque
from typing import Optional
from jinja2 import Template

from src.llm.gateway_client import (
    get_gateway_client, PRIORITY_MAP, trim_context,
    Priority, GatewayError,
)
from src.llm.prompts import (
    NPC_DIALOGUE_SYSTEM, NPC_DIALOGUE_USER, NPC_ACTION_SYSTEM,
    NPC_SOCIAL_OPEN, NPC_SOCIAL_REPLY, NPC_GREETING,
    NPC_INNER_THOUGHT, NPC_ACTION_NARRATIVE,
    NPC_CONFESSION_SYSTEM, NPC_PROPOSAL_SYSTEM, NPC_BREAKUP_SYSTEM,
    BOUNDARY_VIOLATION_NARRATIVE,
    NPC_POST_GENERATION, NPC_COMMENT_REPLY, NPC_GOAL_PROMPT,
    NPC_PERFORMANCE,
)
from src.common.utils import now_iso, clamp
from src.npc.action_rules import (
    ACTION_RULES, PHYSICAL_ACTIONS, ACTION_CATEGORY_DESC,
    apply_action_rules, check_physical_action, parse_attributes,
)

logger = logging.getLogger("npc.dialogue")

# ── Career → Workplace mapping ──────────────────────
# Maps career keywords to the scene IDs where NPCs work.
# Multiple career keywords can map to the same workplace.
CAREER_WORKPLACE: dict[str, str] = {
    "咖啡店主": "scene_coffee_shop",
    "咖啡店员": "scene_coffee_shop",
    "图书管理员": "scene_library",
    "超市店主": "scene_market",
    "超市收银员": "scene_market",
    "内科医生": "scene_hospital",
    "护士": "scene_hospital",
    "语文教师": "scene_school",
    "高中生": "scene_school",
    "大学生": "scene_school",
}

# ── Career greeting templates (no LLM needed) ───────
# Each career has 3-5 template greetings for workplace scenarios.
# Audio for these is pre-generated at init time and served instantly.
CAREER_GREETINGS: dict[str, list[str]] = {
    "咖啡店主": [
        "欢迎光临阳光咖啡店！今天想喝点什么？",
        "你好呀，来看看我们新到的咖啡豆吧～",
        "欢迎！老位置还给你留着呢。",
    ],
    "咖啡店员": [
        "欢迎光临！请问需要点什么呢？",
        "你好～今天有限定特调哦，要不要试试？",
        "欢迎光临阳光咖啡店！",
    ],
    "图书管理员": [
        "欢迎来到图书馆，请保持安静哦～",
        "你好，需要帮忙找什么书吗？",
        "欢迎～最近新到了一批书，可以来看看。",
    ],
    "超市店主": [
        "欢迎光临便民超市！随便看看～",
        "你好！今天蔬菜很新鲜哦。",
        "欢迎光临，有什么需要尽管问我。",
    ],
    "超市收银员": [
        "欢迎光临！",
        "你好～需要购物袋吗？",
        "欢迎光临便民超市！",
    ],
    "内科医生": [
        "你好，请坐。哪里不舒服？",
        "你好，先量一下体温吧。",
        "请进，今天感觉怎么样？",
    ],
    "护士": [
        "你好，请问有预约吗？",
        "欢迎来到小镇医院，请先挂号哦~",
        "你好，量一下血压吧。",
    ],
    "语文教师": [
        "同学们好，请回到座位上。",
        "你好呀，今天来旁听吗？",
        "欢迎来到学校～",
    ],
    "高中生": [
        "你好呀！你也来上学吗？",
        "嗨～今天作业好多啊...",
        "你好！你是新来的同学吗？",
    ],
}


def _clean_response(text: str) -> str:
    """Strip model thinking artifacts and hallucinated player continuations."""
    import re
    # Remove Gemma thinking channel markers (multiple formats)
    text = re.sub(r'<\$channel\$>thought\s*', '', text)
    text = re.sub(r'<\$channel\$>', '', text)
    text = re.sub(r'<\|channel>thought\s*', '', text)
    text = re.sub(r'<channel\|>', '', text)
    text = re.sub(r'^\s*use_thought\s*', '', text)
    # Remove bare thought tags
    text = re.sub(r'</?thought>', '', text)
    # Remove any remaining <$...> or <|channel... tags
    text = re.sub(r'<\$[^>]*>', '', text)
    text = re.sub(r'<\|?channel[^>]*>', '', text)
    # Strip hallucinated player continuations (model may generate "Player: ..." without stop tokens)
    for pattern in [r'\n\s*测试玩家[：:].*$', r'\n\s*Player[：:].*$', r'\n\s*玩家[：:].*$',
                    r'\n\s*\{[^}]*测试玩家\}.*$', r'\n\s*\{[^}]*玩家\}.*$']:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    # Trim whitespace per line
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return '\n'.join(lines).strip()


def _load_personality_description(npc_id: str) -> str:
    """Build rich personality description from 39-set system for LLM prompts."""
    import json, os
    try:
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")
        map_path = os.path.join(config_dir, "npc_personality_map.json")
        with open(map_path, "r", encoding="utf-8") as f:
            pmap = json.load(f)
        entry = pmap.get(npc_id)
        if not entry:
            return ""
    except Exception:
        return ""

    from src.npc.personality import ALL_PERSONALITIES
    ids_ = [entry["primary"]] + entry.get("secondary", []) + [entry.get("romance")]
    ids_ = [i for i in ids_ if i and i in ALL_PERSONALITIES]
    if not ids_:
        return ""

    lines = []
    for pid in ids_:
        p = ALL_PERSONALITIES[pid]
        lines.append(f"- {p['name']}：{p['description']}")
    return "\n".join(lines)


class InteractionContext:
    """Tracks recent interactions and physical state for NPC continuity."""
    
    STATE_MAP = {
        "hug": "hugging", "sudden_hug": "hugging", "back_hug": "hugging",
        "hold_hands": "holding hands", "hold_hands_walk": "holding hands", "arm_in_arm": "holding hands",
        "stand_close": "standing very close",
        "kiss": "kissing", "cheek_kiss": "kissing on the cheek",
        "forehead_kiss": "kissing on the cheek", "goodbye_kiss": "kissing",
        "sweet_talk": "whispering sweet words", "whisper": "whispering sweet words",
        "head_pat": "receiving head pats",
        "cuddle": "cuddling",
        "pull_sleeve": "being close",
        "fix_hair": "being close",
        "playful_punch": "playful interaction",
    }
    
    STATE_DURATION = {
        "hugging": 6, "holding hands": 8, "standing very close": 3,
        "kissing": 3, "kissing on the cheek": 2, "whispering sweet words": 2,
        "receiving head pats": 4, "cuddling": 5, "being close": 3,
        "playful interaction": 2,
    }
    
    def __init__(self):
        self.recent_actions: deque = deque(maxlen=5)
        self.physical_states: dict[str, float] = {}
    
    def add_action(self, action_name: str, action_desc: str, response: str):
        """Record an action and update physical state."""
        now = __import__('datetime').datetime.now().isoformat()
        self.recent_actions.append({
            "time": now, "action": action_name,
            "desc": action_desc, "response": response[:120],
        })
        state = self.STATE_MAP.get(action_name)
        if state:
            duration = self.STATE_DURATION.get(state, 3)
            self.physical_states[state] = duration
            # Merge compatible states
            if state == "kissing" and "hugging" in self.physical_states:
                self.physical_states["hugging while kissing"] = max(
                    self.physical_states.get("hugging while kissing", 0), duration)
                del self.physical_states["hugging"]
                del self.physical_states["kissing"]
    
    def tick(self, game_minutes: int = 15):
        """Decay physical states. Called each autonomous cycle."""
        expired = []
        for state, remaining in list(self.physical_states.items()):
            self.physical_states[state] = round(remaining - game_minutes / 60.0, 1)
            if self.physical_states[state] <= 0:
                expired.append(state)
        for state in expired:
            del self.physical_states[state]
    
    def get_physical_context(self) -> str:
        """Summarize current physical state for LLM prompts."""
        if not self.physical_states:
            return ""
        items = sorted(self.physical_states.items(), key=lambda x: x[1], reverse=True)
        states_text = "，".join(s for s, _ in items)
        return f"当前的肢体状态：你正和玩家处于{states_text}的状态。你需要注意这个状态并在回应中体现出来。"
    
    def get_recent_context(self) -> str:
        """Summarize recent interactions for LLM prompts."""
        if not self.recent_actions:
            return ""
        parts = []
        for a in list(self.recent_actions)[-3:]:
            parts.append(f"- 玩家{a['desc']} → 你的反应：{a['response']}")
        return "最近的互动：\n" + "\n".join(parts)
    
    def get_full_context(self) -> str:
        """Get full interaction context for LLM injection."""
        parts = []
        phys = self.get_physical_context()
        if phys:
            parts.append(phys)
        recent = self.get_recent_context()
        if recent:
            parts.append(recent)
        return "\n".join(parts).strip()


class DialogueHandler:
    def __init__(self, npc_data: dict, memory_mgr, relationship_mgr, mood_mgr):
        self.npc = npc_data
        self.memory_mgr = memory_mgr
        self.relationship_mgr = relationship_mgr
        self.mood_mgr = mood_mgr
        self.interaction_ctx = InteractionContext()
        self._dialogue_lock = asyncio.Lock()
        # Load 39-set personality description for LLM prompts (cached)
        self._personality_desc = _load_personality_description(npc_data.get("id", ""))

    async def respond_to_player(
        self, player_name: str, player_id: str, player_message: str,
        scene_name: str = "", game_time: str = "", player_context: str = "",
        player_data: dict = None,
    ) -> dict:
        """
        Generate NPC response to player dialogue.
        Returns: {
            "content": str,
            "favorability_change": int,
            "new_mood": str,
            "memory_created": dict,
        }
        """
        # Capture pre-interaction state
        mood_before = self.mood_mgr.current
        rel = self.relationship_mgr.get_or_create_relation(player_id, "player")
        fav_before = rel.get("favorability", 0)
        rel_type_cn = self._rel_type_cn(rel["relationship_type"])

        # Dynamically build context within token budget
        budget_chars = 4000  # player_dialogue budget
        memories_text, dialogue_text = await self._build_context_dynamic(
            player_id, budget_chars=budget_chars)

        # Get goals
        goals_text = self._get_goals_text()

        # Calculate age
        age = self._calc_age()

        # Format player identity for prompt
        p_gender, p_age, p_appearance, p_personality, p_role = self._format_player_info(player_data)

        # Build system prompt
        system_template = Template(NPC_DIALOGUE_SYSTEM)
        system_msg = system_template.render(
            npc=self.npc,
            age=age,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name,
            player_name=player_name,
            player_gender=p_gender,
            player_age=p_age,
            player_appearance=p_appearance,
            player_personality=p_personality,
            player_role=p_role,
            rel=rel,
            goals=goals_text,
            memories=memories_text,
            dialogue_history=dialogue_text,
        )

        # Build user message with optional RAG context
        user_msg = NPC_DIALOGUE_USER.replace("{{ player_message }}", f"{player_name}: {player_message}")
        if player_context:
            user_msg = f"[相关背景]\n{player_context}\n\n{user_msg}"

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        # Call LLM via Gateway
        gateway = get_gateway_client()
        try:
            logger.info(f"NPC {self.npc['name']} calling LLM for {player_name}...")
            raw_response = await gateway.submit(
                priority=PRIORITY_MAP["player_dialogue"],
                call_type="player_dialogue",
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                timeout=300,  # thinking model takes 60-180s
            )
            response = _clean_response(raw_response)
            logger.info(f"NPC {self.npc['name']} LLM response: {response[:80]}...")
        except Exception as e:
            logger.warning(f"NPC {self.npc['name']} LLM call failed: {type(e).__name__}: {e}")
            response = self._fallback_response(e)

        # Parse favorability change
        fav_change = self._parse_favorability(response)

        # Apply post-processing rules
        fav_change = self._apply_favorability_rules(rel, fav_change)

        # Update relationship
        self.relationship_mgr.update_interaction(player_id, fav_change)

        # Re-read relationship to get updated favorability
        updated_rel = self.relationship_mgr.get_or_create_relation(player_id, "player")

        # Update mood
        self.mood_mgr.affect(fav_change)

        # Create memory
        memory = self.memory_mgr.add(
            content=f"与{player_name}对话: {player_message[:100]} → 我回复了",
            game_time=game_time,
            importance=max(3, abs(fav_change) + 3),
            emotion="joy" if fav_change > 0 else ("anger" if fav_change < -1 else ""),
            related_entity_id=player_id,
            related_entity_type="player",
        )

        return {
            "content": response.strip(),
            "favorability_change": fav_change,
            "favorability_before": fav_before,
            "favorability_after": updated_rel.get("favorability", fav_before + fav_change),
            "familiarity_after": rel.get("familiarity", 0),
            "mood_before": mood_before,
            "new_mood": self.mood_mgr.current,
            "relationship_type": rel.get("relationship_type", "stranger"),
            "memory_created": memory,
        }

    def _calc_age(self) -> int:
        """Calculate age from birth date. Game starts in 2026."""
        try:
            birth_year = int(self.npc["birth_date"].split("-")[0])
            return 2026 - birth_year
        except (ValueError, KeyError, IndexError):
            return 25

    @staticmethod
    def _format_player_info(player_data: dict = None) -> tuple:
        """Format player identity for prompt templates.
        Returns (gender, age, appearance, personality, role)."""
        if not player_data:
            return ("未知", "未知", "普通", "友好", "小镇居民")
        # Gender
        gender_map = {"male": "男", "female": "女", "other": "其他"}
        gender = gender_map.get(player_data.get("gender", ""), "未知")
        # Age
        try:
            birth_year = int(player_data.get("birth_date", "2000").split("-")[0])
            age = str(2026 - birth_year)
        except (ValueError, IndexError):
            age = "未知"
        # Appearance
        appearance = player_data.get("appearance", "{}")
        if isinstance(appearance, str):
            try:
                appearance = json.loads(appearance)
            except (json.JSONDecodeError, TypeError):
                appearance = {}
        if appearance:
            appearance_str = "，".join(f"{v}" for v in appearance.values())
        else:
            appearance_str = "普通"
        # Personality
        personality = player_data.get("personality", "[]")
        if isinstance(personality, str):
            try:
                personality = json.loads(personality)
            except (json.JSONDecodeError, TypeError):
                personality = []
        personality_str = "，".join(personality) if personality else "友好"
        # Role
        role = player_data.get("career", "") or "小镇居民"
        return (gender, age, appearance_str, personality_str, role)

    def _parse_favorability(self, response: str) -> int:
        """Extract [[FAVORABILITY: N]] from LLM response."""
        match = re.search(r'\[\[FAVORABILITY:\s*([+-]?\d+)\]\]', response)
        if match:
            return clamp(int(match.group(1)), -3, 3)
        # Guess based on sentiment if no explicit tag
        positive_words = ["谢谢", "开心", "哈哈", "太好了", "喜欢", "❤"]
        negative_words = ["滚", "讨厌", "恶心", "混蛋", "傻", "烦"]
        pos_count = sum(1 for w in positive_words if w in response)
        neg_count = sum(1 for w in negative_words if w in response)
        if pos_count > neg_count:
            return 1
        elif neg_count > pos_count:
            return -1
        return 0

    def _apply_favorability_rules(self, rel: dict, delta: int) -> int:
        """Post-processing rules for favorability changes.
        Core adjustments (stranger buffer, curve scale, friend/forgiveness)
        are handled by RelationshipManager._adjust_favorability."""
        return clamp(delta, -3, 3)

    def _fallback_response(self, error: Exception) -> str:
        """Fallback response when LLM is unavailable."""
        logger.warning(f"Using fallback response due to: {error}")
        fallbacks = [
            "嗯...（有点走神）",
            "啊，不好意思，我刚才在想别的事情。",
            "嗯？你说什么？",
            "（微笑）你好呀。",
        ]
        return f"{random.choice(fallbacks)} [[FAVORABILITY: 0]]"

    def _format_memories(self, memories: list[dict]) -> str:
        if not memories:
            return "（暂无关于这个人的记忆）"
        return "\n".join(f"- ({m.get('game_time', '')}) {m['content']}" for m in memories[:5])

    def _get_recent_dialogue(self, player_id: str, limit: int = 5) -> list[dict]:
        """Get recent dialogue history from database."""
        from src.common.database import get_connection, fetch_all
        conn = get_connection()
        try:
            rows = fetch_all(conn,
                "SELECT * FROM dialogue WHERE "
                "(speaker_id = ? AND listener_id = ?) OR (speaker_id = ? AND listener_id = ?) "
                "ORDER BY created_at DESC LIMIT ?",
                (self.npc["id"], player_id, player_id, self.npc["id"], limit))
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _format_dialogue(self, dialogues: list[dict]) -> str:
        if not dialogues:
            return "（暂无对话历史）"
        lines = []
        for d in reversed(dialogues):
            speaker_name = self.npc["name"] if d["speaker_id"] == self.npc["id"] else "对方"
            lines.append(f"{speaker_name}: {d['content'][:80]}")
        return "\n".join(lines)

    def _get_goals_text(self) -> list:
        from src.common.database import get_connection, fetch_all
        conn = get_connection()
        try:
            rows = fetch_all(conn,
                "SELECT * FROM goal WHERE entity_id = ? AND entity_type = 'npc' "
                "AND is_short_term = 1 AND status = 'active' ORDER BY priority LIMIT 3",
                (self.npc["id"],))
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def _build_context_dynamic(self, player_id: str, budget_chars: int = 4000) -> tuple[str, str]:
        """Dynamically select memories and dialogue history within token budget.
        Goals are fixed (~30 chars); remaining budget split between dialogue (newest first)
        and memories (newest first). Returns (memories_text, dialogue_text)."""
        # Goals are small and always included (handled separately)
        # Fetch more items than we need, then select dynamically
        recent_dialogues = self._get_recent_dialogue(player_id, limit=20)
        recent_memories = self.memory_mgr.get_recent_about(player_id, limit=20)

        # Reserve ~200 chars for goals + template overhead
        available = max(budget_chars - 200, 200)

        # Dialogues first (higher priority), each ≤80 chars
        dialogue_lines = []
        dialogue_budget = available * 2 // 3
        for d in reversed(recent_dialogues):
            speaker_name = self.npc["name"] if d["speaker_id"] == self.npc["id"] else "对方"
            line = f"{speaker_name}: {d['content'][:80]}"
            if len(line) > dialogue_budget:
                break
            dialogue_lines.append(line)
            dialogue_budget -= len(line)

        # Memories second, each ≤100 chars; gets 1/3 + unused dialogue budget
        memory_lines = []
        memory_budget = available // 3 + dialogue_budget
        for m in recent_memories:
            line = f"- ({m.get('game_time', '')}) {m['content'][:100]}"
            if len(line) > memory_budget:
                break
            memory_lines.append(line)
            memory_budget -= len(line)

        memories_text = "\n".join(memory_lines) if memory_lines else "（暂无关于这个人的记忆）"
        dialogue_text = "\n".join(dialogue_lines) if dialogue_lines else "（暂无对话历史）"
        return memories_text, dialogue_text

    @staticmethod
    def _rel_type_cn(rel_type: str) -> str:
        """Translate relationship type to Chinese."""
        mapping = {
            "parent": "父母",
            "sibling": "兄弟姐妹",
            "child": "子女",
            "stranger": "陌生人",
            "acquaintance": "认识的人",
            "friend": "朋友",
            "best_friend": "好朋友",
            "boyfriend": "男朋友",
            "girlfriend": "女朋友",
            "spouse": "配偶",
            "dislike": "讨厌的人",
            "enemy": "仇敌",
        }
        return mapping.get(rel_type, rel_type)

    # ── Action interaction ──────────────────────────

    @staticmethod
    def _parse_action(content: str) -> tuple[str, str]:
        """
        Parse action from content. Returns (action_name, extra_text).
        Supports: /动作名, /动作名 额外内容
        Returns ("", content) if not an action command.
        """
        if content.startswith("/"):
            parts = content[1:].split(None, 1)
            action_name = parts[0].strip()
            extra = parts[1].strip() if len(parts) > 1 else ""
            if action_name in ACTION_RULES or action_name in PHYSICAL_ACTIONS:
                return action_name, extra
            # Unknown action, return as is
            return "", content
        return "", content

    async def respond_to_action(
        self, player_name: str, player_id: str, action_name: str,
        scene_name: str = "", game_time: str = "", scene_type: str = "indoor",
        player_attrs: dict | None = None, npc_attrs: dict | None = None,
        player_data: dict = None,
    ) -> dict:
        """
        Generate NPC reaction to a player action (non-dialogue).
        Handles regular, intimate, and physical (attribute-checked) actions.
        Returns same format as respond_to_player.
        """
        player_attrs = player_attrs or {}
        npc_attrs = npc_attrs or {}

        # Check if it's a regular or physical action
        action = ACTION_RULES.get(action_name)
        physical_action = PHYSICAL_ACTIONS.get(action_name) if not action else None

        if not action and not physical_action:
            return self._fallback_action_response(action_name)

        # Get relationship
        mood_before = self.mood_mgr.current
        rel = self.relationship_mgr.get_or_create_relation(player_id, "player")
        fav_before = rel.get("favorability", 0)

        # Handle physical action with attribute check
        is_physical = physical_action is not None
        action_success = True
        action_result = ""
        base_delta = 0

        if is_physical:
            check = check_physical_action(action_name, player_attrs, npc_attrs)
            action_success = check["success"]
            action_result = check["action_desc"]
            base_delta = check["base_delta"]
            category = physical_action.get("category", "force")
            action_desc = physical_action.get("success_desc" if action_success else "fail_desc", action_name)
            min_rel = None
            rejected = False
        else:
            base_delta = action.get("base_delta", 0)
            min_rel = action.get("min_relation")
            category = action.get("category", "friendly")
            action_desc = action.get("desc", action_name)
            rejected = min_rel is not None and not self._meets_rel_requirement(
                rel["relationship_type"], min_rel)

        # Calculate age
        age = self._calc_age()

        # Format player identity for prompt
        p_gender, p_age, p_appearance, p_personality, p_role = self._format_player_info(player_data)

        # Build action system prompt with interaction context
        interaction_ctx = self.interaction_ctx.get_full_context()
        system_template = Template(NPC_ACTION_SYSTEM)
        system_msg = system_template.render(
            npc=self.npc,
            age=age,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name,
            player_name=player_name,
            player_gender=p_gender,
            player_age=p_age,
            player_appearance=p_appearance,
            player_personality=p_personality,
            player_role=p_role,
            rel=rel,
            action_name=action_name,
            action_desc=action_desc,
            action_category=ACTION_CATEGORY_DESC.get(category, "一般互动"),
            rejected=rejected,
            is_physical=is_physical,
            action_success=action_success,
            action_result=action_result,
            base_delta=base_delta,
            interaction_context=interaction_ctx,
        )

        # Build messages
        user_msg = f"{player_name}对你做了动作：{action_desc}"
        if is_physical:
            user_msg += f"。动作结果：{'成功' if action_success else '失败'}——{action_result}"

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        # Call LLM via Gateway
        gateway = get_gateway_client()
        try:
            logger.info(f"NPC {self.npc['name']} reacting to action '{action_name}' "
                        f"(physical={is_physical}, success={action_success}) from {player_name}...")
            raw_response = await gateway.submit(
                priority=PRIORITY_MAP["player_action"],
                call_type="player_action",
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                timeout=300,
            )
            response = _clean_response(raw_response)
            logger.info(f"NPC {self.npc['name']} action response: {response[:80]}...")
        except Exception as e:
            logger.warning(f"NPC {self.npc['name']} action LLM call failed: {type(e).__name__}: {e}")
            response = self._fallback_action_response(action_name)

        # Parse favorability change
        fav_change = self._parse_favorability(response)

        # Apply standard dialogue rules (familiarity buffer etc.)
        fav_change = self._apply_favorability_rules(rel, fav_change)

        # Apply action-specific rules (relationship check, mood, scene, success/fail)
        fav_change = apply_action_rules(
            action_name, rel, fav_change,
            self.mood_mgr.current, scene_type, action_success,
        )

        # Update relationship
        self.relationship_mgr.update_interaction(player_id, fav_change)

        # Re-read relationship to get updated favorability
        updated_rel = self.relationship_mgr.get_or_create_relation(player_id, "player")

        # Update mood
        self.mood_mgr.affect(fav_change)

        # Create memory
        result_tag = ""
        if is_physical:
            result_tag = f"({'成功' if action_success else '失败'})"
        elif min_rel and not self._meets_rel_requirement(updated_rel["relationship_type"], min_rel):
            result_tag = "(被拒绝)"

        memory = self.memory_mgr.add(
            content=f"玩家对我做了动作「{action_name}」{result_tag}",
            game_time=game_time,
            importance=max(3, abs(fav_change) + 3),
            emotion="joy" if fav_change > 0 else ("anger" if fav_change < -1 else ""),
            related_entity_id=player_id,
            related_entity_type="player",
        )

        return {
            "content": response.strip(),
            "favorability_change": fav_change,
            "favorability_before": fav_before,
            "favorability_after": updated_rel.get("favorability", fav_before + fav_change),
            "familiarity_after": rel.get("familiarity", 0),
            "mood_before": mood_before,
            "new_mood": self.mood_mgr.current,
            "relationship_type": rel.get("relationship_type", "stranger"),
            "memory_created": memory,
        }

    def _fallback_action_response(self, action_name: str) -> str:
        """Fallback response when LLM unavailable for action."""
        fallbacks = [
            f"（听到动静转过头来，疑惑地看了看）嗯？你在做什么？",
            f"（被突如其来的动作吓了一跳）啊！怎么了？",
            f"（微微一愣，然后露出礼貌的微笑）你好？",
        ]
        return f"{random.choice(fallbacks)} [[FAVORABILITY: 0]]"

    # ── NPC→NPC Social ──────────────────────────────

    async def generate_social_opening(
        self, target_name: str, target_id: str,
        scene_name: str = "", game_time: str = "",
    ) -> dict:
        """Generate NPC→NPC social opening line."""
        rel = self.relationship_mgr.get_or_create_relation(target_id, "npc")
        system_template = Template(NPC_SOCIAL_OPEN)
        system_msg = system_template.render(
            npc=self.npc, other_name=target_name,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name, rel=rel,
        )
        return await self._simple_llm_call(system_msg, f"向{target_name}发起互动", max_tokens=512, call_type="social_open")

    async def respond_to_npc(
        self, other_npc_name: str, other_npc_id: str, other_message: str,
        scene_name: str = "", game_time: str = "",
    ) -> dict:
        """Generate NPC response to another NPC's social interaction."""
        rel = self.relationship_mgr.get_or_create_relation(other_npc_id, "npc")
        system_template = Template(NPC_SOCIAL_REPLY)
        system_msg = system_template.render(
            npc=self.npc, other_name=other_npc_name,
            other_message=other_message,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name, rel=rel,
        )
        return await self._simple_llm_call(system_msg, f"回应{other_npc_name}", max_tokens=512, call_type="social_reply")

    # ── NPC→Player initiated interactions ──────────

    async def generate_greeting(
        self, player_name: str, player_id: str,
        scene_name: str = "", game_time: str = "",
        player_data: dict = None,
        at_workplace: bool = False,
    ) -> dict:
        """Generate NPC greeting when player enters scene."""
        rel = self.relationship_mgr.get_or_create_relation(player_id, "player")
        p_gender, p_age, p_appearance, p_personality, p_role = self._format_player_info(player_data)
        system_template = Template(NPC_GREETING)
        system_msg = system_template.render(
            npc=self.npc, player_name=player_name,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name, rel=rel,
            player_gender=p_gender,
            player_age=p_age,
            player_appearance=p_appearance,
            player_personality=p_personality,
            player_role=p_role,
            at_workplace=at_workplace,
        )
        return await self._simple_llm_call(system_msg, f"向{player_name}打招呼", max_tokens=512, call_type="greeting")

    async def generate_action_narrative(
        self, target_name: str, target_id: str, action_name: str,
        action_desc: str, scene_name: str = "", game_time: str = "",
        player_data: dict = None,
    ) -> dict:
        """Generate narrative for NPC-initiated action toward a target."""
        rel = self.relationship_mgr.get_or_create_relation(target_id, "player")
        p_gender, p_age, p_appearance, p_personality, p_role = self._format_player_info(player_data)
        interaction_ctx = self.interaction_ctx.get_full_context()
        system_template = Template(NPC_ACTION_NARRATIVE)
        system_msg = system_template.render(
            npc=self.npc, target_name=target_name,
            action_desc=action_desc,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name, rel=rel,
            player_gender=p_gender,
            player_age=p_age,
            player_appearance=p_appearance,
            player_personality=p_personality,
            player_role=p_role,
            interaction_context=interaction_ctx,
        )
        return await self._simple_llm_call(system_msg, f"对{target_name}做{action_name}", max_tokens=512, call_type="action_narrative")

    # ── Inner thought ───────────────────────────────

    async def generate_inner_thought(
        self, scene_name: str = "", game_time: str = "", weather: str = "sunny",
    ) -> str:
        """Generate a brief inner thought (not spoken)."""
        system_template = Template(NPC_INNER_THOUGHT)
        system_msg = system_template.render(
            npc=self.npc,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name, game_time=game_time, weather=weather,
        )
        thoughts = ["（今天的风真舒服呢）", "（有点想喝杯热咖啡）",
                    "（待会要做点什么呢...）", "（今天的心情还不错~）"]
        try:
            result = await self._simple_llm_call(system_msg, "内心独白", max_tokens=512, call_type="inner_thought")
            return result.get("content", random.choice(thoughts))
        except Exception:
            return random.choice(thoughts)

    # ── Romance system helpers ──────────────────────

    async def generate_confession(
        self, target_name: str, target_id: str,
        scene_name: str = "", game_time: str = "",
    ) -> dict:
        """Generate NPC confession to player."""
        rel = self.relationship_mgr.get_or_create_relation(target_id, "player")
        system_template = Template(NPC_CONFESSION_SYSTEM)
        system_msg = system_template.render(
            npc=self.npc, target_name=target_name,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name, game_time=game_time, rel=rel,
        )
        return await self._simple_llm_call(system_msg, f"向{target_name}告白", max_tokens=1024, call_type="confession")

    async def generate_proposal(
        self, target_name: str, target_id: str,
        scene_name: str = "", game_time: str = "",
    ) -> dict:
        """Generate NPC proposal to player."""
        rel = self.relationship_mgr.get_or_create_relation(target_id, "player")
        system_template = Template(NPC_PROPOSAL_SYSTEM)
        system_msg = system_template.render(
            npc=self.npc, target_name=target_name,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name, game_time=game_time, rel=rel,
        )
        return await self._simple_llm_call(system_msg, f"向{target_name}求婚", max_tokens=1024, call_type="proposal")

    async def generate_breakup(
        self, target_name: str, target_id: str, reason: str,
        fav_delta: int = -30, scene_name: str = "", game_time: str = "",
    ) -> dict:
        """Generate NPC breakup dialogue."""
        rel = self.relationship_mgr.get_or_create_relation(target_id, "player")
        system_template = Template(NPC_BREAKUP_SYSTEM)
        system_msg = system_template.render(
            npc=self.npc, target_name=target_name, reason=reason,
            fav_delta=fav_delta,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name, rel=rel,
        )
        return await self._simple_llm_call(system_msg, f"与{target_name}分手", max_tokens=1024, call_type="breakup")

    # ── Boundary violation narrative ────────────────

    async def generate_violation_reaction(
        self, actor_name: str, actor_id: str, action_desc: str,
        severity: str = "minor", fav_delta: int = -20,
        scene_name: str = "", game_time: str = "",
    ) -> dict:
        """Generate NPC reaction to a boundary violation."""
        rel = self.relationship_mgr.get_or_create_relation(actor_id, "player")
        system_template = Template(BOUNDARY_VIOLATION_NARRATIVE)
        system_msg = system_template.render(
            npc=self.npc, actor_name=actor_name,
            action_desc=action_desc, severity=severity,
            fav_delta=fav_delta,
            personality_list=", ".join(json.loads(self.npc.get("personality", "[]"))),
            personality_desc=self._personality_desc,
            scene_name=scene_name, rel=rel,
        )
        return await self._simple_llm_call(system_msg, f"对{actor_name}越界行为的反应", max_tokens=1024, call_type="violation")

    # ── Social feed post generation ───────────────

    async def generate_post_content(
        self, scene_name: str = "", game_time: str = "",
        recent_memory: str = "",
    ) -> str:
        """Generate social feed post content via LLM."""
        personality = json.loads(self.npc.get("personality", "[]"))
        system_template = Template(NPC_POST_GENERATION)
        system_msg = system_template.render(
            npc=self.npc,
            personality_list=", ".join(personality),
            personality_desc=self._personality_desc,
            scene_name=scene_name,
            recent_memory=recent_memory or "无特别的事件",
        )
        result = await self._simple_llm_call(system_msg, "发朋友圈", max_tokens=512, call_type="post")
        return result["content"]

    async def generate_comment_reply(
        self, post_content: str, comment_content: str,
        commenter_name: str, commenter_id: str,
    ) -> str:
        """Generate a reply to a social feed comment via LLM."""
        rel = self.relationship_mgr.get_or_create_relation(commenter_id, "player")
        system_template = Template(NPC_COMMENT_REPLY)
        system_msg = system_template.render(
            npc=self.npc,
            post_content=post_content[:200],
            comment_content=comment_content[:200],
            commenter_name=commenter_name,
            rel=rel,
        )
        result = await self._simple_llm_call(system_msg, "回复评论", max_tokens=512, call_type="comment_reply")
        return result["content"]

    # ── Goal evaluation ───────────────────────────

    async def evaluate_goal(self, goal: dict) -> dict:
        """Evaluate goal progress via LLM, returns {progress_delta, thought}."""
        system_template = Template(NPC_GOAL_PROMPT)
        system_msg = system_template.render(npc=self.npc, goal=goal)
        gateway = get_gateway_client()
        try:
            raw = await gateway.submit(
                priority=PRIORITY_MAP["goal_eval"],
                call_type="goal_eval",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": "评估今天的目标进展"},
                ],
                temperature=0.5,
                max_tokens=512,
            )
            match = re.search(r'\{[^}]+\}', raw)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            logger.warning(f"Goal eval LLM failed: {e}")
        return {"progress_delta": 0.0, "thought": ""}

    # ── NPC↔NPC Fused Performance ──────────────────

    async def generate_social_performance(
        self, *,
        activity: str,
        location: str,
        duration_hint: str,
        participants: list[dict],
        shared_context: str = "",
    ) -> dict:
        """
        Single LLM call generates both NPCs' dialogue sequence.
        participants: [{"name":..., "role_tag":"host"|"guest",
                        "personality":..., "current_needs":...,
                        "relationship_to_other":...}, ...]
        Returns: {"dialogue_sequence": [...], "end_condition": "natural"}
        """
        template = Template(NPC_PERFORMANCE)
        system_msg = template.render(
            activity=activity,
            location=location,
            duration_hint=duration_hint,
            participants=participants,
            shared_context=shared_context or f"双方进行{activity}。",
        )

        gateway = get_gateway_client()
        try:
            raw = await gateway.submit(
                priority=PRIORITY_MAP["social_performance"],
                call_type="social_performance",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": f"请生成{activity}的对话序列。"},
                ],
                temperature=0.8,
                max_tokens=512,
            )
            # Parse JSON from response
            json_str = raw.strip()
            # Handle markdown code blocks
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            result = json.loads(json_str)
            return {
                "dialogue_sequence": result.get("dialogue_sequence", []),
                "end_condition": result.get("end_condition", "natural"),
            }
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Social performance LLM failed: {e}")
            # Fallback: simple canned exchange
            p1 = participants[0] if participants else {"name": "A"}
            p2 = participants[1] if len(participants) > 1 else {"name": "B"}
            return {
                "dialogue_sequence": [
                    {"speaker": p1["name"], "text": f"一起{activity}吧？",
                     "action": "微笑着说", "emotion": "友好"},
                    {"speaker": p2["name"], "text": "好啊。",
                     "action": "点点头", "emotion": "平静"},
                ],
                "end_condition": "natural",
            }

    # ── Simple LLM call helper ──────────────────────

    async def _simple_llm_call(self, system_msg: str, context: str,
                               max_tokens: int = 200, call_type: str = "") -> dict:
        """Make a simple LLM call via Gateway and parse favorability from response."""
        gateway = get_gateway_client()
        try:
            raw_response = await gateway.submit(
                priority=PRIORITY_MAP.get(call_type, Priority.MEDIUM),
                call_type=call_type,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": context},
                ],
                temperature=0.8,
                max_tokens=max_tokens,
            )
            response = _clean_response(raw_response)
            fav_change = self._parse_favorability(response)
            return {"content": response.strip(), "favorability_change": fav_change}
        except Exception as e:
            logger.warning(f"LLM call failed ({context}): {type(e).__name__}: {e}")
            return {"content": f"（{context}）[[FAVORABILITY: 0]]", "favorability_change": 0}

    @staticmethod
    def _meets_rel_requirement(current_type: str, required: str) -> bool:
        """Check if relationship type meets the minimum requirement."""
        hierarchy = ["stranger", "acquaintance", "friend", "best_friend",
                      "boyfriend", "girlfriend", "spouse",
                      "parent", "sibling", "child"]
        romantic_pairs = {"boyfriend", "girlfriend"}
        if current_type in romantic_pairs and required in romantic_pairs:
            return True
        if current_type == "spouse" and required in romantic_pairs:
            return True
        if current_type in hierarchy and required in hierarchy:
            return hierarchy.index(current_type) >= hierarchy.index(required)
        return False

    # ── Future voice interface hooks ──────────────

    async def process_voice_input(self, audio_data: bytes, player_name: str, player_id: str) -> dict:
        """[FUTURE] Transcribe voice to text, then respond normally."""
        # Will use lmstudio_client.voice_transcribe(audio_data) → text
        # Then call respond_to_player with transcribed text
        # Then optionally call synthesize_voice_response
        raise NotImplementedError("Voice input will be added in a future update.")

    async def synthesize_voice_response(self, text: str) -> bytes:
        """[FUTURE] Convert response text to speech with NPC's voice profile."""
        # Will use lmstudio_client.voice_synthesize(text, voice_profile=self.npc['voice_type'])
        raise NotImplementedError("Voice output will be added in a future update.")

def parse_stage_and_dialogue(text: str) -> list[dict]:
    """Parse text into stage direction and dialogue segments for TTS.
    
    Stage directions in （） use narrator voice, dialogue in 「」 uses NPC voice.
    Falls back to a single dialogue segment if no markers found.
    """
    import re
    
    segments = []
    # Match either （stage） or 「dialogue」 patterns
    pattern = re.compile(r'（([^（]*)）|「([^」]*)」')
    last_end = 0
    
    for match in pattern.finditer(text):
        start = match.start()
        # If there's unmarked text between matches, treat it as dialogue
        if start > last_end:
            unmarked = text[last_end:start].strip()
            if unmarked:
                segments.append({"text": unmarked, "type": "dialogue"})
        
        stage = match.group(1)
        dialogue = match.group(2)
        if stage and stage.strip():
            segments.append({"text": stage.strip(), "type": "stage"})
        elif dialogue and dialogue.strip():
            segments.append({"text": dialogue.strip(), "type": "dialogue"})
        
        last_end = match.end()
    
    # Remaining text after last match
    remaining = text[last_end:].strip()
    if remaining:
        segments.append({"text": remaining, "type": "dialogue"})
    
    # If no markers found at all, return whole text as dialogue
    if not segments and text.strip():
        segments.append({"text": text.strip(), "type": "dialogue"})
    
    return segments
