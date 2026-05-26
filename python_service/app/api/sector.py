"""Sector Analysis API — market scan + sector deep analysis endpoints."""
import os
import re
import json
import math
import asyncio
import uuid
from datetime import datetime, date
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from ..utils.responses import success_response, error_response

router = APIRouter(prefix="/sector", tags=["sector"])

# In-memory store for scan/analysis jobs (same pattern as AnalysisJobService)
_scan_jobs: Dict[str, Dict[str, Any]] = {}
_scan_tasks: Dict[str, asyncio.Task] = {}


class SectorScanRequest(BaseModel):
    model: Optional[str] = None
    date: Optional[str] = None
    force: Optional[bool] = False


class SectorAnalyzeRequest(BaseModel):
    sector_name: str
    model: Optional[str] = None
    date: Optional[str] = None
    force: Optional[bool] = False


def _resolve_model(requested: Optional[str] = None) -> str:
    if requested:
        return requested
    provider = os.getenv("DEFAULT_LLM_PROVIDER", "deepseek").lower()
    if provider == "deepseek":
        return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    return os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")


def _sanitize_for_json(obj):
    """Recursively replace NaN/Inf float values with None for JSON safety."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    # Handle numpy types
    try:
        import numpy as np
        if isinstance(obj, (np.floating, np.integer)):
            v = float(obj)
            return None if math.isnan(v) or math.isinf(v) else v
    except (ImportError, TypeError):
        pass
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


# ---------- Scan ----------

@router.post("/scan")
async def start_scan(req: SectorScanRequest):
    """Start an async market sector scan."""
    from ..db.sqlite import build_session_factory, DATABASE_URL
    from ..db.models import AnalysisJob
    from sqlmodel import select

    target_date = req.date if req.date else datetime.now().strftime("%Y-%m-%d")
    model = _resolve_model(req.model)

    # Cache check
    if not req.force:
        session_factory = build_session_factory(DATABASE_URL)
        with session_factory() as session:
            statement = select(AnalysisJob).where(
                AnalysisJob.symbol == "market_sector_scan",
                AnalysisJob.market == "sector",
                AnalysisJob.status == "completed",
                AnalysisJob.snapshot_id == target_date
            ).order_by(AnalysisJob.finished_at.desc())
            existing_job = session.exec(statement).first()
            if existing_job:
                result_data = None
                if existing_job.result_payload:
                    try:
                        result_data = json.loads(existing_job.result_payload)
                    except Exception:
                        pass
                
                if result_data:
                    # Register in-memory for status polling compatibility
                    _scan_jobs[existing_job.job_id] = {
                        "status": "completed",
                        "progress": "已从历史数据载入",
                        "result": result_data.get("result"),
                        "sectors": result_data.get("sectors"),
                        "error": None,
                        "created_at": existing_job.created_at.isoformat() if existing_job.created_at else datetime.now().isoformat()
                    }
                    return success_response({
                        "job_id": existing_job.job_id,
                        "status": "completed",
                        "result": result_data
                    })

    job_id = f"scan_{uuid.uuid4().hex[:8]}"
    _scan_jobs[job_id] = {
        "status": "running",
        "progress": "正在扫描A股市场板块轮动...",
        "result": None,
        "sectors": [],
        "error": None,
        "created_at": datetime.now().isoformat(),
    }

    task = asyncio.create_task(_run_scan(job_id, model, target_date))
    _scan_tasks[job_id] = task
    task.add_done_callback(lambda t: _scan_tasks.pop(job_id, None))

    return success_response({"job_id": job_id, "status": "running"})


@router.get("/scan/{job_id}")
async def get_scan_status(job_id: str):
    """Poll scan job status. Returns sectors list when completed."""
    job = _scan_jobs.get(job_id)
    if not job:
        return error_response("NOT_FOUND", "Scan job not found")
    return success_response(job)


async def _run_scan(job_id: str, model: str, target_date: str):
    """Execute the market sector scan via LLM + tools."""
    from ..services.llm_gateway import llm_gateway
    from ..prompting.runtime import prompt_runtime

    try:
        _scan_jobs[job_id]["progress"] = "正在加载扫描提示..."

        prompt_data = prompt_runtime.get_prompt("market_sector_scanner")
        template = prompt_data["template"]

        context = f"""
