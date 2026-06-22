from fastapi.testclient import TestClient
from main import app
from app.db.database import init_db
from app.api.analysis import get_job_service

init_db()

service = get_job_service()

# Clear auth requirement
app.dependency_overrides = {}
from app.security import require_api_token
app.dependency_overrides[require_api_token] = lambda: "test_token"

client = TestClient(app)

response = client.post("/api/analysis/jobs", json={
    "symbol": "AAPL",
    "market": "US-Share",
    "analysis_level": "standard",
    "requested_model": "gemini"
})
print("POST Status:", response.status_code)
print("POST Response:", response.json())

if response.status_code == 202:
    job_id = response.json().get("data", {}).get("job_id")
    if job_id:
        get_res = client.get(f"/api/analysis/jobs/{job_id}")
        print("GET Status:", get_res.status_code)
        print("GET Response:", get_res.json())
