from fastapi.testclient import TestClient


def test_python_app_cors_restricts_origins(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173,https://alsa.example")
    from importlib import reload
    import python_service.main as main
    reload(main)

    origins = [m.kwargs.get("allow_origins") for m in main.app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert origins
    assert origins[0] == ["http://localhost:5173", "https://alsa.example"]


def test_python_app_requires_api_token_when_configured(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "secret")
    from importlib import reload
    import python_service.main as main
    reload(main)
    client = TestClient(main.app)

    unauthorized = client.get("/api/market/indices")
    assert unauthorized.status_code == 401

    authorized = client.get("/api/market/indices", headers={"Authorization": "Bearer secret"})
    assert authorized.status_code != 401