--- SYSTEM DIRECTIVE ---
You are an institutional-grade AI analyst. You MUST use web_search to get real-time data. NEVER fabricate data.

--- SYSTEM INSTRUCTIONS ---
{template}

--- CONTEXT ---
Current Date: {target_date}
Market: A-Share (中国A股)
"""

        _scan_jobs[job_id]["progress"] = "正在搜索和分析市场数据..."

        use_tools = "deepseek" in model.lower()
        if use_tools:
            scan_result = await llm_gateway.generate_with_tools(context, model=model, max_tool_rounds=20)
        else:
            scan_result = await llm_gateway.generate_content(context, model=model)

        if not scan_result:
            _scan_jobs[job_id]["status"] = "failed"
            _scan_jobs[job_id]["error"] = "扫描返回空结果"
            return

        # Extract sectors from the 7-column recommendation table
        sectors = _extract_sectors(scan_result)

        _scan_jobs[job_id]["status"] = "completed"
        _scan_jobs[job_id]["result"] = scan_result
        _scan_jobs[job_id]["sectors"] = sectors
        _scan_jobs[job_id]["progress"] = "扫描完成"

        # Save to SQLite database
        from ..db.sqlite import build_session_factory, DATABASE_URL
        from ..db.models import AnalysisJob
        from sqlmodel import select
        session_factory = build_session_factory(DATABASE_URL)
        with session_factory() as session:
            statement = select(AnalysisJob).where(
                AnalysisJob.symbol == "market_sector_scan",
                AnalysisJob.market == "sector",
                AnalysisJob.snapshot_id == target_date
            )
            for old_job in session.exec(statement).all():
                session.delete(old_job)

            job = AnalysisJob(
                job_id=job_id,
                symbol="market_sector_scan",
                market="sector",
                analysis_level="scan",
                requested_model=model,
                resolved_model=model,
                snapshot_id=target_date,
                status="completed",
                created_at=datetime.now(),
                started_at=datetime.now(),
                finished_at=datetime.now(),
                result_payload=json.dumps({
                    "result": scan_result,
                    "sectors": sectors
                })
            )
            session.add(job)
            session.commit()

    except Exception as e:
        import traceback
        traceback.print_exc()
        _scan_jobs[job_id]["status"] = "failed"
        _scan_jobs[job_id]["error"] = str(e)


def _extract_sectors(scan_result: str) -> list:
    """Extract sector names from the 7-column recommendation table only."""
    sector_lines = re.findall(
        r'(\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|[^|\n]*\|)',
        scan_result
    )
    sectors = []
    seen = set()
    for line in sector_lines:
        m = re.match(r'\|\s*(?:⭐?\d+)\s*\|\s*([^|]+?)\s*\|', line)
        if m:
            name = m.group(1).strip().replace('**', '').strip()
            if len(name) >= 2 and not name.startswith('排序') and name not in seen:
                seen.add(name)
                sectors.append(name)
    return sectors


# ---------- Analyze ----------

@router.post("/analyze")
async def start_sector_analysis(req: SectorAnalyzeRequest):
    """Start a sector deep analysis job (snapshot → expert discussion → report)."""
    from ..db.sqlite import build_session_factory, DATABASE_URL
    from ..db.repositories.job_repo import JobRepository
    from ..services.sector_analysis_service import SectorAnalysisService
    from ..db.models import AnalysisJob
    from sqlmodel import select

    session_factory = build_session_factory(DATABASE_URL)
    job_repo = JobRepository(session_factory)
    service = SectorAnalysisService(job_repo)

    target_date = req.date if req.date else datetime.now().strftime("%Y-%m-%d")
    model = _resolve_model(req.model)

    # Cache check
    if not req.force:
        with session_factory() as session:
            statement = select(AnalysisJob).where(
                AnalysisJob.symbol == req.sector_name,
                AnalysisJob.market == "sector",
                AnalysisJob.status == "completed",
                AnalysisJob.snapshot_id == target_date
            ).order_by(AnalysisJob.finished_at.desc())
            existing_job = session.exec(statement).first()
            if existing_job:
                # Register in-memory reference
                _scan_jobs[f"analyze_{existing_job.job_id}"] = {
                    "service": service,
                    "job_repo": job_repo,
                }
                return success_response({
                    "job_id": existing_job.job_id,
                    "status": "completed"
                })

    job_id = await service.start_sector_job(req.sector_name, model=model, target_date=target_date)

    # Keep reference so we can poll progress
    _scan_jobs[f"analyze_{job_id}"] = {
        "service": service,
        "job_repo": job_repo,
    }

    return success_response({"job_id": job_id, "status": "running"})


@router.get("/analyze/{job_id}")
async def get_sector_analysis_status(job_id: str):
    """Poll sector analysis job status."""
    meta = _scan_jobs.get(f"analyze_{job_id}")

    # If in-memory reference lost (e.g. after hot-reload), recreate from DB
    if not meta:
        from ..db.sqlite import build_session_factory, DATABASE_URL
        from ..db.repositories.job_repo import JobRepository
        from ..services.sector_analysis_service import SectorAnalysisService

        session_factory = build_session_factory(DATABASE_URL)
        job_repo = JobRepository(session_factory)
        service = SectorAnalysisService(job_repo)
        meta = {"service": service, "job_repo": job_repo}
        _scan_jobs[f"analyze_{job_id}"] = meta

    service: Any = meta["service"]
    job_repo = meta["job_repo"]

    db_job = job_repo.get_by_id(job_id)
    if not db_job:
        return error_response("NOT_FOUND", "Job not found in database")

    progress = service.get_progress(job_id)

    result_data = None
    if db_job.status == "completed":
        result_data = service.get_result(job_id)
        if not result_data and db_job.result_payload:
            import json
            try:
                result_data = json.loads(db_job.result_payload)
            except Exception:
                pass

    return JSONResponse(content=_sanitize_for_json({
        "success": True,
        "data": {
            "job_id": job_id,
            "status": db_job.status,
            "progress": progress,
            "error": db_job.error_message,
            "result": result_data,
        }
    }))


@router.get("/report/{job_id}")
async def get_sector_report(job_id: str):
    """Generate and return sector HTML report."""
    from ..services.sector_report_service import SectorReportService
    from fastapi.responses import HTMLResponse

    meta = _scan_jobs.get(f"analyze_{job_id}")
    if not meta:
        from ..db.sqlite import build_session_factory, DATABASE_URL
        from ..db.repositories.job_repo import JobRepository
        from ..services.sector_analysis_service import SectorAnalysisService

        session_factory = build_session_factory(DATABASE_URL)
        job_repo = JobRepository(session_factory)
        service = SectorAnalysisService(job_repo)
        meta = {"service": service, "job_repo": job_repo}
        _scan_jobs[f"analyze_{job_id}"] = meta

    service = meta["service"]
    job_repo = meta["job_repo"]

    result = service.get_result(job_id)
    if not result:
        db_job = job_repo.get_by_id(job_id)
        if db_job and db_job.result_payload:
            import json
            try:
                result = json.loads(db_job.result_payload)
            except Exception:
                pass

    if not result:
        return error_response("NO_RESULT", "No analysis result available for report")

    report_service = SectorReportService()
    sector_name = result.get("symbol", "sector")
    output_path = f"sector_{sector_name}_report.html"

    model = _resolve_model()
    html_path = await report_service.generate_sector_report(result, output_path, model=model)

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)


def _get_sector_result(job_id: str):
    """Helper: retrieve sector analysis result from memory or DB."""
    meta = _scan_jobs.get(f"analyze_{job_id}")
    if not meta:
        from ..db.sqlite import build_session_factory, DATABASE_URL
        from ..db.repositories.job_repo import JobRepository
        from ..services.sector_analysis_service import SectorAnalysisService

        session_factory = build_session_factory(DATABASE_URL)
        job_repo = JobRepository(session_factory)
        service = SectorAnalysisService(job_repo)
        meta = {"service": service, "job_repo": job_repo}

    service = meta["service"]
    job_repo = meta["job_repo"]

    result = service.get_result(job_id)
    if not result:
        db_job = job_repo.get_by_id(job_id)
        if db_job and db_job.result_payload:
            try:
                result = json.loads(db_job.result_payload)
            except Exception:
                pass
    return result


@router.get("/report/{job_id}/pdf")
async def export_sector_pdf(job_id: str):
    """Export sector report as PDF."""
    from ..services.sector_report_service import SectorReportService
    from ..services.export_service import export_service
    from fastapi.responses import Response

    result = _get_sector_result(job_id)
    if not result:
        return error_response("NO_RESULT", "No analysis result available")

    report_service = SectorReportService()
    sector_name = result.get("symbol", "sector")
    output_path = f"sector_{sector_name}_report.html"
    model = _resolve_model()
    html_path = await report_service.generate_sector_report(result, output_path, model=model)

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    pdf_bytes = await export_service.html_to_pdf(html_content, landscape=False)
    filename = f"SectorReport_{sector_name}_{job_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report/{job_id}/share-card")
async def export_sector_share_card(job_id: str):
    """Generate a share card image for sector analysis."""
    from ..services.export_service import export_service
    from fastapi.responses import Response

    result = _get_sector_result(job_id)
    if not result:
        return error_response("NO_RESULT", "No analysis result available")

    sector_name = result.get("symbol", "板块")
    summary_text = result.get("summary", "")
    highlights = []
    if isinstance(summary_text, str) and len(summary_text) > 20:
        # Split into sentences for highlights
        sentences = [s.strip() for s in summary_text.replace("。", ".\n").split("\n") if s.strip()]
        highlights = sentences[:4]

    card_html = export_service.build_share_card_html(
        title=f"{sector_name} 板块分析",
        verdict="",
        score=None,
        highlights=highlights or [summary_text[:100]] if summary_text else [],
        report_type="sector",
    )
    png_bytes = await export_service.html_to_image(card_html, width=460)
    filename = f"ShareCard_Sector_{sector_name}.png"
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- History ----------

@router.get("/history/dates")
async def get_history_dates():
    """Retrieve all dates (snapshot_ids) that have completed scans or analyses."""
    from ..db.sqlite import build_session_factory, DATABASE_URL
    from ..db.models import AnalysisJob
    from sqlmodel import select

    session_factory = build_session_factory(DATABASE_URL)
    with session_factory() as session:
        statement = select(AnalysisJob.snapshot_id).where(
            AnalysisJob.market == "sector",
            AnalysisJob.status == "completed",
            AnalysisJob.snapshot_id != None
        )
        dates = session.exec(statement).all()
        # Filter to only valid date format YYYY-MM-DD
        valid_dates = sorted(list(set(d for d in dates if d and re.match(r'^\d{4}-\d{2}-\d{2}$', d))))
        return success_response({"dates": valid_dates})


@router.get("/history")
async def get_history_by_date(date: str, type: str, sector_name: Optional[str] = None):
    """Retrieve historical scan or analysis result for a given date."""
    from ..db.sqlite import build_session_factory, DATABASE_URL
    from ..db.models import AnalysisJob
    from sqlmodel import select

    if type not in ("scan", "analysis"):
        return error_response("INVALID_PARAM", "Type must be scan or analysis")

    symbol = "market_sector_scan" if type == "scan" else sector_name
    if not symbol:
        return error_response("INVALID_PARAM", "sector_name is required for analysis type")

    session_factory = build_session_factory(DATABASE_URL)
    with session_factory() as session:
        statement = select(AnalysisJob).where(
            AnalysisJob.symbol == symbol,
            AnalysisJob.market == "sector",
            AnalysisJob.status == "completed",
            AnalysisJob.snapshot_id == date
        ).order_by(AnalysisJob.finished_at.desc())
        job = session.exec(statement).first()
        if not job:
            return error_response("NOT_FOUND", "No historical record found for this date")

        result_data = None
        if job.result_payload:
            try:
                result_data = json.loads(job.result_payload)
            except Exception:
                pass

        return success_response({
            "job_id": job.job_id,
            "status": job.status,
            "result": result_data,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None
        })
