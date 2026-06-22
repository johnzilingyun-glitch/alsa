import sys
import json
import subprocess
import os

project_root = "/home/ubuntu/work/alsa"
venv_python = os.path.join(project_root, ".venv_qlib", "bin", "python")
bridge_script = os.path.join(project_root, "python_service", "paper_trading_system", "execution_layer", "run_qlib_bridge.py")

cmd = [
    venv_python, bridge_script,
    "--start_date", "2021-01-01",
    "--end_date", "2021-12-30",  # Use date within Qlib calendar range
    "--model", "mock",  # This triggers AIAgentStrategy
    "--market", "CN",
    "--initial_cash", "100000.0",
    "--commission", "0.0003",
    "--target_symbol", "SH600519",
    "--params", "{}"
]

env = os.environ.copy()
env["PYTHONPATH"] = os.path.join(project_root, "python_service")

print("Running command...")
try:
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, timeout=120)
    print("Return Code:", res.returncode)
    print("--- STDERR ---")
    print(res.stderr)
    print("--- STDOUT ---")
    print(res.stdout)
except subprocess.TimeoutExpired:
    print("ERROR: Test timed out after 120 seconds!")
