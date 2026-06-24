"""Sector Analysis API — market scan + sector deep analysis endpoints."""
import os
import re
import json
import math
import asyncio
import uuid
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from ..utils.responses import success_response, error_response
from ..db.redis_client import RedisManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sector", tags=["sector"])

# Project root: python_service/app/api/sector.py -> api -> app -> python_service -> <root>
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SECTOR_REPORTS_DIR = os.getenv("SECTOR_REPORTS_DIR", os.path.join(_PROJECT_ROOT, "reports", "sector"))

# In-memory store for scan/analysis jobs (same pattern as AnalysisJobService)
_scan_jobs: Dict[str, Dict[str, Any]] = {}
_scan_tasks: Dict[str, asyncio.Task] = {}

async def _update_scan_job_redis(job_id: str, **kwargs):
    redis = await RedisManager.get_client()
    key = f"scan_job:{job_id}"
    data = await redis.get(key)
    job = json.loads(data) if data else {}
    job.update(kwargs)
    await redis.set(key, json.dumps(job), ex=86400)

async def _get_scan_job_redis(job_id: str):
    redis = await RedisManager.get_client()
    data = await redis.get(f"scan_job:{job_id}")
    return json.loads(data) if data else None




class SectorScanRequest(BaseModel):
    model: Optional[str] = None
    date: Optional[str] = None
    force: Optional[bool] = False
    gemini_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None


class SectorAnalyzeRequest(BaseModel):
    sector_name: str
    model: Optional[str] = None
    date: Optional[str] = None
    force: Optional[bool] = False
    gemini_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    pipeline_version: Optional[str] = "production"


class SerenityAnalyzeRequest(BaseModel):
    sector_name: Optional[str] = None
    model: Optional[str] = None
    date: Optional[str] = None
    force: Optional[bool] = False
    gemini_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    pipeline_version: Optional[str] = "production"


def _resolve_model(requested: Optional[str] = None) -> str:
    if requested:
        return requested
    
    # Fallback based on available API keys
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY"))
    
    if has_gemini:
        return os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    elif has_deepseek:
        return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    else:
        raise ValueError("请在配置中添加大模型 API Key（Gemini 或 DeepSeek）")


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


def _escape_like(s: str) -> str:
    """Escape special characters for SQL LIKE clause."""
    if not s:
        return s
    # Also block SQL injection characters
    s = s.replace("'", "").replace('"', '').replace('--', '').replace(';', '')
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

# ---------- Scan ----------

@router.post("/run")
async def start_scan(req: SectorScanRequest):
    """Start an async market sector scan."""
    from ..db.database import session_factory
    from ..db.models import AnalysisJob
    from sqlmodel import select

    target_date = req.date if req.date else datetime.now().strftime("%Y-%m-%d")
    try:
        model = _resolve_model(req.model)
    except ValueError as e:
        return error_response("INVALID_PARAM", str(e))

    # Cache check
    if not req.force:
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
                        result_data = existing_job.result_payload if isinstance(existing_job.result_payload, dict) else (json.loads(existing_job.result_payload) if existing_job.result_payload else None)
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
    asyncio.create_task(_update_scan_job_redis(job_id, 
        status="running",
        progress="正在扫描A股市场板块轮动...",
        result=None,
        sectors=[],
        error=None,
        created_at=datetime.now().isoformat()
    ))

    task = asyncio.create_task(_run_scan(
        job_id, model, target_date, 
        gemini_api_key=req.gemini_api_key, 
        deepseek_api_key=req.deepseek_api_key
    ))
    _scan_tasks[job_id] = task
    task.add_done_callback(lambda t: _scan_tasks.pop(job_id, None))

    logger.info(f"[SectorScan] Started {job_id} with model={model}, date={target_date}")
    return success_response({"job_id": job_id, "status": "running"})


@router.get("/run/{job_id}")
async def get_scan_status(job_id: str):
    """Poll scan job status. Returns sectors list when completed."""
    job = await _get_scan_job_redis(job_id)
    if not job:
        return error_response("NOT_FOUND", "Scan job not found")
    return success_response(job)


@router.post("/run/{job_id}/cancel")
async def cancel_scan(job_id: str):
    """Cancel a running scan job."""
    task = _scan_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
        if job_id in _scan_jobs:
            asyncio.create_task(_update_scan_job_redis(job_id, status="cancelled"))
            asyncio.create_task(_update_scan_job_redis(job_id, error="已手动取消"))
        return success_response({"status": "cancelled"})
    return error_response("NOT_FOUND", "Running scan job not found or already completed")


