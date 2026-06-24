"""
Idea Screening Engine — Multi-factor stock screening inspired by Anthropic FSI idea-generation.
Supports Value, Growth, Quality, Short, and Thematic screens.
"""
import asyncio
from typing import List, Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)


SCREEN_PRESETS = {
    "value": {
        "label": "Deep Value",
        "description": "Low PE/PB, high FCF yield, dividend paying",
        "criteria": {"pe_max": 15, "pb_max": 2.0, "fcf_yield_min": 5.0, "dividend_yield_min": 2.0}
    },
    "growth": {
        "label": "High Growth",
        "description": "Revenue growth >15%, expanding margins, accelerating earnings",
        "criteria": {"revenue_growth_min": 15, "earnings_growth_min": 20, "margin_expanding": True}
    },
    "quality": {
        "label": "Quality Compounder",
        "description": "Consistent growth, high ROE, low debt, strong cash conversion",
        "criteria": {"roe_min": 15, "debt_equity_max": 1.0, "fcf_positive_years": 3}
    },
    "short": {
        "label": "Short Candidate",
        "description": "Declining revenue, margin compression, high debt, insider selling",
        "criteria": {"revenue_growth_max": -5, "margin_declining": True, "debt_equity_min": 2.0}
    },
    "momentum": {
        "label": "Momentum Leaders",
        "description": "Strong price momentum, relative strength, volume confirmation",
        "criteria": {"rs_rank_min": 80, "above_200ma": True, "volume_trend": "increasing"}
    }
}


