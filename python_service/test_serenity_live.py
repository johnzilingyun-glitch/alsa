import requests
import time

url = "http://127.0.0.1:8001/api/sector/serenity-analyze"
headers = {
    "Authorization": "Bearer QvbdCfBoV-T41bzkWzP-f5DQXZm0_wVuJUPUiKYqvbY",
    "Content-Type": "application/json"
}
payload = {
    "sector_name": "A股市场",
    "model": "gemini-3.5-flash",
    "gemini_api_key": "fake_key"
}

print("POSTing to", url)
response = requests.post(url, json=payload, headers=headers)
print("Status:", response.status_code)
print("Response:", response.text)

if response.status_code == 200:
    data = response.json()
    job_id = data.get("data", {}).get("job_id")
    if job_id:
        print(f"Tracking job {job_id}...")
        for i in range(30):
            progress_url = f"http://127.0.0.1:8001/api/analysis/progress/{job_id}"
            p_res = requests.get(progress_url, headers=headers)
            if p_res.status_code == 200:
                print(f"Progress: {p_res.text}")
            else:
                print(f"Progress fetch failed: {p_res.status_code} {p_res.text}")
            time.sleep(2)
