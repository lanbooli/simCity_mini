#!/bin/bash
# 城市小镇 - Stop all services
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "Stopping 城市小镇 services..."

# Send SIGTERM to any running game processes
pkill -f "src.system.process" 2>/dev/null && echo "  System process stopped." || true
pkill -f "src.npc.process" 2>/dev/null && echo "  NPC processes stopped." || true
pkill -f "src.player.process" 2>/dev/null && echo "  Player process stopped." || true
pkill -f "src.api.server" 2>/dev/null && echo "  API server stopped." || true
pkill -f "uvicorn.*src.api.server" 2>/dev/null && echo "  Uvicorn stopped." || true
pkill -f "src.supervisor" 2>/dev/null && echo "  Supervisor stopped." || true

echo "Done."
