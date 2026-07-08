#!/bin/bash
# Start ALSA app without IBKR - all services in background
# Usage: bash start-alsa.sh
#        PUBLIC_IP=your.ip.here bash start-alsa.sh  (for network access)
#
# To stop: bash stop-alsa.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
PUBLIC_IP="${PUBLIC_IP:-localhost}"
LOGS_DIR="$PROJECT_DIR/logs"

# Create logs directory if it doesn't exist
mkdir -p "$LOGS_DIR"

# Cleanup handler for Ctrl+C / SIGTERM
cleanup() {
    echo ""
    echo "Shutting down ALSA services..."
    # Kill using PID files first (precise, graceful)
    for pid_file in "$PROJECT_DIR"/.alsa-*.pid; do
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            kill "$pid" 2>/dev/null || true
            rm -f "$pid_file"
        fi
    done
    # Fallback pkill for any remaining processes
    pkill -f "tsx server.ts" 2>/dev/null || true
    pkill -f "vite --host" 2>/dev/null || true
    pkill -f "run_py_service" 2>/dev/null || true
    pkill -f "uvicorn" 2>/dev/null || true
    pkill -f "celery -A app.worker.celery_app" 2>/dev/null || true
    echo "All services stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

# Kill any existing instances before starting fresh
echo "Stopping any existing services..."
pkill -f "tsx server.ts" 2>/dev/null || true
pkill -f "vite --host" 2>/dev/null || true
pkill -f "run_py_service" 2>/dev/null || true
pkill -f "uvicorn" 2>/dev/null || true
pkill -f "celery -A app.worker.celery_app" 2>/dev/null || true
sleep 1

# Clean up stale PID files from previous runs
rm -f "$PROJECT_DIR"/.alsa-*.pid

# All services run from project root so npx can find package.json
cd "$PROJECT_DIR"

# --- Start Express API gateway (port 3000) ---
setsid bash -c 'HOST=0.0.0.0 exec npx tsx server.ts' > "$LOGS_DIR/api.log" 2>&1 &
echo $! > "$PROJECT_DIR/.alsa-api.pid"
echo "API started (PID $(cat "$PROJECT_DIR/.alsa-api.pid"))"

# --- Start Vite dev server (port 5173) ---
setsid bash -c 'exec npx vite --host 0.0.0.0 --port 5173' > "$LOGS_DIR/vite.log" 2>&1 &
echo $! > "$PROJECT_DIR/.alsa-vite.pid"
echo "Vite dev server started (PID $(cat "$PROJECT_DIR/.alsa-vite.pid"))"

# --- Start Python FastAPI service (port 8001) ---
AKSHARE_ENABLED=true nohup "$PROJECT_DIR/run_py_service_with_env.sh" > "$LOGS_DIR/py_api.log" 2>&1 &
echo $! > "$PROJECT_DIR/.alsa-python.pid"
echo "Python API started (PID $(cat "$PROJECT_DIR/.alsa-python.pid"))"

# --- Start Celery Worker (async task queue) ---
# Purge any stale tasks left in Redis from a previous unclean shutdown
PYTHONPATH="$PROJECT_DIR/python_service" "$PROJECT_DIR/python_service/.venv/bin/celery" \
    -A app.worker.celery_app purge -f 2>/dev/null || true
PYTHONPATH="$PROJECT_DIR/python_service" REDIS_URL=redis://localhost:6379/0 \
    nohup "$PROJECT_DIR/python_service/.venv/bin/celery" -A app.worker.celery_app worker --loglevel=info > "$LOGS_DIR/celery.log" 2>&1 &
echo $! > "$PROJECT_DIR/.alsa-celery.pid"
echo "Celery worker started (PID $(cat "$PROJECT_DIR/.alsa-celery.pid"))"

echo "---"
echo "ALSA app is running!"
echo "  Frontend: http://${PUBLIC_IP}:5173"
echo "  API:      http://localhost:3000/api/health"
echo ""
echo "To stop:  $PROJECT_DIR/stop-alsa.sh"
echo ""
echo "To view logs:"
echo "  tail -f $LOGS_DIR/api.log"
echo "  tail -f $LOGS_DIR/vite.log"
echo "  tail -f $LOGS_DIR/py_api.log"
echo "  tail -f $LOGS_DIR/celery.log"
