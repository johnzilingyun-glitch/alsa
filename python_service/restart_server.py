import os
import signal
import subprocess

pids = []
try:
    output = subprocess.check_output(["pgrep", "-f", "uvicorn|main.py|python_service"]).decode()
    for line in output.splitlines():
        if line.strip():
            pids.append(int(line.strip()))
except subprocess.CalledProcessError:
    pass

for pid in pids:
    try:
        os.kill(pid, signal.SIGKILL)
        print(f"Killed {pid}")
    except Exception as e:
        print(f"Failed to kill {pid}: {e}")

print("All found server processes killed.")
