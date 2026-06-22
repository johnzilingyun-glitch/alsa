from fastapi.testclient import TestClient
from main import app
from app.db.database import init_db
import traceback

try:
    init_db()
    client = TestClient(app)
    
    response = client.post("/api/sector/serenity-analyze", json={
        "sector_name": "A股市场",
        "model": "gemini-3.5-flash",
        "gemini_api_key": "fake_key"
    })
    print("POST Status:", response.status_code)
    print("POST Response:", response.text)
except Exception as e:
    traceback.print_exc()
