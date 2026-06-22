#!/usr/bin/env python3
"""End-to-end auth flow test. Run after restarting Node gateway."""
import os, sys, json

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

os.environ['SQLITE_PATH'] = os.path.join(project_root, 'data', 'app.db')
os.environ['API_TOKEN'] = 'mock-token'

import python_service.app
from python_service.app.db.database import engine
for name in list(sys.modules.keys()):
    if name.startswith('python_service.app.'):
        alias = 'app.' + name[len('python_service.app.'):]
        if alias not in sys.modules:
            sys.modules[alias] = sys.modules[name]

from python_service.main import app
os.environ['API_TOKEN'] = 'mock-token'

from fastapi.testclient import TestClient

def test_auth_flow():
    client = TestClient(app)
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  ✓ {name}")
            passed += 1
        else:
            print(f"  ✗ {name} — {detail}")
            failed += 1

    print("=== Login ===")
    resp = client.post("/api/auth/token", data={"username": "zily", "password": "zily9958"})
    check("POST /api/auth/token returns 200", resp.status_code == 200, f"got {resp.status_code}: {resp.text[:100]}")
    token = resp.json().get("access_token", "")
    check("Token returned", len(token) > 20)

    print("\n=== Auth endpoints ===")
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    check("GET /api/auth/me returns 200", resp.status_code == 200)
    check("User is zily with admin role", resp.json().get("role") == "admin")

    resp = client.get("/api/auth/users", headers={"Authorization": f"Bearer {token}"})
    check("GET /api/auth/users returns 200", resp.status_code == 200, f"got {resp.status_code}")
    users = resp.json()
    check(f"Users list has {len(users)} entries", len(users) > 0)

    print("\n=== Permission checks ===")
    resp = client.get("/api/auth/users")
    check("No token → 401", resp.status_code == 401)

    print(f"\n=== Result: {passed} passed, {failed} failed ===")
    return failed == 0

if __name__ == "__main__":
    ok = test_auth_flow()
    sys.exit(0 if ok else 1)
