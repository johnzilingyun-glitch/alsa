import os
from fastapi import Header, HTTPException


def get_allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("API_TOKEN")
    if not expected:
        return
    token = authorization.removeprefix("Bearer ") if authorization else ""
    if token != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
