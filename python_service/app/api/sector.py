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

# English section-title blacklist for Gemini fallback. Used by
# _extract_sectors._is_valid_sector_name (allow_english path). Module-level so
# the lowercased lookup set can be built once at import time (avoid rebuilding on
# every sector-name check).
_EN_SECTION_TITLES = frozenset({
    "Risk Warning", "Risk Warnings", "Risk Disclosure", "Risk Disclosures",
    "Risk Statement", "Data Verification", "Data Source", "Data Sources",
    "Data Note", "Disclaimer", "Disclaimers", "Executive Summary",
    "Summary", "Introduction", "Conclusion", "Methodology",
    "Methodologies", "Method", "Methods",
})
_en_section_titles_lower = frozenset(t.lower() for t in _EN_SECTION_TITLES)

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


# ---------- Local sector snapshot (ground truth fallback) ----------
#
# 为什么需要：板块扫描（market_sector_scanner）原本完全依赖 LLM 自己调
# web_search / news_search 拿数据。当前生产环境下：
#   1) DDG 通过 SOCKS5 仍然 GFW 阻断
#   2) cn-financial-scraper 30+ 媒体源经 privoxy 转发全 503
#   3) MiniMax/OpenRouter 文本协议模型在第一轮大概率不发 tool_call，
#      nudge 后若工具仍然空返回，会被 agent_orchestrator 第4 轮强制
#      完成"用已有数据写"——但它什么数据都没有，于是老实标 UNKNOWN
# 所以结果就是：扫描完成 → sectors=["数据源验证","替代数据源",...]
# 全是章节标题，正则解析误识别为板块。
#
# 修复：在 prompt 注入之前，预先用 ths_provider 取一次申万行业（90 个）
# 的真实板块快照（涨幅/5日/10日/20日/主力净流入/量比/领涨股/涨跌家数
# /成交额/市值），作为 [GROUND TRUTH] block 强制喂给模型。thsdk 直连
# （无需代理），两次批量调用 ~1 秒即可完成 90 个板块，零依赖外网。
#
# 取数 schema：见 expert_tools.py -> ths_provider.get_market_data_block
#   基础数据: 成交量/总金额/领涨股/涨跌家数/板块流通市值/板块总市值
#   扩展:     量比/涨幅/5日/10日/20日涨幅/板块涨速/主力净流入
async def _build_market_scan_snapshot(target_date: str) -> str:
    """Return a markdown snapshot table for all SW industries, or '' on failure.

    The table is sorted by today's 涨跌幅 descending and capped to TOP 25 +
    BOTTOM 10 so the model sees the most informative ranking instead of
    raw 90-row dump that would blow the context budget. 失败时返回空串，
    让上游继续走老路径（不会因为本地数据源挂了把整个扫描任务搞挂）。"""
    try:
        from ..services.data_providers.ths_provider import ths_provider
    except Exception as e:
        logger.warning(f"[SectorScan] ths_provider import failed: {e}")
        return ""

    try:
        ind = await asyncio.wait_for(ths_provider.get_ths_industry(), timeout=10.0)
        codes = [d.get("代码") for d in (ind.get("data") or []) if d.get("代码")]
        if not codes:
            logger.warning("[SectorScan] ths_industry returned no codes")
            return ""

        # 两次批量：基础数据 + 扩展。两批都吃 90 板块 ~1 秒，比串行 180
        # 次 thsdk 连接快 2 个数量级；thsdk guest 账户每连接换 mac，
        # 串行调用会导致 mac 池耗尽被服务端拒绝。
        #
        # ths_provider.get_market_data_block 内部已经 try/except + 返回空 dict，
        # 所以这里不需要再次 isinstance(Exception) 隔离；只要空 dict 即可。
        # 但仍要保留 timeout + 各自的 wait_for —— 防止 thsdk guest 线程
        # 永久卡死（thsdk 是同步的，_run_sync 把同步函数扔进 thread pool，
        # timeout 不能取消 thread；最多放弃等待、让 thread 自己完成——这是 B3
        # bug，已记录但暂不修，因为 guest 账户每次换 mac 后旧 thread 自然死）。
        base_q = await asyncio.wait_for(
            ths_provider.get_market_data_block(codes, "基础数据"), timeout=15.0
        )
        ext_q = await asyncio.wait_for(
            ths_provider.get_market_data_block(codes, "扩展"), timeout=15.0
        )
        # ths_provider 返回的 _error 字段提示本次调用 soft-failed
        if base_q.get("_error"):
            logger.warning(f"[SectorScan] snapshot 基础数据 soft-failed: {base_q['_error']}")
        if ext_q.get("_error"):
            logger.warning(f"[SectorScan] snapshot 扩展 soft-failed: {ext_q['_error']}")
    except Exception as e:
        # 板块快照失败必须静默——thsdk guest 账户不稳定是常态，不能让本地
        # 数据源挂了把整个扫描任务搞挂。返回空串让 prompt 退回旧路径。
        logger.warning(f"[SectorScan] Local sector snapshot failed: {e}")
        return ""

    base_by_code = {r.get("代码"): r for r in (base_q.get("data") or []) if r.get("代码")}
    ext_by_code = {r.get("代码"): r for r in (ext_q.get("data") or []) if r.get("代码")}

    # NaN/inf 过滤：thsdk 给停牌/异常板块可能返回 nan/inf。Python isinstance 不挡 nan
    # （float('nan') 仍是 float），但排序 + f"{v:.2f}%" 会抛 ValueError/TypeError。
    def _safe_float(v):
        if not isinstance(v, (int, float)):
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if math.isnan(f) or math.isinf(f):
            return None
        return f

    merged = []
    for code in codes:
        b = base_by_code.get(code, {})
        e = ext_by_code.get(code, {})
        merged.append({
            "代码": code,
            "名称": b.get("名称") or e.get("名称") or "",
            "涨幅": _safe_float(e.get("涨幅")),
            "5日涨幅": _safe_float(e.get("5日涨幅")),
            "10日涨幅": _safe_float(e.get("10日涨幅")),
            "20日涨幅": _safe_float(e.get("20日涨幅")),
            "主力净流入": _safe_float(e.get("主力净流入")),
            "量比": _safe_float(e.get("量比")),
            "总金额": _safe_float(b.get("总金额")),
            "领涨股": b.get("领涨股"),
            "涨停家数": b.get("涨停家数"),
            "跌停家数": b.get("跌停家数"),
            "上涨家数": b.get("上涨家数"),
            "下跌家数": b.get("下跌家数"),
        })

    # 仅保留有涨幅数字的板块
    valid = [r for r in merged if r.get("涨幅") is not None]
    if not valid:
        # 区分"快照失败" vs "快照空"：前者 logger.warning(已上抛)，这里
        # 是"thsdk 在线但没数据"，必须 logger.error 让人看见——否则模型
        # 退回老路径又会写全 UNKNOWN，但日志看不到根因。
        logger.error(
            "[SectorScan] thsdk returned no usable sector data "
            "(基础 + 扩展 两批都无有效涨幅). snapshot 视作不可用，prompt 退回 web_search 路径"
        )
        return ""

    # 按今日涨幅降序
    valid.sort(key=lambda r: r.get("涨幅") or 0.0, reverse=True)
    top25 = valid[:25]
    bottom10 = valid[-10:]

    def _fmt_money(v):
        if not isinstance(v, (int, float)):
            return "N/A"
        # 主力净流入用亿；总金额也用亿。thsdk 给的是「元」
        return f"{v / 1e8:.2f}亿"

    def _fmt_pct(v):
        if not isinstance(v, (int, float)):
            return "N/A"
        return f"{v:.2f}%"

    def _row(r):
        return (
            f"| {r['名称']} | {_fmt_pct(r['涨幅'])} | "
            f"{_fmt_pct(r['5日涨幅'])} | {_fmt_pct(r['10日涨幅'])} | "
            f"{_fmt_money(r['主力净流入'])} | "
            f"{_fmt_money(r['总金额'])} | {r['领涨股'] or 'N/A'} |"
        )

    lines = [
        f"## 申万行业板块实时快照（{target_date}，共 {len(valid)} 个板块）",
        "",
        "### TOP 25（涨幅由高到低）",
        "",
        "| 板块 | 今日涨幅 | 5日涨幅 | 10日涨幅 | 主力净流入 | 总金额 | 领涨股 |",
        "|------|---------|--------|---------|-----------|-------|-------|",
    ]
    lines.extend(_row(r) for r in top25)
    lines.append("")
    lines.append("### BOTTOM 10（今日跌幅最大）")
    lines.append("")
    lines.append("| 板块 | 今日涨幅 | 5日涨幅 | 10日涨幅 | 主力净流入 | 总金额 | 领涨股 |")
    lines.append("|------|---------|--------|---------|-----------|-------|-------|")
    lines.extend(_row(r) for r in bottom10)
    lines.append("")

    # 把板块名清单也单独附上，方便模型直接抄表（不要让模型再去 web_search
    # 重新发现板块名）。这是修复 sectors 解析空白的核心：直接喂名字。
    lines.append("### 完整板块名清单（90 个，按涨幅降序）")
    lines.append("")
    lines.append(", ".join(r["名称"] for r in valid if r["名称"]))
    lines.append("")

    return "\n".join(lines)

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