async def _run_scan(job_id: str, model: str, target_date: str, gemini_api_key: str = None, deepseek_api_key: str = None):
    """Execute the market sector scan via LLM + tools."""
    from ..services.llm_gateway import llm_gateway
    from ..services.agent_orchestrator import agent_orchestrator
    from ..prompting.runtime import prompt_runtime

    try:
        asyncio.create_task(_update_scan_job_redis(job_id, progress="正在加载扫描提示..."))

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

        asyncio.create_task(_update_scan_job_redis(job_id, progress="正在搜索和分析市场数据..."))

        use_tools = "deepseek" in model.lower()

        # Stream progress callback: update in-memory job data with char count
        # so the frontend polling sees live progress and never times out while AI is active
        def _on_chunk(count, message=None):
            if message:
                asyncio.create_task(_update_scan_job_redis(job_id, progress=message))
            else:
                asyncio.create_task(_update_scan_job_redis(job_id, progress=f"AI 正在生成分析内容... ({count:,} chars)"))
            asyncio.create_task(_update_scan_job_redis(job_id, content_count=count))

        # No hard timeout — let the model run as long as it is producing output.
        # The frontend uses activity-based timeout (300s of zero progress change).
        if use_tools:
            scan_result = await agent_orchestrator.generate_with_tools(
                context, model=model, max_tool_rounds=20,
                on_chunk=_on_chunk,
                gemini_api_key=gemini_api_key, deepseek_api_key=deepseek_api_key
            )
        else:
            scan_result = await llm_gateway.generate_content(
                context, model=model,
                on_chunk=_on_chunk,
                gemini_api_key=gemini_api_key, deepseek_api_key=deepseek_api_key
            )

        if not scan_result:
            asyncio.create_task(_update_scan_job_redis(job_id, status="failed"))
            asyncio.create_task(_update_scan_job_redis(job_id, error="扫描返回空结果"))
            return

        # Extract sectors from the 7-column recommendation table
        sectors = _extract_sectors(scan_result)

        asyncio.create_task(_update_scan_job_redis(job_id, status="completed"))
        asyncio.create_task(_update_scan_job_redis(job_id, result=scan_result))
        asyncio.create_task(_update_scan_job_redis(job_id, sectors=sectors))
        asyncio.create_task(_update_scan_job_redis(job_id, progress="扫描完成"))

        # Save to SQLite database
        from ..db.database import session_factory
        from ..db.models import AnalysisJob
        from sqlmodel import select
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
        asyncio.create_task(_update_scan_job_redis(job_id, status="failed"))
        asyncio.create_task(_update_scan_job_redis(job_id, error=str(e)))


def _extract_sectors(scan_result: str) -> list:
    """Extract sector names from the recommendation table or fallback lists."""
    sectors = []
    seen = set()
    
    # Primary: Parse markdown table rows where first column is a rank (number or ⭐number)
    for line in scan_result.split('\n'):
        line = line.strip()
        if not line.startswith('|'):
            continue
            
        m = re.match(r'^\|\s*(?:⭐?\s*\d+\.?)\s*\|\s*([^|]+?)\s*\|', line)
        if m:
            name = m.group(1).strip().replace('**', '').strip()
            if len(name) >= 2 and not name.startswith('排序') and name not in seen:
                seen.add(name)
                sectors.append(name)

    # Fallback: Parse numbered lists if the AI failed to generate a table
    if not sectors:
        list_matches = re.findall(r'^\s*\d+\.\s*(?:\*\*)?([^:\*\n]+)(?:\*\*)?[:：]', scan_result, re.MULTILINE)
        for name in list_matches:
            name = name.strip().replace('**', '').strip()
            if len(name) >= 2 and name not in seen:
                seen.add(name)
                sectors.append(name)
                
    return sectors


# ---------- Analyze ----------

