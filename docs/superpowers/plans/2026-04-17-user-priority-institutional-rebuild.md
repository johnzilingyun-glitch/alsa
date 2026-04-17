# User-Priority Institutional Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the current AI financial analysis app into an institutional-grade platform by prioritizing the highest-frequency user journeys first: stock lookup, trustworthy analysis, history replay, tracking, and post-trade review.

**Architecture:** Keep the current React + Express + FastAPI split, but move the system from client-led orchestration to server-led orchestration. All analysis must be generated from immutable market-data snapshots, all LLM access must terminate at the backend, and all user-facing workflows must persist to a database instead of local JSON or browser-only state.

**Tech Stack:** React 19, TypeScript, Zustand, Express, FastAPI, Zod, PostgreSQL, Redis, BullMQ-style job queue, Vitest, Testing Library

---

## Scope Check

This is a master rebuild plan because the user requested one institution-grade document organized by real user workflow priority. Execution should still happen in phases, with each phase shipping a usable slice:

1. `查股票 -> 看分析`
2. `回看历史 -> 导出/分享`
3. `加入跟踪 -> 收到提醒`
4. `记决策 -> 做复盘`
5. `运营治理 -> PromptOps -> 审计`

## User-Priority Ordering

### P0: Daily core journey

1. Stock lookup and real-time quote accuracy
2. Single-stock AI analysis reliability
3. Multi-expert discussion consistency
4. History replay correctness
5. Report export and delivery

### P1: Retention journey

1. Watchlist
2. Alerting and rescan
3. Daily market report

### P2: Institutional maturity

1. Decision journal and review loop
2. Prompt governance and evaluation
3. Audit trail, diagnostics control, compliance guardrails

## Target File Structure

### Existing files to modify

- Modify: `server.ts`
- Modify: `server/debugRoutes.ts`
- Modify: `server/historyRoutes.ts`
- Modify: `server/stockRoutes.ts`
- Modify: `server/llmGateway.ts`
- Modify: `python_service/main.py`
- Modify: `src/App.tsx`
- Modify: `src/services/analysisService.ts`
- Modify: `src/services/discussionService.ts`
- Modify: `src/services/geminiService.ts`
- Modify: `src/services/marketService.ts`
- Modify: `src/services/llmProvider.ts`
- Modify: `src/services/promptRegistry.ts`
- Modify: `src/services/promptRegistration.ts`
- Modify: `src/stores/useConfigStore.ts`
- Modify: `src/stores/useWatchlistStore.ts`
- Modify: `src/stores/useDecisionStore.ts`
- Modify: `src/components/admin/AdminPanel.tsx`
- Modify: `package.json`
- Modify: `.env.example`
- Modify: `README.md`

### New backend files

- Create: `server/db/client.ts`
- Create: `server/db/migrations/2026-04-17-001_user_priority_core.sql`
- Create: `server/domain/analysis/analysisSnapshot.ts`
- Create: `server/domain/watchlist/watchlistItem.ts`
- Create: `server/domain/journal/decisionEntry.ts`
- Create: `server/providers/market/providerTypes.ts`
- Create: `server/providers/market/yahooProvider.ts`
- Create: `server/providers/market/akshareProxyProvider.ts`
- Create: `server/providers/market/fallbackProvider.ts`
- Create: `server/services/marketSnapshotService.ts`
- Create: `server/services/analysisJobService.ts`
- Create: `server/services/reportDeliveryService.ts`
- Create: `server/services/promptMetricsService.ts`
- Create: `server/services/auditService.ts`
- Create: `server/repositories/analysisRepository.ts`
- Create: `server/repositories/watchlistRepository.ts`
- Create: `server/repositories/decisionRepository.ts`
- Create: `server/routes/analysisRoutes.ts`
- Create: `server/routes/watchlistRoutes.ts`
- Create: `server/routes/journalRoutes.ts`
- Create: `server/routes/adminRoutes.ts`
- Create: `server/jobs/analysisWorker.ts`
- Create: `server/jobs/watchlistScanWorker.ts`

### New frontend files

