"""Pydantic models for ALSA SDK requests and responses."""

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class AnalysisJob(BaseModel):
    job_id: str
    status: str  # queued, running, completed, failed
    symbol: Optional[str] = None
    market: Optional[str] = None
    progress: Optional[dict] = None
    analysis_id: Optional[str] = None
    result: Optional[Any] = None
    error_message: Optional[str] = None


class MarketQuote(BaseModel):
    symbol: str
    name: Optional[str] = None
    price: Optional[float] = None
    change: Optional[float] = None
    changePercent: Optional[float] = None
    volume: Optional[float] = None
    market: Optional[str] = None


class WatchlistItem(BaseModel):
    item_id: Optional[str] = None
    symbol: str
    name: Optional[str] = None
    market: str
    added_at: Optional[datetime] = None


class Alert(BaseModel):
    alert_id: Optional[str] = None
    symbol: str
    market: str
    entry_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    status: str = "active"
    created_at: Optional[datetime] = None


class AnalysisResult(BaseModel):
    analysis_id: str
    symbol: str
    market: str
    summary_verdict: Optional[str] = None
    score: Optional[float] = None
    risk_level: Optional[str] = None
    created_at: Optional[datetime] = None


class ApiKeyInfo(BaseModel):
    key_id: str
    name: str
    scopes: list[str] = []
    rate_limit_override: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool = True
