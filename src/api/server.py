"""
FastAPI application server. Serves REST API, WebSocket, and static frontend files.
"""

import json
import logging
import os
import sys
import traceback
from contextlib import asynccontextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config.settings import settings
from src.common.message_broker import RedisBroker
from src.api.websocket_manager import WSManager
from src.common.database import get_connection, fetch_one, fetch_all
from src.common.utils import game_time_to_str
from src.common.home_access import can_enter_home, get_access_error, compute_room_access
from src.api.routes import player, npc, scene, dialogue, system, admin, social, tts

# ── Debug logging (1-day retention) ──────────────────

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("api")
logger.setLevel(logging.DEBUG)

# File handler: rotate at midnight, keep 1 backup (today + yesterday max)
fh = TimedRotatingFileHandler(
    LOG_DIR / "api.log",
    when="midnight",
    interval=1,
    backupCount=1,
    encoding="utf-8",
)
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
logger.addHandler(fh)

# Also log to stdout for supervisor capture
sh = logging.StreamHandler(sys.stdout)
sh.setLevel(logging.INFO)
sh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
logger.addHandler(sh)


# ── Global state ───────────────────────────────────

broker: RedisBroker = RedisBroker()
ws_manager: WSManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ws_manager
    # Startup
    logger.info(f"API server starting on {settings.api_host}:{settings.api_port}")
    await broker.connect()
    logger.info("Redis broker connected")
    ws_manager = WSManager(broker)
    logger.info(f"API server ready on {settings.api_host}:{settings.api_port}")
    yield
    # Shutdown
    logger.info("API server shutting down")
    await broker.disconnect()
    logger.info("Redis broker disconnected")


# ── App factory ────────────────────────────────────