- Create: `src/services/api/analysisClient.ts`
- Create: `src/services/api/watchlistClient.ts`
- Create: `src/services/api/journalClient.ts`
- Create: `src/hooks/useAnalysisJob.ts`
- Create: `src/hooks/useWatchlistSync.ts`
- Create: `src/hooks/useDecisionJournal.ts`

### New tests

- Create: `server/__tests__/analysisRepository.test.ts`
- Create: `server/__tests__/analysisRoutes.test.ts`
- Create: `server/__tests__/marketSnapshotService.test.ts`
- Create: `server/__tests__/watchlistRoutes.test.ts`
- Create: `server/__tests__/journalRoutes.test.ts`
- Create: `server/__tests__/adminRoutes.test.ts`
- Create: `src/components/__tests__/HistoryReplay.test.tsx`
- Create: `src/services/__tests__/analysisClient.test.ts`
- Create: `src/services/__tests__/promptMetrics.test.ts`

## Architecture Decisions

1. Every analysis run gets a server-generated `analysis_id`, immutable input snapshot, model metadata, prompt version, and audit record.
2. The browser can choose a service mode, but it cannot send or persist raw provider keys for production execution.
3. `watchlist` and `decision journal` move from browser-only Zustand state into backend persistence, with Zustand becoming a cache, not the source of truth.
4. `historyRoutes.ts` becomes a compatibility layer during migration, then hands off to repository-backed storage.
5. Debug and diagnostics endpoints become admin-only and disabled by default in production.

## Delivery Phases

### Phase A: Trustworthy core analysis

- Server-side LLM gateway
- Canonical market snapshot
- Async analysis jobs
- Reliable history replay

### Phase B: Retention workflows

- Watchlist
- Alert scan
- Report delivery

### Phase C: Institutional governance

- Decision journal
- PromptOps
- Audit/compliance/admin

### Task 1: Build the Institutional Persistence Baseline

**Files:**
- Create: `server/db/client.ts`
- Create: `server/db/migrations/2026-04-17-001_user_priority_core.sql`
- Create: `server/domain/analysis/analysisSnapshot.ts`
- Create: `server/repositories/analysisRepository.ts`
- Test: `server/__tests__/analysisRepository.test.ts`
- Modify: `package.json`

- [ ] **Step 1: Write the failing repository test**

```ts
import { describe, expect, it } from 'vitest';
import { createAnalysisRepository } from '../repositories/analysisRepository';

describe('analysisRepository', () => {
  it('stores immutable snapshots and returns the latest stock analysis by symbol', async () => {
    const repo = createAnalysisRepository();

    await repo.save({
      analysisId: 'ana_001',
      kind: 'stock',
      symbol: '600519',
      market: 'A-Share',
      inputSnapshot: { quote: { price: 1688.0 } },
      outputPayload: { summary: 'valid payload' },
      promptVersion: 'stock-analysis-v2',
      model: 'gpt-5.4',
    });

    const latest = await repo.getLatestStockAnalysis('600519', 'A-Share');
    expect(latest?.analysisId).toBe('ana_001');
    expect(latest?.inputSnapshot.quote.price).toBe(1688.0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- server/__tests__/analysisRepository.test.ts`
Expected: FAIL with `Cannot find module '../repositories/analysisRepository'`

- [ ] **Step 3: Write the migration, domain model, and repository**

```sql
create table analysis_runs (
  analysis_id text primary key,
  kind text not null,
  symbol text,
  market text,
  status text not null default 'completed',
  prompt_version text not null,
  model text not null,
  input_snapshot jsonb not null,
  output_payload jsonb not null,
  created_at timestamptz not null default now()
);

create index analysis_runs_symbol_market_created_idx
  on analysis_runs(symbol, market, created_at desc);
```

```ts
export interface AnalysisRunRecord {
  analysisId: string;
  kind: 'stock' | 'market';
  symbol?: string;
  market?: string;
  status?: 'queued' | 'running' | 'completed' | 'failed';
  promptVersion: string;
  model: string;
  inputSnapshot: Record<string, unknown>;
  outputPayload: Record<string, unknown>;
  createdAt?: string;
}
```

