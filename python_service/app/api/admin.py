from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel
import os

import secrets
from app.api.auth import get_optional_user

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
async def stack_status(
    x_admin_token: str | None = Header(default=None),
    current_user = Depends(get_optional_user),
):
    _require_admin_access(x_admin_token, current_user)
    
    return {
        "fastapi": "active",
        "sqlite": "active",
        "parquet": "active",
        "duckdb": "active",
        "polars": "active",
        "lancedb": "active"
    }

from sqlmodel import Session, select
from typing import Dict, Any
from app.db.database import get_session
from app.db.models import PipelineVersion
from app.time_utils import utc_now
from app.observability.failure_capture import (
    get_incident_detail,
    list_incidents_by_job_id,
    query_incidents,
)
import uuid


def _require_admin_access(x_admin_token: str | None, current_user) -> None:
    token_ok = bool(x_admin_token and x_admin_token == ADMIN_TOKEN)
    role_ok = bool(current_user and getattr(current_user, "role", None) == "admin")
    if not token_ok and not role_ok:
        raise HTTPException(status_code=403, detail="admin access required")

class PipelineVersionCreate(BaseModel):
    name: str
    status: str = "development"
    config: Dict[str, Any] | None = None
    release_notes: str | None = None

class PipelineVersionUpdate(BaseModel):
    status: str
    release_notes: str | None = None

@router.get("/pipeline-versions")
async def list_pipeline_versions(
    x_admin_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user),
):
    _require_admin_access(x_admin_token, current_user)
    versions = session.exec(select(PipelineVersion).order_by(PipelineVersion.created_at.desc())).all()
    return {"success": True, "data": versions}

@router.post("/pipeline-versions")
async def create_pipeline_version(
    payload: PipelineVersionCreate,
    x_admin_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user),
):
    _require_admin_access(x_admin_token, current_user)
    
    new_version = PipelineVersion(
        id=f"pv_{uuid.uuid4().hex[:8]}",
        name=payload.name,
        status=payload.status,
        config=payload.config,
        release_notes=payload.release_notes,
    )
    session.add(new_version)
    session.commit()
    session.refresh(new_version)
    return {"success": True, "data": new_version}

@router.post("/pipeline-versions/{version_id}/status")
async def update_pipeline_version_status(
    version_id: str,
    payload: PipelineVersionUpdate,
    x_admin_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
    current_user = Depends(get_optional_user),
):
    _require_admin_access(x_admin_token, current_user)
    
    version = session.get(PipelineVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Pipeline version not found")
        
    if payload.status == "production":
        # Demote current production to deprecated
        current_prods = session.exec(select(PipelineVersion).where(PipelineVersion.status == "production")).all()
        for prod in current_prods:
            if prod.id != version_id:
                prod.status = "deprecated"
                prod.updated_at = utc_now()
                session.add(prod)
                
    version.status = payload.status
    if payload.release_notes is not None:
        version.release_notes = payload.release_notes
    version.updated_at = utc_now()
    
    session.add(version)
    session.commit()
    session.refresh(version)
    return {"success": True, "data": version}


@router.get("/incidents/{incident_id}")
async def get_incident_snapshot(
    incident_id: str,
    x_admin_token: str | None = Header(default=None),
    current_user = Depends(get_optional_user),
):
    _require_admin_access(x_admin_token, current_user)

    detail = get_incident_detail(incident_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"success": True, "data": detail}


@router.get("/incidents")
async def list_incidents_for_job(
    job_id: str,
    limit: int = 20,
    x_admin_token: str | None = Header(default=None),
    current_user = Depends(get_optional_user),
):
    _require_admin_access(x_admin_token, current_user)
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    items = list_incidents_by_job_id(job_id, limit=limit)
    return {"success": True, "data": items}


@router.get("/incident-query")
async def incident_query(
    job_id: str | None = None,
    incident_id: str | None = None,
    limit: int = 20,
    x_admin_token: str | None = Header(default=None),
    current_user = Depends(get_optional_user),
):
    """One-shot query for frontend "view snapshot" button.

    - If incident_id exists: returns full detail in latest.
    - Else if job_id exists: returns incident list + latest detail.
    """
    _require_admin_access(x_admin_token, current_user)
    if not job_id and not incident_id:
        raise HTTPException(status_code=400, detail="job_id or incident_id is required")

    data = query_incidents(job_id=job_id, incident_id=incident_id, limit=limit)
    latest = data.get("latest") if isinstance(data, dict) else None
    diagnostics = latest.get("diagnostics") if isinstance(latest, dict) else None
    if isinstance(data, dict):
        data["diagnostics"] = diagnostics or {}
    return {"success": True, "data": data}
