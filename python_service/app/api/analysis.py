import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, Dict, Any
from ..services.analysis_job_service import AnalysisJobService
from ..utils.responses import success_response, error_response
from ..db.sqlite import session_factory
from ..services.lineage_service import build_analysis_lineage

class AnalysisJobCreate(BaseModel):
    symbol: str
    market: str
    analysis_level: str = "standard"
    requested_model: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class ApiKeySubmission(BaseModel):
    provider: str = "gemini"
    apiKey: str

router = APIRouter(prefix="/analysis", tags=["analysis"])

def get_job_service():
    # Attempt to import from a safe location to avoid circular imports
    try:
        from python_service.main import get_analysis_job_service
        return get_analysis_job_service()
    except ImportError:
        # Fallback for different environments
        from ...main import get_analysis_job_service
        return get_analysis_job_service()

@router.post("/jobs", status_code=202)
async def create_job(payload: AnalysisJobCreate, service: AnalysisJobService = Depends(get_job_service)):
    # Check if there are any active jobs in the queue
    if service.job_repo.has_any_running():
        return error_response("QUEUE_FULL", "当前已有分析任务正在进行中，请等待其完成后再提交新任务。")

    job_id = await service.start_job(
        symbol=payload.symbol, 
        market=payload.market, 
        level=payload.analysis_level,
        model=payload.requested_model,
        config=payload.config
    )
    return success_response({
        "job_id": job_id, 
        "status": "queued"
    })

@router.get("/jobs/{job_id}")
async def get_job(job_id: str, service: AnalysisJobService = Depends(get_job_service)):
    job = service.get_status(job_id)
    if not job:
        return error_response("JOB_NOT_FOUND", "Analysis job not found")
    
    result = None
    if job.status == "completed" and job.result_payload:
        import json
        try:
            result = json.loads(job.result_payload)
        except:
            result = job.result_payload

    # Use live in-memory progress from the service if available
    progress_data = service._progress.get(job_id)
    if progress_data:
        progress = progress_data
    elif job.status == "completed":
        progress = {"stage": "completed", "percent": 100}
    elif job.status == "running":
        progress = {"stage": "running", "percent": 5}
    else:
        progress = {"stage": job.status, "percent": 0}

    return success_response({
        "job_id": job.job_id,
        "status": job.status,
        "progress": progress,
        "analysis_id": job.analysis_id,
        "error_message": job.error_message,
        "result": result
    })

@router.get("/runs/{analysis_id}")
async def get_analysis_run(analysis_id: str, service: AnalysisJobService = Depends(get_job_service)):
    # This might need a separate service or method in AnalysisJobService
    # For now, let's assume we can get it or handle it in the service
    run = service.get_analysis_run(analysis_id)
    if not run:
        return error_response("ANALYSIS_NOT_FOUND", "Analysis run not found")
    
    return success_response(run)


@router.get("/runs/{analysis_id}/lineage")
async def get_analysis_lineage(analysis_id: str):
    with session_factory() as session:
        lineage = build_analysis_lineage(session, analysis_id)
    if not lineage:
        return error_response("ANALYSIS_NOT_FOUND", "Analysis run not found")
    return success_response(lineage)

@router.post("/jobs/{job_id}/apikey")
async def submit_api_key(job_id: str, body: ApiKeySubmission, service: AnalysisJobService = Depends(get_job_service)):
    """Receive API key from frontend. Stored in memory only — never saved to disk.
       Key is cached globally and reused across subsequent jobs."""
    ok = service.submit_api_key(job_id, body.provider, body.apiKey)
    if not ok:
        return error_response("JOB_NOT_WAITING", "Job is not waiting for an API key")
    return success_response({"job_id": job_id, "provider": body.provider, "status": "accepted"})

@router.post("/apikey")
async def set_api_key_global(body: ApiKeySubmission, service: AnalysisJobService = Depends(get_job_service)):
    """Proactively set/update an API key in memory cache (e.g. user changes key in settings).
       No job_id needed — key is cached globally for all future jobs."""
    service.set_api_key(body.provider, body.apiKey)
    return success_response({"provider": body.provider, "status": "cached"})

