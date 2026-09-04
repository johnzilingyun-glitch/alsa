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
from pydantic import BaseModel, Field
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

# Per-job update locks: serialize the Redis read-modify-write cycle below.
# Race fix (scan stuck in "running" forever): scan completion used to fire
# FOUR concurrent fire-and-forget updates, each doing GET → merge → SET on the
# same `scan_job:{job_id}` key. Interleaved GETs all observed the same stale
# snapshot, so the last SET won and silently dropped fields written by the
# other tasks — get_scan_status then served a job dict missing
# status/result/sectors and SectorScanner.tsx (which switches UI state on
# job.status === 'completed') never detected the completed state. All
# scan-job writers live in this process (asyncio tasks on the API loop), so an
# in-process lock fully serializes them; locks are created lazily inside the
# running loop (Python ≥3.10 asyncio primitives bind to the loop on first
# use, never at construction).
_scan_job_update_locks: Dict[str, asyncio.Lock] = {}

async def _update_scan_job_redis(job_id: str, **kwargs):
    redis = await RedisManager.get_client()
    key = f"scan_job:{job_id}"
    lock = _scan_job_update_locks.setdefault(job_id, asyncio.Lock())
    async with lock:
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
    openrouter_api_key: Optional[str] = None


class SectorAnalyzeRequest(BaseModel):
    # pattern=\S uses search semantics: the name must contain at least one
    # non-whitespace char, so " 化肥 " stays valid while pure whitespace
    # (" ", "\t") is rejected. min_length=1 alone lets " " through.
    sector_name: str = Field(..., min_length=1, pattern=r"\S")
    model: Optional[str] = None
    date: Optional[str] = None
    force: Optional[bool] = False
    gemini_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    pipeline_version: Optional[str] = "production"
    verification_mode: str = "quick"  # Modes: 'extreme', 'quick', 'quality'


class SerenityAnalyzeRequest(BaseModel):
    # None keeps the "A股市场" default inside the handler; only empty strings
    # and pure-whitespace strings are rejected (same \S pattern as above).
    sector_name: Optional[str] = Field(None, min_length=1, pattern=r"\S")
    model: Optional[str] = None
    date: Optional[str] = None
    force: Optional[bool] = False
    gemini_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    pipeline_version: Optional[str] = "production"
    experts: Optional[list[str]] = None
    verification_mode: str = "quick"  # Modes: 'extreme', 'quick', 'quality'

