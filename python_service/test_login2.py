from fastapi.testclient import TestClient
from main import app
import traceback

try:
    client = TestClient(app)
    
    response = client.post("/api/auth/token", data={
        "username": "zily",
        "password": "zily9958"
    })
    print("POST Status:", response.status_code)
    print("POST Response:", response.text)
except Exception:
    traceback.print_exc()
