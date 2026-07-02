import json
import os
import asyncio
import uuid
import logging

logger = logging.getLogger(__name__)
from datetime import date, datetime
from ..time_utils import utc_now
from typing import Optional, Dict, Any, List
from ..db.repositories.job_repo import JobRepository
from ..decision.trading_fields_validator import TradingFieldsValidator
from .market_snapshot_service import MarketSnapshotService
from .lineage_service import apply_data_quality_review_gate
from ..quant.polars_indicators import compute_indicator_frame

PROGRESS_REDIS_PREFIX = "analysis_progress"

class AnalysisJobService:
    def __init__(self, job_repo: JobRepository, snapshot_service: MarketSnapshotService):
        self.job_repo = job_repo
        self.snapshot_service = snapshot_service
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._progress: Dict[str, Dict[str, Any]] = {}
        # In-memory API key store — NEVER persisted to disk, shared across jobs
        self._api_key_events: Dict[str, asyncio.Event] = {}
        self._api_keys: Dict[str, str] = {}  # {provider: key} — global cache
        self._key_timestamps: Dict[str, float] = {}  # {provider: last_used_timestamp}
        self._KEY_TTL: int = 1800  # 30 minutes inactivity timeout before auto-clear
        # Allow multiple concurrent analysis jobs (default 5). The LLM gateway has its own rate limiter.
        import os
        self._concurrency_limit = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_JOBS", "5")))

    async def start_job(self, symbol: str, market: str, level: str = "standard", model: Optional[str] = None, config: Optional[Dict[str, Any]] = None, user_id: str = "default_user") -> str:
        import re
        if not re.match(r"^[A-Za-z0-9.\-_]+$", symbol) or not re.match(r"^[A-Za-z0-9.\-_]+$", market):
            raise ValueError("Invalid symbol or market format. Must be alphanumeric.")

        # Deduplicate: if same symbol+market already has a running/queued job within 60s, reuse it
        existing = self.job_repo.find_recent_running(symbol, market, within_seconds=60)
        if existing:
            logger.info(f"Dedup: returning existing job {existing} for {symbol} (already running/queued)")
            return existing
        
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        self.job_repo.create(job_id, symbol, market, level=level, model=model, user_id=user_id)
        
        if os.getenv("ALSA_DISABLE_BACKGROUND_JOBS") == "true" or os.getenv("PYTEST_CURRENT_TEST"):
            return job_id

        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            from app.worker import run_analysis_task
            logger.info(f"Dispatching job {job_id} to Celery worker")
            run_analysis_task.delay(job_id, symbol, market, config)
        else:
            logger.info(f"Running job {job_id} in local asyncio pool (Graceful Degradation)")
            # Fire and forget the background task
            task = asyncio.create_task(self._run_job(job_id, symbol, market, config=config))
            self._running_tasks[job_id] = task
            # Clean up task reference when done
            task.add_done_callback(lambda t: self._running_tasks.pop(job_id, None))
        
        return job_id

    def submit_api_key(self, job_id: str, provider: str, api_key: str) -> bool:
        """Receive an API key from the frontend. Cached in memory — never persisted.
           Once cached, subsequent jobs reuse the key without asking the frontend again."""
        import time
        # Store in global cache (shared across all jobs)
        self._api_keys[provider] = api_key
        self._key_timestamps[provider] = time.time()  # Track when key was provided
        # Wake the specific job if it's waiting
        if job_id in self._api_key_events:
            self._api_key_events[job_id].set()
        
        # Share key via Redis for Celery worker processes
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            r.set(f"alsa:apikey:{provider}", api_key, ex=1800)
            r.set(f"alsa:job:{job_id}:apikey:{provider}", api_key, ex=300)
        except Exception as e:
            logger.warning(f"[AnalysisJobService] Failed to share API key to Redis: {e}")
        return True

    def set_api_key(self, provider: str, api_key: str):
        """Proactively register/update an API key in memory cache (user settings change)."""
        import time
        self._api_keys[provider] = api_key
        self._key_timestamps[provider] = time.time()
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
            r.set(f"alsa:apikey:{provider}", api_key, ex=1800)
        except Exception as e:
            logger.warning(f"[AnalysisJobService] Failed to share set API key to Redis: {e}")

    def _clear_stale_keys(self):
        """Clear API keys that have been idle longer than KEY_TTL to prevent leakage."""
        import time
        now = time.time()
        stale = [p for p, ts in self._key_timestamps.items() if now - ts > self._KEY_TTL]
        for provider in stale:
            self._api_keys.pop(provider, None)
            self._key_timestamps.pop(provider, None)
            try:
                import redis
                r = redis.Redis(host='localhost', port=6379, db=0)
                r.delete(f"alsa:apikey:{provider}")
            except Exception:
                pass

    def get_key_status(self) -> Dict[str, Any]:
        """Return which providers have cached keys and when they expire."""
        import time
        now = time.time()
        status = {}
        for provider, key in self._api_keys.items():
            ts = self._key_timestamps.get(provider, 0)
            remaining = max(0, int(self._KEY_TTL - (now - ts))) if ts else 0
            # Show only whether key exists and remaining TTL — never expose the key itself
            status[provider] = {
                "cached": bool(key),
                "expires_in_seconds": remaining,
            }
        return status

    def clear_api_key(self, provider: str = None):
        """Clear cached API key for a specific provider, or all if provider is None."""
        if provider:
            self._api_keys.pop(provider, None)
            self._key_timestamps.pop(provider, None)
            try:
                import redis
                r = redis.Redis(host='localhost', port=6379, db=0)
                r.delete(f"alsa:apikey:{provider}")
            except Exception:
                pass
        else:
            self._api_keys.clear()
            self._key_timestamps.clear()
            try:
                import redis
                r = redis.Redis(host='localhost', port=6379, db=0)
                keys = r.keys("alsa:apikey:*")
                if keys:
                    r.delete(*keys)
            except Exception:
                pass

    def _refresh_key_timestamp(self, provider: str):
        """Update the last-used timestamp for a key (called when key is used)."""
        import time
        if provider in self._api_keys:
            self._key_timestamps[provider] = time.time()

    async def _wait_for_api_key(self, job_id: str, provider: str, timeout: int = 120, config: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Pause the job and wait for the frontend to send an API key.
           If key is already cached from a previous job, return it immediately."""
        # Clear stale keys before checking cache
        self._clear_stale_keys()

        # Check if the config object provided with the job has the key first
        if config:
            # Check both deepseekApiKey and generic apiKey
            key_from_config = config.get(f"{provider}ApiKey") or config.get("apiKey")
            if key_from_config:
                # Proactively update the global cache with this fresh key
                self.set_api_key(provider, key_from_config)
                self.update_job_progress(job_id, "discussion", 50, message="使用任务最新 API Key")
                return key_from_config

        # Check cache second — reuse key across jobs
        cached = self._api_keys.get(provider)
        
        # Try to pull from Redis if memory is empty (e.g. Celery worker startup)
        if not cached:
            try:
                from ..db.redis_client import get_redis
                r_client = await get_redis()
                cached_val = await r_client.get(f"alsa:apikey:{provider}")
                if cached_val:
                    cached = cached_val if isinstance(cached_val, str) else cached_val.decode('utf-8')
                    self._api_keys[provider] = cached
                    import time
                    self._key_timestamps[provider] = time.time()
            except Exception as e:
                logger.debug(f"[AnalysisJobService] Failed to check Redis cache: {e}")

        if cached:
            self._refresh_key_timestamp(provider)
            self.update_job_progress(job_id, "discussion", 50, message="使用缓存的 API Key")
            return cached
        
        # Check environment variables as fallback
        env_key = os.getenv(f"{provider.upper()}_API_KEY")
        if env_key:
            self.set_api_key(provider, env_key)
            self.update_job_progress(job_id, "discussion", 50, message="使用环境变量 API Key")
            return env_key
        
        event = asyncio.Event()
        self._api_key_events[job_id] = event
        # Signal frontend via progress that we need a key
        self.update_job_progress(job_id, "need_api_key", 50, message=f"需要{provider} API Key")
        
        # Poll Redis and wait for event concurrently
        try:
            from ..db.redis_client import get_redis
            r_client = await get_redis()
        except Exception:
            r_client = None

        key = None
        start_time = asyncio.get_event_loop().time()
        try:
            while asyncio.get_event_loop().time() - start_time < timeout:
                if event.is_set():
                    key = self._api_keys.get(provider)
                    break
                if r_client:
                    try:
                        val = await r_client.get(f"alsa:job:{job_id}:apikey:{provider}")
                        if not val:
                            val = await r_client.get(f"alsa:apikey:{provider}")
                        if val:
                            key = val if isinstance(val, str) else val.decode('utf-8')
                            self._api_keys[provider] = key
                            import time
                            self._key_timestamps[provider] = time.time()
                            break
                    except Exception as e:
                        logger.warning(f"Error polling Redis for key: {e}")
                await asyncio.sleep(1.0)
            if not key:
                logger.warning(f"Timeout waiting for API key for job {job_id}")
        except Exception as e:
            logger.error(f"Error in wait_for_api_key loop: {e}")
        finally:
            self._api_key_events.pop(job_id, None)
            
        return key

    async def _run_job(self, job_id: str, symbol: str, market: str, config: Optional[Dict[str, Any]] = None):
        from .discussion_service import discussion_service
        from ..db.models import AnalysisRun, AnalysisJob, PredictionRecord
        from .token_guard import token_guard
        from .llm_gateway import current_token_usage
        
        # Apply user-configured token guard level (default: "high")
        if config and config.get("tokenGuardLevel"):
            token_guard.set_level(config["tokenGuardLevel"])
        
        # Wait for our turn in the queue (only 1 job runs at a time)
        async with self._concurrency_limit:
            # Mark job as running in the database immediately
            self.job_repo.update_status(job_id, "running")
            self.update_job_progress(job_id, "need_api_key", 5, message="正在校验 API 密钥...")
            # Watchdog heartbeat: keep the frontend idle timer alive during silent phases
            # (critic review, finalizing, LLM retry/backoff) so a busy-but-quiet job is
            # never mistaken for "AI stopped responding".
            heartbeat_task = asyncio.create_task(self._heartbeat(job_id))
            
            try:
                # 0. Retrieve and validate API key first
                job = self.job_repo.get_by_id(job_id)
                requested_model = job.requested_model if job else None
                if not requested_model and config:
                    requested_model = config.get("model")
                provider = "deepseek" if (requested_model or "").lower().startswith("deepseek") else "gemini"
                
                api_key = await self._wait_for_api_key(job_id, provider, config=config)
                if not api_key:
                    raise ValueError("未收到 API Key，研判任务取消")
                
                # Check key validity
                self.update_job_progress(job_id, "need_api_key", 8, message="正在校验 API Key...")
                from .llm_gateway import llm_gateway
                is_valid = await llm_gateway.validate_api_key(provider, api_key)
                if not is_valid:
                    raise ValueError(f"API Key 校验失败，无效的 {provider} API Key")
                    
                # Inject key into config for the discussion service
                safe_config = dict(config or {})
                safe_config[f"{provider}ApiKey"] = api_key
                
                # 1. Create snapshot (saves to Parquet)
                self.update_job_progress(job_id, "snapshot", 10)
                snapshot = await self.snapshot_service.create_snapshot(market, symbol)
                if not snapshot:
                    raise ValueError("Failed to fetch market data")
                snapshot["market"] = market
                
                self.update_job_progress(job_id, "quant", 30)
                # 2. Compute quantitative factors using Polars
                if snapshot.get("history"):
                    indicator_df = compute_indicator_frame(snapshot["history"])
                    indicators = indicator_df.tail(1).to_dicts()[0] if len(indicator_df) > 0 else {}
                else:
                    indicators = {}
                snapshot["indicators"] = indicators
                
                self.update_job_progress(job_id, "discussion", 50)
                
                # 3b. Run Expert Discussion
                level = job.analysis_level if job else "standard"
                def report_discussion_progress(round, total, msg, count=None, error_type=None, **kwargs):
                    self.update_job_progress(job_id, "discussion", 50 + int((round/total) * 40), round=round, total_rounds=total, message=msg, count=count, error_type=error_type)
    
                # Determine language: explicit config > market-based auto-detection
                # NOTE: US-Share intentionally uses zh-CN (Chinese) — the entire report system
                # is Chinese-primary, and LLMs handle Chinese financial analysis well.
                language = (config or {}).get("language") or "zh-CN"
    
                # Initialize ContextVar for precise token tracking during this job
                job_usage = {"promptTokens": 0, "candidatesTokens": 0, "totalTokens": 0}
                token_ctx = current_token_usage.set(job_usage)
    
                try:
                    discussion_messages = await discussion_service.run_discussion(
                        symbol, 
                        snapshot.get("name", symbol), 
                        snapshot, 
                        level=level,
                        language=language,
                        model=requested_model,
                        on_progress=report_discussion_progress,
                        job_id=job_id,
                        config=safe_config
                    )
                finally:
                    current_token_usage.reset(token_ctx)
                
                # Run Critic Agent on the discussion messages
                critique_res = None
                try:
                    from app.services.critic_agent import critic_agent
                    critique_res = await critic_agent.critique(
                        analyses=discussion_messages,
                        symbol=symbol,
                        name=snapshot.get("name", symbol),
                        context=snapshot,
                        gemini_api_key=safe_config.get("geminiApiKey"),
                        deepseek_api_key=safe_config.get("deepseekApiKey"),
                        model=requested_model
                    )
                except Exception as e:
                    logger.error(f"Critic Agent critique failed: {e}")

                self.update_job_progress(job_id, "finalizing", 90)
                # Key used — refresh timestamp (keeps it alive while job is active)
                self._refresh_key_timestamp(provider)
                # 4. Final Payload — enrich stockInfo with quote data for Flash UI
                quote = snapshot.get("quote", {})
                snapshot_id = snapshot.get("snapshot_id")
                result = {
                    "symbol": symbol,
                    "market": market,
                    "snapshot_id": snapshot_id,
                    "as_of_date": snapshot.get("as_of_date"),
                    "data_quality": snapshot.get("data_quality"),
                    "stockInfo": {
                        "symbol": symbol,
                        "market": market,
                        "name": snapshot.get("name", symbol),
                        "price": quote.get("price") or snapshot.get("price"),
                        "change": quote.get("change"),
                        "changePercent": quote.get("changePercent") or snapshot.get("changePercent"),
                        "currency": quote.get("currency") or snapshot.get("currency", "CNY" if market == "A-Share" else "USD"),
                        "previousClose": quote.get("previousClose"),
                        "marketCap": quote.get("marketCap"),
                        "pe": quote.get("trailingPE"),
                        "forwardPE": quote.get("forwardPE"),
                        "pb": quote.get("priceToBook"),
                        "dividendYield": quote.get("dividendYield"),
                        "lastUpdated": utc_now().strftime("%Y/%m/%d %H:%M:%S") + " CST",
                    },
                    "technicals": indicators,
                    "indicators": indicators,
                    "valuation": snapshot.get("valuation"),
                    "financials": snapshot.get("financials"),
                    "snapshot": snapshot,
                    "discussion": discussion_messages,
                    "critique": critique_res,
                    "summary": self._extract_summary(discussion_messages),
                    "usageMetadata": job_usage,
                }
                
                # Extract structured fields for Flash UI (sentiment, recommendation, risks, etc.)
                try:
                    structured = self._extract_structured_fields(discussion_messages)
                except ValueError as e:
                    logger.warning(f"[AnalysisJobService] Structured field extraction failed (non-fatal): {e}")
                    structured = {
                        "sentiment": "Neutral",
                        "recommendation": "Hold",
                        "tradingPlan": {"strategy": "分析完成，但结构化提取失败"},
                        "keyRisks": [],
                    }
                result.update(structured)
                
                # Validate trading fields — reject garbage regex output, enforce numeric sanity
                validation = TradingFieldsValidator.validate(structured)
                result["_validation"] = {
                    "is_valid": validation.is_valid,
                    "signal_eligible": validation.signal_eligible,
                    "errors": validation.errors,
                }
                if not validation.is_valid and structured.get("tradingPlan"):
                    # Mark trading plan as unvalidated so downstream never treats it as a signal
                    structured["tradingPlan"]["_validated"] = False
                    structured["tradingPlan"]["_validation_errors"] = validation.errors
                elif validation.signal_eligible:
                    structured["tradingPlan"]["_validated"] = True
                apply_data_quality_review_gate(result)
                
                # 5. Create Analysis Run and Update Job
                with self.job_repo.session_factory() as session:
                    # Derive verdict from structured extraction
                    rec = result.get("recommendation", structured.get("recommendation", "Hold"))
                    if rec in ("Buy",): verdict = "buy"
                    elif rec in ("Overweight",): verdict = "buy"
                    elif rec in ("Sell",): verdict = "sell"
                    elif rec in ("Underweight",): verdict = "sell"
                    else: verdict = "watch"
                    
                    run_score = float(structured.get("score", 70.0))
                    
                    analysis_run = AnalysisRun(
                        job_id=job_id,
                        symbol=symbol,
                        market=market,
                        snapshot_id=snapshot_id,
                        summary_verdict=verdict,
                        score=run_score,
                        risk_level="medium"
                    )
                    session.add(analysis_run)
                    session.commit()
                    session.refresh(analysis_run)
                    
                    # Extract and save PredictionRecord if target price exists
                    try:
                        target_price_str = structured.get("tradingPlan", {}).get("targetPrice")
                        if target_price_str:
                            import re
                            match = re.search(r"[\d.]+", str(target_price_str))
                            if match:
                                tp = float(match.group())
                                cp = float(quote.get("price") or snapshot.get("price", 0.0))
                                if tp > 0 and cp > 0:
                                    pred = PredictionRecord(
                                        job_id=job_id,
                                        symbol=symbol,
                                        market=market,
                                        target_price=tp,
                                        current_price_at_prediction=cp
                                    )
                                    session.add(pred)
                                    session.commit()
                    except Exception as e:
                        logger.warning(f"Failed to save PredictionRecord: {e}")
                    
                    # Update job
                    db_job = session.get(AnalysisJob, job_id)
                    if db_job:
                        db_job.status = "completed"
                        db_job.analysis_id = analysis_run.analysis_id
                        db_job.snapshot_id = snapshot_id
                        
                        def json_serial(obj):
                            if isinstance(obj, (datetime, date)):
                                return obj.isoformat()
                            raise TypeError(f"Type {type(obj)} not serializable")
                        
                        db_job.result_payload = result
                        db_job.finished_at = utc_now()
                        session.add(db_job)
                        session.commit()
    
            except asyncio.CancelledError:
                self.job_repo.update_status(job_id, "cancelled")
                raise
            except Exception as e:
                error_msg = str(e)
                # Check if this is a user-initiated stop — still save partial results
                if "stopped by user" in error_msg:
                    logger.info(f"Analysis job {job_id} stopped by user, saving partial results")
                    try:
                        _msgs = locals().get("discussion_messages", [])
                        _snap = locals().get("snapshot", {})
                        _inds = locals().get("indicators", {})
                        if _snap:
                            await self._save_partial_results(job_id, symbol, market, _snap, _inds, _msgs)
                        else:
                            self.job_repo.update_status(job_id, "failed", json.dumps({"error": "Stopped before data was ready"}))
                    except Exception as save_err:
                        logger.error(f"Failed to save partial results: {save_err}")
                        self.job_repo.update_status(job_id, "failed", json.dumps({"error": error_msg}))
                else:
                    logger.exception(f"Analysis job {job_id} failed: {e}")
                    self.job_repo.update_status(job_id, "failed", json.dumps({"error": error_msg}))
            
            finally:
                # Stop the watchdog heartbeat
                heartbeat_task.cancel()
                # Only clean up the event — the key stays cached globally for reuse
                self._api_key_events.pop(job_id, None)
    
    async def _save_partial_results(self, job_id: str, symbol: str, market: str, snapshot: Dict[str, Any], indicators: Dict[str, Any], discussion_messages: List[Dict[str, Any]]):
        """Save partial results when analysis is interrupted (user abort or 402)."""
        from ..db.models import AnalysisRun, AnalysisJob
        
        # Filter out empty messages
        valid_messages = [m for m in discussion_messages if m.get("content")]
        
        self.update_job_progress(job_id, "finalizing", 90, message="正在保存已获取的部分内容...")
        
        quote = snapshot.get("quote", {})
        snapshot_id = snapshot.get("snapshot_id")
        result = {
            "symbol": symbol,
            "market": market,
            "snapshot_id": snapshot_id,
            "as_of_date": snapshot.get("as_of_date"),
            "data_quality": snapshot.get("data_quality"),
            "stockInfo": {
                "symbol": symbol,
                "market": market,
                "name": snapshot.get("name", symbol),
                "price": quote.get("price") or snapshot.get("price"),
                "change": quote.get("change"),
                "changePercent": quote.get("changePercent") or snapshot.get("changePercent"),
                "currency": quote.get("currency") or snapshot.get("currency", "CNY" if market == "A-Share" else "USD"),
                "lastUpdated": utc_now().strftime("%Y/%m/%d %H:%M:%S") + " CST",
            },
            "technicals": indicators,
            "valuation": snapshot.get("valuation"),
            "financials": snapshot.get("financials"),
            "snapshot": snapshot,
            "discussion": valid_messages,
            "summary": self._extract_summary(valid_messages),
            "partial": True  # Flag indicating partial results
        }
        apply_data_quality_review_gate(result)
        
        with self.job_repo.session_factory() as session:
            last_msg = valid_messages[-1]["content"] if valid_messages else ""
            verdict = "watch"
            if "买入" in last_msg or "BUY" in last_msg.upper(): verdict = "buy"
            elif "卖出" in last_msg or "SELL" in last_msg.upper(): verdict = "sell"
            
            analysis_run = AnalysisRun(
                job_id=job_id,
                symbol=symbol,
                market=market,
                snapshot_id=snapshot_id,
                summary_verdict=verdict,
                score=50.0,  # Lower score for partial
                risk_level="medium"
            )
            session.add(analysis_run)
            session.commit()
            session.refresh(analysis_run)
            
            # Skip PredictionRecord for partial results — no reliable structured data available
            # (structured fields are only extracted after full discussion completes)
            
            db_job = session.get(AnalysisJob, job_id)
            if db_job:
                db_job.status = "completed"
                db_job.analysis_id = analysis_run.analysis_id
                db_job.snapshot_id = snapshot_id
                
                def json_serial(obj):
                    if isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")
                
                db_job.result_payload = result
                db_job.finished_at = utc_now()
                session.add(db_job)
                session.commit()
        
        logger.info(f"Partial results saved for job {job_id}: {len(valid_messages)} expert messages")

    @staticmethod
    def _extract_summary(discussion_messages: List[Dict[str, Any]]) -> str:
        """Extract a short summary from the Chief Strategist (last) message."""
        if not discussion_messages:
            return ""
        last = discussion_messages[-1]
        content = last.get("content", "")
        # Try to find a tagline or thesis section
        for marker in ["Tagline", "Investment Thesis", "核心摘要", "核心结论"]:
            idx = content.find(marker)
            if idx != -1:
                # Grab the paragraph after the marker
                block = content[idx:idx + 600]
                lines = [l.strip() for l in block.split("\n") if l.strip() and not l.strip().startswith("#")]
                # Skip the marker line itself, take up to 3 lines
                useful = [l for l in lines[1:4] if l and not l.startswith("|") and not l.startswith("---")]
                if useful:
                    return " ".join(useful)[:400]
        # Fallback: first non-heading paragraph
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("|") and not stripped.startswith("---") and len(stripped) > 30:
                return stripped[:400]
        return ""

    @staticmethod
    def _extract_structured_fields(discussion_messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract structured analysis fields from the Chief Strategist's output for Flash UI."""
        import re
        fields: Dict[str, Any] = {}
        
        # Find expert messages by role
        chief_content = ""
        technical_content = ""
        fundamental_content = ""
        for msg in discussion_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "Chief Strategist" and content:
                chief_content = content
            elif role == "Technical Analyst" and content and not technical_content:
                technical_content = content
            elif role == "Fundamental Analyst" and content and not fundamental_content:
                fundamental_content = content
        
        # Populate technicalAnalysis and fundamentalAnalysis from expert messages
        if technical_content:
            fields["technicalAnalysis"] = technical_content[:2000]
        if fundamental_content:
            fields["fundamentalAnalysis"] = fundamental_content[:2000]
        
        if not chief_content:
            return fields
        
        # --- Structured JSON parsing (CRITICAL) ---
        json_match = re.search(r'<structured_data>\s*(\{.*?\})\s*</structured_data>', chief_content, re.DOTALL)
        if json_match:
            try:
                import json
                parsed = json.loads(json_match.group(1))
                fields["sentiment"] = parsed.get("sentiment", "Neutral")
                fields["recommendation"] = parsed.get("recommendation", "Hold")
                
                tp = parsed.get("targetPrice")
                sl = parsed.get("stopLossPrice")
                trading_plan = {}
                if tp is not None:
                    trading_plan["targetPrice"] = str(tp)
                if sl is not None:
                    trading_plan["stopLoss"] = str(sl)
                
                trading_plan["strategy"] = "基于多智能体决策"
                if "confidence" in parsed:
                    trading_plan["strategy"] += f" (信心指数: {parsed['confidence']}%)"
                if trading_plan:
                    fields["tradingPlan"] = trading_plan
                    
                fields["keyRisks"] = parsed.get("keyRisks", [])
                if parsed.get("catalysts"):
                    fields["keyOpportunities"] = parsed.get("catalysts")
                    
                # Return early to skip fragile regex if we got the core fields
                if fields.get("sentiment") and fields.get("tradingPlan"):
                    return fields
                else:
                    raise ValueError("Structured data missing essential fields (sentiment or tradingPlan)")
            except Exception as e:
                logger.warning(f"[AnalysisJobService] Failed to parse <structured_data> JSON: {e}")
                raise ValueError(f"Structured data missing or invalid: {e}")
        else:
            raise ValueError("No <structured_data> JSON block found in LLM output")
        
        return fields

    def update_job_progress(self, job_id: str, stage: str, percent: int, round: Optional[int] = None, total_rounds: Optional[int] = None, message: Optional[str] = None, count: Optional[int] = None, error_type: Optional[str] = None):
        prev = self._progress.get(job_id, {})
        progress = {
            "stage": stage, 
            "percent": percent,
            "round": round,
            "total_rounds": total_rounds,
            "message": message,
            "count": count if count is not None else prev.get("count"),
            "error_type": error_type or prev.get("error_type")
        }
        self._progress[job_id] = progress
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._write_shared_progress(job_id, progress))
        except RuntimeError:
            pass

    async def get_job_progress(self, job_id: str) -> Optional[Dict[str, Any]]:
        progress = self._progress.get(job_id)
        if progress:
            return progress
        try:
            from ..db.redis_client import get_redis
            r_client = await get_redis()
            raw = await r_client.get(f"{PROGRESS_REDIS_PREFIX}:{job_id}")
            if raw:
                return json.loads(raw if isinstance(raw, str) else raw.decode("utf-8"))
        except Exception as e:
            logger.debug(f"[AnalysisJobService] Failed to read shared progress for {job_id}: {e}")
        return None

    async def _write_shared_progress(self, job_id: str, progress: Dict[str, Any]) -> None:
        try:
            from ..db.redis_client import get_redis
            r_client = await get_redis()
            await r_client.set(f"{PROGRESS_REDIS_PREFIX}:{job_id}", json.dumps(progress, ensure_ascii=False), ex=86400)
        except Exception as e:
            logger.debug(f"[AnalysisJobService] Failed to persist shared progress for {job_id}: {e}")

    async def _heartbeat(self, job_id: str, interval: int = 15):
        """Emit a lightweight progress pulse while a job is running so the frontend
        idle-timeout never trips during legitimately silent phases (critic review,
        finalizing, LLM retry/backoff). Preserves the current stage/percent/count and
        only refreshes the message with elapsed time to signal liveness."""
        import time
        start = time.monotonic()
        try:
            while True:
                await asyncio.sleep(interval)
                prev = self._progress.get(job_id)
                if not prev:
                    continue
                stage = prev.get("stage")
                if stage in ("completed", "failed"):
                    break
                elapsed = int(time.monotonic() - start)
                base = (prev.get("message") or "").split(" · 运行")[0]
                self.update_job_progress(
                    job_id,
                    stage or "running",
                    prev.get("percent") or 0,
                    round=prev.get("round"),
                    total_rounds=prev.get("total_rounds"),
                    message=f"{base} · 运行 {elapsed}s",
                    count=prev.get("count"),
                )
        except asyncio.CancelledError:
            pass

    def get_status(self, job_id: str):
        job = self.job_repo.get_by_id(job_id)
        return job

    def get_analysis_run(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        run = self.job_repo.get_analysis_run(analysis_id)
        if not run:
            return None
        
        job = self.job_repo.get_by_id(run.job_id)
        if not job or not job.result_payload:
            return run.dict()
            
        result = job.result_payload if isinstance(job.result_payload, dict) else (json.loads(job.result_payload) if job.result_payload else None)
        result["analysis_id"] = run.analysis_id
        result["job_id"] = run.job_id
        result["summary_verdict"] = run.summary_verdict
        result["score"] = run.score
        result["risk_level"] = run.risk_level
        # Ensure top-level symbol/market for report generator
        if "symbol" not in result:
            result["symbol"] = run.symbol
        if "market" not in result:
            result["market"] = run.market
        
        # Backfill structured fields if missing (for older jobs)
        if "sentiment" not in result or "recommendation" not in result:
            discussion = result.get("discussion", [])
            if discussion:
                try:
                    structured = self._extract_structured_fields(discussion)
                    for k, v in structured.items():
                        if k not in result or result[k] is None:
                            result[k] = v
                except ValueError as e:
                    logger.warning(f"[AnalysisJobService] Backfill structured fields failed: {e}")
                # Also backfill summary
                if not result.get("summary"):
                    result["summary"] = self._extract_summary(discussion)
        apply_data_quality_review_gate(result)
        
        return result

    async def cancel_job(self, job_id: str) -> bool:
        task = self._running_tasks.get(job_id)
        if task:
            task.cancel()
            return True
        
        job = self.job_repo.get_by_id(job_id)
        if job and job.status in ["queued", "running"]:
            self.job_repo.update_status(job_id, "cancelled")
            return True
        return False

    def recover_orphaned_jobs(self) -> int:
        """On startup, mark any queued/running jobs as failed.
        
        These jobs lost their in-memory asyncio tasks due to a process restart.
        Returns the count of recovered jobs.
        """
        count = self.job_repo.recover_orphaned_jobs()
        if count > 0:
            logger.info(f"[Startup Recovery] Marked {count} orphaned job(s) as failed.")
        return count

    async def retry_job(self, job_id: str, config: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Re-submit a failed/cancelled job with the same parameters.
        
        Returns the new job_id, or None if the original job was not found
        or is not in a retryable state.
        """
        job = self.job_repo.get_by_id(job_id)
        if not job or job.status not in ["failed", "cancelled"]:
            return None
        
        return await self.start_job(
            symbol=job.symbol,
            market=job.market,
            level=job.analysis_level,
            model=job.requested_model,
            config=config
        )
