#!/usr/bin/env python3
"""
Supervisor process: manages lifecycle of all game processes.
Usage: python -m src.supervisor [start|stop|status]
"""

import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings

DATA_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "data"
PROCESS_STATUS_FILE = DATA_DIR / "processes.json"
PID_FILE = DATA_DIR / "supervisor.pid"
ADMIN_CMD_CHANNEL = "admin:process:cmd"
MAX_RESTART_COUNT = 5
RESTART_WINDOW_SECONDS = 30

PROCESSES = {
    "system": {
        "module": "src.system.process",
        "args": [],
        "env": {},
        "type": "system",
        "description": "时间/天气/事件系统",
    },
    "llm_gateway": {
        "module": "src.llm.gateway",
        "args": [],
        "env": {},
        "type": "gateway",
        "description": "LLM Gateway (LM Studio)",
    },
    "player": {
        "module": "src.player.process",
        "args": ["player_001"],
        "env": {"PLAYER_ID": "player_001"},
        "type": "player",
        "description": "玩家进程",
    },
}

NPC_IDS = [
    "npc_li_ming", "npc_wang_fang", "npc_zhang_wei", "npc_chen_xue", "npc_liu_jie",
    "npc_photo_01", "npc_photo_02", "npc_photo_03", "npc_photo_04", "npc_photo_05",
    "npc_photo_06", "npc_photo_07", "npc_photo_08", "npc_photo_09", "npc_photo_10",
    "npc_photo_11", "npc_photo_12", "npc_photo_13",
]

API_PROCESS = {
    "module": "uvicorn",
    "args": ["src.api.server:app", "--host", settings.api_host, "--port", str(settings.api_port)],
    "env": {},
}


