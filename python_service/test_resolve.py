from fastapi.testclient import TestClient
from main import app
from app.db.database import init_db

init_db()
client = TestClient(app)

response = client.post("/api/sector/serenity-analyze", json={
    "sector_name": "A股市场"
})
print("POST Status:", response.status_code)
print("POST Response:", response.text)
