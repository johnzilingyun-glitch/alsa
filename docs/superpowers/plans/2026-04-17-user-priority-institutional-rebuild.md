# User-Priority Institutional Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the current AI financial analysis app into an institutional-grade platform using a validated Python-first backend data stack while preserving the highest-value user flows first.

**Architecture:** Use FastAPI as the backend control plane. Store transactional metadata in SQLite, historical market data in Parquet, analytical reads in DuckDB, indicators/factors in Polars, and semantic retrieval in LanceDB. Keep the existing Node layer only as a frontend shell and migration proxy.

**Tech Stack:** React 19, TypeScript, Zustand, FastAPI, Pydantic, SQLite, SQLModel/SQLAlchemy, Parquet, DuckDB, Polars, LanceDB, Express proxy, Pytest, Vitest

---

## Scope Check

The backend stack is now explicitly validated as:

| Component | Role | Decision |
| --- | --- | --- |
| FastAPI | 调度中心 / API 中枢 | Adopt |
| SQLite | 业务元数据 / ACID | Adopt |
| Parquet | 原始 OHLC / 快照仓 | Adopt |
| DuckDB | Parquet SQL 分析 | Adopt |
| Polars | 指标 / 因子计算 | Adopt |
| LanceDB | 研报 / 新闻语义检索 | Adopt |
| Express | 前端外壳 / 兼容代理 | Keep temporarily |

This stack is the preferred target for the next stage because the current project is still a single-node analytical product, not a multi-service SaaS. Do not reintroduce PostgreSQL/Redis/BullMQ in this phase unless the stack above demonstrably fails.

## User-Priority Ordering

1. `查股票 -> 看分析`
2. `回看历史 -> 导出/分享`
3. `加入跟踪 -> 收到提醒`
4. `记决策 -> 做复盘`
5. `运营治理 -> PromptOps -> 审计`

## Core Architecture Rules

1. FastAPI owns new backend workflows.
2. SQLite stores only metadata, settings, secrets, watchlist, journal, jobs, and prompt metrics.
3. OHLC and snapshot history never live in SQLite blobs; they live in Parquet.
4. DuckDB queries Parquet; it does not replace SQLite.
5. Polars computes indicators and factors; frontend math must be removed.
6. LanceDB stores chunked, versioned research/news embeddings only.
7. API keys stored in SQLite must be encrypted before persistence.

## File Structure

### Existing files to modify

- Modify: `server.ts`
- Modify: `server/historyRoutes.ts`
- Modify: `server/debugRoutes.ts`
- Modify: `python_service/main.py`
- Modify: `python_service/technicals.py`
- Modify: `src/App.tsx`
- Modify: `src/services/analysisService.ts`
- Modify: `src/services/discussionService.ts`
- Modify: `src/services/marketService.ts`
- Modify: `src/stores/useConfigStore.ts`
- Modify: `src/stores/useWatchlistStore.ts`
- Modify: `src/stores/useDecisionStore.ts`
- Modify: `README.md`
- Modify: `.env.example`

### New backend files

- Create: `python_service/app/api/router.py`
- Create: `python_service/app/api/analysis.py`
- Create: `python_service/app/api/market.py`
- Create: `python_service/app/api/watchlist.py`
- Create: `python_service/app/api/journal.py`
- Create: `python_service/app/api/admin.py`
- Create: `python_service/app/core/config.py`
- Create: `python_service/app/db/sqlite.py`
- Create: `python_service/app/db/models.py`
- Create: `python_service/app/db/repositories/watchlist_repo.py`
- Create: `python_service/app/db/repositories/journal_repo.py`
- Create: `python_service/app/db/repositories/job_repo.py`
- Create: `python_service/app/lake/parquet_store.py`
- Create: `python_service/app/lake/duckdb_engine.py`
- Create: `python_service/app/quant/polars_indicators.py`
- Create: `python_service/app/vector/lancedb_store.py`
- Create: `python_service/app/services/market_snapshot_service.py`
- Create: `python_service/app/services/analysis_job_service.py`
- Create: `python_service/app/services/watchlist_scan_service.py`

