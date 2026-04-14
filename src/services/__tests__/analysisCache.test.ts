import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AnalysisCache } from '../analysisCache';
import type { StockAnalysis } from '../../types';

function makeAnalysis(symbol: string, price = 100): StockAnalysis {
  return {
    stockInfo: {
      symbol,
      name: `${symbol} Inc`,
      price,
      change: 1,
      changePercent: 1,
      market: 'A-Share',
      currency: 'CNY',
      lastUpdated: new Date().toISOString(),
      previousClose: price - 1,
    },
    news: [],
    summary: 'test summary',
    technicalAnalysis: 'test tech',
    fundamentalAnalysis: 'test fundamental',
    sentiment: 'Neutral',
    score: 60,
    recommendation: 'Hold',
    keyRisks: [],
    keyOpportunities: [],
  };
}

describe('AnalysisCache', () => {
  let cache: AnalysisCache;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-27T10:00:00Z'));
    cache = new AnalysisCache();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns undefined for cache miss', () => {
    expect(cache.get('AAPL')).toBeUndefined();
  });

  it('caches and retrieves analysis for same symbol', () => {
    const analysis = makeAnalysis('AAPL');
    cache.set('AAPL', analysis);
    expect(cache.get('AAPL')).toEqual(analysis);
  });

  it('returns cached data within TTL (5 minutes)', () => {
    const analysis = makeAnalysis('AAPL');
    cache.set('AAPL', analysis);

    // Advance 4 minutes
    vi.advanceTimersByTime(4 * 60 * 1000);
    expect(cache.get('AAPL')).toEqual(analysis);
  });

  it('returns undefined after TTL expires (5 minutes)', () => {
    const analysis = makeAnalysis('AAPL');
    cache.set('AAPL', analysis);

    // Advance 5 minutes + 1ms
    vi.advanceTimersByTime(5 * 60 * 1000 + 1);
    expect(cache.get('AAPL')).toBeUndefined();
  });

  it('overwrites existing cache entry', () => {
    const v1 = makeAnalysis('AAPL', 100);
    const v2 = makeAnalysis('AAPL', 120);
    cache.set('AAPL', v1);
    cache.set('AAPL', v2);
    expect(cache.get('AAPL')?.stockInfo.price).toBe(120);
  });

  it('caches different symbols independently', () => {
    const aapl = makeAnalysis('AAPL');
    const goog = makeAnalysis('GOOG');
    cache.set('AAPL', aapl);
    cache.set('GOOG', goog);
    expect(cache.get('AAPL')?.stockInfo.symbol).toBe('AAPL');
    expect(cache.get('GOOG')?.stockInfo.symbol).toBe('GOOG');
  });

  it('clears all cached entries', () => {
    cache.set('AAPL', makeAnalysis('AAPL'));
    cache.set('GOOG', makeAnalysis('GOOG'));
    cache.clear();
    expect(cache.get('AAPL')).toBeUndefined();
    expect(cache.get('GOOG')).toBeUndefined();
  });

  it('invalidates a specific symbol', () => {
    cache.set('AAPL', makeAnalysis('AAPL'));
    cache.set('GOOG', makeAnalysis('GOOG'));
    cache.invalidate('AAPL');
    expect(cache.get('AAPL')).toBeUndefined();
    expect(cache.get('GOOG')).toBeDefined();
  });

  it('supports custom TTL', () => {
    const shortCache = new AnalysisCache(60 * 1000); // 1 minute
    shortCache.set('AAPL', makeAnalysis('AAPL'));

    vi.advanceTimersByTime(61 * 1000);
    expect(shortCache.get('AAPL')).toBeUndefined();
  });

  it('reports cache size', () => {
    expect(cache.size).toBe(0);
    cache.set('AAPL', makeAnalysis('AAPL'));
    expect(cache.size).toBe(1);
    cache.set('GOOG', makeAnalysis('GOOG'));
    expect(cache.size).toBe(2);
  });
});