@router.post("/analyze")
async def start_sector_analysis(req: SectorAnalyzeRequest):
    """Start a sector deep analysis job (snapshot → expert discussion → report)."""
    from ..db.database import session_factory
    from ..db.repositories.job_repo import JobRepository
    from ..services.sector_analysis_service import SectorAnalysisService
    from ..db.models import AnalysisJob
    from sqlmodel import select

    job_repo = JobRepository(session_factory)
    service = SectorAnalysisService(job_repo)

    target_date = req.date if req.date else datetime.now().strftime("%Y-%m-%d")
    try:
        model = _resolve_model(req.model)
    except ValueError as e:
        return error_response("INVALID_PARAM", str(e))

    # Cache check
    if not req.force:
        with session_factory() as session:
            statement = select(AnalysisJob).where(
                AnalysisJob.market == "sector",
                AnalysisJob.status == "completed",
                AnalysisJob.snapshot_id == target_date,
                AnalysisJob.symbol.like(f"%{_escape_like(req.sector_name)}%")
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

    job_id = await service.start_sector_job(
        req.sector_name, model=model, target_date=target_date,
        config={
            "geminiApiKey": req.gemini_api_key,
            "deepseekApiKey": req.deepseek_api_key
        }
    )

    # Keep reference so we can poll progress
    _scan_jobs[f"analyze_{job_id}"] = {
        "service": service,
        "job_repo": job_repo,
    }

    return success_response({"job_id": job_id, "status": "running"})


@router.post("/serenity-analyze")
async def start_serenity_analysis(req: SerenityAnalyzeRequest):
    """Start a sector analysis job using Serenity Alpha Analyst only."""
    from ..db.database import session_factory
    from ..db.repositories.job_repo import JobRepository
    from ..services.sector_analysis_service import SectorAnalysisService
    from ..services.serenity_graph import SerenityGraphService
    from ..db.models import AnalysisJob
    from sqlmodel import select

    job_repo = JobRepository(session_factory)
    if req.pipeline_version == "development":
        service = SerenityGraphService(job_repo)
    else:
        service = SectorAnalysisService(job_repo)

    sector_name = req.sector_name if req.sector_name else "A股市场"
    target_date = req.date if req.date else datetime.now().strftime("%Y-%m-%d")
    try:
        model = _resolve_model(req.model)
    except ValueError as e:
        return error_response("INVALID_PARAM", str(e))

    # Cache check
    if not req.force:
        with session_factory() as session:
            statement = select(AnalysisJob).where(
                AnalysisJob.market == "sector",
                AnalysisJob.analysis_level == "serenity_alpha",
                AnalysisJob.status == "completed",
                AnalysisJob.snapshot_id == target_date,
                AnalysisJob.symbol.like(f"%{_escape_like(sector_name)}%")
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

    job_id = await service.start_sector_job(
        sector_name, model=model, target_date=target_date, level="serenity_alpha",
        config={
            "geminiApiKey": req.gemini_api_key,
            "deepseekApiKey": req.deepseek_api_key
        }
    )

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
        from ..db.database import session_factory
        from ..db.repositories.job_repo import JobRepository
        from ..services.sector_analysis_service import SectorAnalysisService

        job_repo = JobRepository(session_factory)
        service = SectorAnalysisService(job_repo)
        meta = {"service": service, "job_repo": job_repo}
        _scan_jobs[f"analyze_{job_id}"] = meta

    service: Any = meta["service"]
    job_repo = meta["job_repo"]

    db_job = job_repo.get_by_id(job_id)
    if not db_job:
        return error_response("NOT_FOUND", "Job not found in database")

    progress = await service.get_progress(job_id)

    result_data = None
    if db_job.status == "completed":
        result_data = service.get_result(job_id)
        if not result_data and db_job.result_payload:
            import json
            try:
                result_data = db_job.result_payload if isinstance(db_job.result_payload, dict) else (json.loads(db_job.result_payload) if db_job.result_payload else None)
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


@router.post("/analyze/{job_id}/cancel")
async def cancel_sector_analysis(job_id: str):
    """Cancel a running sector analysis job."""
    meta = _scan_jobs.get(f"analyze_{job_id}")
    if meta:
        service = meta["service"]
        task = service._running_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            service.job_repo.update_status(job_id, "cancelled")
            return success_response({"status": "cancelled"})
    return error_response("NOT_FOUND", "Running analysis job not found or already completed")


@router.get("/report/{job_id}")
async def get_sector_report(job_id: str):
    """Generate and return sector HTML report."""
    from ..services.sector_report_service import SectorReportService
    from fastapi.responses import HTMLResponse

    meta = _scan_jobs.get(f"analyze_{job_id}")
    if not meta:
        from ..db.database import session_factory
        from ..db.repositories.job_repo import JobRepository
        from ..services.sector_analysis_service import SectorAnalysisService

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
                result = db_job.result_payload if isinstance(db_job.result_payload, dict) else (json.loads(db_job.result_payload) if db_job.result_payload else None)
            except Exception:
                pass

    if not result:
        return error_response("NO_RESULT", "No analysis result available for report")

    report_service = SectorReportService()
    date_str = datetime.now().strftime("%Y-%m-%d")
    last_updated = result.get("stockInfo", {}).get("lastUpdated", "")
    if last_updated:
        date_str = last_updated[:10].replace("/", "-")
        
    output_path = os.path.join(SECTOR_REPORTS_DIR, date_str, f"report_{job_id}.html")

    # Report rendering is pure markdown->HTML; no LLM/API key required.
    html_path = await report_service.generate_sector_report(result, output_path)

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)


def _get_sector_result(job_id: str):
    """Helper: retrieve sector analysis result from memory or DB."""
    meta = _scan_jobs.get(f"analyze_{job_id}")
    if not meta:
        from ..db.database import session_factory
        from ..db.repositories.job_repo import JobRepository
        from ..services.sector_analysis_service import SectorAnalysisService

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
                result = db_job.result_payload if isinstance(db_job.result_payload, dict) else (json.loads(db_job.result_payload) if db_job.result_payload else None)
            except Exception:
                pass
    return result


@router.get("/report/{job_id}/html")
async def export_sector_html(job_id: str):
    """Export sector report as HTML file."""
    from ..services.sector_report_service import SectorReportService
    from fastapi.responses import Response

    result = _get_sector_result(job_id)
    if not result:
        return error_response("NO_RESULT", "No analysis result available")

    report_service = SectorReportService()
    date_str = datetime.now().strftime("%Y-%m-%d")
    last_updated = result.get("stockInfo", {}).get("lastUpdated", "")
    if last_updated:
        date_str = last_updated[:10].replace("/", "-")
        
    output_path = os.path.join(SECTOR_REPORTS_DIR, date_str, f"report_{job_id}.html")
    html_path = await report_service.generate_sector_report(result, output_path)

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    import urllib.parse
    filename = f"SectorReport_{job_id}.html"
    encoded_filename = urllib.parse.quote(filename)
    return Response(
        content=html_content,
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"},
    )
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
    date_str = datetime.now().strftime("%Y-%m-%d")
    last_updated = result.get("stockInfo", {}).get("lastUpdated", "")
    if last_updated:
        date_str = last_updated[:10].replace("/", "-")
        
    output_path = os.path.join(SECTOR_REPORTS_DIR, date_str, f"report_{job_id}.html")
    html_path = await report_service.generate_sector_report(result, output_path)

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    pdf_bytes = await export_service.html_to_pdf(html_content, landscape=False)
    import urllib.parse
    filename = f"SectorReport_{job_id}.pdf"
    encoded_filename = urllib.parse.quote(filename)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"},
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
    filename = f"ShareCard_Sector_{job_id}.png"
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- History ----------

@router.get("/history/dates")
async def get_history_dates():
    """Retrieve all dates (snapshot_ids) that have completed scans or analyses."""
    from ..db.database import session_factory
    from ..db.models import AnalysisJob
    from sqlmodel import select

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
    from ..db.database import session_factory
    from ..db.models import AnalysisJob
    from sqlmodel import select

    if type not in ("scan", "analysis"):
        return error_response("INVALID_PARAM", "Type must be scan or analysis")

    symbol = "market_sector_scan" if type == "scan" else sector_name
    if not symbol:
        return error_response("INVALID_PARAM", "sector_name is required for analysis type")

    with session_factory() as session:
        if type == "scan":
            # Fetch the main scan job if it exists
            statement = select(AnalysisJob).where(
                AnalysisJob.symbol == symbol,
                AnalysisJob.market == "sector",
                AnalysisJob.status == "completed",
                AnalysisJob.snapshot_id == date
            ).order_by(AnalysisJob.finished_at.desc())
            job = session.exec(statement).first()

            # Also fetch all manually analyzed sectors for this date
            manual_statement = select(AnalysisJob.symbol).where(
                AnalysisJob.market == "sector",
                AnalysisJob.status == "completed",
                AnalysisJob.snapshot_id == date,
                AnalysisJob.symbol != "market_sector_scan"
            )
            manual_sectors = session.exec(manual_statement).all()

            if not job and not manual_sectors:
                return error_response("NOT_FOUND", "No historical record found for this date")

            # Build or extend the scan result payload
            result_data = None
            sectors_set = set()
            
            if job and job.result_payload:
                try:
                    result_data = job.result_payload if isinstance(job.result_payload, dict) else (json.loads(job.result_payload) if job.result_payload else None)
                    sectors_set.update(result_data.get("sectors", []))
                except Exception:
                    pass
            
            if not result_data:
                result_data = {
                    "result": "当日未执行全市场扫描大模型分析。以下为手动分析保存的板块/主题：", 
                    "sectors": []
                }
            
            # Merge custom manually analyzed sectors
            for s in manual_sectors:
                if s:
                    sectors_set.add(s)
            
            result_data["sectors"] = list(sectors_set)

            return success_response({
                "job_id": job.job_id if job else "custom_history",
                "status": "completed",
                "result": result_data
            })
        else:
            statement = select(AnalysisJob).where(
                AnalysisJob.market == "sector",
                AnalysisJob.status == "completed",
                AnalysisJob.snapshot_id == date,
                AnalysisJob.symbol.like(f"%{_escape_like(symbol)}%")
            ).order_by(AnalysisJob.finished_at.desc())
            
            job = session.exec(statement).first()
            if not job:
                return error_response("NOT_FOUND", "No historical record found for this date")

            result_data = None
            if job.result_payload:
                try:
                    result_data = job.result_payload if isinstance(job.result_payload, dict) else (json.loads(job.result_payload) if job.result_payload else None)
                except Exception:
                    pass

            return success_response({
                "job_id": job.job_id,
                "status": job.status,
            "result": result_data,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None
        })
