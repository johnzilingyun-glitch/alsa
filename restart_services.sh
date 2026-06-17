#!/bin/bash
# Kill existing processes
pkill -f "uvicorn.*8001" 2>/dev/null
pkill -f "tsx server.ts" 2>/dev/null
sleep 2

# Start Python service
cd /home/ubuntu/work/alsa
source python_service/.venv/bin/activate
nohup python -m uvicorn python_service.main:app --host 0.0.0.0 --port 8001 > python_service.log 2>&1 &
echo "Python service started (PID: $!)"

sleep 3

# Start Node server
nohup npx tsx server.ts > logs/server.log 2>&1 &
echo "Node server started (PID: $!)"

sleep 2

# Verify services
echo "Checking services..."
curl -s http://127.0.0.1:8001/api/health && echo ""
curl -s http://127.0.0.1:3000/api/health && echo ""
echo "Done!"