def _resolve_model(requested: Optional[str] = None) -> str:
    if requested:
        return requested
    
    # Fallback based on available API keys. Provider ordering mirrors
    # llm_gateway._generate_content_inner: for non-gemini models OpenRouter is
    # tried FIRST, so an OpenRouter key wins the fallback chain and resolves to
    # the same default model as LLMGateway.default_model (DEFAULT_LLM_MODEL env).
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY"))
    has_openrouter = bool(os.getenv("OPENROUTER_API_KEY"))
    
    if has_openrouter:
        # `or` (not getenv default): a present-but-empty DEFAULT_LLM_MODEL must
        # fall back to the builtin default instead of resolving to "" (empty
        # model name would fail every provider after the job has started).
        return os.getenv("DEFAULT_LLM_MODEL") or "minimax/minimax-m3:free"
    elif has_gemini:
        return os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    elif has_deepseek:
        return os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    else:
        raise ValueError("请在配置中添加大模型 API Key（OpenRouter、Gemini 或 DeepSeek）")


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
    # Await the initial full-state write (was fire-and-forget) so the job
    # record is durably in Redis BEFORE _run_scan's progress updates can
    # interleave with it — the per-job lock keeps them lossless, and awaiting
    # guarantees a well-defined baseline document for every later merge.
    await _update_scan_job_redis(job_id,
        status="running",
        progress="正在扫描A股市场板块轮动...",
        result=None,
        sectors=[],
        error=None,
        created_at=datetime.now().isoformat()
    )

    task = asyncio.create_task(_run_scan(
        job_id, model, target_date, 
        gemini_api_key=req.gemini_api_key, 
        deepseek_api_key=req.deepseek_api_key,
        openrouter_api_key=req.openrouter_api_key
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
            # Single atomic write (was two concurrent racing tasks that could
            # drop the status field when interleaved).
            await _update_scan_job_redis(job_id, status="cancelled", error="已手动取消")
        return success_response({"status": "cancelled"})
    return error_response("NOT_FOUND", "Running scan job not found or already completed")


async def _run_scan(job_id: str, model: str, target_date: str, gemini_api_key: str = None, deepseek_api_key: str = None, openrouter_api_key: str = None):
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

        # 与讨论路径(discussion_service._call_expert)一致的能力判定：
        # - Gemini: llm_gateway 内部自动附加 google_search 原生接地
        # - DeepSeek: agent_orchestrator 内部走原生函数调用
        # - 其余模型(MiniMax/OpenRouter 全系): generate_with_tools 的
        #   【文本】工具循环。旧门控 use_tools = "deepseek" in model.lower()
        #   使 MiniMax 走无工具的 generate_content，而上方 SYSTEM DIRECTIVE
        #   却要求 MUST web_search；且文本循环模型必须在 context 中注入
        #   文本协议工具文档，否则模型无从发起工具调用（修复 2026-09-01）。
        model_lower = (model or "").lower()
        is_gemini = "gemini" in model_lower
        is_deepseek = "deepseek" in model_lower
        use_text_tool_protocol = not is_gemini and not is_deepseek

        if use_text_tool_protocol:
            from ..services.expert_tools import format_tool_descriptions
            context += (
                "\n\n--- [MANDATORY] SEARCH TOOL STATUS ---\n"
                "✅ **搜索工具状态: 工具调用已启用**\n"
                "使用规则：\n"
                "1. **主动使用工具**: 当需要实时数据时，必须使用工具获取数据，严禁猜测。\n"
                "2. **禁止伪造**: 如果工具返回无结果，标注 'UNKNOWN'，绝不编造。\n\n"
                + format_tool_descriptions(role=None, language="zh-CN")
            )

        # Stream progress callback: update in-memory job data with char count
        # so the frontend polling sees live progress and never times out while AI is active
        def _on_chunk(count, message=None):
            # ONE Redis write per chunk carrying BOTH progress and content_count.
            # Previously these were two concurrent fire-and-forget
            # read-modify-write tasks on the same key and one of the two fields
            # was regularly lost to the race; the per-job update lock now
            # serializes any remaining concurrent writers as well.
            progress = message or f"AI 正在生成分析内容... ({count:,} chars)"
            asyncio.create_task(_update_scan_job_redis(job_id, progress=progress, content_count=count))

        # No hard timeout — let the model run as long as it is producing output.
        # The frontend uses activity-based timeout (300s of zero progress change).
        if use_text_tool_protocol or is_deepseek:
            # tools_enabled: 仅文本协议模型(MiniMax/OpenRouter 全系)为 True，
            # 使 agent_orchestrator 在首轮无 tool_call 时发送一次性强制提醒
            # （nudge）；DeepSeek 走内部原生 FC，不受该参数影响。
            scan_result = await agent_orchestrator.generate_with_tools(
                context, model=model, max_tool_rounds=20,
                on_chunk=_on_chunk,
                gemini_api_key=gemini_api_key, deepseek_api_key=deepseek_api_key,
                openrouter_api_key=openrouter_api_key,
                tools_enabled=use_text_tool_protocol
            )
        else:
            scan_result = await llm_gateway.generate_content(
                context, model=model,
                on_chunk=_on_chunk,
                gemini_api_key=gemini_api_key, deepseek_api_key=deepseek_api_key,
                openrouter_api_key=openrouter_api_key
            )

        if not scan_result:
            # Single atomic write of the full failed state (was two racing tasks).
            await _update_scan_job_redis(job_id, status="failed", error="扫描返回空结果")
            return

        # Extract sectors from the 7-column recommendation table
        sectors = _extract_sectors(scan_result)

        # Single atomic write of the FULL completed state (status + result +
        # sectors + progress in ONE payload). The old code fired four
        # concurrent read-modify-write tasks on the same key; interleaved reads
        # meant the last writer dropped fields written by the others, leaving
        # the polled job without status/result/sectors. Awaiting (instead of
        # fire-and-forget) guarantees the completed state is durable in Redis
        # before SQLite persistence / task exit, so the frontend poller sees
        # "completed" immediately on its next poll.
        await _update_scan_job_redis(job_id, status="completed", result=scan_result, sectors=sectors, progress="扫描完成")

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
        logger.exception(f"[SectorScan] Job {job_id} failed")
        try:
            # Single atomic write of the full failed state (was two racing tasks).
            await _update_scan_job_redis(job_id, status="failed", error=str(e))
        except Exception as redis_err:
            # Redis being down must not mask the original failure in the logs.
            logger.error(f"[SectorScan] Failed to persist failed status for {job_id}: {redis_err}")


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
            "deepseekApiKey": req.deepseek_api_key,
            "openrouterApiKey": req.openrouter_api_key,
        },
        verification_mode=req.verification_mode
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

    # Cache check — skip when specific experts are selected or force is set
    if not req.force and not req.experts:
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
            "deepseekApiKey": req.deepseek_api_key,
            "openrouterApiKey": req.openrouter_api_key,
            "experts": req.experts,
        },
        verification_mode=req.verification_mode
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
