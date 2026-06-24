from fastapi.testclient import TestClient
from main import app
from app.db.database import init_db
import traceback

try:
    init_db()
    client = TestClient(app)
    
    response = client.post("/api/auth/token", data={
        "username": "zily",
        "password": "wrong_password"
    })
    print("POST Status:", response.status_code)
    print("POST Response:", response.text)
except Exception:
    traceback.print_exc()
