#!/usr/bin/env python3
"""Launcher - sets up path and starts the FastAPI app."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Install the python_service package so relative imports work
from importlib import import_module
mod = import_module("python_service.main")
app = mod.app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