### New frontend files

- Create: `src/services/api/analysisClient.ts`
- Create: `src/services/api/watchlistClient.ts`
- Create: `src/services/api/journalClient.ts`
- Create: `src/hooks/useAnalysisJob.ts`
- Create: `src/hooks/useWatchlistSync.ts`
- Create: `src/hooks/useDecisionJournal.ts`

### New tests

- Create: `python_service/tests/test_analysis_api.py`
- Create: `python_service/tests/test_sqlite_repositories.py`
- Create: `python_service/tests/test_parquet_duckdb_pipeline.py`
- Create: `python_service/tests/test_polars_indicators.py`
- Create: `python_service/tests/test_lancedb_retrieval.py`
- Create: `python_service/tests/test_watchlist_journal_api.py`
- Create: `python_service/tests/test_admin_api.py`
- Create: `src/components/__tests__/HistoryReplay.test.tsx`
- Create: `src/services/__tests__/analysisClient.test.ts`

### Task 1: Make FastAPI the Control Plane

**Files:**
- Create: `python_service/app/api/router.py`
- Create: `python_service/app/api/analysis.py`
- Create: `python_service/app/api/market.py`
- Modify: `python_service/main.py`
- Modify: `server.ts`
- Test: `python_service/tests/test_analysis_api.py`

- [ ] **Step 1: Write the failing FastAPI job test**

```python
from fastapi.testclient import TestClient
from python_service.main import app

def test_create_analysis_job():
    client = TestClient(app)
    resp = client.post("/api/analysis/jobs", json={"symbol": "600519", "market": "A-Share", "level": "standard"})
    assert resp.status_code == 202
    assert resp.json()["job_id"].startswith("job_")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest python_service/tests/test_analysis_api.py -q`
Expected: FAIL with missing route

- [ ] **Step 3: Implement FastAPI routes and Node proxy**

```python
class AnalysisJobCreate(BaseModel):
    symbol: str
    market: str
    level: str

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

@router.post("/jobs", status_code=202)
async def create_job(payload: AnalysisJobCreate):
    return {"job_id": f"job_{payload.symbol}", "status": "queued"}
```

```python
app = FastAPI(title="ALSA Backend")
app.include_router(api_router)
```

```ts
app.use('/api', createProxyMiddleware({ target: 'http://127.0.0.1:8000', changeOrigin: true }));
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest python_service/tests/test_analysis_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python_service/main.py python_service/app/api server.ts python_service/tests/test_analysis_api.py
git commit -m "feat: make fastapi the backend control plane"
```

### Task 2: Build SQLite as the Business Brain

**Files:**
- Create: `python_service/app/core/config.py`
- Create: `python_service/app/db/sqlite.py`
- Create: `python_service/app/db/models.py`
- Create: `python_service/app/db/repositories/watchlist_repo.py`
- Create: `python_service/app/db/repositories/journal_repo.py`
- Create: `python_service/app/db/repositories/job_repo.py`
- Test: `python_service/tests/test_sqlite_repositories.py`
- Modify: `.env.example`

- [ ] **Step 1: Write the failing repository test**

```python
from python_service.app.db.sqlite import build_session_factory
from python_service.app.db.repositories.watchlist_repo import WatchlistRepository

def test_watchlist_repo_persists_item(tmp_path):
    repo = WatchlistRepository(build_session_factory(tmp_path / "app.db"))
    repo.create(symbol="600519", name="贵州茅台", market="A-Share")
    items = repo.list_items()
    assert len(items) == 1
    assert items[0].symbol == "600519"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest python_service/tests/test_sqlite_repositories.py -q`
Expected: FAIL with missing repository/session factory

- [ ] **Step 3: Implement SQLite models and repos**

```python
class WatchlistItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    name: str
    market: str
```

```python
class Settings(BaseSettings):
    sqlite_path: str = "python_service/data/app.db"
    admin_token: str = "change-me"
    secret_encryption_key: str = "change-me"

settings = Settings()
```