def _fire_and_forget_redis_write(*args, **kwargs):
    """Wrap _update_scan_job_redis in create_task with exception logging.

    背景：文件头部的 race fix 注释指出 4 concurrent fire-and-forget
    写会丢字段。后续为了进展现成 race 已经用 per-job Lock 串行化；
    但 asyncio.create_task 没 done_callback 时，Redis 暂时不可用导致
    task 抛异常会被 GC，**只在 Python 退出时**打印"Task exception was never
    retrieved"，运行时看不到。

    这里所有 fire-and-forget 写都走这个 wrapper，保证运行时可见。
    仍在 race 范围内——锁已经处理了字段丢问题。
    """
    task = asyncio.create_task(_update_scan_job_redis(*args, **kwargs))

    def _log_if_failed(t):
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error(
                f"[SectorScan] fire-and-forget Redis write failed: {exc}",
                exc_info=exc,
            )
    task.add_done_callback(_log_if_failed)
    return task


async def _run_scan(job_id: str, model: str, target_date: str, gemini_api_key: str = None, deepseek_api_key: str = None, openrouter_api_key: str = None):
    """Execute the market sector scan via LLM + tools."""
    from ..services.llm_gateway import llm_gateway
    from ..services.agent_orchestrator import agent_orchestrator
    from ..prompting.runtime import prompt_runtime

    try:
        _fire_and_forget_redis_write(job_id, progress="正在加载扫描提示...")

        prompt_data = prompt_runtime.get_prompt("market_sector_scanner")
        template = prompt_data["template"]

        # ---- 本地板块快照（核心修复）----
        # 拿一次 thsdk 申万全行业行情（~1秒，零外网依赖），作为 [GROUND TRUTH]
        # 注入 prompt，强制模型基于真实数字撰写。
        # 老路径里 system directive 只丢一句 "MUST use web_search"，模型拿
        # 不到任何数据，于是老实输出全 UNKNOWN；前端 sectors 字段正则错把
        # 章节标题（"数据源验证"/"替代数据源"/"历史参考"/"风险提示"）当成
        # 板块名——这就是用户看到的"完全没数据"的根因。
        # 快照获取失败时返回空串，prompt 退回老路径，不让 thsdk guest 账户
        # 不稳定把整个扫描任务搞挂。
        # Await（不用 asyncio.create_task）：头部 race fix 注释明确警告
        # 4 concurrent fire-and-forget write 会丢字段；进度消息即便不是
        # 关键状态也应 await，与同函数其他写入路径一致。
        await _update_scan_job_redis(job_id, progress="正在加载本地板块快照...")
        snapshot_md = await _build_market_scan_snapshot(target_date)

        snapshot_block = ""
        if snapshot_md:
            snapshot_block = (
                "\n\n--- [MANDATORY] GROUND TRUTH: SW INDUSTRY SNAPSHOT ---\n"
                "以下为今日 A 股申万一级行业全部板块的实时行情快照（来自本地同花顺数据源，"
                "时间为扫描时刻；非样本、非估算，可直接引用）。\n"
                "**纪律**：\n"
                "1) 板块热度排名必须直接基于下表的「今日涨幅」「主力净流入」「总金额」三列；\n"
                "2) 不得编造未在下表中出现的板块名；\n"
                "3) 表格中已含领涨股代码，可据此撰写热点解读；\n"
                "4) 严禁输出 UNKNOWN；任何字段必须用上表已有数据填空。\n\n"
                f"{snapshot_md}\n"
                "--- END GROUND TRUTH ---\n"
            )
        else:
            logger.warning(
                f"[SectorScan] Job {job_id}: local snapshot unavailable, "
                "relying on LLM web_search tools (likely to fail in current network env)"
            )

        # Bug 半回潮修复 (2026-09-05 review B4): 原代码在 snapshot_md == ''
        # 时，prompt 仍然保留原始 SYSTEM DIRECTIVE —— "MUST use web_search"，
        # 但实际网络环境里 web_search 全 503，模型又会写全 UNKNOWN，_extract_sectors
        # 返回 [] —— 用户看到的"完全没数据" bug 重新出现。
        # 修法：snapshot 为空时改写 SYSTEM DIRECTIVE 告诉模型"放弃 web_search、
        # 老实承认数据源不可用"，而不是强行让模型去找。
        system_directive = (
            "You are an institutional-grade AI analyst. NEVER fabricate data.\n"
            "本扫描任务尝试加载本地板块快照(snapshot)失败；当前生产环境所有 "
            "外部 web_search/news_search 工具均不可用（DDG GFW 阻断、媒体源 503）。\n"
            "**纪律**：\n"
            "1) 不要尝试 web_search —— 已知会失败；\n"
            "2) 不要编造未经验证的数据；\n"
            "3) 在报告中明确标注「本地数据源 + 网络工具均不可用」，"
            "所有数据字段标记为 UNKNOWN；\n"
            "4) 不要写任何'建议/风险提示/数据源验证'章节——这些是占位文本，"
            "用户已经看到过很多次，重复只会让用户更困惑。"
        ) if not snapshot_md else (
            "You are an institutional-grade AI analyst. You MUST use web_search to get real-time data. NEVER fabricate data."
        )

        context = f"""
--- SYSTEM DIRECTIVE ---
{system_directive}
{snapshot_block}
--- SYSTEM INSTRUCTIONS ---
{template}

--- CONTEXT ---
Current Date: {target_date}
Market: A-Share (中国A股)
"""

        _fire_and_forget_redis_write(job_id, progress="正在搜索和分析市场数据...")

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
            _fire_and_forget_redis_write(job_id, progress=progress, content_count=count)

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
    r"""Extract sector names from the recommendation table or fallback lists.

    Bug history (2026-09): 老版 fallback 用 `^\s*\d+\.\s*(?:\\*\\*)?([^:\\*\\n]+)(?:\\*\\*)?[:：]'
    匹配 markdown 里任何"序号+标题+冒号"的行，碰上 LLM 输出全 UNKNOWN 的章节标题
    （"数据源验证"/"替代数据源"/"历史参考"/"风险提示"）也会被识别为"板块"。前端
    SectorScanner 把这些章节标题当板块渲染，造成用户看到的"完全没数据"假象。

    修复：
      1) 主表解析只接受非 UNKNOWN 行（UNKNOWN 行不是板块，是模型拒绝回答）；
      2) numbered-list 回退接受真实板块名（≥3 字、含中文、不在停用词表）；
      3) 排除常见章节标题动词起首（建议/参考/验证/说明/总结 等）。
    """
    if not scan_result:
        return []

    # 停用词：numbered-list fallback 阶段才用这些过滤常见章节标题/动词起首
    # 的中文短语。**不要在主表解析时用** —— A 股板块名里"数据要素""数据中心"
    # "数据安全""历史"开头的真板块会被误伤；这些场景只在 fallback
    # numbered list 解析时（模型输出纯文本时）才需要防误抓。
    _SECTION_PREFIXES = (
        "建议", "参考", "验证", "说明", "总结", "提示", "注意",
        "风险", "机会", "策略", "结论", "操作", "步骤", "方法",
        "工具", "信号", "跟踪", "后续", "评估", "分析",
        "解读", "展望", "回顾", "思考", "提醒", "免责",
        "替代", "补充", "附录",
    )
    # _EN_SECTION_TITLES / _en_section_titles_lower 定义在 sector.py 模块层级，
    # 这里直接引用。case-insensitive + 复数变体覆盖更全；== 精确匹配（不是
    # startswith）以避免误伤合法板块名（如 "Risk Parity"）。
    # 已知绝对不是板块的固定章节标题（来自 LLM 失败报告里的 "数据源验证"等）
    # 这是真板块名唯一安全的"绝对黑名单"，主表 + fallback 都用它。
    _KNOWN_FAKE_SECTORS = {
        "数据源验证", "替代数据源", "历史参考", "风险提示",
        "板块热度排名", "资金流向追踪", "轮动信号识别", "板块比较与配置建议",
        "数据获取状态声明", "后续建议",
    }

    sectors = []
    seen = set()

    def _is_valid_sector_name(name: str, strict: bool = False, allow_english: bool = False) -> bool:
        """Check if a string looks like a real A-share sector name.

        strict=False: 主表解析用，仅排除明确非板块（黑名单 + UNKNOWN + 长度）。
        strict=True: numbered-list fallback 阶段用，额外排除章节前缀。
        allow_english=False: 默认要求至少一个中文字符（中文 A 股板块名）。
        allow_english=True: 主表解析中英表头 (Gemini 英文 fallback) 时允许纯英文名。
                           必须额外满足英文板块特征（TitleCase + 词数≤4 + ≥3 字符 +
                           不在 _EN_SECTION_TITLES 完整短语黑名单中），
                           否则会放过 "random words here" / "abc" / "Risk Warning" 等垃圾。
        """
        name = name.strip()
        if not name:
            return False
        if name in _KNOWN_FAKE_SECTORS:
            return False
        # UNKNOWN 任何大小写都不收
        if name.upper().startswith("UNKNOWN") or "UNKNOWN" in name.upper():
            return False
        if len(name) < 2 or len(name) > 30:
            return False
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in name)
        # 必须至少含一个中文字符（A 股板块名通常是中文）；allow_english 路径除外
        if not allow_english and not has_cjk:
            return False
        # allow_english 路径：纯英文输入必须看起来像"板块名"而不是"垃圾短语"
        if allow_english and not has_cjk:
            # 1) 至少一个字母（拒纯数字/纯标点）
            if not any(ch.isalpha() for ch in name):
                return False
            # 2) ≥3 字符（拒 "AI"/"IT"/"VR" 等过短 token —— 这些场景 allow_english 路径不该误收，
            #    真有这场景也应该走中文路径）
            if len(name) < 3:
                return False
            # 3) 必须至少一个大写字母（英文板块名通常 TitleCase "Semiconductors" 或 CamelCase；
            #    纯小写短语 "random words here" 是说明文本不是板块名）
            if not any(ch.isupper() for ch in name):
                return False
            # 4) 词数 ≤ 4（真板块名通常是 1-3 词如 "New Energy Vehicles"；
            #    长说明文本会被过滤）
            if len(name.split()) > 4:
                return False
            # 5) 英文章节完整短语黑名单（case-insensitive + 复数变体）：Gemini fallback 写出
            #    "Risk Warning" / "Executive Summary" / "Risk Warnings"（复数）等章节标题
            #    时不能被当板块。完整短语 == 匹配（不是 startswith）以避免误伤合法板块名
            #    （如 "Risk Parity"）；lower() 一次性解决大小写敏感性。
            if name.lower() in _en_section_titles_lower:
                return False
        # 严格模式（fallback）才拒章节动词开头（中文路径）
        if strict and any(name.startswith(p) for p in _SECTION_PREFIXES):
            return False
        return True

    def _clean_markdown_cell(raw: str) -> str:
        """Strip markdown emphasis / link / code from a table cell.

        实测 LLM 在 markdown 表格里偶尔会写：
          | **半导体** | ...
          | *半导体* | ...
          | __半导体__ | ...
          | `半导体` | ...
          | [半导体](url) | ...
        这些都是同一个名字的不同 markdown 渲染。原版 .replace("**","") 只挡
        bold，italic/code/link 全部漏过，导致 _is_valid_sector_name 看到
        "__半导体__" 这种带下划线的非中文开头名字被拒。
        """
        if not raw:
            return ""
        s = raw.strip()
        # 链接 [text](url) → text
        m = re.match(r"^\[([^\]]+)\]\([^)]+\)$", s)
        if m:
            s = m.group(1)
        # 代码 `text` → text
        if s.startswith("`") and s.endswith("`"):
            s = s[1:-1]
        # 强调符号：** __ * _
        s = re.sub(r"^[\*_~]+|[\*_~]+$", "", s).strip()
        # 残留的内联 `code` 也清掉
        s = re.sub(r"`([^`]+)`", r"\1", s)
        return s.strip()

    def _table_first_data_cell(line: str) -> str | None:
        """Return the first cell of a markdown table row, or None if not a data row.

        接受三种格式：
          | 板块 | ...             (LLM 跳过 rank 列直接写板块名)
          | 1. | 板块 | ...         (rank 在独立列)
          | ⭐1. 板块 | ...         (rank 与板块名在同一列)
        """
        if not line.startswith("|"):
            return None
        # 跳过表头分隔行 |---|---|
        if re.match(r"^\|[\s\-:|]+\|?\s*$", line):
            return None
        # 至少 3 个 | 才算数据行（首尾 + 1 数据 + 1+ 数据列）
        if line.count("|") < 3:
            return None
        # 取首列内容
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells:
            return None
        first = cells[0]
        # 去掉首列里的 rank 前缀（数字 / ⭐数字 / 数字. / 中文一二三等）
        first = re.sub(
            r"^(?:⭐\s*)?(?:\d+[\.、]?|[一二三四五六七八九十]+[\.、]?)\s*",
            "",
            first,
        ).strip()
        return first if first else None

    def _table_sector_cells(row: str, sector_col_index: int | None = None) -> list:
        """Given a data row of a sector table, return likely sector name cell(s).

        Three layouts:
          | 板块 | 涨跌幅 | ...           → ['板块']  (sector_col_index=0)
          | 1. | 板块 | 涨跌幅 | ...      → ['板块']  (sector_col_index=1)
          | ⭐1. 板块 | 涨跌幅 | ...       → ['板块']  (rank + name merged)

        sector_col_index: 显式指定的板块列（0-based）；None 时 fallback 到
        "rank 独立列 → 用 cells[1]；否则 cells[0]"。

        Review B8 修复: 当 header 显示板块列不在第一列（如
        | 排名 | 涨跌幅 | 板块 | ...）时，cells[0]="1." / cells[2]="半导体"
        → 必须读 cells[sector_col_index]，不能默认读 cells[1]。
        """
        line = row.strip()
        if not line.startswith("|"):
            return []
        if line.count("|") < 3:
            return []
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            return []
        rank_prefix = r"^(?:⭐\s*)?(?:\d+[\.、]?|[一二三四五六七八九十]+[\.、]?)\s*"
        rank_only = re.compile(rank_prefix + r"$")

        def _strip_rank(text: str) -> str:
            """剥掉 '⭐1.' / '2.' / '三、' 这种 rank 前缀，返回剩余"""
            return _clean_markdown_cell(re.sub(rank_prefix, "", text).strip())

        first = cells[0]
        first_is_merged = bool(re.sub(rank_prefix, "", first).strip())

        # 优先级：
        #   (A) merged-rank: cells[0] 像 "⭐1. 综合"，剥前缀能拿到真名 → 用它
        #   (B) 显式 sector_col: 表头告诉了我们 sector 列在哪；优先用。
        #       但如果 cells[col] 实际是纯 rank（模型合并列），fallback 到 (A)。
        if first_is_merged:
            name = _strip_rank(first)
            return [name] if name else []
        if sector_col_index is not None and 0 <= sector_col_index < len(cells):
            raw = cells[sector_col_index]
            if rank_only.match(raw) and sector_col_index + 1 < len(cells):
                # cells[col] 是纯 rank（极少见），fallback 到 col+1
                raw = cells[sector_col_index + 1]
            name = _clean_markdown_cell(raw)
            return [name] if name else []
        # 形态 1+2: 第一个 cell 是纯 rank（数字 / ⭐ + 数字），板块名在 cells[1]
        if rank_only.match(first):
            return [_clean_markdown_cell(cells[1])]
        return []

    # Review B7 + B8 修复: 中英表头 + 板块列不在首列。
    # 旧版只认 "板块"/"排序" 列名，遇到英文表头 (Sector/Rank/...) 直接丢；
    # 而且板块列在第三列时 cells[0]="1." → 错误返回 cells[1]。
    # 修法：从 header 推断 sector 列的索引，并接受中英文别名。
    _SECTOR_TABLE_COL_HINTS = (
        # 行情特征列：任一列出现即认作"板块行情表"
        "涨跌幅", "涨幅", "成交额", "资金净流入", "主力净流入", "热度评级",
        "领涨股", "总金额", "换手率",
        "Change", "Volume", "Flow", "Lead",
    )
    # 第一列名（中英文）—— 表示该列是 sector 名
    # 不要把 "Rank" 放进这里：上次会话复用时把 Rank 当成 sector 列名了，
    # 导致 | Rank | Sector | ... | 被错认成 sector 在第 0 列，读到了 "1" 而不是 "Semiconductors"。
    # 同样，"排序" 字面是 sort/order 含义，应归到 RANK 列；放进 FIRST 会让
    # | 排序 | 板块 | ... | 误判成 sector 在第 0 列（读到 "1." 而不是 "综合"）。
    _SECTOR_FIRST_COL_NAMES_CN = ("板块", "名称", "行业")
    _SECTOR_FIRST_COL_NAMES_EN = ("Sector", "Industry", "Name")
    # "rank 列" 名（中英文）—— 紧挨着 rank 列后面是 sector 名
    _SECTOR_RANK_COL_NAMES_CN = ("排名", "排序")
    _SECTOR_RANK_COL_NAMES_EN = ("Rank", "No.")

    lines = scan_result.split("\n")
    sector_col_index: int | None = None  # 当前光行所属表的 sector 列 0-based

    def _is_separator(line: str) -> bool:
        return bool(re.match(r"^\|[\s\-:|]+\|?\s*$", line.strip()))

    def _header_cells(header_line: str) -> list:
        return [c.strip() for c in header_line.strip().strip("|").split("|")]

    def _detect_sector_col(header_cells: list) -> int | None:
        """从 header cells 推断 sector 列 0-based 索引。

        优先级：
          1) 列名是"板块/名称/排序/行业"中英文 → 该列
          2) 列名是"排名/Rank/No."中英文 → rank 列；sector 是 rank+1
          3) 否则 None（不是板块表）
        """
        cn_names = _SECTOR_FIRST_COL_NAMES_CN + _SECTOR_RANK_COL_NAMES_CN
        en_names_lower = tuple(n.lower() for n in (_SECTOR_FIRST_COL_NAMES_EN + _SECTOR_RANK_COL_NAMES_EN))
        for idx, h in enumerate(header_cells):
            if h in _SECTOR_FIRST_COL_NAMES_CN:
                return idx
            if h.lower() in en_names_lower and h in _SECTOR_FIRST_COL_NAMES_EN:
                return idx
        for idx, h in enumerate(header_cells):
            if h in _SECTOR_RANK_COL_NAMES_CN:
                return idx + 1 if idx + 1 < len(header_cells) else None
            if h.lower() in en_names_lower and h in _SECTOR_RANK_COL_NAMES_EN:
                return idx + 1 if idx + 1 < len(header_cells) else None
        return None

    def _is_sector_table(header_cells: list) -> bool:
        """header 任一列属于板块行情特征列 → 是板块表

        上次会话 zip 配对写法（zip 后只在固定位置比 Change/Volume/Flow/Lead）
        在 header 是 | Rank | Sector | Change | Volume | 时把 Sector 错配到
        Volume 位置，命中 0 个 → 整张英文表被误判为"非板块表"。修正为位置无关：
        cn_hints/en_hints 任一命中即可。
        """
        cn_hints = _SECTOR_TABLE_COL_HINTS[:9]
        en_hints = _SECTOR_TABLE_COL_HINTS[9:]
        for h in header_cells:
                if h in cn_hints:
                        return True
                if h in en_hints or h.lower() in tuple(e.lower() for e in en_hints):
                        return True
        return False

    # 是否启用英文名支持：根据 header 是否包含英文行情列名判定
    _table_is_english = False

    def _has_english_header(header_cells: list) -> bool:
        """header 任一列是英文行情特征（Change/Volume/Flow/Lead） → 英文表"""
        en_hints = _SECTOR_TABLE_COL_HINTS[9:]
        en_lower = tuple(e.lower() for e in en_hints)
        return any(h in en_hints or h.lower() in en_lower for h in header_cells)

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 表头行：当前行是 | ... | 且下一行是分隔 |---|---|
        if line.startswith("|") and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            header_cells = _header_cells(line)
            sector_col_index = None
            _table_is_english = False
            if _is_sector_table(header_cells):
                sector_col_index = _detect_sector_col(header_cells)
                _table_is_english = _has_english_header(header_cells)
            i += 2  # 跳过表头 + 分隔行
            continue

        sector_cells = _table_sector_cells(line, sector_col_index) if line.startswith("|") else []
        if sector_cells and sector_col_index is not None:
            for raw_name in sector_cells:
                if not raw_name:
                    continue
                # 跳过 header 字面值（避免 "板块" " 名称" 本身被当 sector）
                if raw_name in ("板块", "排序", "名称", "行业", "Sector", "Industry", "Name", "Rank"):
                    continue
                # 英文表头下允许英文名（Gemini 英文 fallback）
                if _is_valid_sector_name(raw_name, allow_english=_table_is_english) and raw_name not in seen:
                    seen.add(raw_name)
                    sectors.append(raw_name)
        i += 1

    # Fallback: numbered list — only if primary table gave < 3 sectors AND no UNKNOWN rows
    # dominated the report. 检查主表解析是否被空响应毁掉了（空表 → 不进 fallback）。
    if len(sectors) < 3:
        # 数一下报告里 UNKNOWN 出现次数。如果 UNKNOWN 占比异常（≥5 行），
        # 说明 LLM 没拿到数据，整篇都是占位文本，回退正则会抓假板块，宁可不抓。
        unknown_count = scan_result.upper().count("UNKNOWN")
        if unknown_count >= 5:
            return sectors  # 模型没数据时不要瞎补

        list_matches = re.findall(
            r"^\s*\d+\.\s*(?:\*\*)?([^:\*\n]+)(?:\*\*)?[:：]",
            scan_result,
            re.MULTILINE,
        )
        for name in list_matches:
            name = name.strip().replace("**", "").strip()
            if _is_valid_sector_name(name, strict=True) and name not in seen:
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