async def run_screen(
    screen_type: str,
    market: str = "US",
    sector: Optional[str] = None,
    custom_criteria: Optional[Dict[str, Any]] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Execute a stock screen based on preset or custom criteria.
    Returns ranked list of candidates with key metrics.
    """
    preset = SCREEN_PRESETS.get(screen_type)
    if not preset and not custom_criteria:
        return {"error": f"Unknown screen type: {screen_type}. Available: {list(SCREEN_PRESETS.keys())}"}

    criteria = custom_criteria or preset["criteria"]

    if market == "A-Share":
        results = await _screen_ashare(screen_type, criteria, sector, limit)
    else:
        results = await _screen_us(screen_type, criteria, sector, limit)

    return {
        "screen_type": screen_type,
        "preset": preset,
        "market": market,
        "sector": sector,
        "criteria": criteria,
        "results": results,
        "count": len(results)
    }


async def _screen_us(screen_type: str, criteria: Dict, sector: Optional[str], limit: int) -> List[Dict]:
    """Screen US stocks asynchronously using yfinance."""
    try:
        tickers_list = _get_sp500_tickers()
        # Expanded coverage: Full S&P 500 (removed arbitrary [:100] slice constraint)
        if screen_type == "momentum":
            return await _filter_by_momentum_async(tickers_list, criteria, limit)
        else:
            return await _filter_tickers_by_criteria_async(tickers_list, criteria, limit)
    except Exception as e:
        logger.error(f"US screening error: {e}")
        return []

def _fetch_batch_info(batch: List[str]) -> List[Tuple[str, Dict]]:
    import yfinance as yf
    res = []
    try:
        tickers_obj = yf.Tickers(" ".join(batch))
        for sym in batch:
            try:
                res.append((sym, tickers_obj.tickers[sym].info))
            except Exception:
                pass
    except Exception:
        pass
    return res

async def _filter_tickers_by_criteria_async(tickers: List[str], criteria: Dict, limit: int) -> List[Dict]:
    """Filter tickers by fundamental criteria asynchronously."""
    results = []
    batch_size = 20
    batches = [tickers[i:i+batch_size] for i in range(0, len(tickers), batch_size)]
    chunk_size = 5 # 5 batches concurrently = 100 tickers per wave
    
    for i in range(0, len(batches), chunk_size):
        if len(results) >= limit:
            break
        current_batches = batches[i:i+chunk_size]
        import asyncio
        tasks = [asyncio.to_thread(_fetch_batch_info, b) for b in current_batches]
        batch_results = await asyncio.gather(*tasks)
        for b_res in batch_results:
            for sym, info in b_res:
                if len(results) >= limit:
                    break
                if _matches_criteria(info, criteria):
                    results.append(_extract_screen_metrics(sym, info))
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:limit]

def _fetch_batch_momentum(batch: List[str]) -> List[Dict]:
    import yfinance as yf
    res = []
    try:
        data = yf.download(batch, period="1y", progress=False)
        if data.empty:
            return res
        for symbol in batch:
            try:
                if len(batch) == 1:
                    close = data['Close'].dropna()
                else:
                    close = data['Close'][symbol].dropna()
                if len(close) < 200:
                    continue
                current = close.iloc[-1]
                ma200 = close.rolling(200).mean().iloc[-1]
                ma50 = close.rolling(50).mean().iloc[-1]
                pct_6m = (current / close.iloc[-126] - 1) * 100

                if current > ma200 and current > ma50 and pct_6m > 10:
                    res.append({
                        "symbol": symbol,
                        "price": round(float(current), 2),
                        "pct_above_200ma": round(float((current/ma200 - 1) * 100), 1),
                        "6m_return": round(float(pct_6m), 1),
                        "ma50_above_ma200": bool(ma50 > ma200),
                        "score": round(float(pct_6m + (current/ma200 - 1) * 50), 1)
                    })
            except Exception:
                continue
    except Exception:
        pass
    return res

async def _filter_by_momentum_async(tickers: List[str], criteria: Dict, limit: int) -> List[Dict]:
    """Filter by price momentum asynchronously."""
    results = []
    batch_size = 20
    batches = [tickers[i:i+batch_size] for i in range(0, len(tickers), batch_size)]
    chunk_size = 5
    
    for i in range(0, len(batches), chunk_size):
        if len(results) >= limit:
            break
        current_batches = batches[i:i+chunk_size]
        import asyncio
        tasks = [asyncio.to_thread(_fetch_batch_momentum, b) for b in current_batches]
        batch_results = await asyncio.gather(*tasks)
        for b_res in batch_results:
            results.extend(b_res)
            
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:limit]


def _matches_criteria(info: Dict, criteria: Dict) -> bool:
    """Check if a stock matches the given screening criteria."""
    try:
        pe = info.get("trailingPE") or info.get("forwardPE")
        pb = info.get("priceToBook")
        roe = (info.get("returnOnEquity") or 0) * 100
        debt_equity = info.get("debtToEquity", 0) / 100 if info.get("debtToEquity") else None
        revenue_growth = (info.get("revenueGrowth") or 0) * 100
        earnings_growth = (info.get("earningsGrowth") or 0) * 100
        dividend_yield = (info.get("dividendYield") or 0) * 100
        fcf = info.get("freeCashflow", 0)
        market_cap = info.get("marketCap", 0)

        # Apply each criterion
        if "pe_max" in criteria and (pe is None or pe > criteria["pe_max"] or pe < 0):
            return False
        if "pb_max" in criteria and (pb is None or pb > criteria["pb_max"] or pb < 0):
            return False
        if "fcf_yield_min" in criteria:
            fcf_yield = (fcf / market_cap * 100) if market_cap > 0 and fcf else 0
            if fcf_yield < criteria["fcf_yield_min"]:
                return False
        if "dividend_yield_min" in criteria and dividend_yield < criteria["dividend_yield_min"]:
            return False
        if "revenue_growth_min" in criteria and revenue_growth < criteria["revenue_growth_min"]:
            return False
        if "earnings_growth_min" in criteria and earnings_growth < criteria["earnings_growth_min"]:
            return False
        if "roe_min" in criteria and roe < criteria["roe_min"]:
            return False
        if "debt_equity_max" in criteria and debt_equity is not None and debt_equity > criteria["debt_equity_max"]:
            return False
        if "revenue_growth_max" in criteria and revenue_growth > criteria["revenue_growth_max"]:
            return False
        if "debt_equity_min" in criteria and (debt_equity is None or debt_equity < criteria["debt_equity_min"]):
            return False

        return True
    except Exception:
        return False


def _extract_screen_metrics(symbol: str, info: Dict) -> Dict:
    """Extract key metrics for screen results."""
    pe = info.get("trailingPE") or info.get("forwardPE")
    pb = info.get("priceToBook")
    roe = (info.get("returnOnEquity") or 0) * 100
    revenue_growth = (info.get("revenueGrowth") or 0) * 100
    earnings_growth = (info.get("earningsGrowth") or 0) * 100
    market_cap = info.get("marketCap", 0)
    fcf = info.get("freeCashflow", 0)
    fcf_yield = (fcf / market_cap * 100) if market_cap > 0 and fcf else 0

    # Composite score based on quality + value + growth (Addressing Audit S3)
    # Using a simple pseudo-z-score approach relative to typical market averages
    # Note: Full industry neutralization requires cross-sectional data, here we do basic standardization
    score = 50  # Base score
    
    # Value factor (PE)
    if pe and pe > 0:
        if pe < 15:
            score += 15
        elif pe < 25:
            score += 5
        elif pe > 40:
            score -= 10
            
    # Quality factor (ROE & FCF Yield)
    if roe > 15:
        score += 10
    elif roe < 5:
        score -= 5
        
    if fcf_yield > 5:
        score += 10
    elif fcf_yield < 0:
        score -= 10
        
    # Growth factor (Revenue & Earnings Growth)
    if earnings_growth > 20:
        score += 10
    elif earnings_growth < 0:
        score -= 5
        
    if revenue_growth > 15:
        score += 5
    elif revenue_growth < 0:
        score -= 5
        
    # Cap score between 0 and 100
    score = max(0, min(100, score))

    return {
        "symbol": symbol,
        "name": info.get("shortName", symbol),
        "sector": info.get("sector", ""),
        "market_cap_b": round(market_cap / 1e9, 1) if market_cap else None,
        "pe": round(pe, 1) if pe else None,
        "pb": round(pb, 2) if pb else None,
        "roe_pct": round(roe, 1),
        "revenue_growth_pct": round(revenue_growth, 1),
        "earnings_growth_pct": round(earnings_growth, 1),
        "fcf_yield_pct": round(fcf_yield, 1),
        "dividend_yield_pct": round((info.get("dividendYield") or 0) * 100, 2),
        "debt_equity": round((info.get("debtToEquity") or 0) / 100, 2),
        "score": round(score, 1)
    }


async def _screen_ashare(screen_type: str, criteria: Dict, sector: Optional[str], limit: int) -> List[Dict]:
    """Screen A-Share stocks using AkShare."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _screen_ashare_sync, screen_type, criteria, sector, limit)


def _screen_ashare_sync(screen_type: str, criteria: Dict, sector: Optional[str], limit: int) -> List[Dict]:
    """Synchronous A-Share screening via AkShare & yfinance."""
    try:
        import akshare as ak
        import pandas as pd

        # Get real-time A-share market data
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return []

        # Map columns
        col_map = {
            "代码": "symbol",
            "名称": "name",
            "最新价": "price",
            "市盈率-动态": "pe",
            "市净率": "pb",
            "涨跌幅": "change_pct",
            "总市值": "market_cap",
            "换手率": "turnover",
            "量比": "volume_ratio"
        }

        # Filter available columns
        available_cols = {k: v for k, v in col_map.items() if k in df.columns}
        df = df[list(available_cols.keys())].rename(columns=available_cols)

        # Convert to numeric
        for col in ["price", "pe", "pb", "change_pct", "market_cap", "turnover"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Apply screen-type specific rough filters
        # These pre-filter before the deep yfinance criteria check
        if screen_type == "value":
            df = df[(df["pe"] > 0) & (df["pe"] < 35)]
            df = df[(df["pb"] > 0) & (df["pb"] < 3.5)]
        elif screen_type == "growth":
            # Growth stocks: moderate PE (high PE = overvalued, not growth)
            # Also require positive PE (profitable) and market_cap > 5B (established)
            df = df[(df["pe"] > 0) & (df["pe"] < 50)]
            if "market_cap" in df.columns:
                df = df[df["market_cap"] > 5e9]  # >50亿市值
        elif screen_type == "quality":
            df = df[(df["pe"] > 0) & (df["pe"] < 60)]
            if "market_cap" in df.columns:
                df = df[df["market_cap"] > 5e9]
        elif screen_type == "short":
            df = df[(df["pe"] < 0) | (df["pe"] > 80)]
        elif screen_type == "momentum":
            df = df[df["change_pct"] > 0]

        # Sort by market cap descending (prefer larger companies)
        if "market_cap" in df.columns:
            df = df.sort_values("market_cap", ascending=False)

        candidates = df.head(40)
        if candidates.empty:
            return []

        # Map A-share symbols to yfinance format
        yf_tickers = []
        symbol_to_name = {}
        for _, row in candidates.iterrows():
            code = str(row["symbol"]).strip()
            if len(code) < 6:
                code = code.zfill(6)
            yf_sym = f"{code}.SS" if code.startswith(("6", "900")) else f"{code}.SZ"
            yf_tickers.append(yf_sym)
            symbol_to_name[yf_sym] = row["name"]

        # Run deep yfinance criteria screening
        import asyncio
        if screen_type == "momentum":
            results = asyncio.run(_filter_by_momentum_async(yf_tickers, criteria, limit))
        else:
            results = asyncio.run(_filter_tickers_by_criteria_async(yf_tickers, criteria, limit))

        # Restore original A-share name for output
        for r in results:
            yf_sym = r["symbol"]
            if yf_sym in symbol_to_name:
                r["name"] = symbol_to_name[yf_sym]

        return results
    except Exception as e:
        logger.error(f"A-Share screening error: {e}")
        return []


# Singleton-style access
screening_service = type('ScreeningService', (), {'run_screen': staticmethod(run_screen), 'PRESETS': SCREEN_PRESETS})()
