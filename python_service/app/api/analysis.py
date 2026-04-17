from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..services.analysis_job_service import AnalysisJobService

class AnalysisJobCreate(BaseModel):
    symbol: str
    market: str
    level: str = "standard"

router = APIRouter(prefix="/analysis", tags=["analysis"])

# We import the service getter from main to avoid circular imports in the subagent run
# But better to use a dedicated dependency module.
def get_job_service():
    from ...main import get_analysis_job_service
    return get_analysis_job_service()

@router.post("/jobs", status_code=202)
async def create_job(payload: AnalysisJobCreate, service: AnalysisJobService = Depends(get_job_service)):
    job_id = await service.start_job(payload.symbol, payload.market)
    return {"job_id": job_id, "status": "queued"}

@router.get("/jobs/{job_id}")
async def get_job(job_id: str, service: AnalysisJobService = Depends(get_job_service)):
    job = service.get_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job.job_id,
        "status": job.status,
        "result": job.result_payload
    }
