const API_BASE = '/api/ibkr';

export interface IBKRPosition {
  conid: number;
  ticker: string;
  name: string;
  position: number;
  avgCost: number;
  mktPrice: number;
  mktValue: number;
  unrealizedPnl: number;
  realizedPnl: number;
  pnlPercent: number;
  currency: string;
}

export interface IBKRAccountSummary {
  accountId: string;
  netLiquidation: number;
  totalCashValue: number;
  unrealizedPnl: number;
  realizedPnl: number;
  dailyPnl: number;
  currency: string;
}

export interface IBKRMonthlyPnL {
  month: string; // "2026-01"
  pnl: number;
  cumulativePnl: number;
  returnPct: number;
}

export interface IBKRDailyPnL {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
  pnl: number;
}

export async function fetchIBKRStatus(): Promise<{ connected: boolean; authenticated: boolean }> {
  const res = await fetch(`${API_BASE}/status`);
  const data = await res.json();
  return { connected: data.connected ?? false, authenticated: data.authenticated ?? false };
}

export async function fetchAccountSummary(): Promise<IBKRAccountSummary> {
  const res = await fetch(`${API_BASE}/account`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch account');
  
  const d = json.data;
  return {
    accountId: d.accountId || d.id || '',
    netLiquidation: d.netliquidation?.amount ?? d.netLiquidation ?? 0,
    totalCashValue: d.totalcashvalue?.amount ?? d.totalCashValue ?? 0,
    unrealizedPnl: d.unrealizedpnl?.amount ?? d.unrealizedPnl ?? 0,
    realizedPnl: d.realizedpnl?.amount ?? d.realizedPnl ?? 0,
    dailyPnl: d.dailyPnl ?? 0,
    currency: d.currency || 'USD',
  };
}

export async function fetchPositions(): Promise<IBKRPosition[]> {
  const res = await fetch(`${API_BASE}/positions`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch positions');
  
  return (json.data || []).map((p: any) => ({
    conid: p.conid,
    ticker: p.contractDesc || p.ticker || p.symbol || '',
    name: p.name || p.contractDesc || '',
    position: p.position || p.pos || 0,
    avgCost: p.avgCost || p.avgPrice || 0,
    mktPrice: p.mktPrice || p.lastPrice || 0,
    mktValue: p.mktValue || 0,
    unrealizedPnl: p.unrealizedPnl || 0,
    realizedPnl: p.realizedPnl || 0,
    pnlPercent: p.avgCost > 0 ? ((p.mktPrice || 0) - p.avgCost) / p.avgCost * 100 : 0,
    currency: p.currency || 'USD',
  }));
}

export async function fetchPnL(): Promise<{ dailyPnl: number; unrealizedPnl: number; realizedPnl: number }> {
  const res = await fetch(`${API_BASE}/pnl`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch P&L');
  
  const d = json.data;
  // IBKR pnl/partitioned returns nested structure
  const upnl = d?.upnl || {};
  const firstKey = Object.keys(upnl)[0];
  const pnlData = firstKey ? upnl[firstKey] : {};

  return {
    dailyPnl: pnlData.dpl ?? d.dailyPnl ?? 0,
    unrealizedPnl: pnlData.upl ?? d.unrealizedPnl ?? 0,
    realizedPnl: pnlData.rpl ?? d.realizedPnl ?? 0,
  };
}

export async function fetchMonthlyPerformance(period: string = '12M'): Promise<IBKRMonthlyPnL[]> {
  const res = await fetch(`${API_BASE}/performance?period=${period}`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch performance');
  
  const d = json.data;
  // Parse IBKR performance response format
  const nav = d?.nav?.data?.[0]?.returns || d?.cps?.data?.[0]?.returns || [];
  const dates = d?.nav?.dates || d?.cps?.dates || [];
  
  let cumulative = 0;
  return dates.map((date: string, i: number) => {
    const ret = nav[i] || 0;
    cumulative += ret;
    return {
      month: date,
      pnl: ret,
      cumulativePnl: cumulative,
      returnPct: ret * 100,
    };
  });
}

export async function fetchDailyPnL(conid: number): Promise<IBKRDailyPnL[]> {
  const res = await fetch(`${API_BASE}/pnl/daily/${conid}`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch daily P&L');
  
  const bars = json.data?.data || json.data?.bars || [];
  return bars.map((bar: any) => ({
    date: new Date(bar.t * 1000).toISOString().split('T')[0],
    open: bar.o,
    close: bar.c,
    high: bar.h,
    low: bar.l,
    volume: bar.v,
    pnl: bar.c - bar.o,
  }));
}

export async function fetchSearchContract(symbol: string): Promise<any[]> {
  const res = await fetch(`${API_BASE}/search/${encodeURIComponent(symbol)}`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Search failed');
  return json.data || [];
}

export async function fetchOptionsStrikes(conid: number, secType: string, month: string): Promise<any> {
  const res = await fetch(`${API_BASE}/options/strikes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conid, secType, month }),
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch strikes');
  return json.data;
}

export async function fetchOptionsChain(conid: number, secType: string, month: string, strike?: number, right?: string): Promise<any> {
  const res = await fetch(`${API_BASE}/options/chain`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conid, secType, month, strike, right }),
  });
  const json = await res.json();
  if (!json.success) throw new Error(json.error || 'Failed to fetch option chain');
  return json.data;
}
