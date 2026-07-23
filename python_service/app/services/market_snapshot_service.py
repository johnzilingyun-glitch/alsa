import logging
from ..lake.parquet_store import ParquetMarketStore
from typing import List, Dict, Any
import asyncio
import os
import pandas as pd
import numpy as np
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MarketSnapshotService:
    def __init__(self, store: ParquetMarketStore):
        self.store = store

    def _normalize_ohlc_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        rename_map = {
            "??": "trade_date", "Date": "trade_date",
            "??": "open", "Open": "open",
            "??": "high", "High": "high",
            "??": "low", "Low": "low",
            "??": "close", "Close": "close",
            "???": "volume", "Volume": "volume",
        }
        normalized = df.rename(columns={key: value for key, value in rename_map.items() if key in df.columns})
        required = ["trade_date", "open", "high", "low", "close", "volume"]
        if not all(column in normalized.columns for column in required) and len(normalized.columns) >= 6:
            normalized = normalized.rename(columns={normalized.columns[i]: required[i] for i in range(6)})
        return normalized

    async def create_snapshot(self, market: str, symbol: str) -> Dict[str, Any]:
        """
        Fetches market data and saves it to the Parquet lake.
        Uses the DataRouter for robust multi-source fallback.
        """
        import time
        t0 = time.time()
        logger.info("Creating snapshot for %s stock: %s", market, symbol)
        try:
            from .data_providers import data_router

            async def _fetch_history():
                """Use DataRouter for history (AStockDirect → Tencent → Fallback)."""
                df = await data_router.get_history(symbol, period="2y", interval="1d")
                if df is not None and not df.empty:
                    df = df.rename(columns={'date': 'trade_date'})
                    trade_dates = pd.to_datetime(df['trade_date'], errors='coerce')
                    df['trade_date'] = trade_dates.dt.strftime('%Y-%m-%d')
                    df = df.dropna(subset=['trade_date'])
                return df

            async def _fetch_financials():
                """Get financial summary. For A-Share, call AStockDirectProvider
                directly to guarantee comprehensive A-Share-specific fields
                (扣非净利润, 资本支出, 净现金, 机构持仓, β, ROIC, WACC等).
                The router's concurrent-fallback strategy calls yfinance in
                parallel and will return its result if AStockDirectProvider
                times out (>30s of serial HTTP calls: THS, EastMoney, Sina
                ×5 statements, Tencent kline for beta, ownership, etc.).
                yfinance lacks these fields → report renders N/A.  Direct call
                avoids the race entirely."""
                if market == "A-Share":
                    try:
                        provider = data_router._a_stock_primary
                        summary = await provider.get_financial_summary(symbol)
                        if summary and "error" not in summary:
                            return summary
                        logger.warning("AStockDirectProvider returned error/empty for %s, falling back to router", symbol)
                    except Exception as e:
                        logger.warning("AStockDirectProvider financial summary failed for %s: %s; falling back to router", symbol, e)
                return await data_router.get_financial_summary(symbol)

            async def _fetch_valuation():
                """Extract valuation-relevant fields from the financial summary
                (which is already fetched above for A-Share, or via router for
                non-A-Share).  Avoids a duplicate router call."""
                if market != "A-Share":
                    return {}
                # For A-Share, derive from financials (already fetched or about to be)
                # NB: _fetch_financials() runs before _fetch_valuation() for A-Share.
                return {}

            async def _fetch_quotes():
                """Get real-time quote from DataRouter (Tencent API)."""
                quote = await data_router.get_quote(symbol)
                return quote.to_dict() if quote else {}

            # --- Run fetches — API calls sequentially to avoid connection conflicts ---
            history_result = await _fetch_history()
            
            df = history_result
            if df is None:
                df = pd.DataFrame()

            if df.empty:
                logger.warning("Snapshot: no history data for %s, continuing with empty history", symbol)
            else:
                # Data quality validation before storing
                try:
                    from .data_quality import data_quality_pipeline
                    quality_report = data_quality_pipeline.validate(df, symbol)
                    logger.info("[DataQuality] %s: score=%.2f, passed=%s", symbol, quality_report.score, quality_report.overall_passed)
                    if not quality_report.overall_passed:
                        critical_checks = [c for c in quality_report.checks if not c.passed and c.severity == "critical"]
                        for c in critical_checks:
                            logger.warning("[DataQuality] CRITICAL: %s", c)
                except Exception as e:
                    logger.warning("[DataQuality] Validation failed for %s: %s", symbol, e)

            # Run secondary fetches (use connection pool, not concurrent).
            # For A-Share: fetch financials FIRST (direct AStockDirectProvider
            # call, guaranteed comprehensive) then derive valuation from it.
            # For non-A-Share: valuation first (router), then financials (router).
            if market == "A-Share":
                financials = await _fetch_financials()
                # Derive valuation from the already-fetched financials
                if financials and isinstance(financials, dict) and "error" not in financials:
                    valuation = {
                        "pe": financials.get("pe"),
                        "pb": financials.get("pb"),
                        "market_cap": financials.get("marketCap"),
                        "industry": financials.get("industry"),
                        "total_shares": financials.get("totalShares"),
                        "float_shares": financials.get("floatShares"),
                    }
                else:
                    valuation = {}
            else:
                valuation = await _fetch_valuation()
                financials = await _fetch_financials()

            # Attach per-field financial data quality (flags missing/thin fields for LLM transparency)
            if financials and isinstance(financials, dict) and "error" not in financials:
                from .data_providers.base import score_financial_quality
                _qf_fields = [
                    "marketCap", "pe", "pb", "roe", "revenue",
                    "netProfit", "revenueYoY", "netProfitYoY",
                ]
                financials["data_quality"] = {
                    "score": score_financial_quality(financials),
                    "total_fields": len(_qf_fields),
                    "available_fields": sum(1 for k in _qf_fields if financials.get(k) is not None),
                    "per_field": {k: financials.get(k) is not None for k in _qf_fields},
                }

            quote = await _fetch_quotes()

            rows = df.tail(120).to_dict(orient="records") if not df.empty else []
            data_cutoff = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            vendor = "a-stock-direct" if market == "A-Share" else "yfinance"
            
            ohlc_observation = None
            if rows:
                ohlc_observation = self.store.write_ohlc(
                    "ohlc",
                    market,
                    symbol,
                    rows,
                    vendor=vendor,
                    observed_at=data_cutoff,
                    ingested_at=data_cutoff,
                    published_at=data_cutoff,
                    effective_from=data_cutoff,
                )

            # A+H cross-listing check (depends on quote name, so runs after)
            cross_listing = None
            if market == "A-Share":
                cross_listing = await self._get_ah_cross_listing(quote.get("name", ""), symbol)

            # Northbound flow (北向资金): per-stock holdings, daily change, 5-day net inflow.
            # Best-effort; failure is non-fatal.
            northbound = None
            if market == "A-Share":
                try:
                    from .sentiment_data_service import SentimentDataService
                    nb_result = await SentimentDataService().get_northbound_flow(symbol, days=5)
                    if nb_result and "error" not in nb_result:
                        latest = nb_result.get("latest") or {}
                        northbound = {
                            "latest_hold_pct": latest.get("pct_of_float"),
                            "daily_change_shares": latest.get("daily_change_shares"),
                            "daily_change_value": latest.get("daily_change_value"),
                            "five_day_net_inflow": nb_result.get("five_day_net_inflow"),
                            "five_day_trend": nb_result.get("five_day_trend"),
                            "as_of": latest.get("date"),
                        }
                except Exception as e:
                    logger.warning("Northbound flow fetch failed for %s: %s", symbol, e)

            # Industry peer comparison (可比公司/Comps): best-effort for A-Share.
            # Fetches real peer companies with PE/PB/ROE/net margin/market cap
            # using EastMoney datacenter. Failure is non-fatal.
            peer_comparison = None
            if market == "A-Share":
                industry_cn = None
                # Direct EastMoney lookup for Chinese industry name (f127).
                # The valuation/financials dict may carry an English yfinance
                # industry when the AStockDirectProvider times out; RPT_VALUEANALYSIS_DET
                # requires the Chinese name, so we query it directly.
                try:
                    import requests as _requests
                    _clean = symbol.strip()
                    _mk = 1 if _clean.startswith("6") else 0
                    _url = "https://push2delay.eastmoney.com/api/qt/stock/get"
                    _params = {
                        "fltt": "2", "invt": "2",
                        "fields": "f127",
                        "secid": f"{_mk}.{_clean}",
                    }
                    loop = asyncio.get_event_loop()
                    def _do():
                        r = _requests.get(
                            _url, params=_params,
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=5,
                        )
                        return r.json()
                    _info = await loop.run_in_executor(None, _do)
                    _d = _info.get("data") if isinstance(_info, dict) else None
                    industry_cn = _d.get("f127", "").strip() if isinstance(_d, dict) else ""
                except Exception:
                    pass
                # Fallback: use the valuation/financials industry (might be English)
                if not industry_cn:
                    industry_cn = (
                        valuation.get("industry") if isinstance(valuation, dict) else ""
                    ) or ""
                if industry_cn:
                    try:
                        from .data_providers.a_stock_direct import fetch_industry_peers
                        peers = await fetch_industry_peers(
                            industry_name=industry_cn.strip(),
                            top_n=10,
                            exclude_symbol=symbol,
                        )
                        if peers:
                            peer_comparison = peers
                    except Exception as e:
                        logger.warning("Industry peer comparison fetch failed for %s (industry=%s): %s",
                                       symbol, industry_cn, e)

            # Baijiu wholesale price (飞天茅台批价): best-effort only via akshare.
            # Do NOT fabricate — if the API is unavailable, leave it None.
            baijiu_price = None
            if market == "A-Share" and "600519" in symbol:
                baijiu_price = await self._fetch_baijiu_price(symbol)

            elapsed = time.time() - t0
            logger.info("Snapshot created for %s in %.1fs", symbol, elapsed)
            
            # Compute Quant Ensemble indicators
            quant_ensemble = self._compute_quant_ensemble(df)

            return {
                "snapshot_id": f"snap_{uuid.uuid4().hex[:12]}",
                "as_of_date": data_cutoff,
                "data_cutoff": data_cutoff,
                "name": quote.get("name", symbol),
                "price": quote.get("price"),
                "changePercent": quote.get("changePercent"),
                "currency": quote.get("currency"),
                "history": rows,
                "quantEnsemble": quant_ensemble,
                "valuation": valuation,
                "financials": financials,
                "quote": quote,
                "crossListing": cross_listing,
                "source_observations": [ohlc_observation] if ohlc_observation else [],
                "data_quality": self._score_snapshot_quality(rows, quote, financials),
                "northbound": northbound,
                "baijiu_price": baijiu_price,
                "peer_comparison": peer_comparison,
            }
        except Exception as e:
            logger.error("Snapshot creation failed for %s: %s", symbol, e)
            return {}

    async def _get_ah_cross_listing(self, stock_name: str, symbol: str) -> dict | None:
        """Check if an A-share stock has a corresponding H-share listing."""
        
    def _score_snapshot_quality(self, rows: List[Dict[str, Any]], quote: Dict[str, Any], financials: Dict[str, Any]) -> Dict[str, Any]:
        score = 0.55
        warnings = []
        if len(rows) >= 60:
            score += 0.20
        else:
            warnings.append({"code": "SHORT_HISTORY", "severity": "medium", "message": "Less than 60 OHLC rows available."})
        if quote.get("price") is not None:
            score += 0.15
        else:
            warnings.append({"code": "MISSING_PRICE", "severity": "high", "message": "Latest quote price is missing."})
        if financials:
            score += 0.10
        else:
            warnings.append({"code": "MISSING_FINANCIALS", "severity": "low", "message": "Financial summary is missing."})
        return {
            "score": round(min(score, 1.0), 2),
            "blocking_errors": [],
            "warnings": warnings,
            "field_coverage": {
                "ohlc": 1.0 if rows else 0.0,
                "quote": 1.0 if quote.get("price") is not None else 0.0,
                "financials": 1.0 if financials else 0.0,
            },
        }

    @staticmethod
    def _compute_quant_ensemble(df: pd.DataFrame) -> dict:
        if df is None or df.empty or len(df) < 30:
            return {}
        
        try:
            close = df['close'].astype(float)
            high = df['high'].astype(float)
            low = df['low'].astype(float)
            
            # 1. Z-score (20-day mean reversion)
            mean_20 = close.rolling(20).mean()
            std_20 = close.rolling(20).std()
            z_score = (close.iloc[-1] - mean_20.iloc[-1]) / std_20.iloc[-1] if std_20.iloc[-1] != 0 else 0
            
            # 2. RSI (14-day)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs.iloc[-1])) if loss.iloc[-1] != 0 else 50
            
            # 3. Momentum (20-day)
            momentum = ((close.iloc[-1] / close.iloc[-20]) - 1) * 100
            
            # 4. Volatility (Annualized 20-day)
            daily_return = close.pct_change()
            volatility = daily_return.rolling(20).std().iloc[-1] * np.sqrt(252) * 100
            
            # 5. ADX (14-day)
            up_move = high.diff()
            down_move = -low.diff()
            
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
            
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            atr = tr.rolling(14).mean()
            plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / atr)
            minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / atr)
            
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1)
            adx = dx.rolling(14).mean().iloc[-1]
            
            # 6. Hurst Exponent (simplified)
            lags = np.arange(2, min(20, len(close) // 2))
            tau_values = []
            for lag in lags:
                lagged_diff = np.subtract(close.values[lag:], close.values[:-lag])
                std = np.std(lagged_diff)
                tau_values.append(np.sqrt(std) if np.isfinite(std) and std > 0 else np.nan)
            tau = np.array(tau_values, dtype=float)
            valid = np.isfinite(tau) & (tau > 0)
            if valid.sum() >= 2:
                poly = np.polyfit(np.log(lags[valid]), np.log(tau[valid]), 1)
                hurst = poly[0] * 2.0
            else:
                hurst = 0.5
            
            return {
                "trendScore": int(min(max(adx if not pd.isna(adx) else 50, 0), 100)),
                "momentumScore": int(min(max(50 + momentum*2, 0), 100)),
                "meanReversionSignal": "oversold" if z_score < -2 else "overbought" if z_score > 2 else "neutral",
                "indicators": {
                    "ADX": round(float(adx), 2) if not pd.isna(adx) else 50.0,
                    "Z_score": round(float(z_score), 2) if not pd.isna(z_score) else 0.0,
                    "RSI": round(float(rsi), 2) if not pd.isna(rsi) else 50.0,
                    "Hurst": round(float(hurst), 2) if not pd.isna(hurst) else 0.5,
                    "Volatility_pct": round(float(volatility), 2) if not pd.isna(volatility) else 0.0
                }
            }
        except Exception as e:
            logger.exception("Quant calc error: %s", e)
            return {}

    @staticmethod
    async def _fetch_baijiu_price(symbol: str) -> dict | None:
        """Best-effort fetch of 飞天茅台 wholesale price via akshare liquor endpoint.
        Returns {price, unit, as_of} or None on any failure.
        Only relevant for 白酒 (baijiu) stocks like 600519 贵州茅台."""
        try:
            import akshare as ak
            df = await asyncio.to_thread(
                lambda: ak.liquor_price(category="飞天茅台")
            )
            if df is not None and not df.empty:
                row = df.iloc[0].to_dict() if hasattr(df, "iloc") else {}
                price = row.get("价格") or row.get("price") or row.get("最新价")
                unit = row.get("单位") or "元/瓶"
                as_of = str(row.get("日期") or row.get("date") or "")
                if price is not None:
                    return {"price": float(price), "unit": unit, "as_of": as_of}
        except Exception as e:
            logger.warning("Baijiu price fetch failed for %s: %s", symbol, e)
        return None

# Singleton instance
from ..lake.parquet_store import ParquetMarketStore
parquet_store = ParquetMarketStore()
market_snapshot_service = MarketSnapshotService(parquet_store)
