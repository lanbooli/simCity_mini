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
echo "🧹 清理 Python 缓存..."
find src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find src -name "*.pyc" -delete 2>/dev/null || true
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

# ── Swift 桌面宠物（自动编译 + 启动）────────────────
PET_SRC="desktop_pet/native/PetApp.swift"
PET_WIN="desktop_pet/native/PetWindow.swift"
PET_BIN="desktop_pet/native/PetApp"
PET_DIR="desktop_pet/native"

if [ -f "$PET_SRC" ]; then
    NEED_BUILD=0
    if [ ! -f "$PET_BIN" ]; then
        NEED_BUILD=1
    elif [ "$PET_SRC" -nt "$PET_BIN" ] || [ "$PET_WIN" -nt "$PET_BIN" ]; then
        NEED_BUILD=1
    fi

    if [ "$NEED_BUILD" -eq 1 ]; then
        echo "🔨 编译桌面宠物..."
        if command -v swiftc &>/dev/null; then
            (cd "$PET_DIR" && swiftc main.swift PetApp.swift -o PetApp -framework SwiftUI -framework AppKit -framework AVFoundation 2>&1) && echo "✅ 编译成功" || {
                echo "⚠️  编译失败，使用旧版本（如有）"
            }
        elif command -v xcodebuild &>/dev/null; then
            echo "⚠️  swiftc 不可用，请用 Xcode 编译"
        fi
    fi

    if [ -f "$PET_BIN" ]; then
        echo "🐱 启动桌面宠物..."
        ./"$PET_BIN" &
    else
        echo "💡 桌面宠物未编译：cd $PET_DIR && swiftc main.swift PetApp.swift -o PetApp -framework SwiftUI -framework AppKit -framework AVFoundation"
    fi
fi

echo "🌟 全部就绪 (Ctrl+C 停止)"
wait
