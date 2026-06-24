#!/bin/bash
# Restart all ALSA backend services (Python + Node + Vite)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
LOGS_DIR="$PROJECT_DIR/logs"

# Ensure logs directory exists
mkdir -p "$LOGS_DIR"

# Kill existing processes
echo "Stopping existing services..."
pkill -f "uvicorn.*8001" 2>/dev/null || true
pkill -f "tsx server.ts" 2>/dev/null || true
pkill -f "vite --host" 2>/dev/null || true
sleep 2

# All services run from project root
cd "$PROJECT_DIR"

# --- Start Python FastAPI service (port 8001) ---
echo "Starting Python service..."
AKSHARE_ENABLED=true nohup "$PROJECT_DIR/run_py_service_with_env.sh" > "$LOGS_DIR/py_api.log" 2>&1 &
PYTHON_PID=$!
echo "Python service started (PID: $PYTHON_PID)"

sleep 3

# --- Start Express API gateway (port 3000) ---
echo "Starting Node server..."
nohup npx tsx server.ts > "$LOGS_DIR/server.log" 2>&1 &
NODE_PID=$!
echo "Node server started (PID: $NODE_PID)"

sleep 2

# --- Start Vite dev server (port 5173) ---
echo "Starting Vite dev server..."
nohup npx vite --host 0.0.0.0 > "$LOGS_DIR/vite.log" 2>&1 &
VITE_PID=$!
echo "Vite started (PID: $VITE_PID)"

sleep 2

# Verify services
echo ""
echo "Checking services..."
if curl -s http://127.0.0.1:8001/api/health > /dev/null 2>&1; then
    echo "  [OK] Python API on port 8001"
else
    echo "  [WARNING] Python API not responding on port 8001"
fi

if curl -s http://127.0.0.1:3000/api/health > /dev/null 2>&1; then
    echo "  [OK] Node API on port 3000"
else
    echo "  [WARNING] Node API not responding on port 3000"
fi
echo ""
echo "Done! All services restarted."
