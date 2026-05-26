#!/bin/bash
pkill -9 -f uvicorn || true
sleep 1
cd /home/zily/alsa
nohup .venv/bin/python -m uvicorn python_service.main:app --host 0.0.0.0 --port 8001 > python_service.log 2>&1 < /dev/null &
echo "Uvicorn started in background"