@router.get("/apikey/status")
async def get_api_key_status(service: AnalysisJobService = Depends(get_job_service)):
    """Check which API keys are cached and their remaining TTL.
       Never exposes the actual key value."""
    status = service.get_key_status()
    return success_response(status)

@router.delete("/apikey/{provider}")
async def clear_api_key(provider: str, service: AnalysisJobService = Depends(get_job_service)):
    """Clear cached API key for a specific provider from memory."""
    service.clear_api_key(provider)
    return success_response({"provider": provider, "status": "cleared"})

@router.delete("/apikey")
async def clear_all_api_keys(service: AnalysisJobService = Depends(get_job_service)):
    """Clear all cached API keys from memory."""
    service.clear_api_key()
    return success_response({"status": "all_keys_cleared"})

@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, service: AnalysisJobService = Depends(get_job_service)):
    success = await service.cancel_job(job_id)
    if not success:
        return error_response("CANCEL_FAILED", "Could not cancel job")
    return success_response({"job_id": job_id, "status": "cancelled"})

@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, service: AnalysisJobService = Depends(get_job_service)):
    """Re-submit a failed or cancelled job with the same parameters."""
    new_job_id = await service.retry_job(job_id)
    if not new_job_id:
        return error_response("RETRY_FAILED", "Job not found or not in a retryable state (must be failed or cancelled)")
    return success_response({"original_job_id": job_id, "new_job_id": new_job_id, "status": "queued"})

@router.get("/history/{symbol}")
async def get_analysis_history(symbol: str, service: AnalysisJobService = Depends(get_job_service)):
    """Get completed analysis history for a symbol."""
    jobs = service.job_repo.list_completed_by_symbol(symbol)
    items = []
    for job in jobs:
        items.append({
            "job_id": job.job_id,
            "analysis_id": job.analysis_id,
            "symbol": job.symbol,
            "market": job.market,
            "model": job.requested_model,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        })
    return success_response(items)


class ReportRequest(BaseModel):
    deepseekApiKey: Optional[str] = None
    geminiApiKey: Optional[str] = None

