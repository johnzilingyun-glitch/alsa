"""
Base classes and unified data schema for all data providers.
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)


class MarketType(Enum):
    A_SHARE = "A-Share"
    HK_SHARE = "HK-Share"
    US_SHARE = "US-Share"
    UNKNOWN = "Unknown"


@dataclass
class QuoteData:
    """Unified quote structure returned by all providers."""
    symbol: str
    name: str
    price: float
    open: float
    high: float
    low: float
    last_close: float
    change: float
    change_pct: float
    volume: float
    amount: float
    market_cap: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    turnover_pct: Optional[float] = None
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with camelCase keys expected by downstream consumers."""
        raw = {k: v for k, v in self.__dict__.items() if v is not None}
        # Map snake_case field names to camelCase used by report/snapshot services
        key_map = {
            "change_pct": "changePercent",
            "last_close": "previousClose",
            "market_cap": "marketCap",
            "pe_ttm": "trailingPE",
            "turnover_pct": "turnoverRate",
        }
        return {key_map.get(k, k): v for k, v in raw.items()}


@dataclass
class DataQuality:
    """Quality assessment for financial/market data (score in [0, 1]).

    Supports numeric comparison so it can be used where a raw float was previously
    expected (e.g. quality thresholds in DataRouter).
    """
    score: float = 0.0
    total_fields: int = 0
    available_fields: int = 0

    def __lt__(self, other):
        if isinstance(other, DataQuality):
            return self.score < other.score
        return self.score < other

    def __le__(self, other):
        if isinstance(other, DataQuality):
            return self.score <= other.score
        return self.score <= other

    def __gt__(self, other):
        if isinstance(other, DataQuality):
            return self.score > other.score
        return self.score > other

    def __ge__(self, other):
        if isinstance(other, DataQuality):
            return self.score >= other.score
        return self.score >= other

    def __eq__(self, other):
        if isinstance(other, DataQuality):
            return self.score == other.score
        if isinstance(other, (int, float)):
            return self.score == other
        return NotImplemented

    def __hash__(self):
        return hash(self.score)

    def __float__(self):
        return self.score


@dataclass
class FinancialData:
    """Structured financial data with quarterly history and quality metadata."""
    quarterly_history: list[dict[str, Any]] = field(default_factory=list)
    data_quality: Optional["DataQuality"] = None


# Standard OHLCV column names for historical data
OHLCV_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize any OHLCV DataFrame to standard column names.
    Handles common variations (Date/date/日期, Open/open/开盘, etc.)
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    # Column mapping: various names → standard
    col_map = {}
    for col in df.columns:
        cl = str(col).lower().strip()
        if cl in ("date", "datetime", "日期", "trade_date", "time"):
            col_map[col] = "date"
        elif cl in ("open", "开盘", "开盘价", "today_open"):
            col_map[col] = "open"
        elif cl in ("high", "最高", "最高价"):
            col_map[col] = "high"
        elif cl in ("low", "最低", "最低价"):
            col_map[col] = "low"
        elif cl in ("close", "收盘", "收盘价", "adj close"):
            col_map[col] = "close"
        elif cl in ("volume", "vol", "成交量"):
            col_map[col] = "volume"
        elif cl in ("amount", "成交额"):
            col_map[col] = "amount"

    df = df.rename(columns=col_map)

    # Ensure required columns exist
    for col in OHLCV_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Convert date column to string if datetime
    if "date" in df.columns and df["date"].dtype != object:
        try:
            # Preserve time if it exists and is not midnight, otherwise just date
            df["date"] = pd.to_datetime(df["date"]).apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if x.hour > 0 or x.minute > 0 else x.strftime("%Y-%m-%d")
            )
        except Exception:
            df["date"] = df["date"].astype(str)

    # Select and order standard columns (plus extras if present)
    extra_cols = [c for c in df.columns if c not in OHLCV_COLUMNS and c != "amount"]
    result_cols = OHLCV_COLUMNS + (["amount"] if "amount" in df.columns else []) + extra_cols
    result_cols = [c for c in result_cols if c in df.columns]

    return df[result_cols].reset_index(drop=True)


