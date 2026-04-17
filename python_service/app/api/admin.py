from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel
import os

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-me")

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
