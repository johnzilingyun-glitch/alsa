import urllib.request, json
req = urllib.request.Request(
    "http://127.0.0.1:8001/api/sector/scan",
    data=json.dumps({"model": "gemini-2.5-flash", "force": True}).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
res = urllib.request.urlopen(req)
print(res.read().decode())
