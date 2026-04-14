import type { StockAnalysis } from '../types';

const DEFAULT_TTL_MS = 5 * 60 * 1000; // 5 minutes

interface CacheEntry {
  data: StockAnalysis;
  timestamp: number;
}

export class AnalysisCache {
  private cache = new Map<string, CacheEntry>();
  private ttlMs: number;

  constructor(ttlMs: number = DEFAULT_TTL_MS) {
    this.ttlMs = ttlMs;
  }

  get(symbol: string): StockAnalysis | undefined {
    const entry = this.cache.get(symbol);
    if (!entry) return undefined;

    if (Date.now() - entry.timestamp > this.ttlMs) {
      this.cache.delete(symbol);
      return undefined;
    }

    return entry.data;
  }

  set(symbol: string, data: StockAnalysis): void {
    this.cache.set(symbol, { data, timestamp: Date.now() });
  }

  invalidate(symbol: string): void {
    this.cache.delete(symbol);
  }

  clear(): void {
    this.cache.clear();
  }

  get size(): number {
    return this.cache.size;
  }
}

export const analysisCache = new AnalysisCache();
