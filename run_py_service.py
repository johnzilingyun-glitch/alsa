#!/usr/bin/env python3
"""Launcher - sets up path and starts the FastAPI app."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "python_service"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set default REDIS_URL if not already set
if not os.getenv("REDIS_URL"):
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"
    print(f"[init] REDIS_URL not set, using default: {os.environ['REDIS_URL']}")

from dotenv import load_dotenv
load_dotenv()
load_dotenv(".env.runtime")

# Set default API_TOKEN if not already set (for development/testing)

if not os.getenv("API_TOKEN"):
    os.environ["API_TOKEN"] = "alsa-dev-token-2026"
    print(f"[init] API_TOKEN not set, using default: {os.environ['API_TOKEN']}")

# Install the python_service package so relative imports work
from importlib import import_module
mod = import_module("python_service.main")
app = mod.app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
