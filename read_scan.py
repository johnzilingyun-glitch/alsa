import urllib.request, json
res = urllib.request.urlopen("http://127.0.0.1:8001/api/sector/scan/scan_3439f88c")
data = json.loads(res.read().decode())["data"]
print(f"Status: {data['status']}")
print(f"Progress: {data['progress']}")
print(f"Sectors found: {len(data['sectors'])}")
print()
for i, s in enumerate(data["sectors"]):
    print(f"{i+1}. {s}")
print()
result_text = data.get("result", "")
print(f"Result length: {len(result_text)} chars")
print("--- First 2000 chars ---")
print(result_text[:2000])
