/**
 * THS (同花顺) API Client
 * Wraps /api/ths/* endpoints for frontend use.
 */

const BASE = '/api/ths';

async function thsFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
  const qs = params ? '?' + new URLSearchParams(params).toString() : '';
  const res = await fetch(`${BASE}${path}${qs}`);
  if (!res.ok) throw new Error(`THS API error: ${res.status}`);
  const json = await res.json();
  if (!json.success) throw new Error(json.error?.message || 'THS request failed');
  return json.data;
}

// ── Search ──────────────────────────────────────────────────

export interface ThsSymbol {
  THSCODE: string;
  Name: string;
  MarketStr: string;
  Code: string;
  MarketDisplay: string;
}

export async function thsSearch(keyword: string): Promise<ThsSymbol[]> {
  return thsFetch<ThsSymbol[]>('/search', { keyword });
}

// ── K-lines ─────────────────────────────────────────────────

export interface KlineBar {
  时间: string;
  开盘价: number;
  最高价: number;
  最低价: number;
  收盘价: number;
  成交量: number;
  总金额?: number;
}

export interface KlineResult {
  data: KlineBar[];
  columns: string[];
}

export async function thsKlines(code: string, interval: string = '5m', count: number = 78): Promise<KlineResult> {
  return thsFetch<KlineResult>('/klines', { code, interval, count: String(count) });
}

// ── Intraday ────────────────────────────────────────────────

export interface IntradayBar {
  时间: string;
  价格: number;
  成交量: number;
  总金额?: number;
}

export async function thsIntraday(code: string): Promise<{ data: IntradayBar[]; columns: string[] }> {
  return thsFetch('/intraday', { code });
}

// ── Depth ───────────────────────────────────────────────────

export interface DepthRecord {
  代码?: string;
  名称?: string;
  买1价?: number;
  买1量?: number;
  卖1价?: number;
  卖1量?: number;
  [key: string]: any;
}

export async function thsDepth(codes: string[]): Promise<{ data: DepthRecord[]; columns: string[] }> {
  return thsFetch('/depth', { codes: codes.join(',') });
}

// ── Big Order Flow ──────────────────────────────────────────

export interface BigOrderRecord {
  时间: string;
  成交方向: string;
  成交量: number;
  总金额: number;
  [key: string]: any;
}

export async function thsBigOrder(code: string): Promise<{ data: BigOrderRecord[]; columns: string[] }> {
  return thsFetch('/big_order', { code });
}

// ── Quote (CN/HK/US) ───────────────────────────────────────

export interface QuoteRecord {
  [key: string]: any;
}

export async function thsQuoteCn(codes: string[], queryKey: string = '基础数据'): Promise<{ data: QuoteRecord[]; columns: string[] }> {
  return thsFetch('/quote/cn', { codes: codes.join(','), query_key: queryKey });
}

export async function thsQuoteHk(code: string, queryKey: string = '基础数据'): Promise<{ data: QuoteRecord[]; columns: string[] }> {
  return thsFetch('/quote/hk', { code, query_key: queryKey });
}

export async function thsQuoteUs(code: string, queryKey: string = '基础数据'): Promise<{ data: QuoteRecord[]; columns: string[] }> {
  return thsFetch('/quote/us', { code, query_key: queryKey });
}

// ── Index ───────────────────────────────────────────────────

export async function thsIndex(codes: string[]): Promise<{ data: QuoteRecord[]; columns: string[] }> {
  return thsFetch('/index', { codes: codes.join(',') });
}

// ── Sectors ─────────────────────────────────────────────────

export interface SectorItem {
  代码: string;
  名称: string;
}

export async function thsIndustry(): Promise<{ data: SectorItem[]; total: number }> {
  return thsFetch('/industry');
}

export async function thsConcept(): Promise<{ data: SectorItem[]; total: number }> {
  return thsFetch('/concept');
}

export async function thsBlockQuote(code: string, queryKey: string = '基础数据'): Promise<{ data: QuoteRecord[]; columns: string[] }> {
  return thsFetch('/block/quote', { code, query_key: queryKey });
}

export async function thsBlockConstituents(code: string): Promise<{ data: SectorItem[]; total: number }> {
  return thsFetch('/block/constituents', { code });
}

// ── Wencai NLP ──────────────────────────────────────────────

export async function thsWencai(query: string): Promise<{ data: Record<string, any>[]; columns: string[] }> {
  return thsFetch('/wencai', { query });
}

// ── News ────────────────────────────────────────────────────

export interface ThsNewsItem {
  Title: string;
  Properties: string;
  Time?: number;
  [key: string]: any;
}

export async function thsNews(): Promise<{ data: ThsNewsItem[] }> {
  return thsFetch('/news');
}

// ── Auction Anomaly ─────────────────────────────────────────

export async function thsAuctionAnomaly(market: string = 'USHA'): Promise<{ data: Record<string, any>[]; columns: string[] }> {
  return thsFetch('/auction/anomaly', { market });
}

// ── Forex / Futures ─────────────────────────────────────────

export async function thsForex(code: string): Promise<{ data: QuoteRecord[]; columns: string[] }> {
  return thsFetch('/forex', { code });
}

export async function thsFuture(code: string): Promise<{ data: QuoteRecord[]; columns: string[] }> {
  return thsFetch('/future', { code });
}
