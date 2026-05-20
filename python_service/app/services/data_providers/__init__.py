"""
Data Providers — Market-aware data routing with unified schema.

Architecture:
  DataRouter → detects market from ticker → routes to optimal provider
  ├── AStockDirectProvider (Primary A-share: direct HTTP APIs)
  ├── AkShareFallbackProvider (Fallback A-share: akshare)
  └── YFinanceProvider (US/HK stocks)

Usage:
    from app.services.data_providers import data_router

    # Historical OHLCV
    df = await data_router.get_history("600519", period="3mo")
    df = await data_router.get_history("AAPL", period="1y")

    # Real-time quote
    quote = await data_router.get_quote("688017")

    # Financial summary (valuation + fundamentals)
    summary = await data_router.get_financial_summary("002532")

    # News search (Iwencai 同花顺问财)
    from app.services.data_providers.iwencai_news import search_news
    result = await search_news("人工智能最新动态")
"""

from .router import DataRouter, data_router
from .base import DataProvider, MarketType
from .iwencai_news import (
    search_news, search_announcements, search_reports,
    search_comprehensive, search_news_batch,
)

__all__ = [
    "DataRouter", "data_router", "DataProvider", "MarketType",
    "search_news", "search_announcements", "search_reports",
    "search_comprehensive", "search_news_batch",
]