```ts
export function createAnalysisRepository() {
  const memory = new Map<string, AnalysisRunRecord>();

  return {
    async save(record: AnalysisRunRecord) {
      memory.set(record.analysisId, record);
    },
    async getLatestStockAnalysis(symbol: string, market: string) {
      return [...memory.values()]
        .filter(item => item.kind === 'stock' && item.symbol === symbol && item.market === market)
        .sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''))[0] ?? null;
    },
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- server/__tests__/analysisRepository.test.ts`
Expected: PASS with `1 passed`

- [ ] **Step 5: Commit**

```bash
git add package.json server/db server/domain/analysis server/repositories server/__tests__/analysisRepository.test.ts
git commit -m "feat: add institutional analysis persistence baseline"
```

### Task 2: Move LLM Execution Fully Behind the Backend Boundary

**Files:**
- Modify: `server/llmGateway.ts`
- Create: `server/routes/analysisRoutes.ts`
- Modify: `server.ts`
- Modify: `src/services/geminiService.ts`
- Modify: `src/services/llmProvider.ts`
- Modify: `src/stores/useConfigStore.ts`
- Test: `server/__tests__/analysisRoutes.test.ts`

- [ ] **Step 1: Write the failing route test**

```ts
import { describe, expect, it } from 'vitest';
import request from 'supertest';
import { buildAnalysisApp } from '../routes/analysisRoutes';

describe('analysis routes', () => {
  it('rejects browser-supplied raw api keys and creates a server-owned job', async () => {
    const app = buildAnalysisApp();

    const response = await request(app)
      .post('/api/analysis/jobs')
      .send({
        symbol: '600519',
        market: 'A-Share',
        apiKey: 'should-not-be-accepted',
      });

    expect(response.status).toBe(202);
    expect(response.body.jobId).toMatch(/^job_/);
    expect(response.body.acceptedClientSecrets).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- server/__tests__/analysisRoutes.test.ts`
Expected: FAIL with missing `buildAnalysisApp` or missing `/api/analysis/jobs`

- [ ] **Step 3: Implement the server-owned analysis job entrypoint**

```ts
router.post('/api/analysis/jobs', async (req, res) => {
  const { symbol, market, serviceMode, model } = req.body;

  const job = await analysisJobService.enqueue({
    symbol,
    market,
    serviceMode,
    model,
    acceptedClientSecrets: false,
  });

  res.status(202).json({
    jobId: job.jobId,
    status: 'queued',
    acceptedClientSecrets: false,
  });
});
```

```ts
export function getApiKey() {
  throw new Error('Client-side direct provider execution is disabled after institutional rebuild.');
}
```

```ts
setConfig: (config) => {
  const sanitized = { ...config, apiKey: undefined };
  localStorage.setItem('gemini_config', JSON.stringify(sanitized));
  set({ geminiConfig: sanitized, config: sanitized });
},
```

- [ ] **Step 4: Run test and targeted regression checks**

Run: `npm test -- server/__tests__/analysisRoutes.test.ts src/services/geminiService.test.ts src/services/geminiService.ts`
Expected: route test PASS, existing Gemini tests updated to assert backend-only execution path

- [ ] **Step 5: Commit**

```bash
git add server/llmGateway.ts server/routes/analysisRoutes.ts server.ts src/services/geminiService.ts src/services/llmProvider.ts src/stores/useConfigStore.ts server/__tests__/analysisRoutes.test.ts
git commit -m "refactor: move llm execution behind backend analysis jobs"
```

### Task 3: Standardize Market Data into Immutable Analysis Snapshots

**Files:**
- Create: `server/providers/market/providerTypes.ts`
- Create: `server/providers/market/yahooProvider.ts`
- Create: `server/providers/market/akshareProxyProvider.ts`
- Create: `server/providers/market/fallbackProvider.ts`
- Create: `server/services/marketSnapshotService.ts`
- Modify: `server/stockRoutes.ts`
- Modify: `python_service/main.py`
- Test: `server/__tests__/marketSnapshotService.test.ts`

- [ ] **Step 1: Write the failing snapshot test**