app = FastAPI(
    title="城市小镇 API",
    description="City Town - A City Life Simulation Game",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── HTTP request logging middleware ──────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.debug(f"HTTP {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        if response.status_code >= 400:
            logger.warning(f"HTTP {request.method} {request.url.path} → {response.status_code}")
        return response
    except Exception:
        logger.error(f"HTTP {request.method} {request.url.path} crashed:\n{traceback.format_exc()}")
        raise

# REST routes
app.include_router(player.router)
app.include_router(npc.router)
app.include_router(scene.router)
app.include_router(dialogue.router)
app.include_router(system.router)
app.include_router(admin.router)
app.include_router(social.router)
app.include_router(tts.router)


# ── Home access helpers ────────────────────────────

def _load_scene_for_player(player_id: str, scene_id: str) -> dict | None:
    """Load full scene data for the player entering a scene."""
    conn = get_connection()
    try:
        row = fetch_one(conn, "SELECT * FROM scene WHERE id = ?", (scene_id,))
        if not row:
            return None
        d = dict(row)

        # Parse JSON fields
        d["rooms"] = json.loads(d.get("rooms", "[]")) if isinstance(d.get("rooms"), str) else (d.get("rooms") or [])
        d["residents"] = json.loads(d.get("residents", "[]")) if isinstance(d.get("residents"), str) else (d.get("residents") or [])

        # NPCs currently in the scene
        npcs = fetch_all(conn, """SELECT n.id, n.name, n.gender, n.career,
                        n.current_mood, n.current_activity,
                        sn.role, json_extract(n.appearance, '$.avatar') as avatar,
                        json_extract(n.appearance, '$.fullbody') as fullbody,
                        json_extract(n.personality, '$') as personality
                        FROM scene_npc sn JOIN npc n ON sn.npc_id = n.id
                        WHERE sn.scene_id = ? AND n.is_active = 1""", (scene_id,))
        d["npcs"] = [dict(n) for n in npcs]

        # Items in the scene (grouped by room for home scenes)
        items = fetch_all(conn, "SELECT * FROM item WHERE scene_id = ?", (scene_id,))
        d["items"] = [dict(i) for i in items]

        return d
    finally:
        conn.close()


async def _check_home_access(player_id: str, scene_id: str) -> dict:
    """Check if the player can enter a home scene. Returns access info dict
    with per-room `can_enter` flags, including dynamic bathroom occupancy."""
    conn = get_connection()
    try:
        # Load residents and rooms
        row = fetch_one(conn, "SELECT residents, rooms FROM scene WHERE id = ?", (scene_id,))
        if not row:
            return {"can_enter": False, "error": "scene_not_found", "message": "场景不存在"}

        residents = json.loads(row["residents"]) if isinstance(row["residents"], str) else (row["residents"] or [])
        rooms = json.loads(row["rooms"]) if isinstance(row["rooms"], str) else (row["rooms"] or [])

        # If player is a resident, full access to all rooms (but still check bathroom occupancy)
        if player_id in residents:
            occupied = await _get_occupied_rooms(residents)
            resident_rooms = []
            for r in rooms:
                room_name = r.get("name", "")
                can_enter = True
                # Bathroom occupied by someone else → resident can't enter either
                if any(kw in room_name for kw in ["浴室"]) and any(kw in occupied for kw in ["浴室"]):
                    can_enter = False
                resident_rooms.append({**r, "can_enter": can_enter})
            return {
                "can_enter": True, "is_resident": True,
                "rooms": resident_rooms,
            }

        # Check relationship with each resident
        best_rel_type = "stranger"
        best_fav = -999
        player_rels: dict[str, dict] = {}

        for resident_id in residents:
            rel = fetch_one(conn,
                "SELECT relationship_type, favorability FROM relationship "
                "WHERE entity_a_id = ? AND entity_a_type = 'npc' "
                "AND entity_b_id = ? AND entity_b_type = 'player'",
                (resident_id, player_id))
            if rel:
                fav = rel.get("favorability", 0)
                player_rels[resident_id] = {
                    "relationship_type": rel.get("relationship_type", "stranger"),
                    "favorability": fav,
                }
                if fav > best_fav:
                    best_fav = fav
                    best_rel_type = rel.get("relationship_type", "stranger")

        if not player_rels:
            return {
                "can_enter": False,
                "error": "access_denied",
                "message": "你和这里的住户素不相识，不便打扰",
                "required_relation": "acquaintance",
            }

        if not can_enter_home(best_rel_type, best_fav):
            error_info = get_access_error(best_rel_type, best_fav)
            return {
                "can_enter": False,
                "error": "access_denied",
                "message": error_info.get("message", "你和TA还不够熟悉，不便打扰"),
                "required_relation": error_info.get("required_relation", "friend"),
            }

        # Access granted — check bathroom occupancy then compute per-room access
        occupied = await _get_occupied_rooms(residents)
        rooms_with_access = compute_room_access(
            rooms=rooms,
            residents=residents,
            best_rel_type=best_rel_type,
            best_fav=best_fav,
            player_rels=player_rels,
            occupied_rooms=occupied,
        )

        return {
            "can_enter": True,
            "is_resident": False,
            "rooms": rooms_with_access,
            "relationship": best_rel_type,
            "favorability": best_fav,
        }
    finally:
        conn.close()


async def _get_occupied_rooms(residents: list[str]) -> set[str]:
    """Query Redis for NPC states and return which room types are occupied."""
    occupied = set()
    for npc_id in residents:
        try:
            state = await broker.kv_get(f"state:npc:{npc_id}")
            if state:
                room = state.get("current_room", "")
                if room and "浴室" in room:
                    occupied.add("浴室")
        except Exception:
            pass
    return occupied


# ── WebSocket ──────────────────────────────────────

@app.websocket("/ws/game")
async def game_websocket(ws: WebSocket, player_id: str = "player_001"):
    await ws_manager.connect(player_id, ws)
    logger.info(f"WS connect: player={player_id}")
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "")
            logger.debug(f"WS msg: player={player_id} type={msg_type}")

            if msg_type == "dialogue_send":
                d = msg.get("data", {})
                npc_id = d.get("npc_id", "")
                logger.info(f"WS dialogue: player={player_id} npc={npc_id}")
                # Forward to dialogue inbound stream
                game_time = await broker.kv_get("state:game_time")
                time_str = ""
                if game_time:
                    time_str = game_time_to_str(
                        game_time.get("day", 1),
                        game_time.get("hour", 8),
                        game_time.get("minute", 0),
                    )
                # Look up player name from DB for the stream message
                player_name = "新居民"
                try:
                    conn = get_connection()
                    try:
                        row = fetch_one(conn, "SELECT name FROM player WHERE id = ?", (player_id,))
                        if row:
                            player_name = row["name"]
                    finally:
                        conn.close()
                except Exception:
                    pass
                await broker.stream_add(f"stream:dialogue:{npc_id}", {
                    "player_id": player_id,
                    "npc_id": npc_id,
                    "content": d.get("content", ""),
                    "game_time": time_str,
                    "player_name": player_name,
                })

            elif msg_type == "scene_focus":
                d = msg.get("data", {})
                scene_id = d.get("scene_id", "")
                room_name = d.get("room_name", "")
                if scene_id:
                    # Load scene info from DB
                    scene_data = _load_scene_for_player(player_id, scene_id)
                    if not scene_data:
                        await ws.send_json({"type": "error", "data": {
                            "code": "scene_not_found",
                            "message": f"场景 {scene_id} 不存在",
                        }})
                        continue

                    # Home access permission check
                    if scene_data.get("scene_type") == "home":
                        access = await _check_home_access(player_id, scene_id)
                        scene_data["home_access"] = access
                        if not access.get("can_enter"):
                            await ws.send_json({"type": "home_access_denied", "data": {
                                "scene_id": scene_id,
                                "scene_name": scene_data.get("name", ""),
                                "error": access.get("error", "access_denied"),
                                "message": access.get("message", "你和TA还不够熟悉，不便打扰"),
                                "required_relation": access.get("required_relation", ""),
                            }})
                            continue

                    # Remove player from old scene's NPC list
                    old_loc = await broker.kv_get(f"state:player:{player_id}:location")
                    if old_loc and isinstance(old_loc, dict) and old_loc.get("scene_id"):
                        old_scene = old_loc["scene_id"]
                        old_npcs_data = await broker.kv_get(f"state:scene:{old_scene}:npcs")
                        old_npcs = old_npcs_data.get("npcs", []) if isinstance(old_npcs_data, dict) else []
                        if player_id in old_npcs:
                            old_npcs.remove(player_id)
                            await broker.kv_set(f"state:scene:{old_scene}:npcs", {"npcs": old_npcs})

                    # Add player to new scene NPC list
                    new_npcs_data = await broker.kv_get(f"state:scene:{scene_id}:npcs")
                    new_npcs = new_npcs_data.get("npcs", []) if isinstance(new_npcs_data, dict) else []
                    if player_id not in new_npcs:
                        new_npcs.append(player_id)
                    await broker.kv_set(f"state:scene:{scene_id}:npcs", {"npcs": new_npcs})

                    # Update player location in Redis with scene context
                    await broker.kv_set(f"state:player:{player_id}:location", {
                        "scene_id": scene_id,
                        "scene_name": scene_data.get("name", ""),
                        "scene_type": scene_data.get("scene_type", ""),
                        "room_name": room_name,
                        "rooms": scene_data.get("rooms", []),
                    })

                    await ws.send_json({"type": "scene_update", "data": scene_data})

                    # Look up player name for the greeting notification
                    player_name = "新居民"
                    try:
                        conn = get_connection()
                        try:
                            row = fetch_one(conn, "SELECT name FROM player WHERE id = ?", (player_id,))
                            if row:
                                player_name = row["name"]
                        finally:
                            conn.close()
                    except Exception:
                        pass

                    # Notify NPCs that a player entered their scene (for immediate greeting)
                    await broker.publish("system:player_entered", {
                        "player_id": player_id,
                        "player_name": player_name,
                        "scene_id": scene_id,
                        "scene_type": scene_data.get("scene_type", ""),
                        "room_name": room_name,
                    })

            elif msg_type == "ping":
                await ws.send_json({"type": "pong", "data": {}})

            # ── Voice interface hook (future) ──────
            elif msg_type == "voice_input":
                # Receive speech-recognized text from browser and forward to NPC dialogue
                d = msg.get("data", {})
                npc_id = d.get("npc_id", "")
                content = d.get("content", "").strip()
                if not npc_id or not content:
                    await ws.send_json({"type": "error", "data": {
                        "code": "invalid_voice_input",
                        "message": "语音输入无效",
                    }})
                    continue
                logger.info(f"WS voice_input: player={player_id} npc={npc_id} content={content[:50]}")
                game_time = await broker.kv_get("state:game_time")
                time_str = ""
                if game_time:
                    time_str = game_time_to_str(
                        game_time.get("day", 1),
                        game_time.get("hour", 8),
                        game_time.get("minute", 0),
                    )
                # Look up player name from DB
                player_name = "新居民"
                try:
                    conn = get_connection()
                    try:
                        row = fetch_one(conn, "SELECT name FROM player WHERE id = ?", (player_id,))
                        if row:
                            player_name = row["name"]
                    finally:
                        conn.close()
                except Exception:
                    pass
                await broker.stream_add(f"stream:dialogue:{npc_id}", {
                    "player_id": player_id,
                    "npc_id": npc_id,
                    "content": content,
                    "game_time": time_str,
                    "player_name": player_name,
                })
                # Acknowledge to frontend
                await ws.send_json({"type": "voice_input_ack", "data": {
                    "npc_id": npc_id,
                    "content": content,
                }})

    except WebSocketDisconnect:
        logger.info(f"WS disconnect: player={player_id}")
        ws_manager.disconnect(player_id, ws)
    except Exception:
        logger.error(f"WS error player={player_id}:\n{traceback.format_exc()}")
        ws_manager.disconnect(player_id, ws)


# ── File upload ───────────────────────────────────

import shutil
from fastapi import UploadFile, File

UPLOAD_DIR = Path(__file__).parent.parent.parent / "frontend" / "assets" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload an image file and return its URL."""
    import uuid
    ext = Path(file.filename).suffix if file.filename else ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = UPLOAD_DIR / filename
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"url": f"/assets/uploads/{filename}"}

# ── Health check ───────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "city-town-api", "version": "0.1.0"}


# ── Static files (frontend) ────────────────────────
# NOTE: Must be mounted last; root mount overrides all routes below it in Starlette

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    # Mount at root for SPA-style serving; explicit routes above still work
    # because FastAPI processes routes before falling through to mounts
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
