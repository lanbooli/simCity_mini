"""
桌面宠物 — 悬浮窗 + 气泡对话 + 语音播放
连接现有 city-town WebSocket API，复用 LM Studio 对话和 TTS
运行方式: cd city-town && source venv/bin/activate && python desktop_pet/pet_app.py
"""

import tkinter as tk
from tkinter import ttk
import json
import threading
import time
import os
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime

try:
    import websocket
except ImportError:
    print("需要 websocket-client: source venv/bin/activate && pip install websocket-client")
    sys.exit(1)

# 尝试导入 PIL（可选，用于全身照缩放）
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


# ── 配置 ────────────────────────────────────────────
WS_URL = "ws://localhost:8000/ws/game?player_id=player_001"
API_BASE = "http://localhost:8000"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVATAR_DIR = os.path.join(PROJECT_ROOT, "frontend", "assets", "avatars")
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "frontend", "assets", "uploads")

# 窗口大小
WIN_W, WIN_H = 320, 520


class DesktopPet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("桌面小助手")
        self.root.geometry(f"{WIN_W}x{WIN_H}+{self.root.winfo_screenwidth()-WIN_W-40}+60")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#000000")
        self.root.wm_attributes("-transparentcolor", "#000000")

        # 状态
        self.npcs = {}
        self.current_npc = None
        self.ws = None
        self.audio_process = None
        self.bubble_ids = []
        self.bubble_timer = None

        self._build_ui()
        self._load_npcs()
        self._connect_ws()

        self.root.after(100, self._ws_poll)
        self.root.mainloop()

    # ── UI ──────────────────────────────────────────

    def _build_ui(self):
        """构建悬浮窗UI"""
        # 主容器
        self.main_frame = tk.Frame(self.root, bg="#1a1a2e", bd=0)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # 标题栏（可拖动）
        self.title_bar = tk.Frame(self.main_frame, bg="#16213e", height=36, cursor="fleur")
        self.title_bar.pack(fill=tk.X)
        self.title_bar.bind("<Button-1>", self._start_drag)
        self.title_bar.bind("<B1-Motion>", self._on_drag)

        title_lbl = tk.Label(self.title_bar, text="🌸 桌面小助手", bg="#16213e", fg="#e0e0ff",
                             font=("Microsoft YaHei", 12, "bold"))
        title_lbl.pack(side=tk.LEFT, padx=12)

        close_btn = tk.Label(self.title_bar, text="✕", bg="#16213e", fg="#8888aa",
                             font=("Arial", 14), cursor="hand2")
        close_btn.pack(side=tk.RIGHT, padx=10, pady=4)
        close_btn.bind("<Button-1>", lambda e: self.root.destroy())

        # 角色选择
        self.selector_frame = tk.Frame(self.main_frame, bg="#1a1a2e")
        self.selector_frame.pack(fill=tk.X, padx=16, pady=(8, 0))
        tk.Label(self.selector_frame, text="对话角色", bg="#1a1a2e", fg="#8888aa",
                 font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self.npc_var = tk.StringVar()
        self.npc_combo = ttk.Combobox(self.selector_frame, textvariable=self.npc_var,
                                      state="readonly", width=16, font=("Microsoft YaHei", 11))
        self.npc_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.npc_combo.bind("<<ComboboxSelected>>", self._on_npc_change)

        # 头像 + 气泡区域
        self.avatar_frame = tk.Frame(self.main_frame, bg="#1a1a2e")
        self.avatar_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(12, 0))

        # 气泡层（在头像上方）
        self.bubble_canvas = tk.Canvas(self.avatar_frame, bg="#1a1a2e", bd=0, highlightthickness=0,
                                       height=100)
        self.bubble_canvas.pack(fill=tk.X, pady=(0, 5))

        # 头像
        self.avatar_label = tk.Label(self.avatar_frame, bg="#1a1a2e")
        self.avatar_label.pack(pady=(0, 10))
        self._set_default_avatar()

        # 角色名
        self.name_label = tk.Label(self.avatar_frame, text="选择角色", bg="#1a1a2e", fg="#c0c0e0",
                                   font=("Microsoft YaHei", 13, "bold"))
        self.name_label.pack()

        # 心情
        self.mood_label = tk.Label(self.avatar_frame, text="", bg="#1a1a2e", fg="#8888aa",
                                   font=("Microsoft YaHei", 10))
        self.mood_label.pack()

        # 输入区域
        self.input_frame = tk.Frame(self.main_frame, bg="#16213e")
        self.input_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=10)

        self.msg_entry = tk.Text(self.input_frame, height=2, bg="#0f0f23", fg="#e0e0ff",
                                 insertbackground="#e0e0ff", font=("Microsoft YaHei", 12),
                                 bd=0, padx=8, pady=6, wrap=tk.WORD)
        self.msg_entry.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self.msg_entry.bind("<Return>", self._on_send)

        send_btn = tk.Label(self.input_frame, text="发送", bg="#7c3aed", fg="white",
                            font=("Microsoft YaHei", 12, "bold"), padx=14, pady=6,
                            cursor="hand2")
        send_btn.pack(side=tk.RIGHT, padx=(8, 0))
        send_btn.bind("<Button-1>", self._on_send)

    # ── 拖动 ────────────────────────────────────────

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_x)
        y = self.root.winfo_y() + (event.y - self._drag_y)
        self.root.geometry(f"+{x}+{y}")

    # ── 头像 ────────────────────────────────────────

    def _set_default_avatar(self):
        """设置默认头像"""
        try:
            default_path = os.path.join(AVATAR_DIR, "default.png")
            if os.path.exists(default_path):
                img = tk.PhotoImage(file=default_path)
                img = img.subsample(max(1, img.width() // 100), max(1, img.height() // 100))
                self.avatar_label.configure(image=img, text="")
                self.avatar_label.image = img
            else:
                raise FileNotFoundError()
        except Exception:
            self.avatar_label.configure(image="", text="🌸", font=("Apple Color Emoji", 48))

    # ── 气泡 ────────────────────────────────────────

    def _show_bubble(self, text, is_player=False):
        """显示气泡"""
        text_color = "#ffffff" if is_player else "#e0e0ff"
        bubble_bg = "#7c3aed" if is_player else "#1e3a5f"

        # 清除旧气泡
        for bid in self.bubble_ids:
            self.bubble_canvas.delete(bid)
        self.bubble_ids = []

        # 取消之前的定时器
        if self.bubble_timer:
            self.root.after_cancel(self.bubble_timer)
            self.bubble_timer = None

        # 自动换行
        wrap_width = 260
        lines = self._wrap_text(text, wrap_width, 14)
        line_height = 22
        pad_x, pad_y = 12, 10
        bubble_w = min(wrap_width + pad_x * 2, 300)
        bubble_h = len(lines) * line_height + pad_y * 2

        # 居中
        canvas_w = self.bubble_canvas.winfo_width()
        x0 = max(5, (canvas_w - bubble_w) // 2) if canvas_w > 1 else 10
        x1 = x0 + bubble_w
        y0, y1 = 5, 5 + bubble_h

        bubble_id = self._draw_rounded_rect(x0, y0, x1, y1, bubble_bg, radius=12)
        text_id = self.bubble_canvas.create_text(
            x0 + pad_x, y0 + pad_y, text="\n".join(lines), anchor="nw", fill=text_color,
            font=("Microsoft YaHei", 12), width=bubble_w - pad_x * 2
        )

        self.bubble_canvas.tag_raise(text_id)
        self.bubble_ids = [bubble_id, text_id]

        # 8秒后淡出
        self.bubble_timer = self.root.after(8000, lambda: self._clear_bubble(0))

    def _draw_rounded_rect(self, x0, y0, x1, y1, color, radius=10):
        """绘制圆角矩形气泡"""
        r = radius
        points = [
            x0 + r, y0,
            x1 - r, y0,
            x1, y0,
            x1, y0 + r,
            x1, y1 - r,
            x1, y1,
            x1 - r, y1,
            x0 + r, y1,
            x0, y1,
            x0, y1 - r,
            x0, y0 + r,
            x0, y0,
        ]
        return self.bubble_canvas.create_polygon(points, fill=color, smooth=True, outline="")

    def _wrap_text(self, text, max_width, font_size):
        """简单文本换行"""
        chars_per_line = max(1, max_width // (font_size + 2))
        lines = []
        current = ""
        for char in text:
            current += char
            if len(current) >= chars_per_line:
                lines.append(current)
                current = ""
        if current:
            lines.append(current)
        return lines[:8]

    def _clear_bubble(self, step=0):
        """清除气泡（渐变）"""
        if step >= 5:
            for bid in self.bubble_ids:
                self.bubble_canvas.delete(bid)
            self.bubble_ids = []
            self.bubble_timer = None
            return
        self.bubble_timer = self.root.after(200, lambda: self._clear_bubble(step + 1))

    # ── NPC 数据 ─────────────────────────────────────

    def _find_avatar(self, npc_data):
        """查找 NPC 头像，优先全身照"""
        npc_id = npc_data.get("id", "")
        npc_name = npc_data.get("name", "")

        # 1. 检查全身照
        fullbody_paths = [
            os.path.join(UPLOAD_DIR, f"{npc_id}_fullbody.png"),
            os.path.join(UPLOAD_DIR, f"{npc_id}_fullbody.jpg"),
            os.path.join(UPLOAD_DIR, f"{npc_name}_fullbody.png"),
            os.path.join(UPLOAD_DIR, f"{npc_name}_fullbody.jpg"),
        ]
        for fp in fullbody_paths:
            if os.path.exists(fp):
                return fp

        # 2. 检查头像
        avatar_paths = [
            os.path.join(AVATAR_DIR, f"{npc_id}.png"),
            os.path.join(AVATAR_DIR, f"{npc_id}.jpg"),
            os.path.join(AVATAR_DIR, f"{npc_name}.png"),
            os.path.join(AVATAR_DIR, f"{npc_name}.jpg"),
            os.path.join(UPLOAD_DIR, f"{npc_id}.png"),
            os.path.join(UPLOAD_DIR, f"{npc_id}.jpg"),
        ]
        for ap in avatar_paths:
            if os.path.exists(ap):
                return ap

        return None

    def _display_avatar(self, avatar_path):
        """显示头像或全身照"""
        try:
            if HAS_PIL:
                img = Image.open(avatar_path)
                max_size = (200, 280) if "fullbody" in avatar_path.lower() else (120, 120)
                img.thumbnail(max_size, Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
            else:
                photo = tk.PhotoImage(file=avatar_path)
                if photo.width() > 200:
                    photo = photo.subsample(max(1, photo.width() // 120),
                                            max(1, photo.height() // 120))

            self.avatar_label.configure(image=photo, text="")
            self.avatar_label.image = photo
        except Exception:
            self._set_default_avatar()

    def _load_npcs(self):
        """从localhost API加载NPC列表"""
        try:
            import urllib.request
            url = f"{API_BASE}/api/v1/npcs"
            resp = urllib.request.urlopen(url, timeout=5)
            response = json.loads(resp.read().decode())
            data_list = response.get("data", [])
            npcs = {}
            for ndata in data_list:
                nid = ndata.get("id", "")
                if not nid:
                    continue

                # 直接从列表获取心情（current_mood），再查关系
                mood = ndata.get("current_mood", "neutral")
                relationship = "stranger"
                try:
                    rel_url = f"{API_BASE}/api/v1/npc/{nid}/relationship/player_001"
                    resp2 = urllib.request.urlopen(rel_url, timeout=3)
                    rel_data = json.loads(resp2.read().decode()).get("data", {})
                    relationship = rel_data.get("relationship_type", "stranger")
                except:
                    pass
                npcs[nid] = {
                    "id": nid,
                    "name": ndata.get("name", ""),
                    "mood": mood,
                    "relationship": relationship,
                    "personality": ndata.get("personality", ""),
                    "occupation": ndata.get("career", ""),
                    "gender": ndata.get("gender", ""),
                    "voice_type": ndata.get("voice_type", ""),
                }

            self.npcs = npcs
            names = []
            for v in npcs.values():
                rel = v.get("relationship", "")
                rel_icon = {"friend": "👫", "close": "💕", "lover": "❤️",
                            "family": "👨‍👩‍👧"}.get(rel, "")
                names.append(f"{rel_icon} {v['name']}")
            self.npc_combo["values"] = names

        except Exception as e:
            print(f"加载NPC失败: {e}")
            import traceback
            traceback.print_exc()
            # 降级
            fallback = (
                ["npc_li_ming", "npc_wang_fang", "npc_zhang_wei",
                 "npc_chen_xue", "npc_liu_jie"]
                + [f"npc_photo_{i:02d}" for i in range(1, 14)]
            )
            self.npcs = {nid: {"id": nid, "name": nid, "mood": "neutral"}
                         for nid in fallback}
            self.npc_combo["values"] = list(self.npcs.keys())

    def _on_npc_change(self, event=None):
        """NPC选择变更"""
        selected = self.npc_var.get()
        if not selected:
            return
        # 移除 emoji 和空格前缀
        selected_name = re.sub(r'^[^\w]*', '', selected).strip()
        if not selected_name:
            return

        for nid, ndata in self.npcs.items():
            if ndata['name'] == selected_name:
                self.current_npc = nid
                self.name_label.configure(text=selected_name)
                mood_text = ndata.get('mood', 'neutral')
                self.mood_label.configure(text=f"心情: {mood_text}")

                avatar_path = self._find_avatar(ndata)
                if avatar_path:
                    self._display_avatar(avatar_path)
                else:
                    self._set_default_avatar()
                break

    # ── WebSocket ────────────────────────────────────

    def _connect_ws(self):
        """连接WebSocket"""
        def run():
            self.ws = websocket.WebSocketApp(
                WS_URL,
                on_open=lambda ws: print("✅ WebSocket 已连接"),
                on_message=self._on_ws_message,
                on_error=lambda ws, e: print(f"WS Error: {e}"),
                on_close=lambda ws, code, msg: print(f"WS closed ({code}), 3s 后重连..."),
            )
            while True:
                try:
                    self.ws.run_forever(ping_interval=30, ping_timeout=10)
                except Exception as e:
                    print(f"WS 连接失败: {e}")
                time.sleep(3)

        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _on_ws_message(self, ws, message):
        """接收WebSocket消息"""
        try:
            msg = json.loads(message)
            msg_type = msg.get("type", "")
            data = msg.get("data", {})

            if msg_type == "dialogue_response":
                content = data.get("content", "")
                npc_name = data.get("npc_name", "")
                npc_id = data.get("npc_id", "")
                fav_change = data.get("favorability_change", "")
                new_mood = data.get("new_mood", "")
                action_name = data.get("action_name", "")

                if content:
                    prefix = f"{npc_name}: " if npc_name else ""
                    self.root.after(0, lambda: self._show_bubble(f"{prefix}{content}"))
                    # 好感变化提示
                    if fav_change:
                        try:
                            fc = int(fav_change)
                            if fc != 0:
                                icon = "↑" if fc > 0 else "↓"
                                self.root.after(2000, lambda: self._show_bubble(
                                    f"好感度 {icon}{abs(fc)}", is_player=False))
                        except:
                            pass
                if new_mood:
                    self.root.after(0, lambda: self.mood_label.configure(
                        text=f"心情: {new_mood}"))

            elif msg_type == "tts_audio":
                audio_url = data.get("audio_url", "")
                if audio_url:
                    self.root.after(0, lambda: self._play_audio(audio_url))

            elif msg_type == "npc_initiated_dialogue":
                content = data.get("content", "")
                npc_name = data.get("npc_name", "")
                npc_id = data.get("npc_id", "")
                if content and npc_name:
                    self.root.after(0, lambda: self._show_bubble(
                        f"{npc_name}: {content}", is_player=False))

            elif msg_type == "npc_state_update":
                npc_id = data.get("npc_id", "")
                mood = data.get("mood", "")
                if npc_id == self.current_npc and mood:
                    self.root.after(0, lambda: self.mood_label.configure(
                        text=f"心情: {mood}"))
                if npc_id in self.npcs and mood:
                    self.npcs[npc_id]["mood"] = mood

            elif msg_type == "greeting":
                content = data.get("content", "")
                npc_name = data.get("npc_name", "")
                if content and npc_name:
                    self.root.after(0, lambda: self._show_bubble(
                        f"👋 {npc_name}: {content}", is_player=False))

        except json.JSONDecodeError:
            pass

    def _ws_poll(self):
        """Tkinter定时轮询"""
        self.root.after(200, self._ws_poll)

    def _send_message(self, text):
        """发送对话"""
        if not self.current_npc:
            self._show_bubble("请先选择一个角色哦~")
            return
        if not self.ws or not self.ws.sock:
            self._show_bubble("连接中，请稍后...")
            return

        # 显示玩家消息
        self._show_bubble(text, is_player=True)
        msg = {
            "type": "dialogue_send",
            "data": {
                "npc_id": self.current_npc,
                "content": text,
            }
        }
        try:
            self.ws.send(json.dumps(msg))
        except Exception as e:
            self._show_bubble(f"发送失败: {e}")

    def _on_send(self, event=None):
        """发送按钮"""
        text = self.msg_entry.get("1.0", "end-1c").strip()
        if not text:
            return "break"
        self.msg_entry.delete("1.0", "end")
        self._send_message(text)
        return "break"

    # ── 语音播放 ─────────────────────────────────────

    def _play_audio(self, url):
        """播放音频（macOS用afplay）"""
        if not url:
            return
        try:
            # /assets/audio/xxx.wav → frontend/assets/audio/xxx.wav
            if url.startswith("/assets/"):
                full_path = os.path.join(PROJECT_ROOT, "frontend", url.lstrip("/"))
            elif url.startswith("/"):
                full_path = url
            elif url.startswith("static/"):
                full_path = os.path.join(PROJECT_ROOT, url)
            elif url.startswith("http"):
                full_path = url
            else:
                full_path = os.path.join(PROJECT_ROOT, url)

            if not os.path.exists(full_path) and not full_path.startswith("http"):
                print(f"Audio file not found: {full_path}")
                return

            # 停止之前的播放
            if self.audio_process:
                try:
                    self.audio_process.kill()
                except:
                    pass

            self.audio_process = subprocess.Popen(
                ["afplay", full_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"Audio error: {e}")


def main():
    try:
        import websocket
    except ImportError:
        print("请先安装 websocket-client:")
        print("  source venv/bin/activate && pip install websocket-client")
        sys.exit(1)

    pet = DesktopPet()


if __name__ == "__main__":
    main()
