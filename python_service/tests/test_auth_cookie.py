from types import SimpleNamespace

from python_service.app.api import auth


def test_resolve_auth_token_prefers_bearer_token():
    request = SimpleNamespace(cookies={auth.AUTH_COOKIE_NAME: "cookie-token"})

    assert auth._resolve_auth_token(request, "bearer-token") == "bearer-token"


def test_resolve_auth_token_falls_back_to_http_only_cookie():
    request = SimpleNamespace(cookies={auth.AUTH_COOKIE_NAME: "cookie-token"})

    assert auth._resolve_auth_token(request, None) == "cookie-token"


def test_decode_token_username_returns_subject():
    token = auth.create_access_token({"sub": "alice"})

    assert auth._decode_token_username(token) == "alice"