```python
def build_session_factory(db_path):
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return lambda: Session(engine)
```

```env
SQLITE_PATH=python_service/data/app.db
SECRET_ENCRYPTION_KEY=change-me
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest python_service/tests/test_sqlite_repositories.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python_service/app/db python_service/tests/test_sqlite_repositories.py .env.example
git commit -m "feat: add sqlite business metadata layer"
```

### Task 3: Build the Parquet + DuckDB Market Lake

**Files:**
- Create: `python_service/app/lake/parquet_store.py`
- Create: `python_service/app/lake/duckdb_engine.py`
- Create: `python_service/app/services/market_snapshot_service.py`
- Modify: `python_service/app/api/market.py`
- Test: `python_service/tests/test_parquet_duckdb_pipeline.py`

- [ ] **Step 1: Write the failing pipeline test**

```python
from python_service.app.lake.parquet_store import ParquetMarketStore
from python_service.app.lake.duckdb_engine import DuckDBMarketQuery

def test_parquet_and_duckdb_round_trip(tmp_path):
    store = ParquetMarketStore(tmp_path / "lake")
    store.write_ohlc("ohlc", "A-Share", "600519", [{"trade_date": "2026-04-16", "close": 1698, "volume": 15678}])
    row = DuckDBMarketQuery().latest_close(store.glob_path("ohlc", "A-Share", "600519"))
    assert row["close"] == 1698
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest python_service/tests/test_parquet_duckdb_pipeline.py -q`
Expected: FAIL with missing Parquet store or query engine

- [ ] **Step 3: Implement Parquet partitioning and DuckDB query layer**

```python
class ParquetMarketStore:
    def write_ohlc(self, dataset, market, symbol, rows):
        frame = pl.DataFrame(rows)
        target = self.root / dataset / f"market={market}" / "year=2026" / f"symbol={symbol}"
        target.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(target / "part-000.parquet")
```

```python
class DuckDBMarketQuery:
    def latest_close(self, parquet_glob):
        row = duckdb.sql(f"select close from read_parquet('{parquet_glob}') order by trade_date desc limit 1").df().iloc[0]
        return {"close": int(row['close'])}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest python_service/tests/test_parquet_duckdb_pipeline.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python_service/app/lake python_service/app/services/market_snapshot_service.py python_service/app/api/market.py python_service/tests/test_parquet_duckdb_pipeline.py
git commit -m "feat: add parquet market lake and duckdb analytics"
```

### Task 4: Move Indicators and Factors into Polars

**Files:**
- Create: `python_service/app/quant/polars_indicators.py`
- Modify: `python_service/technicals.py`
- Modify: `python_service/app/services/market_snapshot_service.py`
- Test: `python_service/tests/test_polars_indicators.py`

- [ ] **Step 1: Write the failing Polars test**

```python
from python_service.app.quant.polars_indicators import compute_indicator_frame

def test_compute_indicator_frame_has_core_columns():
    rows = [{"trade_date": f"2026-04-{i:02d}", "close": 100 + i, "high": 101 + i, "low": 99 + i, "volume": 1000 + i} for i in range(1, 40)]
    frame = compute_indicator_frame(rows)
    assert "ma_20" in frame.columns
    assert "macd" in frame.columns
    assert "rsi_14" in frame.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest python_service/tests/test_polars_indicators.py -q`
Expected: FAIL with missing function

- [ ] **Step 3: Implement Polars indicator engine**

```python
def compute_indicator_frame(rows):
    frame = pl.DataFrame(rows).sort("trade_date")
    return frame.with_columns([
        pl.col("close").rolling_mean(5).alias("ma_5"),
        pl.col("close").rolling_mean(20).alias("ma_20"),
        (pl.col("close").ewm_mean(span=12) - pl.col("close").ewm_mean(span=26)).alias("macd"),
    ]).with_columns([
        (100 - (100 / (1 + (
            pl.when((pl.col("close") - pl.col("close").shift(1)) > 0)
            .then(pl.col("close") - pl.col("close").shift(1)).otherwise(0).rolling_mean(14)
            /
            pl.when((pl.col("close") - pl.col("close").shift(1)) < 0)
            .then(-(pl.col("close") - pl.col("close").shift(1))).otherwise(0).rolling_mean(14)
        )))).alias("rsi_14")
    ])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest python_service/tests/test_polars_indicators.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python_service/app/quant python_service/technicals.py python_service/app/services/market_snapshot_service.py python_service/tests/test_polars_indicators.py
git commit -m "feat: add polars-based indicator engine"
```

