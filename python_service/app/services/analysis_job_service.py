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
from ..observability.failure_capture import capture_failure_incident

PROGRESS_REDIS_PREFIX = "analysis_progress"


def _build_fundamentals(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Derive a StockFundamentals-shaped dict from the analysis snapshot.

    The analysis result previously omitted ``fundamentals`` entirely, so the
    entire fundamental-metrics grid (StockHeroCard / reportGenerator / prompts
    / comparison & quantitative services) rendered empty for every analysis —
    the "很多数据N/A" symptom for A-shares like 600584.

    The snapshot already carries rich, reliable data from the DataRouter
    (AStockDirectProvider for A-shares, YFinanceProvider for US/HK), so we
    surface it here instead of depending on the flakier yfinance A-share path.
    """
    if not isinstance(snapshot, dict):
        return {}
    fin = snapshot.get("financials") or {}
    if not isinstance(fin, dict) or not fin:
        return {}

    def _num(key):
        v = fin.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    debt_to_equity = None
    td, eq = _num("totalDebt"), _num("equity")
    if td is not None and eq not in (None, 0):
        debt_to_equity = round(td / eq * 100, 1)

    # Valuation percentile ≈ price percentile over available history.
    # PE_t ∝ price_t for roughly constant TTM EPS, so the percentile of the
    # current price within the historical range equals the PE percentile.
    valuation_percentile = None
    hist = snapshot.get("history") or []
    if isinstance(hist, list) and len(hist) > 1:
        closes = [r.get("close") for r in hist if isinstance(r, dict) and r.get("close") is not None]
        if len(closes) > 1:
            cur = closes[-1]
            below = sum(1 for c in closes if c <= cur)
            valuation_percentile = round(below / len(closes) * 100, 1)

    rev_growth = _num("revenueGrowthYoY")
    if rev_growth is None:
        rev_growth = _num("revenueYoY")
    np_growth = _num("netProfitGrowthYoY")
    if np_growth is None:
        np_growth = _num("netProfitGrowth")

    # StockFundamentals is string-typed (src/types.ts). Downstream consumers
    # call string methods on these values — e.g. driftDetection.ts does
    # `analysis.fundamentals.pe.replace(/[^0-9.\-]/g, '')`. Return strings,
    # not floats, so we honor the contract and avoid a runtime TypeError.
    def _s(v):
        if v is None:
            return None
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    return {
        "marketCap": _s(_num("marketCap")),
        "pe": _s(_num("pe")),
        "pb": _s(_num("pb")),
        "roe": _s(_num("roe")),
        "eps": _s(_num("eps")),
        "grossMargin": _s(_num("grossMargin")),
        "revenue": _s(_num("revenue")),
        "netProfit": _s(_num("netProfit")),
        "nonGaapNetProfit": _s(_num("netProfitDeduct")),
        "revenueGrowth": _s(rev_growth),
        "netProfitGrowth": _s(np_growth),
        "debtToEquity": _s(debt_to_equity),
        "dividend": _s(_num("dividendPerShare")),
        "dividendYield": _s(_num("dividendYield")),
        "valuationPercentile": _s(valuation_percentile),
    }


def _derive_forward_pe(snapshot: Dict[str, Any]) -> Optional[float]:
    """Approximate forward PE for markets where yfinance provides no forwardPE
    (e.g. A-shares). forwardPE ≈ PE / (1 + net profit growth).

    Returns None if inputs are missing or the estimate is implausible. Growth
    from EastMoney is a percentage (e.g. 15.5 == 15.5%), so values with
    abs > 1.0 are normalized to a ratio before use.
    """
    if not isinstance(snapshot, dict):
        return None
    fin = snapshot.get("financials")
    if not isinstance(fin, dict) or not fin:
        return None

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    pe = _f(fin.get("pe")) or _f(fin.get("trailingPE"))
    if pe is None or pe <= 0:
        return None

    growth = (
        _f(fin.get("netProfitGrowth"))
        or _f(fin.get("netProfitGrowthYoY"))
        or _f(fin.get("revenueGrowthYoY"))
    )
    if growth is None:
        return None
    if abs(growth) > 1.0:
        growth = growth / 100.0
    # Guard against implausible estimates (e.g. growth near -100% would blow up)
    if growth <= -0.9:
        return None

    fwd = pe / (1.0 + growth)
    if fwd <= 0:
        return None
    return round(fwd, 2)


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

    @staticmethod
    def _sanitize_config(config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Deep-clean config dict to ensure Celery serialization safety.

        Removes non-JSON-serializable values (DataFrames, slices, custom objects)
        that would cause pickle/JSON failures during Redis transport.
        """
        if not config:
            return config
        import json
        try:
            json.dumps(config, default=str)
            return config
        except (TypeError, ValueError):
            pass
        # Fallback: keep only JSON-safe primitives
        sanitized = {}
        for k, v in config.items():
            try:
                json.dumps(v, default=str)
                sanitized[k] = v
            except (TypeError, ValueError):
                logger.warning(f"[Config] Dropping non-serializable key '{k}' (type={type(v).__name__})")
        return sanitized

    @staticmethod
    def _sanitize_result_payload(result: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure result_payload is fully JSON-serializable before DB storage.
        
        Removes DataFrame/Series/ndarray objects and other non-serializable types
        that cause 'unhashable type: slice' errors during SQLAlchemy JSON commit.
        """
        import json
        import numpy as np
        
        def _clean(obj, depth=0):
            if depth > 12:
                return str(obj)[:200]
            if obj is None or isinstance(obj, (bool, int, float, str)):
                return obj
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, (np.ndarray,)):
                return obj.tolist()
            if isinstance(obj, dict):
                return {k: _clean(v, depth + 1) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_clean(item, depth + 1) for item in obj]
            # DataFrame / Series / Polars objects → drop them (too large for JSON)
            type_name = type(obj).__name__
            if type_name in ("DataFrame", "Series", "LazyFrame"):
                return f"[{type_name} removed for serialization]"
            # Try json.dumps as last resort
            try:
                json.dumps(obj)
                return obj
            except (TypeError, ValueError):
                return str(obj)[:200]
        
        try:
            cleaned = _clean(result)
            # Final validation
            json.dumps(cleaned, default=str)
            return cleaned
        except Exception as e:
            logger.warning(f"[Sanitize] result_payload sanitization failed: {e}")
            # Nuclear fallback: json roundtrip with default=str
            try:
                return json.loads(json.dumps(result, default=str))
            except Exception:
                return {"error": "Result payload could not be serialized"}

    async def start_job(self, symbol: str, market: str, level: str = "standard", model: Optional[str] = None, config: Optional[Dict[str, Any]] = None, user_id: str = "default_user", verification_mode: str = "quick") -> str:
        import re
        if not re.match(r"^[A-Za-z0-9.\-_\u4e00-\u9fa5]+$", symbol) or not re.match(r"^[A-Za-z0-9.\-_\u4e00-\u9fa5]+$", market):
            raise ValueError("Invalid symbol or market format. Must be alphanumeric or Chinese.")

        # Deduplicate: if same symbol+market already has a running/queued job within 60s, reuse it
        existing = self.job_repo.find_recent_running(symbol, market, within_seconds=60)
        if existing:
            logger.info(f"Dedup: returning existing job {existing} for {symbol} (already running/queued)")
            return existing
        
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        self.job_repo.create(job_id, symbol, market, level=level, model=model, user_id=user_id)
        
        if os.getenv("ALSA_DISABLE_BACKGROUND_JOBS") == "true" or os.getenv("PYTEST_CURRENT_TEST"):
            return job_id

        config = self._sanitize_config(config)

        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            from app.worker import run_analysis_task
            logger.info(f"Dispatching job {job_id} to Celery worker")
            run_analysis_task.delay(job_id, symbol, market, config, verification_mode=verification_mode)
        else:
            # Fallback to local async execution
            logger.warning("Celery not configured. Running job locally.")
            task = asyncio.create_task(self._run_job(job_id, symbol, market, config=config, verification_mode=verification_mode))
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

    async def _run_job(self, job_id: str, symbol: str, market: str, config: Optional[Dict[str, Any]] = None, verification_mode: str = "quick"):
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
                model_lower = (requested_model or "").lower()
                if model_lower.startswith("gemini"):
                    provider = "gemini"
                elif model_lower.startswith("deepseek"):
                    provider = "deepseek"
                else:
                    provider = "openrouter"
                
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

                # Path B: enrich A-Share snapshot with intraday volume (分时量能)
                # from the a-stock-analysis skill so the pipeline LLM sees it
                # directly in its prompt (weak models can't call the tool itself).
                if market == "A-Share":
                    try:
                        from .data_providers.a_stock_direct import fetch_intraday_volume
                        intraday = await fetch_intraday_volume(symbol)
                        if intraday:
                            snapshot["intraday_volume"] = intraday
                    except Exception as exc:
                        logger.warning(
                            "Intraday volume enrichment failed for %s: %s", symbol, exc
                        )

                # Derive forwardPE (yfinance-only field, absent for A-shares) so the
                # expert prompt / report / stockInfo don't surface N/A. Approximation:
                # forwardPE ≈ PE / (1 + net profit growth).
                _fwd_pe = _derive_forward_pe(snapshot)
                if _fwd_pe is not None:
                    snapshot.setdefault("financials", {})["forwardPE"] = _fwd_pe
                
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
                        config=safe_config,
                        market=market,
                        verification_mode=verification_mode
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
                        openrouter_api_key=safe_config.get("openrouterApiKey"),
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
                        "forwardPE": quote.get("forwardPE") or _fwd_pe,
                        "pb": quote.get("pb"),
                        "dividendYield": quote.get("dividendYield"),
                        "lastUpdated": utc_now().strftime("%Y/%m/%d %H:%M:%S") + " CST",
                    },
                    "technicals": indicators,
                    "indicators": indicators,
                    "valuation": snapshot.get("valuation"),
                    "financials": snapshot.get("financials"),
                    "snapshot": snapshot,
                    "fundamentals": _build_fundamentals(snapshot),
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
                        
                        db_job.result_payload = self._sanitize_result_payload(result)
                        db_job.finished_at = utc_now()
                        session.add(db_job)
                        session.commit()
    
            except asyncio.CancelledError:
                self.job_repo.update_status(job_id, "cancelled")
                raise
            except Exception as e:
                raw_error_msg = str(e)
                import traceback
                tb_str = traceback.format_exc()
                incident = capture_failure_incident(
                    component="analysis_job_service",
                    error=e,
                    job_id=job_id,
                    symbol=symbol,
                    market=market,
                    stage=self._progress.get(job_id, {}).get("stage"),
                    context={
                        "progress": self._progress.get(job_id),
                        "config": self._sanitize_config(config),
                        "verification_mode": verification_mode,
                        "discussion_count": len(locals().get("discussion_messages", [])),
                        "snapshot_keys": list((locals().get("snapshot") or {}).keys()),
                    },
                    traceback_text=tb_str,
                )
                incident_id = incident.get("incident_id")
                incident_path = incident.get("incident_path")
                error_msg = f"{raw_error_msg} [incident_id={incident_id}]"
                logger.exception(f"Analysis job {job_id} failed: {e} (incident_id={incident_id})")
                
                # Write traceback to local file for recovery diagnostics
                try:
                    with open("/tmp/analysis_job_traceback.txt", "a") as f:
                        f.write(f"Job {job_id} failed:\n{tb_str}\n")
                except Exception:
                    pass

                # Retain the context / intermediate scene when error occurs
                _msgs = locals().get("discussion_messages", [])
                _snap = locals().get("snapshot", {})
                _inds = locals().get("indicators", {})
                
                error_payload = {
                    "error": error_msg,
                    "traceback": tb_str,
                    "partial": True,
                    "incident_id": incident_id,
                    "incident_path": incident_path,
                    "discussion": _msgs,
                    "snapshot": _snap,
                    "indicators": _inds
                }
                
                # Check if this is a user-initiated stop
                if "stopped by user" in raw_error_msg:
                    logger.info(f"Analysis job {job_id} stopped by user, saving partial results")
                    try:
                        if _snap:
                            await self._save_partial_results(job_id, symbol, market, _snap, _inds, _msgs)
                        else:
                            self.job_repo.update_status(job_id, "failed", json.dumps({"error": "Stopped before data was ready", "traceback": tb_str}))
                    except Exception as save_err:
                        logger.error(f"Failed to save partial results: {save_err}")
                        self.job_repo.update_status(job_id, "failed", json.dumps(error_payload))
                else:
                    try:
                        if _snap:
                            await self._save_partial_results(job_id, symbol, market, _snap, _inds, _msgs, error_msg=error_msg)
                        else:
                            self.job_repo.update_status(job_id, "failed", json.dumps(error_payload))
                    except Exception as save_err:
                        logger.error(f"Failed to save failed job context: {save_err}")
                        self.job_repo.update_status(job_id, "failed", json.dumps(error_payload))
            
            finally:
                # Stop the watchdog heartbeat
                heartbeat_task.cancel()
                # Only clean up the event — the key stays cached globally for reuse
                self._api_key_events.pop(job_id, None)
    
    async def _save_partial_results(self, job_id: str, symbol: str, market: str, snapshot: Dict[str, Any], indicators: Dict[str, Any], discussion_messages: List[Dict[str, Any]], error_msg: Optional[str] = None):
        """Save partial results when analysis is interrupted (user abort, 402, or error)."""
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
            "fundamentals": _build_fundamentals(snapshot),
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
                db_job.status = "failed" if error_msg else "completed"
                db_job.analysis_id = analysis_run.analysis_id
                db_job.snapshot_id = snapshot_id
                if error_msg:
                    db_job.error_message = error_msg
                
                def json_serial(obj):
                    if isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    raise TypeError(f"Type {type(obj)} not serializable")
                
                db_job.result_payload = self._sanitize_result_payload(result)
                db_job.finished_at = utc_now()
                session.add(db_job)
                session.commit()
        
        logger.info(f"Partial results saved for job {job_id} (status: {'failed' if error_msg else 'completed'}): {len(valid_messages)} expert messages")

    @staticmethod
    def _extract_summary(discussion_messages: List[Dict[str, Any]]) -> str:
        """Extract a short summary from the Chief Strategist (last) message."""
        if not discussion_messages:
            return ""
        last = discussion_messages[-1]
        content = last.get("content", "")
        if isinstance(content, dict):
            import json
            content = json.dumps(content, ensure_ascii=False)
        elif not isinstance(content, str):
            content = str(content)
            
        # Try to find a tagline or thesis section
        for marker in ["Tagline", "Investment Thesis", "核心摘要", "核心结论", "趋势定性", "结论"]:
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
            if stripped and not stripped.startswith("#") and not stripped.startswith("|") and not stripped.startswith("---") and not stripped.startswith("**Professional Reviewer") and len(stripped) > 30:
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
            if isinstance(technical_content, dict):
                import json
                technical_content = json.dumps(technical_content, ensure_ascii=False)
            elif not isinstance(technical_content, str):
                technical_content = str(technical_content)
            fields["technicalAnalysis"] = technical_content[:2000]
        if fundamental_content:
            if isinstance(fundamental_content, dict):
                import json
                fundamental_content = json.dumps(fundamental_content, ensure_ascii=False)
            elif not isinstance(fundamental_content, str):
                fundamental_content = str(fundamental_content)
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
            except Exception as e:
                logger.warning(f"[AnalysisJobService] Failed to parse <structured_data> JSON: {e}")
                fields["tradingPlan"] = {"strategy": "分析完成，但结构化JSON提取失败"}
        else:
            logger.warning("[AnalysisJobService] No <structured_data> JSON block found in LLM output")
            fields["tradingPlan"] = {"strategy": "分析完成，未生成结构化数据"}
            
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
