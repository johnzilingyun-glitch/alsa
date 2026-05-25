/**
 * IBKR Client Portal API wrapper
 * 
 * Connects to the IBKR Client Portal Gateway (default: https://localhost:5000)
 * Documentation: https://www.interactivebrokers.com/api/doc.html
 */

import https from 'https';

const IBKR_BASE_URL = process.env.IBKR_GATEWAY_URL || 'https://localhost:5000';
const IBKR_ACCOUNT_ID = process.env.IBKR_ACCOUNT_ID || '';

// IBKR Client Portal uses self-signed cert
const agent = new https.Agent({ rejectUnauthorized: false });

interface FetchOptions {
  method?: string;
  body?: any;
}

async function ibkrFetch(path: string, options: FetchOptions = {}) {
  const url = `${IBKR_BASE_URL}${path}`;
  const res = await fetch(url, {
    method: options.method || 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: options.body ? JSON.stringify(options.body) : undefined,
    // @ts-ignore - Node fetch supports agent
    agent,
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`IBKR API error ${res.status}: ${text}`);
  }

  return res.json();
}

export async function getAccounts(): Promise<any[]> {
  const data = await ibkrFetch('/v1/api/portfolio/accounts');
  return data;
}

export async function getAccountSummary(accountId?: string): Promise<any> {
  const id = accountId || IBKR_ACCOUNT_ID;
  if (!id) {
    const accounts = await getAccounts();
    if (accounts.length === 0) throw new Error('No IBKR accounts found');
    return accounts[0];
  }
  const data = await ibkrFetch(`/v1/api/portfolio/${id}/summary`);
  return data;
}

export async function getPositions(accountId?: string): Promise<any[]> {
  const id = accountId || IBKR_ACCOUNT_ID;
  if (!id) {
    const accounts = await getAccounts();
    if (accounts.length === 0) return [];
    const acctId = accounts[0].accountId || accounts[0].id;
    const data = await ibkrFetch(`/v1/api/portfolio/${acctId}/positions/0`);
    return data;
  }
  const data = await ibkrFetch(`/v1/api/portfolio/${id}/positions/0`);
  return data;
}

export async function getPnL(): Promise<any> {
  const data = await ibkrFetch('/v1/api/iserver/account/pnl/partitioned');
  return data;
}

export async function getPerformance(accountId?: string, period?: string): Promise<any> {
  const id = accountId || IBKR_ACCOUNT_ID;
  const accounts = id ? [id] : (await getAccounts()).map((a: any) => a.accountId || a.id);
  
  const data = await ibkrFetch('/v1/api/pa/performance', {
    method: 'POST',
    body: {
      acctIds: accounts,
      freq: 'M', // Monthly
      period: period || '12M',
    },
  });
  return data;
}

export async function getTransactions(accountId?: string, days: number = 30): Promise<any> {
  const id = accountId || IBKR_ACCOUNT_ID;
  const accounts = id ? [id] : (await getAccounts()).map((a: any) => a.accountId || a.id);
  
  const data = await ibkrFetch('/v1/api/pa/transactions', {
    method: 'POST',
    body: {
      acctIds: accounts,
      days,
    },
  });
  return data;
}

export async function getDailyPnL(conid: number): Promise<any> {
  // Use market data history for daily P&L of specific position
  const data = await ibkrFetch(`/v1/api/iserver/marketdata/history?conid=${conid}&period=1M&bar=1d`);
  return data;
}

export async function searchContract(symbol: string): Promise<any> {
  const data = await ibkrFetch('/v1/api/iserver/secdef/search', {
    method: 'POST',
    body: { symbol, name: true },
  });
  return data;
}

export async function getOptionStrikes(conid: number, secType: string, month: string, exchange?: string): Promise<any> {
  const data = await ibkrFetch('/v1/api/iserver/secdef/strikes', {
    method: 'POST',
    body: { conid, sectype: secType, month, exchange: exchange || '' },
  });
  return data;
}

export async function getOptionChain(conid: number, secType: string = 'OPT', month: string = '', strike?: number, right?: string): Promise<any> {
  const body: any = { conid, sectype: secType, month };
  if (strike !== undefined) body.strike = strike;
  if (right) body.right = right;
  const data = await ibkrFetch('/v1/api/iserver/secdef/info', {
    method: 'POST',
    body,
  });
  return data;
}

export async function getSecDefByConids(conids: number[]): Promise<any> {
  const data = await ibkrFetch(`/v1/api/trsrv/secdef?conids=${conids.join(',')}`);
  return data;
}

export async function getMarketDataHistory(conid: number, period: string = '1Y', bar: string = '1d'): Promise<any> {
  const data = await ibkrFetch(`/v1/api/iserver/marketdata/history?conid=${conid}&period=${period}&bar=${bar}`);
  return data;
}

export async function getAuthStatus(): Promise<any> {
  try {
    const data = await ibkrFetch('/v1/api/iserver/auth/status', { method: 'POST' });
    return data;
  } catch {
    return { authenticated: false, connected: false };
  }
}
