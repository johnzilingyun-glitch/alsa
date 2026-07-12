"""
DataRouter — Market-aware data source router with fallback.

Implements the Strategy Pattern: detects market from ticker and
routes to the optimal data provider. Falls back gracefully on failure.

Routing rules:
  A-Shares (6-digit/.SH/.SZ) → AStockDirectProvider (primary, Tencent+Sina)
  HK (.HK / 4-5 digit)       → YFinanceProvider
  US (alpha / ^prefix)        → YFinanceProvider
"""

import logging
import os
import time
from typing import Dict, Any, Optional, List, Tuple
import contextvars
import json
from pathlib import Path

import yaml

import pandas as pd

from .base import (
    DataProvider,
    QuoteData,
    MarketType,
    detect_market,
    score_quote_quality,
    score_history_quality,
    score_financial_quality,
)
from .a_stock_direct import AStockDirectProvider
from .yfinance_provider import YFinanceProvider
from .extra_providers import THSDataProvider, SinaDataProvider, IwencaiDataProvider

import asyncio
from datetime import datetime, timedelta
from sqlalchemy import text
from app.db.database import engine

logger = logging.getLogger(__name__)

POLICY_PATH = Path(__file__).resolve().parent / "provider_policies.yaml"

class DataRouter:
    """
    Intelligent data router that selects the optimal provider based on market.
    Provides a unified interface hiding all underlying API complexity.
    """

    def __init__(self):
        # Provider instances (lazy-init friendly, stateless)
        self._a_stock_primary = AStockDirectProvider()
        self._yfinance = YFinanceProvider()
        self._ths = THSDataProvider()
        self._sina = SinaDataProvider()
        self._iwencai = IwencaiDataProvider()
        self._provider_map = {
            self._a_stock_primary.name: self._a_stock_primary,
            self._yfinance.name: self._yfinance,
            self._ths.name: self._ths,
            self._sina.name: self._sina,
            self._iwencai.name: self._iwencai,
        }
        self._last_route_meta_var: contextvars.ContextVar = contextvars.ContextVar("last_route_meta", default={})
        self._policy_mtime: float = 0.0
        self._policies: Dict[str, Any] = {}
        self._financial_cache: Dict[str, Tuple[float, Dict[str, Any], Dict[str, Any]]] = {}
        self._runtime_stats = {
            "totals": {"success": 0, "failure": 0, "cache_hit": 0},
            "by_market": {},
            "by_data_type": {},
            "by_provider": {},
        }
        self._load_policies(force=True)

    def _load_policies(self, force: bool = False) -> None:
        try:
            mtime = POLICY_PATH.stat().st_mtime
            if not force and mtime == self._policy_mtime:
                return
            with POLICY_PATH.open("r", encoding="utf-8") as f:
                self._policies = yaml.safe_load(f) or {}
            self._policy_mtime = mtime
        except Exception as e:
            logger.warning(f"[Router Policy] failed to load policies: {e}")
            self._policies = {}

    def _market_key(self, market: str) -> str:
        if not market:
            return "Unknown"
        return market

    def _get_quality_threshold(self, data_type: str, market: str) -> float:
        self._load_policies()
        block = (self._policies.get("quality_thresholds") or {}).get(data_type, {})
        if not isinstance(block, dict):
            return 0.0
        return float(block.get(self._market_key(market), block.get("default", 0.0)) or 0.0)

    def _is_quality_enforced(self) -> bool:
        self._load_policies()
        flags = self._policies.get("flags") or {}
        return bool(flags.get("enforce_quality_threshold", True))

    def _score_quality(self, data_type: str, payload: Any) -> float:
        if data_type == "quote":
            return score_quote_quality(payload)
        if data_type == "history":
            return score_history_quality(payload)
        if data_type == "financial":
            return score_financial_quality(payload)
        return 1.0

    def _get_quote_ttl(self, market: str) -> int:
        self._load_policies()
        block = ((self._policies.get("cache_ttl_seconds") or {}).get("quote") or {})
        return int(block.get(self._market_key(market), block.get("Unknown", 5)) or 5)

    def _get_history_ttl(self, interval: str) -> int:
        self._load_policies()
        block = ((self._policies.get("cache_ttl_seconds") or {}).get("history") or {})
        return int(block.get(interval, block.get("default", 120)) or 120)

    def _get_financial_ttl(self, market: str) -> int:
        self._load_policies()
        block = ((self._policies.get("cache_ttl_seconds") or {}).get("financial") or {})
        return int(block.get(self._market_key(market), block.get("Unknown", 3600)) or 3600)

    def _history_cache_enabled(self) -> bool:
        self._load_policies()
        flags = self._policies.get("flags") or {}
        return bool(flags.get("enable_history_redis_cache", True))

    def _financial_cache_enabled(self) -> bool:
        self._load_policies()
        flags = self._policies.get("flags") or {}
        return bool(flags.get("enable_financial_ttl_cache", True))

    def _stats_bucket(self, container: Dict[str, Any], key: str) -> Dict[str, Any]:
        if key not in container:
            container[key] = {
                "success": 0,
                "failure": 0,
                "cache_hit": 0,
                "requests": 0,
                "total_latency_ms": 0,
                "avg_latency_ms": 0,
            }
        return container[key]

    def _record_runtime_stat(self, meta: Dict[str, Any]) -> None:
        success = bool(meta.get("success"))
        cache_hit = bool(meta.get("cache_hit"))
        latency_ms = float(meta.get("latency_ms") or 0)
        market = str(meta.get("market_detected") or "Unknown")
        data_type = str(meta.get("data_type") or "unknown")
        provider = str(meta.get("provider_used") or "none")

        totals = self._runtime_stats["totals"]
        totals["success"] += 1 if success else 0
        totals["failure"] += 0 if success else 1
        totals["cache_hit"] += 1 if cache_hit else 0

        for key, container in (
            (market, self._runtime_stats["by_market"]),
            (data_type, self._runtime_stats["by_data_type"]),
            (provider, self._runtime_stats["by_provider"]),
        ):
            bucket = self._stats_bucket(container, key)
            bucket["requests"] += 1
            bucket["success"] += 1 if success else 0
            bucket["failure"] += 0 if success else 1
            bucket["cache_hit"] += 1 if cache_hit else 0
            bucket["total_latency_ms"] += latency_ms
            if bucket["requests"] > 0:
                bucket["avg_latency_ms"] = round(bucket["total_latency_ms"] / bucket["requests"], 2)

    def _set_last_route_meta(self, meta: Dict[str, Any]) -> None:
        self._last_route_meta_var.set(meta)
        self._record_runtime_stat(meta)

    def get_last_route_meta(self) -> Dict[str, Any]:
        meta = self._last_route_meta_var.get() or {}
        return dict(meta)

    def get_runtime_stats(self) -> Dict[str, Any]:
        return {
            "totals": dict(self._runtime_stats["totals"]),
            "by_market": dict(self._runtime_stats["by_market"]),
            "by_data_type": dict(self._runtime_stats["by_data_type"]),
            "by_provider": dict(self._runtime_stats["by_provider"]),
        }

    def get_policy_snapshot(self) -> Dict[str, Any]:
        self._load_policies()
        return {
            "policy_path": str(POLICY_PATH),
            "policy_mtime": self._policy_mtime,
            "policies": dict(self._policies),
        }

    def _get_providers(self, symbol: str) -> List[DataProvider]:
        """
        Return ordered list of providers for a symbol.
        First = primary, rest = fallbacks.
        """
        self._load_policies()
        market = detect_market(symbol)
        market_key = market.value

        order = ((self._policies.get("provider_order") or {}).get(market_key) or [])
        selected: List[DataProvider] = []
        for name in order:
            p = self._provider_map.get(name)
            if p:
                selected.append(p)
        if selected:
            return selected

        if market == MarketType.A_SHARE:
            return [self._a_stock_primary, self._yfinance, self._ths, self._sina, self._iwencai]
        elif market == MarketType.HK_SHARE:
            return [self._yfinance, self._a_stock_primary]
        elif market == MarketType.US_SHARE:
            return [self._yfinance]
        else:
            # Unknown market — try yfinance first, then A-share
            return [self._yfinance, self._a_stock_primary]

    CONCURRENT_TIMEOUT = 30

    async def _fetch_concurrently(self, symbol: str, fetch_func, default_val, validation_func, data_type: str, cache_hit: bool = False):
        started_at = time.perf_counter()
        market = detect_market(symbol).value
        quality_threshold = self._get_quality_threshold(data_type, market)
        enforce_quality = self._is_quality_enforced()
        providers = self._get_providers(symbol)

        async def wrap(idx, p):
            try:
                res = await fetch_func(p)
                quality_score = self._score_quality(data_type, res)
                if validation_func(res):
                    return idx, p.name, res, quality_score
            except Exception as e:
                logger.warning(f"[Router] {p.name} failed for {symbol}: {e}")
            return idx, p.name, None, 0.0

        tasks = [asyncio.create_task(wrap(i, p)) for i, p in enumerate(providers)]
        results_by_idx = {}
        highest_pending_idx = 0

        try:
            for fut in asyncio.as_completed(tasks, timeout=self.CONCURRENT_TIMEOUT):
                idx, name, res, quality_score = await fut
                results_by_idx[idx] = (res, quality_score)

                # Check if we can return the highest priority provider
                while highest_pending_idx in results_by_idx:
                    best_res, q = results_by_idx[highest_pending_idx]
                    if best_res is not None and (not enforce_quality or q >= quality_threshold):
                        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                        provider_used = providers[highest_pending_idx].name if highest_pending_idx < len(providers) else name
                        self._set_last_route_meta({
                            "symbol": symbol,
                            "market_detected": market,
                            "data_type": data_type,
                            "provider_used": provider_used,
                            "fallback_depth": highest_pending_idx,
                            "latency_ms": elapsed_ms,
                            "quality_score": q,
                            "quality_threshold": quality_threshold,
                            "cache_hit": cache_hit,
                            "success": True,
                        })
                        logger.info(f"[Router] Concurrent fetch successful for {symbol} (provider index {highest_pending_idx})")
                        return best_res
                    # The highest priority pending task failed, move to next
                    highest_pending_idx += 1

        except asyncio.TimeoutError:
            logger.warning(f"[Router] Concurrent fetch timed out ({self.CONCURRENT_TIMEOUT}s) for {symbol}")
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()

        # If we reach here due to timeout, return the best available result
        for i in range(len(providers)):
            entry = results_by_idx.get(i)
            if entry is not None:
                res, q = entry
                if res is None:
                    continue
                if enforce_quality and q < quality_threshold:
                    continue
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                provider_used = providers[i].name
                self._set_last_route_meta({
                    "symbol": symbol,
                    "market_detected": market,
                    "data_type": data_type,
                    "provider_used": provider_used,
                    "fallback_depth": i,
                    "latency_ms": elapsed_ms,
                    "quality_score": q,
                    "quality_threshold": quality_threshold,
                    "cache_hit": cache_hit,
                    "success": True,
                })
                return res

        logger.error(f"[Router] All concurrent providers failed for {symbol}")
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        self._set_last_route_meta({
            "symbol": symbol,
            "market_detected": market,
            "data_type": data_type,
            "provider_used": None,
            "fallback_depth": len(providers),
            "latency_ms": elapsed_ms,
            "quality_score": 0.0,
            "quality_threshold": quality_threshold,
            "cache_hit": cache_hit,
            "success": False,
        })
        return default_val

    async def get_history(
        self, symbol: str, period: str = "3mo", interval: str = "1d"
    ) -> pd.DataFrame:
        """
        Fetch historical k-lines concurrently, return the fastest valid dataframe.
        """
        market = detect_market(symbol).value
        started_at = time.perf_counter()

        # Redis history cache for intraday and short-window requests
        if self._history_cache_enabled():
            redis_client = None
            history_cache_key = f"router:history:{symbol}:{interval}:{period}"
            try:
                from app.db.redis_client import get_redis
                redis_client = await get_redis()
                cached_data = await redis_client.get(history_cache_key)
                if cached_data:
                    rows = json.loads(cached_data)
                    if isinstance(rows, list) and rows:
                        df_cached = pd.DataFrame(rows)
                        q = self._score_quality("history", df_cached)
                        self._set_last_route_meta({
                            "symbol": symbol,
                            "market_detected": market,
                            "data_type": "history",
                            "provider_used": "redis_history_cache",
                            "fallback_depth": 0,
                            "latency_ms": int((time.perf_counter() - started_at) * 1000),
                            "quality_score": q,
                            "quality_threshold": self._get_quality_threshold("history", market),
                            "cache_hit": True,
                            "success": True,
                        })
                        return df_cached
            except Exception as e:
                logger.warning(f"[Router Cache] Redis history read failed for {symbol}: {e}")

        # --- Cache Check Layer ---
        if interval == "1d":
            # Run blocking DB operations in a thread
            def _check_db():
                try:
                    query = text("SELECT MAX(date) as max_date, COUNT(*) as cnt FROM daily_klines WHERE symbol = :symbol")
                    df_meta = pd.read_sql(query, engine, params={"symbol": symbol})
                    if not df_meta.empty and df_meta['cnt'].iloc[0] > 0:
                        max_date_str = df_meta['max_date'].iloc[0]
                        if max_date_str:
                            max_date = pd.to_datetime(max_date_str).tz_localize(None)
                            now = datetime.now()
                            last_expected_date = now.date()

                            if now.hour < 15 or (now.hour == 15 and now.minute < 30):
                                last_expected_date -= timedelta(days=1)

                            if last_expected_date.weekday() == 5:
                                last_expected_date -= timedelta(days=1)
                            elif last_expected_date.weekday() == 6:
                                last_expected_date -= timedelta(days=2)

                            if max_date.date() >= last_expected_date:
                                logger.info(f"[Router Cache] HIT for {symbol}: max_date {max_date_str} >= expected {last_expected_date}")
                                df_cache = pd.read_sql(text("SELECT date, open, high, low, close, volume FROM daily_klines WHERE symbol = :symbol ORDER BY date ASC"), engine, params={"symbol": symbol})
                                df_cache['date'] = pd.to_datetime(df_cache['date']).dt.strftime('%Y-%m-%d')
                                return df_cache
                except Exception as e:
                    logger.warning(f"[Router Cache] DB read failed: {e}")
                return None

            cached_df = await asyncio.to_thread(_check_db)
            if cached_df is not None and not cached_df.empty:
                self._set_last_route_meta({
                    "symbol": symbol,
                    "market_detected": market,
                    "data_type": "history",
                    "provider_used": "daily_klines_db_cache",
                    "fallback_depth": 0,
                    "latency_ms": int((time.perf_counter() - started_at) * 1000),
                    "quality_score": self._score_quality("history", cached_df),
                    "quality_threshold": self._get_quality_threshold("history", market),
                    "cache_hit": True,
                    "success": True,
                })
                return cached_df

            period_to_fetch = "10y"
        else:
            period_to_fetch = period

        # --- API Concurrent Fetch Layer ---
        def validate_kline(df):
            if df is None or df.empty: return False
            if 'close' not in df.columns or 'date' not in df.columns: return False
            return True

        df = await self._fetch_concurrently(
            symbol,
            lambda p: p.get_history(symbol, period=period_to_fetch, interval=interval),
            pd.DataFrame(),
            validate_kline,
            data_type="history",
            cache_hit=False,
        )

        # --- Cache Write Layer ---
        if interval == "1d" and not df.empty:
            def _write_db(data_df):
                try:
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM daily_klines WHERE symbol = :symbol"), {"symbol": symbol})

                    insert_df = data_df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
                    insert_df['symbol'] = symbol
                    insert_df.to_sql("daily_klines", con=engine, if_exists="append", index=False)
                    logger.info(f"[Router Cache] WRITTEN for {symbol}: {len(insert_df)} rows cached.")
                except Exception as e:
                    logger.warning(f"[Router Cache] DB write failed: {e}")

            asyncio.create_task(asyncio.to_thread(_write_db, df))

        if self._history_cache_enabled() and not df.empty:
            try:
                from app.db.redis_client import get_redis
                redis_client = await get_redis()
                ttl = self._get_history_ttl(interval)
                history_cache_key = f"router:history:{symbol}:{interval}:{period}"
                await redis_client.setex(history_cache_key, ttl, json.dumps(df.to_dict(orient="records"), ensure_ascii=False))
            except Exception as e:
                logger.warning(f"[Router Cache] Redis history write failed for {symbol}: {e}")

        return df

    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        """
        Fetch real-time quote concurrently with short-ttl Redis caching to prevent thundering herds.
        """
        market = detect_market(symbol).value
        started_at = time.perf_counter()

        cache_key = f"router:quote:{symbol}"
        redis_client = None
        try:
            from app.db.redis_client import get_redis
            redis_client = await get_redis()
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                data_dict = json.loads(cached_data)
                self._set_last_route_meta({
                    "symbol": symbol,
                    "market_detected": market,
                    "data_type": "quote",
                    "provider_used": "redis_quote_cache",
                    "fallback_depth": 0,
                    "latency_ms": int((time.perf_counter() - started_at) * 1000),
                    "quality_score": self._score_quality("quote", data_dict),
                    "quality_threshold": self._get_quality_threshold("quote", market),
                    "cache_hit": True,
                    "success": True,
                })
                return QuoteData(**data_dict)
        except Exception as e:
            logger.warning(f"[Router Cache] Redis read failed for {symbol}: {e}")

        async def fetch(p):
            return await p.get_quote(symbol)

        def is_valid(q):
            return q is not None and q.price > 0

        result = await self._fetch_concurrently(symbol, fetch, None, is_valid, data_type="quote", cache_hit=False)

        if result is not None and redis_client is not None:
            try:
                import dataclasses
                ttl = self._get_quote_ttl(market)
                await redis_client.setex(cache_key, ttl, json.dumps(dataclasses.asdict(result)))
            except Exception as e:
                logger.warning(f"[Router Cache] Redis write failed for {symbol}: {e}")

        return result

    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch comprehensive financial metrics concurrently.
        """
        market = detect_market(symbol)

        cache_key = f"financial:{market.value}:{symbol}"
        if self._financial_cache_enabled():
            cached = self._financial_cache.get(cache_key)
            if cached:
                expires_at, payload, cache_meta = cached
                if time.time() < expires_at:
                    self._set_last_route_meta({
                        **cache_meta,
                        "cache_hit": True,
                        "provider_used": "financial_ttl_cache",
                        "latency_ms": 0,
                    })
                    return dict(payload)

        async def fetch(p):
            res = await p.get_financial_summary(symbol)
            if res and "error" not in res:
                res["_routed_via"] = p.name
                res["_market"] = market.value
                return res
            return None

        def is_valid(r):
            if r is None: return False
            boilerplate = {"source", "symbol", "_routed_via", "_market", "currency", "financialCurrency", "name", "price"}
            data_keys = [k for k in r.keys() if k not in boilerplate and r[k] is not None]
            return len(data_keys) > 0

        default_err = {"error": "All providers failed", "symbol": symbol}
        result = await self._fetch_concurrently(symbol, fetch, default_err, is_valid, data_type="financial", cache_hit=False)

        # A-share ownership backfill
        if (
            isinstance(result, dict)
            and market == MarketType.A_SHARE
            and (result.get("heldPercentInsiders") is None or result.get("heldPercentInstitutions") is None)
        ):
            try:
                from .a_stock_direct import fetch_a_share_ownership
                code = "".join(ch for ch in symbol if ch.isdigit())[:6]
                if code:
                    ownership = await fetch_a_share_ownership(code)
                    for key, val in ownership.items():
                        if result.get(key) is None:
                            result[key] = val
            except Exception as e:
                logger.warning(f"[Router] A-share ownership enrichment failed for {symbol}: {e}")

        if self._financial_cache_enabled() and isinstance(result, dict) and "error" not in result:
            ttl = self._get_financial_ttl(market.value)
            meta = self.get_last_route_meta()
            self._financial_cache[cache_key] = (time.time() + ttl, dict(result), dict(meta))

        return result

    async def prewarm_financial_cache(self, symbols: List[str]) -> Dict[str, int]:
        warmed = 0
        failed = 0
        for sym in symbols:
            try:
                result = await self.get_financial_summary(sym)
                if isinstance(result, dict) and "error" not in result:
                    warmed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        return {"warmed": warmed, "failed": failed}

    async def get_quote_with_meta(self, symbol: str) -> Tuple[Optional[QuoteData], Dict[str, Any]]:
        quote = await self.get_quote(symbol)
        return quote, self.get_last_route_meta()

    async def get_history_with_meta(
        self, symbol: str, period: str = "3mo", interval: str = "1d"
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        df = await self.get_history(symbol, period=period, interval=interval)
        return df, self.get_last_route_meta()

    async def get_financial_summary_with_meta(self, symbol: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        summary = await self.get_financial_summary(symbol)
        return summary, self.get_last_route_meta()

    async def get_quotes_batch(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Batch fetch quotes for multiple symbols.
        Routes each symbol independently.
        """
        tasks = [self.get_quote(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = []
        for sym, result in zip(symbols, results):
            if isinstance(result, Exception):
                output.append({"symbol": sym, "error": str(result)})
            elif result is None:
                output.append({"symbol": sym, "error": "No data"})
            else:
                output.append(result.to_dict())
        return output


# Singleton instance
data_router = DataRouter()
