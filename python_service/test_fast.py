import subprocess
import os

project_root = "/home/ubuntu/work/alsa"
venv_python = os.path.join(project_root, ".venv_qlib", "bin", "python")
bridge_script = os.path.join(project_root, "python_service", "paper_trading_system", "execution_layer", "run_qlib_bridge.py")

cmd = [
    venv_python, bridge_script,
    "--start_date", "2021-01-01",
    "--end_date", "2021-06-01",
    "--model", "mock",
    "--market", "CN",
    "--initial_cash", "100000.0",
    "--commission", "0.0003",
    "--target_symbol", "SH600519",
    "--params", "{}"
]

env = os.environ.copy()
env["PYTHONPATH"] = os.path.join(project_root, "python_service")

with open("fast_test.log", "w") as f:
    process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
    print(f"Background test started with PID {process.pid}. Logs in fast_test.log")
