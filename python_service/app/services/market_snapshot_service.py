from ..lake.parquet_store import ParquetMarketStore
from typing import List, Dict, Any
import asyncio
import os
import pandas as pd
import numpy as np
import uuid
from datetime import datetime, timezone

# Only import akshare if enabled (geo-blocked from non-China servers)
AKSHARE_ENABLED = os.getenv("AKSHARE_ENABLED", "false").lower() == "true"
if AKSHARE_ENABLED:
    import akshare as ak

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
        print(f"Creating snapshot for {market} stock: {symbol}")
        try:
            from .data_providers import data_router

            async def _fetch_history():
                """Use DataRouter for history (AStockDirect → Tencent → AkShare fallback)."""
                df = await data_router.get_history(symbol, period="6mo", interval="1d")
                if df is not None and not df.empty:
                    df = df.rename(columns={'date': 'trade_date'})
                    trade_dates = pd.to_datetime(df['trade_date'], errors='coerce')
                    df['trade_date'] = trade_dates.dt.strftime('%Y-%m-%d')
                    df = df.dropna(subset=['trade_date'])
                return df

            async def _fetch_valuation():
                """Get valuation from DataRouter's financial summary."""
                if market != "A-Share":
                    return {}
                try:
                    summary = await data_router.get_financial_summary(symbol)
                    if summary and "error" not in summary:
                        # Pull out valuation-relevant fields
                        return {
                            "pe": summary.get("pe"),
                            "pb": summary.get("pb"),
                            "market_cap": summary.get("marketCap"),
                            "industry": summary.get("industry"),
                            "total_shares": summary.get("totalShares"),
                            "float_shares": summary.get("floatShares"),
                        }
                except Exception as e:
                    print(f"Valuation fetch failed for {symbol}: {e}")
                return {}

            async def _fetch_financials():
                """Get financial summary from DataRouter."""
                return await data_router.get_financial_summary(symbol)

            async def _fetch_quotes():
                """Get real-time quote from DataRouter (Tencent API)."""
                quote = await data_router.get_quote(symbol)
                return quote.to_dict() if quote else {}

            # --- Run fetches — AkShare calls sequentially to avoid connection conflicts ---
            history_result = await _fetch_history()
            
            df = history_result
            if df is None or df.empty:
                print(f"Snapshot: no history data for {symbol}")
                return {}

            # Data quality validation before storing
            try:
                from .data_quality import data_quality_pipeline
                quality_report = data_quality_pipeline.validate(df, symbol)
                print(f"[DataQuality] {symbol}: score={quality_report.score:.2f}, passed={quality_report.overall_passed}")
                if not quality_report.overall_passed:
                    critical_checks = [c for c in quality_report.checks if not c.passed and c.severity == "critical"]
                    for c in critical_checks:
                        print(f"[DataQuality] CRITICAL: {c}")
            except Exception as e:
                print(f"[DataQuality] Validation failed for {symbol}: {e}")

            # Run secondary fetches (use AkShare's own connection pool, not concurrent)
            valuation = await _fetch_valuation()
            financials = await _fetch_financials()
            quote = await _fetch_quotes()

            rows = df.tail(120).to_dict(orient="records")
            data_cutoff = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            vendor = "akshare" if market == "A-Share" and AKSHARE_ENABLED else "yfinance"
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

            elapsed = time.time() - t0
            print(f"Snapshot created for {symbol} in {elapsed:.1f}s")
            
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
            }
        except Exception as e:
            print(f"Snapshot creation failed for {symbol}: {e}")
            return {}

    async def _get_ah_cross_listing(self, stock_name: str, symbol: str) -> dict | None:
        """Check if an A-share stock has a corresponding H-share listing."""
        if not AKSHARE_ENABLED:
            return None
        try:
            df = await asyncio.to_thread(ak.stock_zh_ah_name)
            if df is None or df.empty:
                return None
            # Match by name (strip "股份" suffix for fuzzy match)
            clean_name = stock_name.replace("股份", "").strip()
            match = df[df['名称'].str.contains(clean_name, na=False)]
            if match.empty and len(clean_name) >= 2:
                # Try shorter prefix match (first 2 chars)
                match = df[df['名称'].str.startswith(clean_name[:2], na=False)]
                # Filter further if multiple matches
                if len(match) > 1:
                    match = match[match['名称'].str.contains(clean_name[:3], na=False)] if len(clean_name) >= 3 else match.head(1)
            if not match.empty:
                hk_code = match.iloc[0]['代码']
                hk_name = match.iloc[0]['名称']
                return {
                    "market": "HK",
                    "symbol": f"{hk_code}.HK",
                    "name": hk_name,
                    "type": "A+H"
                }
            return None
        except Exception as e:
            print(f"A+H cross-listing check failed for {symbol}: {e}")
            return None

    @staticmethod
    def _score_snapshot_quality(rows: List[Dict[str, Any]], quote: Dict[str, Any], financials: Dict[str, Any]) -> Dict[str, Any]:
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
            lags = np.arange(2, 20)
            tau = np.array([np.sqrt(np.std(np.subtract(close.values[lag:], close.values[:-lag]))) for lag in lags], dtype=float)
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
            print("Quant calc error:", e)
            return {}

# Singleton instance
from ..lake.parquet_store import ParquetMarketStore
parquet_store = ParquetMarketStore()
market_snapshot_service = MarketSnapshotService(parquet_store)
