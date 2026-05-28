#!/bin/bash
set -e

cd "$(dirname "$0")"

# 清端口
echo "🧹 清理旧进程..."
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
sleep 0.5

# 启动
echo "🚀 启动城市小镇..."
source venv/bin/activate
python -m src.supervisor start

# 打开浏览器（等api就绪后）
sleep 3
open http://localhost:8000 2>/dev/null || true
