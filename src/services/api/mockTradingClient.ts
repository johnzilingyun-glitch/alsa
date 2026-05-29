/**
 * Mock Trading API Client
 * Communicates with the Python FastAPI backend for simulated trading.
 */

const BASE = '/api/mock-trading';

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.error || `HTTP ${res.status}`);
  }
  const json = await res.json();
  return json.data ?? json;
}

// ── Types ────────────────────────────────────────────────────────

export interface MockAccount {
  account_id: string;
  name: string;
  market: string;
  currency: string;
  initial_balance: number;
  current_cash: number;
  status: string;
  created_at?: string;
}

export interface MockPosition {
  position_id: string;
  symbol: string;
  market: string;
  shares: number;
  average_cost: number;
  current_price?: number;
  market_value?: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
}

export interface MockTrade {
  trade_id: string;
  symbol: string;
  market: string;
  action: string;
  shares: number;
  execution_price: number;
  realized_pnl: number | null;
  trigger_source: string;
  timestamp: string;
}

export interface PortfolioSummary {
  account_id: string;
  name: string;
  market: string;
  currency: string;
  initial_balance: number;
  current_cash: number;
  positions_market_value: number;
  total_equity: number;
  total_pnl: number;
  total_pnl_pct: number;
  positions: MockPosition[];
}

export interface Snapshot {
  snapshot_date: string;
  total_equity: number;
  cash_balance: number;
  positions_market_value: number;
}

export interface AnomalyEntry {
  log_id: string;
  symbol: string | null;
  event_type: string;
  magnitude_pct: number;
  news_reasoning: string | null;
  timestamp: string;
}

// ── Account API ──────────────────────────────────────────────────

export async function createMockAccount(name: string, market: string, initialBalance?: number): Promise<MockAccount> {
  const body: any = { name, market };
  if (initialBalance !== undefined) body.initial_balance = initialBalance;
  const payload: any = { name, market };
  if (initialBalance !== undefined) {
    payload.initial_balance = initialBalance;
  }
  return fetchJSON(`${BASE}/accounts`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function listMockAccounts(): Promise<MockAccount[]> {
  return fetchJSON(`${BASE}/accounts`);
}

export async function deleteMockAccount(accountId: string): Promise<boolean> {
  const res = await fetch(`${BASE}/accounts/${accountId}`, { method: 'DELETE' });
  return res.ok;
}

export async function mergeAccounts(sourceAccountIds: string[], targetAccountId: string): Promise<MockAccount> {
  return fetchJSON(`${BASE}/accounts/merge`, {
    method: 'POST',
    body: JSON.stringify({ source_account_ids: sourceAccountIds, target_account_id: targetAccountId }),
  });
}

// ── Trades & Signals ─────────────────────────────────────────────

export async function executeTrade(
  accountId: string,
  symbol: string,
  market: string,
  action: 'BUY' | 'SELL',
  shares: number,
  executionPrice: number,
  triggerSource: string = 'MANUAL'
): Promise<MockTrade> {
  return fetchJSON(`${BASE}/trades`, {
    method: 'POST',
    body: JSON.stringify({
      account_id: accountId,
      symbol,
      market,
      action,
      shares,
      execution_price: executionPrice,
      trigger_source: triggerSource,
    })
  });
}

export async function listTrades(accountId: string, symbol?: string): Promise<MockTrade[]> {
  const url = symbol ? `${BASE}/trades/${accountId}?symbol=${symbol}` : `${BASE}/trades/${accountId}`;
  return fetchJSON(url);
}

// ── Portfolio API ────────────────────────────────────────────────

export async function getPortfolio(accountId: string): Promise<PortfolioSummary> {
  return fetchJSON(`${BASE}/portfolio/${accountId}`);
}

export async function getPortfolioWithPrices(accountId: string, prices: Record<string, number>): Promise<PortfolioSummary> {
  return fetchJSON(`${BASE}/portfolio/${accountId}`, {
    method: 'POST',
    body: JSON.stringify(prices),
  });
}

export async function listPositions(accountId: string): Promise<MockPosition[]> {
  return fetchJSON(`${BASE}/positions/${accountId}`);
}

// ── Snapshot API ─────────────────────────────────────────────────

export async function listSnapshots(accountId: string, startDate?: string, endDate?: string): Promise<Snapshot[]> {
  const params = new URLSearchParams();
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  const qs = params.toString();
  return fetchJSON(`${BASE}/snapshots/${accountId}${qs ? `?${qs}` : ''}`);
}

// ── Anomaly API ──────────────────────────────────────────────────

export async function listAnomalies(accountId: string, symbol?: string): Promise<AnomalyEntry[]> {
  const url = symbol ? `${BASE}/anomalies/${accountId}?symbol=${symbol}` : `${BASE}/anomalies/${accountId}`;
  return fetchJSON(url);
}
