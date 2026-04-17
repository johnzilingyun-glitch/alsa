from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime

class WatchlistItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    name: Optional[str] = None
    market: str = Field(index=True)
    added_at: datetime = Field(default_factory=datetime.utcnow)

class DecisionEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    analysis_id: Optional[str] = Field(default=None, index=True)
    symbol: str = Field(index=True)
    name: Optional[str] = None
    market: str
    action: str  # 'buy', 'sell', 'hold'
    reasoning: Optional[str] = None
    price_at_decision: float
    confidence: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AnalysisJob(SQLModel, table=True):
    job_id: str = Field(primary_key=True)
    symbol: str
    market: str
    status: str  # 'queued', 'running', 'completed', 'failed'
    created_at: datetime = Field(default_factory=datetime.utcnow)
    snapshot_path: Optional[str] = None
    result_payload: Optional[str] = None  # JSON string
