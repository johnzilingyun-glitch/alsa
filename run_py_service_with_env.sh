#!/bin/bash
# ALSA Python backend launcher - loads Iwencai env vars
set -a
source /home/ubuntu/.local/bin/env
set +a
cd /home/ubuntu/work/alsa
export AKSHARE_ENABLED=true
exec /home/ubuntu/work/alsa/python_service/.venv/bin/python3.11 /home/ubuntu/work/alsa/run_py_service.py >> /home/ubuntu/work/alsa/logs/py_api.log 2>&1
