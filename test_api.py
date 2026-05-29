import urllib.request
import json

url = "http://127.0.0.1:8001/api/mock-trading/accounts"
data = {"name": "test_ai_final", "market": "A-Share", "initial_balance": 100000}
req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})

try:
    with urllib.request.urlopen(req) as response:
        print("Status:", response.status)
        print("Body:", response.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code)
    print("Body:", e.read().decode("utf-8"))