```ts
import { describe, expect, it } from 'vitest';
import { buildMarketSnapshot } from '../services/marketSnapshotService';

describe('marketSnapshotService', () => {
  it('returns quote, news, technicals, freshness, and source lineage in one payload', async () => {
    const snapshot = await buildMarketSnapshot({ symbol: '600519', market: 'A-Share' });

    expect(snapshot.quote.symbol).toBe('600519');
    expect(snapshot.lineage.quote.primarySource).toBeDefined();
    expect(snapshot.freshness.quote).toMatch(/fresh|delayed|stale/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- server/__tests__/marketSnapshotService.test.ts`
Expected: FAIL with missing `buildMarketSnapshot`

- [ ] **Step 3: Implement provider adapters and unified snapshot output**

```ts
export interface QuoteSnapshot {
  symbol: string;
  market: 'A-Share' | 'HK-Share' | 'US-Share';
  price: number;
  previousClose: number;
  change: number;
  changePercent: number;
  source: string;
  asOf: string;
}

export interface MarketSnapshot {
  quote: QuoteSnapshot;
  news: Array<{ title: string; url: string; source: string; publishedAt: string }>;
  technicals: Record<string, unknown>;
  freshness: { quote: 'fresh' | 'delayed' | 'stale' };
  lineage: { quote: { primarySource: string; fallbackChain: string[] } };
}
```

```ts
export async function buildMarketSnapshot(input: { symbol: string; market: string }): Promise<MarketSnapshot> {
  const quote = await fallbackProvider.getQuote(input);
  const news = await fallbackProvider.getNews(input);
  const technicals = await fallbackProvider.getTechnicals(input);

  return {
    quote,
    news,
    technicals,
    freshness: { quote: 'fresh' },
    lineage: {
      quote: {
        primarySource: quote.source,
        fallbackChain: ['akshare', 'sina', 'yahoo'],
      },
    },
  };
}
```

```py
@app.get("/api/stock/a_snapshot")
async def get_stock_a_snapshot(symbol: str = Query(..., pattern=r"^\d{6}$")):
    spot = await get_stock_a_spot(symbol)
    history = await get_stock_a_history(symbol)
    technicals = await get_technicals(symbol)
    return {
        "success": True,
        "data": {
            "spot": spot.get("data"),
            "history": history.get("data"),
            "technicals": technicals.get("data"),
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- server/__tests__/marketSnapshotService.test.ts server/__tests__/dataSourceHealth.test.ts`
Expected: PASS with snapshot lineage and freshness asserted

- [ ] **Step 5: Commit**

```bash
git add server/providers/market server/services/marketSnapshotService.ts server/stockRoutes.ts python_service/main.py server/__tests__/marketSnapshotService.test.ts
git commit -m "feat: add immutable market snapshot builder with provider lineage"
```

### Task 4: Rebuild the Core User Journey Around Analysis Jobs and Reliable Replay

**Files:**
- Create: `src/services/api/analysisClient.ts`
- Create: `src/hooks/useAnalysisJob.ts`
- Modify: `src/services/analysisService.ts`
- Modify: `src/services/discussionService.ts`
- Modify: `src/App.tsx`
- Modify: `server/historyRoutes.ts`
- Test: `src/components/__tests__/HistoryReplay.test.tsx`
- Test: `src/services/__tests__/analysisClient.test.ts`

- [ ] **Step 1: Write the failing replay and polling tests**

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';

it('keeps selected history analysis visible when the record has no discussion payload', async () => {
  render(<App />);

  await userEvent.click(screen.getByText('打开历史'));
  await userEvent.click(screen.getByText('STOCK: 600519'));

  expect(screen.getByText(/600519/)).toBeInTheDocument();
});
```

```ts
import { describe, expect, it } from 'vitest';
import { pollAnalysisJob } from '../api/analysisClient';

