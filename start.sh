#!/bin/bash
cd "$(dirname "$0")"

cleanup() {
    echo ""
    echo "🛑 正在停止..."
    kill %1 2>/dev/null
    pkill -f "src.supervisor" 2>/dev/null
    pkill -f "PetApp" 2>/dev/null
    wait 2>/dev/null
    echo "👋 已停止"
    exit 0
}
trap cleanup SIGINT SIGTERM

echo "🧹 清理旧进程..."
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
sleep 0.5

echo "🚀 启动城市小镇..."
source venv/bin/activate
python -m src.supervisor start &
SUPERVISOR_PID=$!

echo "⏳ 等待服务就绪..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/api/v1/npcs > /dev/null 2>&1; then
        echo "✅ 服务已就绪"
        break
    fi
    sleep 1
done

open http://localhost:8000 2>/dev/null || true

# Swift 桌面宠物
PET_BIN="desktop_pet/native/PetApp"
if [ -f "$PET_BIN" ]; then
    echo "🐱 启动桌面宠物..."
    ./"$PET_BIN" &
else
    echo "💡 桌面宠物未编译：cd desktop_pet/native && swiftc PetApp.swift -o PetApp -framework SwiftUI -framework AppKit -framework AVFoundation"
fi

echo "🌟 全部就绪 (Ctrl+C 停止)"
wait
