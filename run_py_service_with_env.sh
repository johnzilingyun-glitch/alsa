#!/bin/bash
# ALSA Python backend launcher - loads Iwencai env vars if available
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

# Source external env file for Iwencai tokens (optional, won't fail if missing)
# The env file is typically at ~/.local/bin/env on the deployment server
if [ -f "$HOME/.local/bin/env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$HOME/.local/bin/env"
    set +a
fi

cd "$PROJECT_DIR"
export AKSHARE_ENABLED=true
export REDIS_URL=redis://localhost:6379/0
exec "$PROJECT_DIR/python_service/.venv/bin/python" "$PROJECT_DIR/run_py_service.py" >> "$PROJECT_DIR/logs/py_api.log" 2>&1