### Task 5: Add LanceDB Semantic Retrieval for Research and News

**Files:**
- Create: `python_service/app/vector/lancedb_store.py`
- Modify: `python_service/app/services/analysis_job_service.py`
- Test: `python_service/tests/test_lancedb_retrieval.py`

- [ ] **Step 1: Write the failing LanceDB test**

```python
from python_service.app.vector.lancedb_store import LanceResearchStore

def test_lancedb_returns_best_match(tmp_path):
    store = LanceResearchStore(tmp_path / "lancedb")
    store.upsert_documents([{"doc_id": "r1", "symbol": "600519", "text": "直营比例提升", "embedding": [0.1, 0.2, 0.3]}])
    result = store.search(symbol="600519", query_embedding=[0.1, 0.2, 0.29], limit=1)
    assert result[0]["doc_id"] == "r1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest python_service/tests/test_lancedb_retrieval.py -q`
Expected: FAIL with missing store

- [ ] **Step 3: Implement LanceDB wrapper**

```python
class LanceResearchStore:
    def __init__(self, root):
        self.db = lancedb.connect(str(root))
        self.table = self.db.create_table("research_chunks", data=[{"doc_id": "bootstrap", "symbol": "BOOT", "text": "", "embedding": [0.0, 0.0, 0.0]}], mode="overwrite")

    def upsert_documents(self, rows):
        self.table.add(rows)

    def search(self, symbol, query_embedding, limit=5):
        return self.table.search(query_embedding).where(f"symbol = '{symbol}'").limit(limit).to_list()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest python_service/tests/test_lancedb_retrieval.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python_service/app/vector python_service/app/services/analysis_job_service.py python_service/tests/test_lancedb_retrieval.py
git commit -m "feat: add lancedb semantic retrieval"
```

### Task 6: Rewire the User-Facing Flows to the New Data Plane

**Files:**
- Create: `src/services/api/analysisClient.ts`
- Create: `src/services/api/watchlistClient.ts`
- Create: `src/services/api/journalClient.ts`
- Create: `src/hooks/useAnalysisJob.ts`
- Create: `src/hooks/useWatchlistSync.ts`
- Create: `src/hooks/useDecisionJournal.ts`
- Modify: `src/services/analysisService.ts`
- Modify: `src/services/marketService.ts`
- Modify: `src/App.tsx`
- Modify: `src/stores/useWatchlistStore.ts`
- Modify: `src/stores/useDecisionStore.ts`
- Test: `src/services/__tests__/analysisClient.test.ts`
- Test: `src/components/__tests__/HistoryReplay.test.tsx`
- Test: `python_service/tests/test_watchlist_journal_api.py`

- [ ] **Step 1: Write the failing polling and replay tests**

```ts
it('polls until fastapi analysis job completes', async () => {
  const payload = await pollAnalysisJob('job_001');
  expect(payload.status).toBe('completed');
});
```

```tsx
it('keeps selected history visible when no discussion payload exists', async () => {
  render(<App />);
  await userEvent.click(screen.getByText('打开历史'));
  await userEvent.click(screen.getByText('STOCK: 600519'));
  expect(screen.getByText(/600519/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- src/services/__tests__/analysisClient.test.ts src/components/__tests__/HistoryReplay.test.tsx`
Expected: FAIL because frontend still depends on old mixed flow

- [ ] **Step 3: Implement clients, fix replay bug, and expose watchlist/journal APIs**

