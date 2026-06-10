import time
import requests
import sys

job_id = "job_f0901972"
url = f"http://localhost:8001/api/analysis/jobs/{job_id}"

print(f"Start monitoring job {job_id}...", flush=True)

while True:
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                job_data = data.get("data", {})
                status = job_data.get("status")
                progress = job_data.get("progress", {})
                
                stage = progress.get("stage", "N/A")
                percent = progress.get("percent", 0)
                message = progress.get("message", "N/A")
                round_num = progress.get("round", "N/A")
                total_rounds = progress.get("total_rounds", "N/A")
                
                print(f"[STATUS UPDATE] Status: {status} | Stage: {stage} ({percent}%) | Msg: {message} | Round: {round_num}/{total_rounds}", flush=True)
                
                if status in ["completed", "failed", "cancelled"]:
                    print(f"Job finished with status: {status}", flush=True)
                    if status == "completed":
                        print("Analysis completed successfully!", flush=True)
                    else:
                        print(f"Error: {job_data.get('error_message')}", flush=True)
                    break
            else:
                print(f"API returned error: {data.get('error')}", flush=True)
        else:
            print(f"HTTP Error {response.status_code}", flush=True)
    except Exception as e:
        print(f"Monitoring error: {e}", flush=True)
        
    time.sleep(30)