class Supervisor:
    def __init__(self):
        self.children: dict[str, subprocess.Popen] = {}
        self._started_at: dict[str, str] = {}
        self._types: dict[str, str] = {}
        self._descriptions: dict[str, str] = {}
        self._restart_history: dict[str, list[float]] = {}
        self._cmd_thread: threading.Thread | None = None
        self._running = False

    def _acquire_pid_lock(self) -> bool:
        """Prevent duplicate supervisor instances via PID file."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if PID_FILE.exists():
            try:
                old_pid = int(PID_FILE.read_text().strip())
                os.kill(old_pid, 0)  # Check if process exists
                print(f"ERROR: Supervisor already running (PID {old_pid}). Stop it first with: python -m src.supervisor stop")
                return False
            except (OSError, ValueError):
                PID_FILE.unlink()  # Stale lock
        PID_FILE.write_text(str(os.getpid()))
        return True

    def _release_pid_lock(self):
        if PID_FILE.exists():
            try:
                if int(PID_FILE.read_text().strip()) == os.getpid():
                    PID_FILE.unlink()
            except (ValueError, OSError):
                pass

    def _check_port_available(self, host: str, port: int) -> bool:
        """Check if TCP port is available before spawning API."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.bind((host, port))
            sock.close()
            return True
        except OSError:
            return False

    def _cleanup_orphans(self):
        """Kill orphaned game processes from previous runs using shell commands."""
        current_pid = os.getpid()
        patterns = [
            "src.npc.process", "src.system.process", "src.player.process",
            "src.llm.gateway", "src.llm.tts_gateway",
            "uvicorn src.api.server",
        ]
        for pat in patterns:
            try:
                result = subprocess.run(
                    ["pgrep", "-f", pat], capture_output=True, text=True
                )
                for pid_str in result.stdout.strip().split("\n"):
                    if not pid_str:
                        continue
                    pid = int(pid_str)
                    if pid == current_pid:
                        continue
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except OSError:
                        pass
            except Exception:
                pass
        time.sleep(1)
        # Force kill survivors
        for pat in patterns:
            try:
                result = subprocess.run(
                    ["pgrep", "-f", pat], capture_output=True, text=True
                )
                for pid_str in result.stdout.strip().split("\n"):
                    if not pid_str:
                        continue
                    pid = int(pid_str)
                    if pid == current_pid:
                        continue
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
            except Exception:
                pass
        # Clean up stale PID file
        if PID_FILE.exists():
            try:
                old_pid = int(PID_FILE.read_text().strip())
                try:
                    os.kill(old_pid, 0)
                except OSError:
                    PID_FILE.unlink()  # Stale lock
            except (ValueError, OSError):
                PID_FILE.unlink()

    def _get_dead_npc_ids(self) -> set[str]:
        """Query database for NPCs marked as dead."""
        try:
            from src.common.database import get_connection, fetch_all
            conn = get_connection()
            rows = fetch_all(conn, "SELECT id FROM npc WHERE is_dead = 1")
            conn.close()
            return {r["id"] for r in rows}
        except Exception as e:
            print(f"[supervisor] Failed to query dead NPCs: {e}")
            return set()

    def _can_restart(self, name: str) -> bool:
        """Restart backoff: max MAX_RESTART_COUNT restarts within RESTART_WINDOW_SECONDS."""
        now = time.time()
        history = self._restart_history.setdefault(name, [])
        history = [t for t in history if now - t < RESTART_WINDOW_SECONDS]
        self._restart_history[name] = history
        if len(history) >= MAX_RESTART_COUNT:
            print(f"[{name}] Too many restarts ({len(history)} in {RESTART_WINDOW_SECONDS}s). Giving up.")
            return False
        history.append(now)
        return True

    def start(self):
        """Start all processes."""
        # Kill any orphaned game processes from previous runs
        self._cleanup_orphans()

        if not self._acquire_pid_lock():
            sys.exit(1)

        print("=== 城市小镇 Supervisor ===")
        print(f"Starting all processes...")

        # 1. System process
        print("[system] Starting system process...")
        self._spawn("system", PROCESSES["system"])

        # 2. Wait for system to initialize
        time.sleep(2)

        # 3. LLM Gateway (must start before NPCs)
        print("[llm_gateway] Starting LLM Gateway...")
        self._spawn("llm_gateway", PROCESSES["llm_gateway"])
        time.sleep(1)

        # 3.5 TTS Gateway (mlx_audio venv, must start before NPCs that send TTS requests)
        if settings.tts_enabled:
            print("[tts_gateway] Starting TTS Gateway...")
            self._spawn_tts_gateway()
            time.sleep(3)  # Wait for MLX model to load (~3s)

        # 4. Start all NPC processes (skip dead NPCs)
        dead_npc_ids = self._get_dead_npc_ids()
        for npc_id in NPC_IDS:
            if npc_id in dead_npc_ids:
                print(f"[npc:{npc_id}] Skipping dead NPC")
                continue
            print(f"[npc:{npc_id}] Starting NPC process...")
            self._spawn(npc_id, {
                "module": "src.npc.process",
                "args": [npc_id],
                "env": {"NPC_ID": npc_id},
            })

        # 5. Player process
        print("[player] Starting player process...")
        self._spawn("player", PROCESSES["player"])

        # 6. API server (check port first)
        time.sleep(1)
        if self._check_port_available(settings.api_host, settings.api_port):
            print(f"[api] Starting API server on {settings.api_host}:{settings.api_port}...")
            self._spawn("api", API_PROCESS)
        else:
            print(f"[api] ERROR: Port {settings.api_port} already in use! Cannot start API.")
            print(f"  → Kill the process using port {settings.api_port} and try again.")

        print(f"\nAll processes started. {len(self.children)} processes running.")
        print(f"Frontend: http://localhost:{settings.api_port}")
        print("Press Ctrl+C to stop all processes.")

        # Start admin command listener in background thread
        self._running = True
        self._cmd_thread = threading.Thread(target=self._listen_admin_commands, daemon=True)
        self._cmd_thread.start()
        # Start health monitor thread
        self._health_thread = threading.Thread(target=self._health_monitor_loop, daemon=True)
        self._health_thread.start()
        self._write_status_file()

    def stop(self):
        """Stop all processes gracefully."""
        print("\nStopping all processes...")
        self._running = False
        for name, proc in list(self.children.items()):
            print(f"[{name}] Sending SIGTERM...")
            try:
                proc.terminate()
            except Exception:
                pass

        # Wait for graceful shutdown
        time.sleep(3)

        # Force kill any remaining
        for name, proc in list(self.children.items()):
            if proc.poll() is None:
                print(f"[{name}] Force killing...")
                try:
                    proc.kill()
                except Exception:
                    pass

        self.children.clear()
        self._write_status_file()
        self._release_pid_lock()
        print("All processes stopped.")

    def status(self):
        """Print status of all child processes."""
        if not self.children:
            print("No processes managed by this supervisor.")
            return
        for name, proc in self.children.items():
            rc = proc.poll()
            status = "RUNNING" if rc is None else f"EXITED ({rc})"
            print(f"  [{name}] {status} (PID: {proc.pid})")

    def _health_monitor_loop(self):
        """Background thread: check process health via Redis, restart stale ones."""
        HEALTH_TIMEOUT = 180  # seconds: if no health report within this time, consider hung
        CHECK_INTERVAL = 20  # seconds between checks
        
        # Map process names used in health reports to supervisor child names
        HEALTH_TO_CHILD = {
            "system": "system",
            "llm_gateway": "llm_gateway",
            "tts": "tts_gateway",
            "player:player_001": "player",
        }
        # NPCs: health key is "npc:{npc_id}", child name is npc_id
        
        while self._running:
            time.sleep(CHECK_INTERVAL)
            try:
                import redis as _redis
                r = _redis.from_url(getattr(settings, "redis_url", "redis://localhost:6379"))
                
                # Scan all health keys
                keys = r.keys("health:*")
                now = time.time()
                
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    name = key_str[len("health:"):]
                    val = r.get(key)
                    if not val:
                        continue
                    try:
                        data = json.loads(val)
                    except json.JSONDecodeError:
                        continue
                    
                    ts = data.get("timestamp", 0)
                    age = now - ts
                    
                    if age < HEALTH_TIMEOUT:
                        continue  # healthy
                    
                    # Map health name to supervisor child name
                    child_name = HEALTH_TO_CHILD.get(name, name)
                    # For NPCs, health key is "npc:{npc_id}", child name is npc_id
                    if name.startswith("npc:"):
                        child_name = name[4:]  # "npc_photo_01"
                    
                    # Check if process is still alive (might just be slow)
                    proc = self.children.get(child_name)
                    if proc and proc.poll() is None:
                        # Process alive but not reporting health — it's hung
                        print(f"[health] {child_name} is alive but not reporting health ({age:.0f}s stale). Restarting...")
                        self._restart_process(child_name)
                    elif proc is None:
                        # Check if this is a dead NPC — clean up stale health key
                        if name.startswith("npc:") and child_name.startswith("npc_"):
                            try:
                                dead_ids = self._get_dead_npc_ids()
                                if child_name in dead_ids:
                                    r.delete(key)
                                    continue
                            except Exception:
                                pass
                        print(f"[health] {child_name} has health key but no supervisor child. Skipping.")
                
                r.close()
            except Exception as e:
                # Don't spam logs if Redis is temporarily unavailable
                pass

    def _write_status_file(self):
        """Write current process status to data/processes.json for the API server."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        processes = {}
        for name, proc in self.children.items():
            rc = proc.poll()
            processes[name] = {
                "pid": proc.pid,
                "status": "running" if rc is None else "stopped",
                "exit_code": rc,
                "started_at": self._started_at.get(name, ""),
                "type": self._types.get(name, "npc" if name.startswith("npc_") else "unknown"),
                "description": self._descriptions.get(name, ""),
            }
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "processes": processes,
        }
        try:
            PROCESS_STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[supervisor] Failed to write status file: {e}")

    def _listen_admin_commands(self):
        """Background thread: subscribe to Redis admin commands (restart/stop)."""
        try:
            import redis
            r = redis.from_url(settings.redis_url)
            pubsub = r.pubsub()
            pubsub.subscribe(ADMIN_CMD_CHANNEL)
            print(f"[supervisor] Admin command listener started on '{ADMIN_CMD_CHANNEL}'")
            while self._running:
                msg = pubsub.get_message(timeout=1.0)
                if msg and msg["type"] == "message":
                    try:
                        cmd = json.loads(msg["data"])
                        action = cmd.get("action", "")
                        target = cmd.get("process", "")
                        print(f"[supervisor] Admin command: {action} {target}")
                        if action == "restart" and target in self.children:
                            self._restart_process(target)
                        elif action == "stop" and target in self.children:
                            self._stop_process(target)
                    except json.JSONDecodeError:
                        pass
                elif msg is None:
                    pass  # timeout, continue
            pubsub.close()
            r.close()
        except Exception as e:
            print(f"[supervisor] Admin command listener error: {e}")

    def _restart_process(self, name: str):
        """Restart a single process by name."""
        proc = self.children.get(name)
        if proc:
            print(f"[{name}] Restarting...")
            try:
                proc.terminate()
                time.sleep(1)
                if proc.poll() is None:
                    proc.kill()
                    time.sleep(0.5)
            except Exception:
                pass

        if name == "tts_gateway" and settings.tts_enabled:
            self._spawn_tts_gateway()
        else:
            config = self._find_config(name)
            if config:
                self._spawn(name, config)
        self._write_status_file()

    def _stop_process(self, name: str):
        """Stop a single process by name (no restart)."""
        proc = self.children.get(name)
        if proc:
            print(f"[{name}] Stopping...")
            try:
                proc.terminate()
                time.sleep(1)
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
            self.children.pop(name, None)
            self._write_status_file()

    def _spawn_tts_gateway(self):
        """Spawn TTS Gateway using mlx_audio venv Python."""
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env["HF_ENDPOINT"] = settings.hf_endpoint
        env["TTS_MODEL_PATH"] = settings.tts_model_path
        env["TTS_NARRATOR_MODEL_PATH"] = settings.tts_narrator_model_path
        env["TTS_NARRATOR_INSTRUCT"] = settings.tts_narrator_instruct
        env["TTS_VOICE_REFS_DIR"] = settings.tts_voice_refs_dir
        env["TTS_AUDIO_DIR"] = settings.tts_audio_dir
        env["TTS_MAX_CONCURRENT"] = str(settings.tts_max_concurrent)
        env["TTS_CLEANUP_AGE_HOURS"] = str(settings.tts_cleanup_age_hours)
        env["REDIS_URL"] = settings.redis_url

        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = open(os.path.join(log_dir, "tts_gateway.log"), "a", buffering=1)
        cmd = [settings.tts_python_path, "-m", "src.llm.tts_gateway"]
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.children["tts_gateway"] = proc
        self._started_at["tts_gateway"] = datetime.now(timezone.utc).isoformat()
        self._types["tts_gateway"] = "gateway"
        self._descriptions["tts_gateway"] = "TTS Gateway (语音合成)"
        self._write_status_file()

    def _spawn(self, name: str, config: dict):
        """Spawn a single subprocess."""
        env = os.environ.copy()
        env.update(config.get("env", {}))
        env["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        cmd = [sys.executable, "-m", config["module"]] + config.get("args", [])
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = open(os.path.join(log_dir, f"{name}.log"), "a", buffering=1)
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.children[name] = proc
        self._started_at[name] = datetime.now(timezone.utc).isoformat()
        self._types[name] = config.get("type", "npc" if name.startswith("npc_") else "unknown")
        self._descriptions[name] = config.get("description", "")
        self._write_status_file()

    def watch(self):
        """Wait for all children and handle restarts with backoff."""
        try:
            while self.children:
                for name, proc in list(self.children.items()):
                    rc = proc.poll()
                    if rc is not None:
                        print(f"[{name}] Process exited with code {rc} (PID {proc.pid}).")
                        # Read last log from file for diagnostics
                        log_path = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "logs", f"{name}.log"
                        )
                        if os.path.exists(log_path):
                            try:
                                with open(log_path, "r") as lf:
                                    lf.seek(0, 2)
                                    size = lf.tell()
                                    if size > 500:
                                        lf.seek(max(0, size - 500))
                                    else:
                                        lf.seek(0)
                                    last = lf.read()
                                print(f"[{name}] Last log output:\n{last}")
                            except Exception:
                                pass

                        if not self._can_restart(name):
                            print(f"[{name}] Removing from watch list.")
                            del self.children[name]
                            self._write_status_file()
                            continue

                        # Skip dead NPCs (don't restart deceased characters)
                        if name.startswith("npc_"):
                            dead_ids = self._get_dead_npc_ids()
                            if name in dead_ids:
                                print(f"[{name}] NPC is dead. Removing from watch list.")
                                del self.children[name]
                                self._write_status_file()
                                continue

                        # Special handling for API: check port before restart
                        if name == "api":
                            if not self._check_port_available(settings.api_host, settings.api_port):
                                print(f"[api] Port {settings.api_port} still in use. Skipping restart (port conflict).")
                                del self.children[name]
                                self._write_status_file()
                                continue

                        print(f"[{name}] Restarting in 3s...")
                        time.sleep(3)
                        if name == "tts_gateway" and settings.tts_enabled:
                            self._spawn_tts_gateway()
                        else:
                            config = self._find_config(name)
                            if config:
                                self._spawn(name, config)
                            else:
                                print(f"[{name}] Cannot restart: config not found.")
                                del self.children[name]
                                self._write_status_file()
                time.sleep(2)
        except KeyboardInterrupt:
            self.stop()

    def _find_config(self, name: str) -> dict:
        if name == "system":
            return PROCESSES["system"]
        elif name == "llm_gateway":
            return PROCESSES["llm_gateway"]
        elif name == "tts_gateway":
            return None  # TTS Gateway has its own spawn method
        elif name == "player":
            return PROCESSES["player"]
        elif name == "api":
            return API_PROCESS
        elif name.startswith("npc_"):
            return {
                "module": "src.npc.process",
                "args": [name],
                "env": {"NPC_ID": name},
            }
        return None


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    sup = Supervisor()

    if cmd == "start":
        sup.start()
        sup.watch()
    elif cmd == "stop":
        # Kill running supervisor and all its children via pgrep
        if PID_FILE.exists():
            try:
                old_pid = int(PID_FILE.read_text().strip())
                print(f"Stopping supervisor (PID {old_pid})...")
                try:
                    os.kill(old_pid, signal.SIGTERM)
                    time.sleep(2)
                    try:
                        os.kill(old_pid, 0)
                        os.kill(old_pid, signal.SIGKILL)
                    except OSError:
                        pass
                except OSError:
                    pass
                PID_FILE.unlink()
            except (ValueError, OSError) as e:
                print(f"Error: {e}")
                PID_FILE.unlink()
        else:
            print("No running supervisor found (no PID file).")
        # Fallback: kill all game processes by pattern
        sup._cleanup_orphans()
        print("Supervisor stopped.")
    elif cmd == "status":
        sup.status()
    elif cmd == "run":
        # Run in foreground (single process mode for debugging)
        sup.start()
        sup.watch()
    else:
        print(f"Usage: python -m src.supervisor [start|stop|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()