```ts
export async function pollAnalysisJob(jobId: string) {
  for (;;) {
    const response = await fetch(`/api/analysis/jobs/${jobId}`);
    const payload = await response.json();
    if (payload.status === 'completed' || payload.status === 'failed') return payload;
    await new Promise(resolve => setTimeout(resolve, 1200));
  }
}
```

```tsx
if (item.discussion) {
  setDiscussionResults(discussionData);
  setScenarioResults(discussionData);
  setShowDiscussion(true);
} else {
  resetDiscussion();
  resetScenario();
  setShowDiscussion(false);
}
```

```python
@router.get("/api/watchlist")
async def list_watchlist():
    return {"items": watchlist_repo.list_items()}

@router.get("/api/journal/pending-reviews")
async def pending_reviews():
    return {"items": journal_repo.pending_reviews()}
```

- [ ] **Step 4: Run verification**

Run: `pytest python_service/tests/test_watchlist_journal_api.py -q`
Expected: PASS

Run: `npm test -- src/services/__tests__/analysisClient.test.ts src/components/__tests__/HistoryReplay.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/api src/hooks src/services/analysisService.ts src/services/marketService.ts src/App.tsx src/stores/useWatchlistStore.ts src/stores/useDecisionStore.ts python_service/app/api/watchlist.py python_service/app/api/journal.py python_service/tests/test_watchlist_journal_api.py
git commit -m "refactor: rewire user flows to sqlite parquet duckdb polars backend"
```

### Task 7: Add Admin Controls, Diagnostics Lockdown, and Cutover Docs

**Files:**
- Create: `python_service/app/api/admin.py`
- Modify: `server/debugRoutes.ts`
- Modify: `README.md`
- Create: `docs/ops/python-data-stack-cutover.md`
- Test: `python_service/tests/test_admin_api.py`

- [ ] **Step 1: Write the failing admin test**

```python
from fastapi.testclient import TestClient
from python_service.main import app

def test_admin_requires_token():
    client = TestClient(app)
    resp = client.get("/api/admin/stack-status")
    assert resp.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest python_service/tests/test_admin_api.py -q`
Expected: FAIL with missing admin route

- [ ] **Step 3: Implement admin route and disable old public diagnostics**

```python
@router.get("/api/admin/stack-status")
async def stack_status(x_admin_token: str | None = Header(default=None)):
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="admin access required")
    return {"fastapi": "active", "sqlite": "active", "parquet": "active", "duckdb": "active", "polars": "active", "lancedb": "active"}
```

```ts
router.use((req, res, next) => {
  if (process.env.NODE_ENV === 'production') {
    return res.status(403).json({ error: 'diagnostics moved to fastapi admin routes' });
  }
  next();
});
```

```md
# Python Data Stack Cutover

1. Start FastAPI.
2. Confirm SQLite path is writable.
3. Confirm Parquet partitions exist.
4. Confirm DuckDB query returns one OHLC row.
5. Confirm Polars indicator pipeline returns MA/MACD/RSI.
6. Confirm LanceDB returns one semantic match.
```

- [ ] **Step 4: Run verification**

Run: `pytest python_service/tests/test_admin_api.py -q`
Expected: PASS

Run: `npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python_service/app/api/admin.py server/debugRoutes.ts README.md docs/ops/python-data-stack-cutover.md python_service/tests/test_admin_api.py
git commit -m "docs: add admin controls and python data stack cutover"
```

## Success Metrics

- Stock lookup P50 under `500ms`
- Analysis job creation under `300ms`
- Analysis completion P50 under `45s`
- 100% of OHLC history written to Parquet
- 100% of grouped historical analytics read through DuckDB
- 100% of indicator snapshots generated by Polars
- 0 plaintext API keys in SQLite

## Risks to Watch

1. Do not store OHLC arrays in SQLite.
2. Do not duplicate indicators across frontend and Python.
3. Do not bypass DuckDB with Python loops for grouped analysis.
4. Do not leave old diagnostics public in production.
5. Do not treat LanceDB as a general document store.

## Recommended Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7

Plan complete and saved to `docs/superpowers/plans/2026-04-17-user-priority-institutional-rebuild.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
