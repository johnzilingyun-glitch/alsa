import os
import secrets
from fastapi import Header, HTTPException

def _ensure_api_token():
    token = os.getenv("API_TOKEN")
    if not token:
        runtime_env = ".env.runtime"
        if os.path.exists(runtime_env):
            with open(runtime_env, "r") as f:
                for line in f:
                    if line.startswith("API_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                        os.environ["API_TOKEN"] = token
                        break
        
        if not token:
            token = secrets.token_urlsafe(32)
            os.environ["API_TOKEN"] = token
            with open(runtime_env, "a") as f:
                f.write(f"\nAPI_TOKEN={token}\n")
            print(f"\n" + "="*50)
            print(f"🔒 Generated secure API_TOKEN: {token}")
            print(f"   (Saved to {runtime_env})")
            print("="*50 + "\n")

_ensure_api_token()

def get_allowed_origins() -> list[str]:
    configured = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("API_TOKEN")
    if not expected:
        raise HTTPException(status_code=401, detail="Unauthorized (API_TOKEN missing)")
    token = authorization.removeprefix("Bearer ") if authorization else ""
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
