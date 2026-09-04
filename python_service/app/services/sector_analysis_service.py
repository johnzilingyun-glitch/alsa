"""
Sector Analysis Service — POC
Orchestrates sector-level multi-expert analysis flow.
"""
import json
import asyncio
import os
import re
import uuid
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from app.db.redis_client import RedisManager
from app.logging import get_logger
from app.observability.failure_capture import capture_failure_incident

logger = get_logger(__name__)



class SectorAnalysisService:
    """Manages sector-level analysis jobs: snapshot → discussion → report."""

    def __init__(self, job_repo):
        self.job_repo = job_repo
        self._running_tasks: Dict[str, asyncio.Task] = {}
        # Strong refs to fire-and-forget progress tasks so the GC can never
        # reap a pending update mid-flight (asyncio only keeps strong refs to
        # scheduled tasks).
        self._progress_tasks: set = set()
        # Store the main event loop so fire-and-forget progress updates
        # work correctly when called from thread contexts (on_chunk callbacks)
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = None

    async def start_sector_job(self, sector_name: str, model: Optional[str] = None, config: Optional[Dict[str, Any]] = None, target_date: Optional[str] = None, level: str = "sector", verification_mode: str = "quick") -> str:
        import os
        job_id = f"sector_{uuid.uuid4().hex[:8]}"
        # Create job in DB
        self.job_repo.create(job_id, sector_name, "sector", level=level, model=model, snapshot_id=target_date)

        if os.getenv("ALSA_DISABLE_BACKGROUND_JOBS") == "true" or os.getenv("PYTEST_CURRENT_TEST"):
            return job_id

        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            from app.worker import run_sector_analysis_task
            print(f"[SectorAnalysis] Dispatching sector job {job_id} to Celery worker")
            run_sector_analysis_task.delay(
                job_id,
                sector_name,
                model=model,
                config=config,
                target_date=target_date,
                level=level,
                pipeline_version="production"
            )
        else:
            print(f"[SectorAnalysis] Running sector job {job_id} in local asyncio pool (Graceful Degradation)")
            task = asyncio.create_task(self._run_sector_job(job_id, sector_name, model=model, config=config, target_date=target_date, level=level))
            self._running_tasks[job_id] = task
            task.add_done_callback(lambda t: self._running_tasks.pop(job_id, None))
        return job_id

    def update_progress(self, job_id: str, stage: str, pct: int, **kwargs):
        """Synchronous wrapper — fire and forget redis update.

        Thread-safe: schedules the coroutine on whichever loop is actually
        usable.

        Bug fix (progress stuck at {} / "coroutine was never awaited"): the
        old implementation only scheduled the coroutine when the running loop
        was *identical* to the loop captured in __init__. In the Celery path
        (app/worker.py:run_sector_analysis_task) the service is constructed in
        a sync task context — no running loop, so _main_loop is None — and the
        job then runs on a fresh asyncio.run() loop. Both branches were
        skipped, the coroutine object was dropped ("coroutine was never
        awaited" warning), and job_progress:{job_id} was never written, so
        get_progress() always returned {}.
        """
        coro = self.update_progress_async(job_id, stage, pct, **kwargs)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Async context: schedule on the CURRENT loop. It is by definition
            # the loop driving this job, regardless of which loop the service
            # was constructed on, so no identity check against _main_loop.
            task = asyncio.create_task(coro)
            self._progress_tasks.add(task)
            task.add_done_callback(self._progress_tasks.discard)
        elif self._main_loop is not None and self._main_loop.is_running():
            # Worker-thread context (e.g. on_chunk from a thread pool): hand
            # off to the main loop. is_running() guards against scheduling on
            # a loop that asyncio.run() already closed.
            asyncio.run_coroutine_threadsafe(coro, self._main_loop)
        else:
            # No usable loop anywhere: close the coroutine explicitly so
            # Python does not emit "coroutine was never awaited", and leave
            # a breadcrumb in the logs for diagnosis.
            coro.close()
            logger.warning(
                "[SectorAnalysis] update_progress dropped for job %s (stage=%s): no running event loop",
                job_id, stage,
            )

    async def update_progress_async(self, job_id: str, stage: str, pct: int, **kwargs):
        redis = await RedisManager.get_client()
        payload = {"stage": stage, "progress": pct, **kwargs}
        await redis.set(f"job_progress:{job_id}", json.dumps(payload), ex=86400) # 24h expiry

    async def get_progress(self, job_id: str) -> Dict[str, Any]:
        redis = await RedisManager.get_client()
        data = await redis.get(f"job_progress:{job_id}")
        if data:
            return json.loads(data)
        return {}

    async def _run_sector_job(self, job_id: str, sector_name: str, model: Optional[str] = None, config: Optional[Dict[str, Any]] = None, target_date: Optional[str] = None, level: str = "sector", verification_mode: str = "quick"):
        from .discussion_service import discussion_service
        from ..db.models import AnalysisRun, AnalysisJob
        from .llm_gateway import current_token_usage

        self.job_repo.update_status(job_id, "running")
        self.update_progress(job_id, "sector_snapshot", 10)

        job_usage = {"promptTokens": 0, "candidatesTokens": 0, "totalTokens": 0}
        token_ctx = current_token_usage.set(job_usage)

        try:
            # 1. Build sector snapshot (lightweight — no per-stock data fetching)
            snapshot = await self._build_sector_snapshot(sector_name)

            # 1.5 Pre-enrich snapshot with sector constituent stocks + real-time prices
            try:
                sector_stocks = await self._fetch_sector_stocks(sector_name)
                if sector_stocks:
                    snapshot["sector_stocks"] = sector_stocks
                    print(f"[SectorAnalysis] Pre-enriched snapshot with {len(sector_stocks)} sector stocks")
            except Exception as e:
                print(f"[SectorAnalysis] Sector stock pre-enrichment failed (non-fatal): {e}")

            self.update_progress(job_id, "discussion", 30, message="正在搜索和整理板块市场数据...")

            # 2. Run sector expert discussion
            job = self.job_repo.get_by_id(job_id)
            requested_model = model
            if not requested_model and job:
                requested_model = job.requested_model

            def report_progress(round_num, total, msg, count=None, error_type=None, **kwargs):
                # round_num=0 means pre-search phase, show 30-35%
                if round_num == 0:
                    self.update_progress(job_id, "discussion", 32,
                                         round=0, total_rounds=total, message=msg,
                                         count=count, error_type=error_type, **kwargs)
                else:
                    self.update_progress(job_id, "discussion", 35 + int((round_num / total) * 50),
                                         round=round_num, total_rounds=total, message=msg,
                                         count=count, error_type=error_type, **kwargs)

            discussion_messages = await discussion_service.run_discussion(
                sector_name,           # symbol → sector_name
                sector_name,           # name → sector_name
                snapshot,
                level=level,           # triggers SECTOR_TOPOLOGY or SERENITY_ALPHA_TOPOLOGY
                model=requested_model,
                on_progress=report_progress,
                job_id=job_id,
                config=config,
                market="sector",       # sector flow — avoid misleading "{keyword}.us" default
                verification_mode=verification_mode
            )

            # Run Critic Agent on the discussion messages
            critique_res = None
            try:
                from app.services.critic_agent import critic_agent
                critique_res = await critic_agent.critique(
                    analyses=discussion_messages,
                    symbol=sector_name,
                    name=f"{sector_name}板块",
                    context=snapshot,
                    gemini_api_key=config.get("geminiApiKey") if config else None,
                    deepseek_api_key=config.get("deepseekApiKey") if config else None,
                    model=requested_model
                )
            except Exception as e:
                print(f"Critic Agent critique failed for sector {sector_name}: {e}")

            self.update_progress(job_id, "finalizing", 90)

            # 3. Build result payload
            result = {
                "symbol": sector_name,
                "market": "sector",
                "job_type": "sector",
                "stockInfo": {
                    "symbol": sector_name,
                    "market": "sector",
                    "name": f"{sector_name}板块分析",
                    "lastUpdated": datetime.now().strftime("%Y/%m/%d %H:%M:%S") + " CST",
                },
                "snapshot": snapshot,
                "discussion": discussion_messages,
                "critique": critique_res,
                "summary": self._extract_summary(discussion_messages),
                "usageMetadata": job_usage,
            }

            # 3.5 Post-process: enrich result with verified real-time prices
            # NOTE: runs with a global 120s timeout — yfinance can hang on Chinese stocks
            try:
                result = await asyncio.wait_for(
                    self._enrich_result_with_prices(result),
                    timeout=120.0,
                )
            except Exception as e:
                print(f"[SectorAnalysis] Post-processing price enrichment failed (non-fatal): {e}")

            # Removed self._results[job_id] = result
            
            # 4. Save to DB
            with self.job_repo.session_factory() as session:
                analysis_run = AnalysisRun(
                    job_id=job_id,
                    symbol=sector_name,
                    market="sector",
                    summary_verdict="watch",
                    score=70.0,
                    risk_level="medium"
                )
                session.add(analysis_run)
                session.commit()
                session.refresh(analysis_run)

                db_job = session.get(AnalysisJob, job_id)
                if db_job:
                    db_job.status = "completed"
                    db_job.analysis_id = analysis_run.analysis_id
                    if target_date:
                        db_job.snapshot_id = target_date

                    def json_serial(obj):
                        if isinstance(obj, (datetime, date)):
                            return obj.isoformat()
                        raise TypeError(f"Type {type(obj)} not serializable")

                    db_job.result_payload = result
                    db_job.finished_at = datetime.now()
                    session.add(db_job)
                    session.commit()

        except asyncio.CancelledError:
            self.job_repo.update_status(job_id, "cancelled")
            raise
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            incident = capture_failure_incident(
                component="sector_analysis_service",
                error=e,
                job_id=job_id,
                symbol=sector_name,
                market="sector",
                stage="sector_job",
                context={
                    "target_date": target_date,
                    "level": level,
                    "verification_mode": verification_mode,
                    "model": model,
                    "config": config,
                    "snapshot": locals().get("snapshot", {}),
                    "discussion": locals().get("discussion_messages", []),
                },
                traceback_text=tb,
            )
            incident_id = incident.get("incident_id")
            logger.exception(f"Sector analysis job failed: {e} (incident_id={incident_id})")
            self.job_repo.update_status(job_id, "failed", error_message=f"{e} [incident_id={incident_id}]")
        finally:
            current_token_usage.reset(token_ctx)

    async def _build_sector_snapshot(self, sector_name: str) -> Dict[str, Any]:
        """Build a lightweight sector snapshot with macro + commodity data."""
        from .macro_service import macro_service

        snapshot = {
            "name": sector_name,
            "type": "sector",
            "timestamp": datetime.now().isoformat(),
        }

        # Fetch macro data
        try:
            fx_data = await macro_service.get_latest_fx()
            snapshot["fx"] = fx_data
        except Exception as e:
            print(f"FX fetch failed: {e}")

        # Fetch relevant commodity data based on sector name
        commodity_keywords = {
            "铝": ["Aluminum", "Alumina"],
            "锂": ["Lithium Carbonate"],
            "铜": ["Copper"],
            "钢": ["Crude Oil"],
            "能源": ["Crude Oil", "Methanol"],
            "化工": ["Crude Oil", "Methanol", "Polypropylene", "LLDPE"],
            "光伏": ["Silicon"],
            "半导体": ["Silicon"],
        }

        for keyword, commodities in commodity_keywords.items():
            if keyword in sector_name:
                try:
                    commodity_data = await macro_service.get_commodity_prices(commodities)
                    snapshot["commodities"] = commodity_data
                except Exception as e:
                    print(f"Commodity fetch failed: {e}")
                break

        # Fetch macro indicators
        try:
            macro_indicators = await macro_service.get_macro_indicators()
            snapshot["macro_indicators"] = macro_indicators
        except Exception as e:
            print(f"Macro indicators failed: {e}")

        return snapshot

    def _extract_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Extract summary from the last expert's output."""
        for msg in reversed(messages):
            content = msg.get("content", "")
            if content and len(content) > 100:
                # Take first 500 chars as summary
                return content[:500]
        return ""

    def get_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        # Fetch directly from DB instead of memory dictionary to support horizontal scaling
        job = self.job_repo.get_by_id(job_id)
        if job and job.result_payload:
            if isinstance(job.result_payload, str):
                import json
                try:
                    return json.loads(job.result_payload)
                except Exception:
                    logger.exception("Failed to parse job result payload as JSON for job %s", job_id)
                    return {}
            return job.result_payload
        return None

    async def _fetch_sector_stocks(self, sector_name: str) -> List[Dict[str, Any]]:
        """Fetch constituent stocks for a sector with real-time prices and core financial metrics from API."""
        from .data_providers import data_router
        from .search_service import search_service

        # Curated presets for common sectors (A-share, HK, US, China Concept)
        sector_presets = {
            "PCB": ["002463", "300476", "002916", "688183", "002384", "603228", "600183", "300657"],
            "印制电路板": ["002463", "300476", "002916", "688183", "002384", "603228", "600183", "300657"],
            "半导体": ["603986", "688981", "600584", "002371", "300782", "688012", "603501", "NVDA"],
            "光伏": ["601012", "600438", "300274", "688599", "600732", "002459"],
            "铝": ["601600", "000807", "600219", "002532", "601702"],
            "锂": ["002466", "300014", "002460", "002756", "300438"],
            "铜": ["600362", "000630", "601168", "000878"],
            "人工智能": ["002230", "300418", "688041", "300308", "000977", "NVDA", "MSFT"],
            "港股": ["00700", "03690", "09988", "09618", "01810", "09888"],
            "港股科技": ["00700", "03690", "09988", "09618", "01810", "09888"],
            "美股": ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"],
            "美股科技": ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"],
            "中概股": ["BABA", "PDD", "BIDU", "JD", "NIO", "LI", "XPEV"],
            "中概": ["BABA", "PDD", "BIDU", "JD", "NIO", "LI", "XPEV"],
        }

        codes = []
        for key, preset_codes in sector_presets.items():
            if key.lower() in sector_name.lower():
                codes.extend(preset_codes)
                break

        if not codes:
            # Fallback: search web for sector concept stocks
            try:
                search_res = await search_service.search(f"{sector_name} 概念股 龙头 股票代码", max_results=5)
                all_text = " ".join([r.get("title", "") + " " + r.get("content", "") for r in search_res or []])
                
                # Extract A-share (6 digits), HK (5 digits/0xxxx), and US tickers (2-5 uppercase chars)
                a_codes = re.findall(r'\b([0368]\d{5})\b', all_text)
                hk_codes = re.findall(r'\b(0\d{4}|\d{4,5}\.HK)\b', all_text, flags=re.IGNORECASE)
                us_codes = re.findall(r'\b([A-Z]{2,5})\b', all_text)

                ignore_words = {"THE", "AND", "FOR", "NEW", "STOCK", "NYSE", "NASDAQ", "US", "HK", "PE", "PB", "ROE", "ETF", "USD", "CNY", "HKD"}
                us_codes = [c for c in us_codes if c not in ignore_words]

                found_codes = a_codes + hk_codes + us_codes
                for c in found_codes:
                    if c not in codes:
                        codes.append(c)
                    if len(codes) >= 8:
                        break
            except Exception as e:
                logger.warning(f"Failed to search constituent stocks for sector {sector_name}: {e}")

        if not codes:
            return []

        # Deduplicate & cap to 8 stocks
        codes = list(dict.fromkeys(codes))[:8]

        stocks_info = []
        async def _fetch_one(c: str):
            try:
                summary = await data_router.get_financial_summary(c)
                if summary and "error" not in summary:
                    stocks_info.append({
                        "code": c,
                        "name": summary.get("name") or c,
                        "price": summary.get("price", "N/A"),
                        "change_pct": summary.get("turnoverPct", "N/A"),
                        "pe": summary.get("pe", "N/A"),
                        "pb": summary.get("pb", "N/A"),
                        "market_cap_yi": summary.get("marketCap", "N/A"),
                        "turnover_pct": summary.get("turnoverPct", "N/A"),
                        "revenue": summary.get("revenue", "N/A"),
                        "net_profit": summary.get("netProfit", "N/A"),
                        "free_cashflow": summary.get("freeCashflow", "N/A"),
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch financial summary for stock {c} in sector {sector_name}: {e}")

        await asyncio.gather(*[_fetch_one(c) for c in codes], return_exceptions=True)
        return stocks_info
    async def _enrich_result_with_prices(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract stock codes from discussion, fetch real-time prices, add to result."""
        import yfinance as yf

        discussion = result.get("discussion", [])
        all_text = " ".join(msg.get("content", "") for msg in discussion)

        # Extract 4 to 6-digit stock codes (A-share and HK)
        codes = set(re.findall(r'\b(\d{4,6})\b', all_text))
        
        valid_codes = []
        for c in codes:
            if len(c) == 6:
                if c[0] in ('0', '3', '6'):
                    valid_codes.append(c)
            elif len(c) in (4, 5):
                valid_codes.append(c)

        if not valid_codes:
            return result

        print(f"[SectorAnalysis] Enriching {len(valid_codes)} stock codes with real-time prices...")

        realtime_prices = {}

        # Run yfinance fetches in a thread pool with per-code timeout to avoid
        # blocking the event loop on slow / hung Yahoo Finance connections.
        async def _fetch_one(code: str) -> None:
            try:
                if len(code) == 6:
                    yf_symbol = f"{code}.SS" if code.startswith("6") else f"{code}.SZ"
                else:
                    hk_code = str(int(code)).zfill(4)
                    yf_symbol = f"{hk_code}.HK"
                info = await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: yf.Ticker(yf_symbol).info
                    ),
                    timeout=15.0,
                )
                price = info.get("currentPrice") or info.get("regularMarketPrice")
                if price:
                    prev_close = info.get("regularMarketPreviousClose")
                    change_pct = ((price - prev_close) / prev_close * 100) if prev_close else None
                    realtime_prices[code] = {
                        "name": info.get("shortName") or info.get("longName") or code,
                        "price": float(price),
                        "change_pct": round(change_pct, 2) if change_pct else None,
                        "open": float(info.get("regularMarketOpen")) if info.get("regularMarketOpen") else None,
                        "high": float(info.get("regularMarketDayHigh")) if info.get("regularMarketDayHigh") else None,
                        "low": float(info.get("regularMarketDayLow")) if info.get("regularMarketDayLow") else None,
                        "prev_close": float(prev_close) if prev_close else None,
                        "volume_yi": None,
                        "pe": float(info.get("trailingPE")) if info.get("trailingPE") else None,
                        "pb": float(info.get("priceToBook")) if info.get("priceToBook") else None,
                        "market_cap_yi": round(float(info.get("marketCap")) / 1e8, 1) if info.get("marketCap") else None,
                        "exchange": "上交所" if code.startswith("6") else "深交所",
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
            except asyncio.TimeoutError:
                print(f"[SectorAnalysis] yfinance timeout for {code}")
            except Exception as e:
                print(f"[SectorAnalysis] yfinance fallback failed for {code}: {e}")

        await asyncio.gather(*[_fetch_one(c) for c in valid_codes], return_exceptions=True)

        if realtime_prices:
            result["realtime_prices"] = realtime_prices
            print(f"[SectorAnalysis] Enriched {len(realtime_prices)} stocks with real-time prices")

        return result
