import importlib
import sys

import pytest


def _reset_module(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_resolve_api_token_fails_fast_in_production(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setenv("ENV", "production")

    with pytest.raises(RuntimeError, match="API_TOKEN"):
        _reset_module("python_service.app.security")


def test_resolve_api_token_uses_configured_value(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "configured-token")

    module = _reset_module("python_service.app.security")

    assert module.resolve_api_token() == "configured-token"


def test_resolve_api_token_generates_development_runtime_secret(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)

    module = _reset_module("python_service.app.security")
    token = module.resolve_api_token()

    assert token
    assert f"API_TOKEN={token}" in (tmp_path / ".env.runtime").read_text()


def test_jwt_secret_fails_fast_in_production(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("ENV", "production")

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        _reset_module("python_service.app.api.auth")


def test_jwt_secret_uses_configured_value(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "configured-jwt-secret")

    module = _reset_module("python_service.app.api.auth")

    assert module.get_or_create_jwt_secret() == "configured-jwt-secret"


def test_allowed_origins_default_to_loopback_in_development(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.setenv("API_TOKEN", "configured-token")

    module = _reset_module("python_service.app.security")

    assert module.get_allowed_origins() == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_allowed_origins_require_explicit_config_in_production(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("API_TOKEN", "configured-token")

    module = _reset_module("python_service.app.security")

    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        module.get_allowed_origins()


def test_allowed_origins_reject_wildcard_in_production(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://alsa.example,*")
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("API_TOKEN", "configured-token")

    module = _reset_module("python_service.app.security")

    with pytest.raises(RuntimeError, match="Wildcard CORS"):
        module.get_allowed_origins()
