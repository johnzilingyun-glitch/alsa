import pytest
from fastapi import HTTPException

from python_service.app import security


def test_python_cors_restricts_origins(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173,https://alsa.example")

    assert security.get_allowed_origins() == ["http://localhost:5173", "https://alsa.example"]


def test_python_requires_api_token_when_configured(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "secret")

    with pytest.raises(HTTPException) as unauthorized:
        security.require_api_token(None)
    assert unauthorized.value.status_code == 401

    security.require_api_token("Bearer secret")
