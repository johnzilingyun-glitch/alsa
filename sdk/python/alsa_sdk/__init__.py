"""ALSA Python SDK — Client for the ALSA Stock Analysis API."""

from .client import ALSAClient
from .models import (
    AnalysisJob,
    MarketQuote,
    WatchlistItem,
    Alert,
    AnalysisResult,
    ApiKeyInfo,
)

__version__ = "1.0.0"
__all__ = [
    "ALSAClient",
    "AnalysisJob",
    "MarketQuote",
    "WatchlistItem",
    "Alert",
    "AnalysisResult",
    "ApiKeyInfo",
]