def detect_market(symbol: str) -> MarketType:
    """
    Detect market type from ticker format.

    Rules:
      - 6-digit numeric, or suffixed .SH/.SZ/.SS → A-Share
      - Suffixed .HK, or 4-5 digit numeric → HK-Share
      - Alpha only (2-5 chars), or ^prefix (indices) → US-Share

    Frontend/gateway composite IDs (e.g. "KLAC.US-Share", "01888.HK-Share")
    are normalized by stripping the market suffix before detection.
    """
    s = symbol.strip().upper()

    # Strip canonical market suffixes appended by the frontend/gateway.
    for msfx in (".A-SHARE", ".HK-SHARE", ".US-SHARE"):
        if s.endswith(msfx):
            s = s[: -len(msfx)]
            break

    # Explicit suffix detection
    if s.endswith((".SH", ".SS", ".SZ")):
        return MarketType.A_SHARE
    if s.endswith(".HK"):
        return MarketType.HK_SHARE

    # Remove any known suffix for further checks
    clean = s.replace(".SH", "").replace(".SS", "").replace(".SZ", "").replace(".HK", "")

    # Pure 6-digit numeric → A-Share
    if clean.isdigit() and len(clean) == 6:
        return MarketType.A_SHARE

    # 4-5 digit numeric → HK-Share
    if clean.isdigit() and len(clean) <= 5:
        return MarketType.HK_SHARE

    # Alpha / alphanumeric (AAPL, MSFT, ^GSPC) → US
    if clean.isalpha() or clean.startswith("^") or "=" in clean:
        return MarketType.US_SHARE

    return MarketType.UNKNOWN


class DataProvider(ABC):
    """Abstract base class for all data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        ...

    @abstractmethod
    async def get_history(
        self, symbol: str, period: str = "3mo", interval: str = "1d"
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data.
        Returns normalized DataFrame with columns: date, open, high, low, close, volume
        """
        ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> Optional[QuoteData]:
        """Fetch real-time quote for a single symbol."""
        ...

    @abstractmethod
    async def get_financial_summary(self, symbol: str) -> Dict[str, Any]:
        """Fetch comprehensive financial metrics (PE, PB, ROE, growth, etc.)"""
        ...


def score_quote_quality(quote: Any) -> float:
    """
    Quote quality score in [0, 1].
    Accepts either QuoteData dataclass or dict-like payload.
    """
    if quote is None:
        return 0.0

    def _get(obj: Any, key: str, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    checks = [
        (_get(quote, "price", 0) or 0) > 0,
        _get(quote, "name") not in (None, "", "-"),
        (_get(quote, "volume", 0) or 0) >= 0,
        _get(quote, "symbol") not in (None, "", "-"),
        _get(quote, "source") not in (None, "", "-"),
    ]
    return round(sum(1 for c in checks if c) / len(checks), 4)


def score_history_quality(df: pd.DataFrame) -> float:
    """
    History quality score in [0, 1] based on required fields and non-empty valid rows.
    """
    if df is None or df.empty:
        return 0.0

    required = ["date", "open", "high", "low", "close", "volume"]
    has_required = all(c in df.columns for c in required)
    if not has_required:
        return 0.0

    valid_close = pd.to_numeric(df["close"], errors="coerce") > 0
    valid_date = df["date"].notna() & (df["date"].astype(str) != "")
    valid_rows = (valid_close & valid_date).sum()
    coverage = float(valid_rows) / float(len(df)) if len(df) > 0 else 0.0

    checks = [
        has_required,
        coverage >= 0.6,
        valid_rows >= min(5, len(df)),
    ]
    return round(sum(1 for c in checks if c) / len(checks), 4)


def score_financial_quality(summary: Dict[str, Any]) -> DataQuality:
    """
    Financial summary quality in [0, 1] from key fields availability.
    Returns a DataQuality object with score, total_fields, and available_fields.
    """
    if not isinstance(summary, dict) or not summary or "error" in summary:
        return DataQuality(score=0.0, total_fields=0, available_fields=0)

    key_fields = [
        "marketCap", "pe", "pb", "roe", "revenue",
        "netProfit", "revenueYoY", "netProfitYoY",
    ]
    available = sum(1 for k in key_fields if summary.get(k) is not None)
    return DataQuality(
        score=round(available / len(key_fields), 4),
        total_fields=len(key_fields),
        available_fields=available,
    )
