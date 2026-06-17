"""
Idea Screening Engine — Multi-factor stock screening inspired by Anthropic FSI idea-generation.
Supports Value, Growth, Quality, Short, and Thematic screens.
"""
import asyncio
from typing import List, Dict, Any, Optional
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
    """Screen US stocks using yfinance."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _screen_us_sync, screen_type, criteria, sector, limit)


def _screen_us_sync(screen_type: str, criteria: Dict, sector: Optional[str], limit: int) -> List[Dict]:
    """Synchronous US screening via yfinance screener."""
    try:
        import yfinance as yf

        # Use yfinance's built-in screeners where possible
        if screen_type == "value":
            # Screen S&P 500 for value characteristics
            tickers_list = _get_sp500_tickers()
            return _filter_tickers_by_criteria(tickers_list[:100], criteria, limit)
        elif screen_type == "growth":
            tickers_list = _get_sp500_tickers()
            return _filter_tickers_by_criteria(tickers_list[:100], criteria, limit)
        elif screen_type == "quality":
            tickers_list = _get_sp500_tickers()
            return _filter_tickers_by_criteria(tickers_list[:100], criteria, limit)
        elif screen_type == "momentum":
            tickers_list = _get_sp500_tickers()
            return _filter_by_momentum(tickers_list[:100], criteria, limit)
        else:
            tickers_list = _get_sp500_tickers()
            return _filter_tickers_by_criteria(tickers_list[:80], criteria, limit)
    except Exception as e:
        logger.error(f"US screening error: {e}")
        return []


def _get_sp500_tickers() -> List[str]:
    """Get S&P 500 ticker list."""
    try:
        import pandas as pd
        table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        return table[0]['Symbol'].tolist()
    except Exception:
        # Fallback: common large-cap tickers
        return [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B",
            "UNH", "JNJ", "V", "XOM", "JPM", "PG", "MA", "HD", "CVX", "MRK",
            "ABBV", "LLY", "PEP", "KO", "COST", "AVGO", "TMO", "WMT", "MCD",
            "CSCO", "ACN", "ABT", "DHR", "NEE", "LIN", "TXN", "PM", "UNP",
            "ADBE", "NKE", "CRM", "ORCL", "AMD", "INTC", "QCOM", "AMAT"
        ]


def _filter_tickers_by_criteria(tickers: List[str], criteria: Dict, limit: int) -> List[Dict]:
    """Filter tickers by fundamental criteria using yfinance."""
    import yfinance as yf
    results = []

    # Process in batches for efficiency
    batch_size = 10
    for i in range(0, len(tickers), batch_size):
        if len(results) >= limit:
            break
        batch = tickers[i:i+batch_size]
        try:
            tickers_obj = yf.Tickers(" ".join(batch))
            for symbol in batch:
                if len(results) >= limit:
                    break
                try:
                    info = tickers_obj.tickers[symbol].info
                    if _matches_criteria(info, criteria):
                        results.append(_extract_screen_metrics(symbol, info))
                except Exception:
                    continue
        except Exception:
            continue

    # Sort by relevance score
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:limit]


def _filter_by_momentum(tickers: List[str], criteria: Dict, limit: int) -> List[Dict]:
    """Filter by price momentum."""
    import yfinance as yf
    results = []

    batch_size = 10
    for i in range(0, len(tickers), batch_size):
        if len(results) >= limit:
            break
        batch = tickers[i:i+batch_size]
        try:
            data = yf.download(batch, period="1y", progress=False)
            if data.empty:
                continue
            for symbol in batch:
                if len(results) >= limit:
                    break
                try:
                    close = data['Close'][symbol].dropna()
                    if len(close) < 200:
                        continue
                    current = close.iloc[-1]
                    ma200 = close.rolling(200).mean().iloc[-1]
                    ma50 = close.rolling(50).mean().iloc[-1]
                    pct_6m = (current / close.iloc[-126] - 1) * 100

                    if current > ma200 and current > ma50 and pct_6m > 10:
                        results.append({
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
            continue

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

    # Composite score based on quality + value + growth
    score = 0
    if pe and 0 < pe < 50:
        score += max(0, 50 - pe)  # lower PE = higher score
    if roe > 10:
        score += roe * 0.5
    if revenue_growth > 0:
        score += revenue_growth * 0.3
    if fcf_yield > 0:
        score += fcf_yield * 2

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
    """Synchronous A-Share screening via AkShare."""
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

        # Apply screen-type specific filters
        if screen_type == "value":
            df = df[(df["pe"] > 0) & (df["pe"] < criteria.get("pe_max", 15))]
            df = df[(df["pb"] > 0) & (df["pb"] < criteria.get("pb_max", 2.0))]
        elif screen_type == "growth":
            # For A-shares, use multi-dimensional growth criteria
            df = df[
                (df["pe"] > 0) & (df["pe"] < 50) &
                (df.get("revenue_growth", 0) > 15) &
                (df.get("earnings_growth", 0) > 20)
            ]
        elif screen_type == "momentum":
            df = df[df["change_pct"] > 0]
            df = df.sort_values("change_pct", ascending=False)
        elif screen_type == "short":
            df = df[(df["pe"] < 0) | (df["pe"] > 100)]

        # Sort by market cap descending (prefer larger companies)
        if "market_cap" in df.columns:
            df = df.sort_values("market_cap", ascending=False)

        results = []
        for _, row in df.head(limit).iterrows():
            results.append({
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "price": round(float(row.get("price", 0)), 2) if pd.notna(row.get("price")) else None,
                "pe": round(float(row.get("pe", 0)), 1) if pd.notna(row.get("pe")) else None,
                "pb": round(float(row.get("pb", 0)), 2) if pd.notna(row.get("pb")) else None,
                "market_cap_b": round(float(row.get("market_cap", 0)) / 1e8, 1) if pd.notna(row.get("market_cap")) else None,
                "change_pct": round(float(row.get("change_pct", 0)), 2) if pd.notna(row.get("change_pct")) else None,
            })

        return results
    except Exception as e:
        logger.error(f"A-Share screening error: {e}")
        return []


# Singleton-style access
screening_service = type('ScreeningService', (), {'run_screen': staticmethod(run_screen), 'PRESETS': SCREEN_PRESETS})()