@router.post("/jobs/{job_id}/report")
async def generate_report(job_id: str, body: ReportRequest = None, service: AnalysisJobService = Depends(get_job_service)):
    """Generate a professional HTML report from a completed analysis job."""
    from ..services.report_generator_service import ReportGeneratorService
    import tempfile, os

    if body is None:
        body = ReportRequest()

    job = service.job_repo.get_by_id(job_id)
    if not job:
        return error_response("JOB_NOT_FOUND", "Job not found")
    if job.status != "completed" or not job.result_payload:
        return error_response("JOB_NOT_READY", "Job is not completed or has no results")

    result = json.loads(job.result_payload)
    report_service = ReportGeneratorService()

    # Generate into a temp file, then read and return HTML
    tmp_path = os.path.join(tempfile.gettempdir(), f"{job.symbol}_{job_id}_report.html")
    try:
        deepseek_key = body.deepseekApiKey or service._api_keys.get("deepseek")
        gemini_key = body.geminiApiKey or service._api_keys.get("gemini")
        await report_service.generate_html_report_async(
            result, tmp_path, model=job.requested_model,
            deepseek_api_key=deepseek_key,
            gemini_api_key=gemini_key
        )
        with open(tmp_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return Response(content=html_content, media_type="text/html")
    except Exception as e:
        return error_response("REPORT_FAILED", f"Report generation failed: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/jobs/{job_id}/export/pdf")
async def export_pdf(job_id: str, body: ReportRequest = None, service: AnalysisJobService = Depends(get_job_service)):
    """Export analysis report as PDF."""
    from ..services.report_generator_service import ReportGeneratorService
    from ..services.export_service import export_service
    import tempfile, os

    if body is None:
        body = ReportRequest()

    job = service.job_repo.get_by_id(job_id)
    if not job:
        return error_response("JOB_NOT_FOUND", "Job not found")
    if job.status != "completed" or not job.result_payload:
        return error_response("JOB_NOT_READY", "Job is not completed or has no results")

    result = json.loads(job.result_payload)
    report_service = ReportGeneratorService()

    tmp_path = os.path.join(tempfile.gettempdir(), f"{job.symbol}_{job_id}_report.html")
    try:
        deepseek_key = body.deepseekApiKey or service._api_keys.get("deepseek")
        gemini_key = body.geminiApiKey or service._api_keys.get("gemini")
        await report_service.generate_html_report_async(
            result, tmp_path, model=job.requested_model,
            deepseek_api_key=deepseek_key,
            gemini_api_key=gemini_key
        )
        with open(tmp_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        pdf_bytes = await export_service.html_to_pdf(html_content)
        filename = f"EquityResearch_{job.symbol}_{job_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        return error_response("PDF_EXPORT_FAILED", f"PDF export failed: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/jobs/{job_id}/export/share-card")
async def export_share_card(job_id: str, service: AnalysisJobService = Depends(get_job_service)):
    """Generate a share card image (PNG) for social sharing."""
    from ..services.export_service import export_service

    job = service.job_repo.get_by_id(job_id)
    if not job:
        return error_response("JOB_NOT_FOUND", "Job not found")
    if job.status != "completed" or not job.result_payload:
        return error_response("JOB_NOT_READY", "Job is not completed or has no results")

    result = json.loads(job.result_payload)
    stock_info = result.get("stockInfo", {})
    summary = result.get("summary", {})

    # Extract key fields
    title = f"{stock_info.get('name', '')} ({stock_info.get('symbol', '')})"
    verdict = summary.get("verdict", "") if isinstance(summary, dict) else ""
    score = summary.get("score") if isinstance(summary, dict) else None
    price_str = str(stock_info.get("price", "")) if stock_info.get("price") else None
    change_pct = None
    if stock_info.get("changePercent") is not None:
        cp = stock_info["changePercent"]
        change_pct = f"+{cp}%" if cp >= 0 else f"{cp}%"

    # Extract highlights from summary
    highlights = []
    if isinstance(summary, dict):
        for key in ("moat", "catalyst", "risk"):
            val = summary.get(key)
            if val and isinstance(val, str):
                highlights.append(val[:80])

    card_html = export_service.build_share_card_html(
        title=title,
        verdict=verdict,
        score=float(score) if score else None,
        price=price_str,
        change_pct=change_pct,
        highlights=highlights,
        report_type=result.get("job_type", "stock"),
    )
    png_bytes = await export_service.html_to_image(card_html, width=460)
    filename = f"ShareCard_{stock_info.get('symbol', 'report')}.png"
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ────────────── Token Guard Settings ──────────────

class TokenGuardLevelRequest(BaseModel):
    level: str  # "none" | "low" | "medium" | "high"

@router.get("/settings/token-guard")
async def get_token_guard_settings():
    """Get current TokenGuard level and available options."""
    from ..services.token_guard import token_guard, VALID_LEVELS
    return success_response({
        "currentLevel": token_guard.level,
        "availableLevels": list(VALID_LEVELS),
        "descriptions": {
            "none": "无限制 (适用于本地模型或调试)",
            "low": "宽松限制 (单轮≈18K tokens，适合大上下文模型)",
            "medium": "中等限制 (单轮≈10K tokens，平衡质量与成本)",
            "high": "严格限制 (单轮≈6K tokens，最小化云端API成本)",
        },
        "enabled": token_guard.config.enabled,
        "roundBudgetChars": token_guard.config.round_budget_chars,
    })

@router.post("/settings/token-guard")
async def set_token_guard_level(body: TokenGuardLevelRequest):
    """Set TokenGuard enforcement level."""
    from ..services.token_guard import token_guard, VALID_LEVELS
    level = body.level.lower().strip()
    if level not in VALID_LEVELS:
        return error_response("INVALID_LEVEL", f"Valid levels: {', '.join(VALID_LEVELS)}")
    token_guard.set_level(level)
    return success_response({
        "level": token_guard.level,
        "enabled": token_guard.config.enabled,
        "roundBudgetChars": token_guard.config.round_budget_chars,
    })
