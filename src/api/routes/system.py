"""System API routes - game time, weather, events."""

from fastapi import APIRouter, HTTPException
from src.api.schemas import ApiResponse
from src.common.database import get_connection, fetch_one, fetch_all
import json

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/time")
def get_time():
    conn = get_connection()
    try:
        row = fetch_one(conn, "SELECT value FROM game_state WHERE key = 'game_time'")
        if row:
            return ApiResponse(data=json.loads(row["value"]))
        return ApiResponse(data={"day": 1, "hour": 8, "minute": 0, "season": "spring", "phase": "morning"})
    finally:
        conn.close()


@router.get("/weather")
def get_weather():
    conn = get_connection()
    try:
        row = fetch_one(conn, "SELECT value FROM game_state WHERE key = 'weather'")
        if row:
            return ApiResponse(data=json.loads(row["value"]))
        return ApiResponse(data={"type": "sunny", "intensity": "light"})
    finally:
        conn.close()


@router.get("/events")
def get_events(scene_id: str = ""):
    conn = get_connection()
    try:
        if scene_id:
            rows = fetch_all(conn,
                "SELECT * FROM game_event WHERE is_active = 1 AND (scene_id = ? OR event_type = 'global')",
                (scene_id,))
        else:
            rows = fetch_all(conn,
                "SELECT * FROM game_event WHERE is_active = 1")
        return ApiResponse(data=[dict(r) for r in rows])
    finally:
        conn.close()


@router.get("/stats")
def get_stats():
    conn = get_connection()
    try:
        npc_count = conn.execute("SELECT COUNT(*) as cnt FROM npc WHERE is_active = 1").fetchone()["cnt"]
        scene_count = conn.execute("SELECT COUNT(*) as cnt FROM scene").fetchone()["cnt"]
        dialogue_count = conn.execute("SELECT COUNT(*) as cnt FROM dialogue").fetchone()["cnt"]
        return ApiResponse(data={
            "total_npcs": npc_count,
            "total_scenes": scene_count,
            "total_dialogues": dialogue_count,
        })
    finally:
        conn.close()
