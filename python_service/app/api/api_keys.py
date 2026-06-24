import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from ..security import authenticate
from ..db.database import session_factory
from ..db.repositories.api_key_repo import ApiKeyRepository
from ..utils.responses import success_response
from .limiter import limiter

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

def get_repo():
    return ApiKeyRepository(session_factory)


class ApiKeyCreate(BaseModel):
    name: str
    scopes: List[str] = ["analysis:read", "market:read", "watchlist:read"]
    rate_limit_override: Optional[str] = None
    expires_in_days: Optional[int] = None


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    scopes: Optional[List[str]] = None
    rate_limit_override: Optional[str] = None


@router.post("/", status_code=201)
@limiter.limit("5/minute")
async def create_api_key(request: Request, body: ApiKeyCreate,
                         auth=Depends(authenticate), repo: ApiKeyRepository = Depends(get_repo)):
    from datetime import timedelta
    from ..time_utils import utc_now
    expires_at = None
    if body.expires_in_days:
        expires_at = utc_now() + timedelta(days=body.expires_in_days)

    api_key_obj, raw_key = repo.create(
        user_id=auth[0],
        name=body.name,
        scopes=json.dumps(body.scopes),
        rate_limit_override=body.rate_limit_override,
        expires_at=expires_at,
    )
    return success_response({
        "key_id": api_key_obj.key_id,
        "key": raw_key,
        "name": api_key_obj.name,
        "scopes": body.scopes,
        "message": "Save this key now — it will not be shown again.",
    })


@router.get("/")
async def list_api_keys(auth=Depends(authenticate), repo: ApiKeyRepository = Depends(get_repo)):
    keys = repo.list_by_user(auth[0])
    items = []
    for k in keys:
        items.append({
            "key_id": k.key_id,
            "name": k.name,
            "scopes": json.loads(k.scopes) if k.scopes else [],
            "rate_limit_override": k.rate_limit_override,
            "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "is_active": k.is_active,
        })
    return success_response(items)


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, auth=Depends(authenticate),
                         repo: ApiKeyRepository = Depends(get_repo)):
    ok = repo.revoke(key_id, auth[0])
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
    return success_response({"key_id": key_id, "status": "revoked"})


@router.put("/{key_id}")
async def update_api_key(key_id: str, body: ApiKeyUpdate,
                         auth=Depends(authenticate), repo: ApiKeyRepository = Depends(get_repo)):
    update_kwargs = {}
    if body.name is not None:
        update_kwargs["name"] = body.name
    if body.scopes is not None:
        update_kwargs["scopes"] = json.dumps(body.scopes)
    if body.rate_limit_override is not None:
        update_kwargs["rate_limit_override"] = body.rate_limit_override

    if not update_kwargs:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = repo.update(key_id, auth[0], **update_kwargs)
    if not result:
        raise HTTPException(status_code=404, detail="API key not found")
    return success_response({
        "key_id": result.key_id,
        "name": result.name,
        "scopes": json.loads(result.scopes) if result.scopes else [],
        "rate_limit_override": result.rate_limit_override,
    })
