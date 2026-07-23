#!/bin/bash
# Restart the FastAPI/Uvicorn Python backend service
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

pkill -9 -f "python -m uvicorn python_service.main:app" || true
sleep 1

cd "$PROJECT_DIR"
nohup "$PROJECT_DIR/python_service/.venv/bin/python" -m uvicorn python_service.main:app \
    --host 127.0.0.1 --port 8001 > "$PROJECT_DIR/logs/py_api.log" 2>&1 < /dev/null &
echo "Uvicorn started in background (PID $!)"
