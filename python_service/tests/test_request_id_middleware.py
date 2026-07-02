from fastapi import FastAPI
from fastapi.testclient import TestClient

from python_service.app.middleware import REQUEST_ID_HEADER, add_request_id_middleware, normalize_request_id


def _client() -> TestClient:
    app = FastAPI()
    add_request_id_middleware(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_normalize_request_id_preserves_safe_values():
    assert normalize_request_id("req_123-abc") == "req_123-abc"


def test_normalize_request_id_replaces_unsafe_values():
    request_id = normalize_request_id("bad id with spaces")

    assert request_id != "bad id with spaces"
    assert len(request_id) == 36


def test_request_id_middleware_echoes_safe_inbound_header():
    response = _client().get("/ping", headers={REQUEST_ID_HEADER: "req-safe"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-safe"


def test_request_id_middleware_generates_missing_header():
    response = _client().get("/ping")

    assert response.status_code == 200
    assert len(response.headers[REQUEST_ID_HEADER]) == 36
