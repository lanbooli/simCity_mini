#!/bin/bash
# 城市小镇 - Start all services
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "=============================="
echo "  城市小镇 - Starting Services"
echo "=============================="

# Check Redis
echo "[1/3] Checking Redis..."
if redis-cli ping > /dev/null 2>&1; then
    echo "  Redis is running."
else
    echo "  Starting Redis..."
    brew services start redis 2>/dev/null || redis-server --daemonize yes 2>/dev/null || {
        echo "  ERROR: Redis is not available. Please install and start Redis first."
        echo "  Install: brew install redis && brew services start redis"
        exit 1
    }
    sleep 1
fi

# Check LM Studio
echo "[2/3] Checking LM Studio..."
LM_URL="${LMSTUDIO_BASE_URL:-http://192.168.50.223:1234}"
if curl -s "$LM_URL/v1/models" > /dev/null 2>&1; then
    echo "  LM Studio is running at $LM_URL"
else
    echo "  WARNING: LM Studio not responding at $LM_URL"
    echo "  Dialogue features will use fallback responses."
fi

# Initialize database
echo "[3/3] Initializing database..."
python scripts/init_db.py

echo ""
echo "=============================="
echo "  Starting Supervisor..."
echo "=============================="
echo ""
echo "  Frontend: http://localhost:${API_PORT:-8000}"
echo "  API Docs: http://localhost:${API_PORT:-8000}/docs"
echo ""
echo "  Press Ctrl+C to stop all processes."
echo ""

# Start supervisor (manages all game processes)
python -m src.supervisor start
