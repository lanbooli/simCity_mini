"""
Social feed (朋友圈) manager for NPC autonomous posting.
"""
import random
from src.common.database import get_connection, execute, fetch_all, fetch_one
from src.common.models import gen_id


POST_COOLDOWN = 480  # ticks between posts
POST_PROBABILITY_BASE = 0.03


class SocialFeedManager:
    def __init__(self, npc_id: str, npc_data: dict):
        self.npc_id = npc_id
        self.npc = npc_data
        self._cooldown = 0
        self._last_browse_tick = 0

    def should_post(self, personality: list, mood: str, tick: int,
                    has_recent_event: bool = False) -> bool:
        """Determine if NPC should post this cycle."""
        if self._cooldown > 0:
            self._cooldown -= 1
            return False

        prob = POST_PROBABILITY_BASE
        is_shy = "害羞" in personality or "内向" in personality
        is_outgoing = "外向" in personality or "开朗" in personality

        if is_outgoing: prob *= 2.5
        if is_shy: prob *= 0.3
        if mood in ("happy", "excited"): prob *= 1.5
        elif mood == "sad": prob *= 1.3
        elif mood == "angry": prob *= 1.2
        if has_recent_event: prob *= 3.0

        if random.random() < prob:
            self._cooldown = POST_COOLDOWN
            return True
        return False

    def create_post(self, content: str, post_type: str = "general",
                    visibility: str = "public", scene_id: str = "",
                    mood: str = "", game_time: str = "",
                    related_entity_id: str = "") -> str:
        """Create a social post in the database."""
        post_id = gen_id()
        conn = get_connection()
        try:
            execute(conn, """INSERT INTO social_post
                (id, author_id, author_type, content, post_type, visibility,
                 scene_id, mood, related_entity_id, game_time)
                VALUES(?, ?, 'npc', ?, ?, ?, ?, ?, ?, ?)""",
                (post_id, self.npc_id, content, post_type, visibility,
                 scene_id, mood, related_entity_id, game_time))
            conn.commit()
        finally:
            conn.close()
        return post_id

    def get_feed(self, viewer_id: str, viewer_type: str = "player",
                 limit: int = 20) -> list[dict]:
        """Get visible posts for a viewer."""
        conn = get_connection()
        try:
            # Get viewer's relationships
            if viewer_type == "player":
                rows = fetch_all(conn, """SELECT sp.*, n.name as author_name
                    FROM social_post sp LEFT JOIN npc n ON sp.author_id = n.id
                    WHERE sp.visibility = 'public'
                    ORDER BY sp.created_at DESC LIMIT ?""", (limit,))
            else:
                rows = fetch_all(conn, """SELECT sp.*, n.name as author_name
                    FROM social_post sp LEFT JOIN npc n ON sp.author_id = n.id
                    WHERE sp.visibility IN ('public', 'friends')
                    ORDER BY sp.created_at DESC LIMIT ?""", (limit,))
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def like_post(self, post_id: str, user_id: str, user_type: str) -> bool:
        """Like a post. Returns True if new like."""
        conn = get_connection()
        try:
            existing = fetch_one(conn,
                "SELECT id FROM social_like WHERE post_id = ? AND user_id = ? AND user_type = ?",
                (post_id, user_id, user_type))
            if existing:
                return False
            execute(conn, """INSERT INTO social_like(id, post_id, user_id, user_type)
                VALUES(?, ?, ?, ?)""", (gen_id(), post_id, user_id, user_type))
            execute(conn, "UPDATE social_post SET like_count = like_count + 1 WHERE id = ?",
                    (post_id,))
            conn.commit()
            return True
        finally:
            conn.close()

    def add_comment(self, post_id: str, author_id: str, author_type: str,
                    content: str, game_time: str = "") -> str:
        """Add a comment to a post."""
        comment_id = gen_id()
        conn = get_connection()
        try:
            execute(conn, """INSERT INTO social_comment(id, post_id, author_id, author_type,
                content, game_time) VALUES(?, ?, ?, ?, ?, ?)""",
                (comment_id, post_id, author_id, author_type, content, game_time))
            execute(conn, "UPDATE social_post SET comment_count = comment_count + 1 WHERE id = ?",
                    (post_id,))
            conn.commit()
            return comment_id
        finally:
            conn.close()

    def get_comments(self, post_id: str, limit: int = 10) -> list[dict]:
        """Get comments for a post."""
        conn = get_connection()
        try:
            rows = fetch_all(conn, """SELECT sc.*,
                CASE WHEN sc.author_type = 'npc' THEN n.name ELSE '玩家' END as author_name
                FROM social_comment sc LEFT JOIN npc n ON sc.author_id = n.id
                WHERE sc.post_id = ?
                ORDER BY sc.created_at ASC LIMIT ?""", (post_id, limit))
            return [dict(r) for r in rows]
        finally:
            conn.close()
