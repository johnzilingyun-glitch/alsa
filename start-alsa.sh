#!/bin/bash
# Start ALSA app without IBKR - survives CLI exit
cd /home/ubuntu/work/alsa || exit 1

# Kill any existing instances
pkill -f "tsx server.ts" 2>/dev/null
pkill -f "vite --host" 2>/dev/null
pkill -f "run_py_service" 2>/dev/null
pkill -f "uvicorn" 2>/dev/null
sleep 1

# Start API server
nohup npx tsx server.ts > /home/ubuntu/work/alsa/logs/api.log 2>&1 &
echo "API started (PID $!)"

# Start Vite dev server  
nohup npx vite --host 0.0.0.0 > /home/ubuntu/work/alsa/logs/vite.log 2>&1 &
echo "Vite started (PID $!)"

# Start Python FastAPI service (with AkShare enabled for Chinese markets)
AKSHARE_ENABLED=true nohup /home/ubuntu/work/alsa/python_service/.venv/bin/python3.11 /home/ubuntu/work/alsa/run_py_service.py > /home/ubuntu/work/alsa/logs/py_api.log 2>&1 &
echo "Python API started (PID $!)"

echo "---"
echo "ALSA app is running!"
echo "  Frontend: http://1.117.62.178:5173"
echo "  API:      http://localhost:3000/api/health"
echo ""
echo "To stop:   pkill -f 'tsx server.ts'; pkill -f 'vite --host'"
echo "To view logs:"
echo "  tail -f ~/work/alsa/logs/api.log"
echo "  tail -f ~/work/alsa/logs/vite.log"
