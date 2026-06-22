from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel
import os

import secrets

router = APIRouter(prefix="/admin", tags=["admin"])

def _ensure_admin_token():
    token = os.getenv("ADMIN_TOKEN")
    if not token or token == "change-me":
        runtime_env = ".env.runtime"
        if os.path.exists(runtime_env):
            with open(runtime_env, "r") as f:
                for line in f:
                    if line.startswith("ADMIN_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                        os.environ["ADMIN_TOKEN"] = token
                        break
        
        if not token or token == "change-me":
            token = secrets.token_urlsafe(32)
            os.environ["ADMIN_TOKEN"] = token
            try:
                with open(runtime_env, "a") as f:
                    f.write(f"\nADMIN_TOKEN={token}\n")
            except IOError:
                pass
    return token

ADMIN_TOKEN = _ensure_admin_token()

@router.get("/stack-status")
async def stack_status(x_admin_token: str | None = Header(default=None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="admin access required")
    
    return {
        "fastapi": "active",
        "sqlite": "active",
        "parquet": "active",
        "duckdb": "active",
        "polars": "active",
        "lancedb": "active"
    }
