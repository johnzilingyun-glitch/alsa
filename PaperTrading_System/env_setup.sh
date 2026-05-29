#!/bin/bash
set -e

echo "Initializing Python 3.9 virtual environment for Qlib..."
cd /home/zily/alsa/PaperTrading_System

# Use uv to create Python 3.9 venv
/home/zily/.local/bin/uv venv --python 3.9 .venv_qlib

echo "Activating virtual environment..."
source .venv_qlib/bin/activate

echo "Installing core dependencies (numpy, pandas, pyqlib, lightgbm)..."
/home/zily/.local/bin/uv pip install numpy pandas pyqlib lightgbm

echo "Environment setup complete!"
