"""Social feed API routes."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from src.api.schemas import ApiResponse
from src.common.database import get_connection, fetch_one, fetch_all, execute
from src.common.models import gen_id

router = APIRouter(prefix="/api/v1/social", tags=["social"])


class LikeRequest(BaseModel):
    player_id: str


class CommentRequest(BaseModel):
    player_id: str
    content: str


@router.get("/feed")
def get_feed(
    post_type: str = Query("", description="Filter by post type"),
    author_id: str = Query("", description="Filter by author NPC id"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    conn = get_connection()
    try:
        where = ["sp.visibility = 'public'"]
        params = []

        if post_type:
            where.append("sp.post_type = ?")
            params.append(post_type)
        if author_id:
            where.append("sp.author_id = ?")
            params.append(author_id)

        where_clause = " AND ".join(where)
        rows = fetch_all(conn, f"""SELECT sp.*, n.name as author_name
            FROM social_post sp LEFT JOIN npc n ON sp.author_id = n.id
            WHERE {where_clause}
            ORDER BY sp.created_at DESC LIMIT ? OFFSET ?""",
            (*params, limit, offset))
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()


@router.get("/post/{post_id}")
def get_post(post_id: str):
    conn = get_connection()
    try:
        row = fetch_one(conn, """SELECT sp.*, n.name as author_name
            FROM social_post sp LEFT JOIN npc n ON sp.author_id = n.id
            WHERE sp.id = ?""", (post_id,))
        if not row:
            raise HTTPException(404, "Post not found")
        return ApiResponse(data=dict(row))
    finally:
        conn.close()


@router.get("/post/{post_id}/comments")
def get_comments(post_id: str, limit: int = Query(10, ge=1, le=50)):
    conn = get_connection()
    try:
        rows = fetch_all(conn, """SELECT sc.*,
            CASE WHEN sc.author_type = 'npc' THEN n.name ELSE '玩家' END as author_name
            FROM social_comment sc LEFT JOIN npc n ON sc.author_id = n.id
            WHERE sc.post_id = ?
            ORDER BY sc.created_at ASC LIMIT ?""", (post_id, limit))
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()


@router.post("/post/{post_id}/like")
def like_post(post_id: str, req: LikeRequest):
    conn = get_connection()
    try:
        existing = fetch_one(conn,
            "SELECT id FROM social_like WHERE post_id = ? AND user_id = ? AND user_type = 'player'",
            (post_id, req.player_id))
        if existing:
            return ApiResponse(data={"liked": False, "reason": "already liked"})

        execute(conn, """INSERT INTO social_like(id, post_id, user_id, user_type)
            VALUES(?, ?, ?, 'player')""", (gen_id(), post_id, req.player_id))
        execute(conn, "UPDATE social_post SET like_count = like_count + 1 WHERE id = ?",
                (post_id,))
        conn.commit()
        return ApiResponse(data={"liked": True})
    finally:
        conn.close()


@router.post("/post/{post_id}/comment")
def add_comment(post_id: str, req: CommentRequest):
    if not req.content.strip():
        raise HTTPException(400, "Comment content cannot be empty")

    conn = get_connection()
    try:
        comment_id = gen_id()
        execute(conn, """INSERT INTO social_comment(id, post_id, author_id, author_type, content)
            VALUES(?, ?, ?, 'player', ?)""",
            (comment_id, post_id, req.player_id, req.content.strip()))
        execute(conn, "UPDATE social_post SET comment_count = comment_count + 1 WHERE id = ?",
                (post_id,))
        conn.commit()
        return ApiResponse(data={"comment_id": comment_id, "status": "created"})
    finally:
        conn.close()
