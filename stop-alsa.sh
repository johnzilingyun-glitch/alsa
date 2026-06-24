#!/bin/bash
# Stop all ALSA services started by start-alsa.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

echo "Stopping ALSA services..."

# --- Phase 1: Kill by PID files (precise) ---
for service in api vite python celery; do
    pid_file="$PROJECT_DIR/.alsa-${service}.pid"
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if kill "$pid" 2>/dev/null; then
            echo "  Stopped $service (PID $pid)"
        else
            echo "  $service (PID $pid) not running, removing stale PID file"
        fi
        rm -f "$pid_file"
    fi
done

# --- Phase 2: Fallback pkill for any remaining processes ---
pkill -f "tsx server.ts" 2>/dev/null && echo "  Stopped tsx server" || true
pkill -f "vite --host" 2>/dev/null && echo "  Stopped vite" || true
pkill -f "run_py_service" 2>/dev/null && echo "  Stopped run_py_service" || true
pkill -f "uvicorn" 2>/dev/null && echo "  Stopped uvicorn" || true
pkill -f "celery -A app.worker.celery_app" 2>/dev/null && echo "  Stopped celery worker" || true

echo "All services stopped."