describe('analysisClient', () => {
  it('polls until the job reaches completed state', async () => {
    const result = await pollAnalysisJob('job_001');
    expect(result.status).toBe('completed');
    expect(result.result.stockInfo.symbol).toBe('600519');
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- src/components/__tests__/HistoryReplay.test.tsx src/services/__tests__/analysisClient.test.ts`
Expected: FAIL because replay still resets analysis and no analysis job client exists

- [ ] **Step 3: Implement job polling and fix history replay state logic**

```ts
export async function createAnalysisJob(input: { symbol: string; market: string; level: string }) {
  const response = await fetch('/api/analysis/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  return response.json();
}

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

```ts
router.get('/history/context', async (_req, res) => {
  const history = await analysisRepository.listRecent({ limit: 100 });
  res.json(history);
});
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- src/components/__tests__/HistoryReplay.test.tsx src/services/__tests__/analysisClient.test.ts src/test/AnalysisResult.test.tsx`
Expected: PASS and history replay no longer clears the selected analysis

- [ ] **Step 5: Commit**

```bash
git add src/services/api/analysisClient.ts src/hooks/useAnalysisJob.ts src/services/analysisService.ts src/services/discussionService.ts src/App.tsx server/historyRoutes.ts src/components/__tests__/HistoryReplay.test.tsx src/services/__tests__/analysisClient.test.ts
git commit -m "refactor: center user analysis flow on backend jobs and reliable replay"
```

### Task 5: Turn Watchlist from Browser State into a Real Tracking System

**Files:**
- Create: `server/domain/watchlist/watchlistItem.ts`
- Create: `server/repositories/watchlistRepository.ts`
- Create: `server/routes/watchlistRoutes.ts`
- Create: `server/services/reportDeliveryService.ts`
- Create: `server/jobs/watchlistScanWorker.ts`
- Create: `src/services/api/watchlistClient.ts`
- Create: `src/hooks/useWatchlistSync.ts`
- Modify: `src/stores/useWatchlistStore.ts`
- Test: `server/__tests__/watchlistRoutes.test.ts`

- [ ] **Step 1: Write the failing watchlist API test**

```ts
import { describe, expect, it } from 'vitest';
import request from 'supertest';
import { buildWatchlistApp } from '../routes/watchlistRoutes';

describe('watchlist routes', () => {
  it('creates a persistent watchlist item and returns it on list', async () => {
    const app = buildWatchlistApp();

    await request(app).post('/api/watchlist').send({
      symbol: '600519',
      name: '贵州茅台',
      market: 'A-Share',
    }).expect(201);

    const response = await request(app).get('/api/watchlist').expect(200);
    expect(response.body.items[0].symbol).toBe('600519');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- server/__tests__/watchlistRoutes.test.ts`
Expected: FAIL because no `/api/watchlist` route exists

- [ ] **Step 3: Implement persistent watchlist and sync hook**

```ts
router.post('/api/watchlist', async (req, res) => {
  const item = await watchlistRepository.create({
    symbol: req.body.symbol,
    name: req.body.name,
    market: req.body.market,
    notes: '',
    alertThreshold: 15,
  });

  res.status(201).json(item);
});
```

```ts
export function useWatchlistSync() {
  return {
    async refresh() {
      const response = await fetch('/api/watchlist');
      return response.json();
    },
  };
}
```

```ts
addItem: async (symbol, name, market) => {
  const created = await watchlistClient.create({ symbol, name, market });
  set(state => ({ items: [...state.items, created] }));
},
```

- [ ] **Step 4: Run test and store regression checks**

Run: `npm test -- server/__tests__/watchlistRoutes.test.ts src/stores/__tests__/useWatchlistStore.test.ts`
Expected: PASS with persisted items and non-empty API-backed store hydration

- [ ] **Step 5: Commit**

```bash
git add server/domain/watchlist server/repositories/watchlistRepository.ts server/routes/watchlistRoutes.ts server/jobs/watchlistScanWorker.ts src/services/api/watchlistClient.ts src/hooks/useWatchlistSync.ts src/stores/useWatchlistStore.ts server/__tests__/watchlistRoutes.test.ts
git commit -m "feat: add persistent watchlist and tracking workflow"
```

### Task 6: Build the Decision Journal and Review Loop for Repeat Users

**Files:**
- Create: `server/domain/journal/decisionEntry.ts`
- Create: `server/repositories/decisionRepository.ts`
- Create: `server/routes/journalRoutes.ts`
- Create: `src/services/api/journalClient.ts`
- Create: `src/hooks/useDecisionJournal.ts`
- Modify: `src/stores/useDecisionStore.ts`
- Test: `server/__tests__/journalRoutes.test.ts`

- [ ] **Step 1: Write the failing journal API test**

```ts
import { describe, expect, it } from 'vitest';
import request from 'supertest';
import { buildJournalApp } from '../routes/journalRoutes';

describe('journal routes', () => {
  it('creates a decision entry and returns it in pending reviews', async () => {
    const app = buildJournalApp();

    await request(app).post('/api/journal').send({
      symbol: '600519',
      name: '贵州茅台',
      market: 'A-Share',
      action: 'buy',
      reasoning: 'valuation reset with improving cash conversion',
      priceAtDecision: 1688,
      confidence: 72,
      analysisId: 'ana_001',
    }).expect(201);

    const response = await request(app).get('/api/journal/pending-reviews').expect(200);
    expect(Array.isArray(response.body.items)).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- server/__tests__/journalRoutes.test.ts`
Expected: FAIL with missing journal route

- [ ] **Step 3: Implement journal persistence and frontend hook**

```ts
router.post('/api/journal', async (req, res) => {
  const entry = await decisionRepository.create({
    ...req.body,
    reviewDate: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
  });
  res.status(201).json(entry);
});
```

```ts
export function useDecisionJournal() {
  return {
    async addEntry(input: {
      symbol: string;
      name: string;
      market: string;
      action: string;
      reasoning: string;
      priceAtDecision: number;
      confidence: number;
      analysisId: string;
    }) {
      const response = await fetch('/api/journal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      });
      return response.json();
    },
  };
}
```

```ts
getPendingReviews: async () => {
  const payload = await journalClient.getPendingReviews();
  set({ entries: payload.items });
  return payload.items;
},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- server/__tests__/journalRoutes.test.ts src/stores/__tests__/useDecisionStore.test.ts`
Expected: PASS with server-backed pending review behavior

- [ ] **Step 5: Commit**

```bash
git add server/domain/journal server/repositories/decisionRepository.ts server/routes/journalRoutes.ts src/services/api/journalClient.ts src/hooks/useDecisionJournal.ts src/stores/useDecisionStore.ts server/__tests__/journalRoutes.test.ts
git commit -m "feat: add decision journal and review loop"
```

### Task 7: Turn Prompt Management, Admin, and Diagnostics into Governance Capabilities

**Files:**
- Create: `server/routes/adminRoutes.ts`
- Create: `server/services/promptMetricsService.ts`
- Create: `server/services/auditService.ts`
- Modify: `src/services/promptRegistry.ts`
- Modify: `src/services/promptRegistration.ts`
- Modify: `server/debugRoutes.ts`
- Modify: `src/components/admin/AdminPanel.tsx`
- Test: `server/__tests__/adminRoutes.test.ts`
- Test: `src/services/__tests__/promptMetrics.test.ts`

- [ ] **Step 1: Write the failing prompt metrics test**

```ts
import { describe, expect, it } from 'vitest';
import { initializePromptRegistry } from '../promptRegistration';
import { getPromptMetrics, recordPromptMetrics } from '../promptRegistry';

describe('prompt metrics', () => {
  it('records usage for the active stock analysis prompt version', () => {
    initializePromptRegistry();
    recordPromptMetrics('stock-analysis', 12000, 0.91, 4800, false);

    const metrics = getPromptMetrics('stock-analysis');
    expect(metrics?.callCount).toBe(1);
    expect(metrics?.avgLatencyMs).toBe(4800);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/services/__tests__/promptMetrics.test.ts`
Expected: FAIL because prompt registry is not initialized in runtime flow and metrics are never emitted

- [ ] **Step 3: Implement runtime prompt registration, metrics, and admin-safe diagnostics**

```ts
initializePromptRegistry();

recordPromptMetrics('stock-analysis', tokenUsage.totalTokens, qualityScore, latencyMs, false);
```

```ts
router.use((req, res, next) => {
  const adminToken = req.header('x-admin-token');
  if (process.env.NODE_ENV === 'production' && adminToken !== process.env.ADMIN_TOKEN) {
    return res.status(403).json({ error: 'admin access required' });
  }
  next();
});
```

```ts
router.get('/api/admin/prompt-metrics', async (_req, res) => {
  res.json({
    stockAnalysis: promptMetricsService.get('stock-analysis'),
    marketOverview: promptMetricsService.get('market-overview'),
  });
});
```

- [ ] **Step 4: Run test and admin regression checks**

Run: `npm test -- src/services/__tests__/promptMetrics.test.ts server/__tests__/adminRoutes.test.ts`
Expected: PASS with active metrics and protected admin diagnostics

- [ ] **Step 5: Commit**

```bash
git add server/routes/adminRoutes.ts server/services/promptMetricsService.ts server/services/auditService.ts src/services/promptRegistry.ts src/services/promptRegistration.ts server/debugRoutes.ts src/components/admin/AdminPanel.tsx src/services/__tests__/promptMetrics.test.ts server/__tests__/adminRoutes.test.ts
git commit -m "feat: add prompt governance and admin-safe diagnostics"
```

### Task 8: Cut Over Documentation, Environment Defaults, and Production Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Create: `docs/ops/institutional-cutover.md`
- Test: `server/__tests__/analysisRoutes.test.ts`
- Test: `server/__tests__/marketSnapshotService.test.ts`
- Test: `server/__tests__/watchlistRoutes.test.ts`
- Test: `server/__tests__/journalRoutes.test.ts`

- [ ] **Step 1: Write the cutover checklist file**

```md
# Institutional Cutover Checklist

1. Set `ADMIN_TOKEN`, `DATABASE_URL`, `REDIS_URL`.
2. Run SQL migration `2026-04-17-001_user_priority_core.sql`.
3. Disable public diagnostics in production.
4. Verify `/api/analysis/jobs` creates and completes jobs.
5. Verify history replay, watchlist create, and journal create in staging.
```

- [ ] **Step 2: Update environment and README guidance**

```env
DATABASE_URL=postgres://user:pass@localhost:5432/alsa
REDIS_URL=redis://localhost:6379
ADMIN_TOKEN=change-me
ENABLE_PUBLIC_DIAGNOSTICS=false
```

```md
## Institutional Mode

- Browser no longer executes provider models directly
- Analysis is created through `/api/analysis/jobs`
- Watchlist and journal data persist in PostgreSQL
- Admin diagnostics require `x-admin-token`
```

- [ ] **Step 3: Run the institutional verification suite**

Run: `npm test -- server/__tests__/analysisRoutes.test.ts server/__tests__/marketSnapshotService.test.ts server/__tests__/watchlistRoutes.test.ts server/__tests__/journalRoutes.test.ts src/components/__tests__/HistoryReplay.test.tsx`
Expected: PASS with the core user journey covered end-to-end

- [ ] **Step 4: Run the full regression suite**

Run: `npm test`
Expected: PASS with all legacy tests updated and no public-flow regressions

- [ ] **Step 5: Commit**

```bash
git add .env.example README.md docs/ops/institutional-cutover.md
git commit -m "docs: add institutional cutover and verification guide"
```

## Success Metrics

### User journey metrics

- Stock analysis first meaningful paint under `8s` for cached quote + queued AI state
- Job completion P50 under `45s`, P95 under `120s`
- History replay success rate above `99%`
- Watchlist rescan alert delivery above `95%`
- Decision review completion rate above `60%` for active users

### Data trust metrics

- Every saved analysis has snapshot, prompt version, model, and lineage
- Quote drift between displayed price and snapshot source under `0.1%`
- Prompt parse success above `97%`
- Unsupported diagnostics access blocked in production

## Risks to Watch During Execution

1. Do not keep browser-local secret storage after backend cutover.
2. Do not let JSON file history remain the primary data store after Task 4.
3. Do not keep watchlist and journal as Zustand-only state after Tasks 5 and 6.
4. Do not add more prompt length until prompt metrics and evaluation are live.
5. Do not expose `/api/diagnostics/*` publicly in production.

## Recommended Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7
8. Task 8

Plan complete and saved to `docs/superpowers/plans/2026-04-17-user-priority-institutional-rebuild.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
