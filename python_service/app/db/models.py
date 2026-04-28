from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
import uuid

class User(SQLModel, table=True):
    user_id: str = Field(primary_key=True, default_factory=lambda: f"user_{uuid.uuid4().hex[:8]}")
    display_name: str
    role: str = "viewer"  # admin/researcher/viewer
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Watchlist(SQLModel, table=True):
    watchlist_id: str = Field(primary_key=True, default_factory=lambda: f"wl_{uuid.uuid4().hex[:8]}")
    user_id: str = Field(foreign_key="user.user_id")
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class WatchlistItem(SQLModel, table=True):
    item_id: str = Field(primary_key=True, default_factory=lambda: f"item_{uuid.uuid4().hex[:8]}")
    watchlist_id: str = Field(foreign_key="watchlist.watchlist_id")
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    name: Optional[str] = None
    tags: Optional[str] = None  # JSON string
    notes: Optional[str] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)

class AnalysisJob(SQLModel, table=True):
    job_id: str = Field(primary_key=True)
    user_id: str = Field(default="default_user")
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    analysis_level: str = "standard"  # quick/standard/deep
    status: str = "queued"  # queued/running/completed/failed/cancelled
    requested_model: Optional[str] = None
    resolved_model: Optional[str] = None
    prompt_version: Optional[str] = None
    snapshot_id: Optional[str] = None
    analysis_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result_payload: Optional[str] = None  # Legacy JSON string support

class AnalysisRun(SQLModel, table=True):
    analysis_id: str = Field(primary_key=True, default_factory=lambda: f"ana_{uuid.uuid4().hex[:8]}")
    job_id: str = Field(foreign_key="analysisjob.job_id")
    user_id: str = Field(default="default_user")
    symbol: str = Field(index=True)
    market: str = Field(index=True)
    snapshot_id: Optional[str] = None
    summary_verdict: str  # buy/hold/sell/watch
    score: float
    risk_level: str  # low/medium/high
    status: str = "completed"  # completed/archived/superseded
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AnalysisArtifact(SQLModel, table=True):
    artifact_id: str = Field(primary_key=True, default_factory=lambda: f"art_{uuid.uuid4().hex[:8]}")
    analysis_id: str = Field(foreign_key="analysisrun.analysis_id")
    artifact_type: str  # input_snapshot/output_json/report_html/discussion_log
    storage_path: str
    content_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class JournalEntry(SQLModel, table=True):
    journal_id: str = Field(primary_key=True, default_factory=lambda: f"jou_{uuid.uuid4().hex[:8]}")
    user_id: str = Field(default="default_user")
    analysis_id: Optional[str] = None
    symbol: str = Field(index=True)
    market: str
    action: str  # buy/sell/hold/reduce/add
    price_at_decision: float
    confidence: int
    reasoning: Optional[str] = None
    review_due_at: Optional[datetime] = None
    outcome_label: str = "unknown"  # win/lose/unknown
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SearchAlert(SQLModel, table=True):
    alert_id: str = Field(primary_key=True, default_factory=lambda: f"alt_{uuid.uuid4().hex[:8]}")
    user_id: str = Field(default="default_user")
    symbol: str = Field(index=True)
    market: str
    name: Optional[str] = None
    entry_price: float
    target_price: float
    stop_loss: float
    currency: str = "CNY"
    status: str = "active"  # active/triggered/closed
    triggered_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class PromptVersion(SQLModel, table=True):
    prompt_version_id: str = Field(primary_key=True, default_factory=lambda: f"pv_{uuid.uuid4().hex[:8]}")
    prompt_name: str
    version: str
    role_scope: str
    template_path: str
    schema_name: str
    status: str = "active"  # active/canary/deprecated
    created_at: datetime = Field(default_factory=datetime.utcnow)

class PromptRun(SQLModel, table=True):
    prompt_run_id: str = Field(primary_key=True, default_factory=lambda: f"pr_{uuid.uuid4().hex[:8]}")
    analysis_id: Optional[str] = None
    job_id: str
    prompt_version_id: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    parse_success: int = 1
    tool_calls: int = 0
    source_coverage_score: float = 0.0
    drift_score: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)

class AuditLog(SQLModel, table=True):
    audit_id: str = Field(primary_key=True, default_factory=lambda: f"aud_{uuid.uuid4().hex[:8]}")
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    before_json: Optional[str] = None
    after_json: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
