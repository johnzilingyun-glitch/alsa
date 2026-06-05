#!/usr/bin/env python3
"""Launcher for ALSA Python service - handles import path setup."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Make relative imports work by setting __package__
__package__ = "python_service"

from main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
