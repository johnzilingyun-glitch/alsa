import { describe, it, expect } from 'vitest';
import { calculateQualityScore, getQualityLabel } from '../dataQualityService';
import { StockInfo } from '../../types';

function makeStockInfo(overrides: Partial<StockInfo> = {}): StockInfo {
  return {
    symbol: '600519.SS',
    name: '贵州茅台',
    price: 1700,
    change: 10,
    changePercent: 0.59,
    market: 'A-Share',
    currency: 'CNY',
    lastUpdated: new Date().toISOString(),
    previousClose: 1690,
    dataSource: 'Yahoo Finance API',
    ...overrides,
  } as StockInfo;
}

describe('dataQualityService', () => {
  describe('calculateQualityScore', () => {
    it('should return high score for complete fresh data from official source', () => {
      const result = calculateQualityScore(makeStockInfo());
      expect(result.score).toBe(100);
      expect(result.sourcePriority).toBe('Official API');
      expect(result.isStale).toBe(false);
      expect(result.missingFields).toEqual([]);
    });

    it('should penalize missing price', () => {
      const result = calculateQualityScore(makeStockInfo({ price: 0 }));
      expect(result.score).toBeLessThanOrEqual(70);
      expect(result.missingFields).toContain('Price');
    });

    it('should penalize missing previousClose', () => {
      const result = calculateQualityScore(makeStockInfo({ previousClose: 0 }));
      expect(result.score).toBe(90);
      expect(result.missingFields).toContain('Previous Close');
    });

    it('should penalize Google Search source', () => {
      const result = calculateQualityScore(makeStockInfo({ dataSource: 'Google Search' }));
      expect(result.score).toBe(90);
      expect(result.sourcePriority).toBe('Search/Scraped');
    });

    it('should penalize AI Inference source more heavily', () => {
      const result = calculateQualityScore(makeStockInfo({ dataSource: 'AI Inference' }));
      expect(result.score).toBe(75);
      expect(result.sourcePriority).toBe('AI Estimated');
    });

    it('should penalize stale data (>4 hours old)', () => {
      const staleDate = new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString();
      const result = calculateQualityScore(makeStockInfo({ lastUpdated: staleDate }));
      expect(result.score).toBe(85);
      expect(result.isStale).toBe(true);
    });

    it('should accumulate multiple penalties', () => {
      const staleDate = new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString();
      const result = calculateQualityScore(makeStockInfo({
        price: 0,
        previousClose: 0,
        dataSource: 'AI Inference',
        lastUpdated: staleDate,
      }));
      // -30 (price) -10 (prevClose) -25 (AI) -15 (stale) = 20
      expect(result.score).toBe(20);
    });

    it('should not go below 0', () => {
      const result = calculateQualityScore(makeStockInfo({
        price: -1,
        previousClose: undefined as any,
        dataSource: 'AI Inference',
        lastUpdated: new Date(0).toISOString(),
      }));
      expect(result.score).toBeGreaterThanOrEqual(0);
    });
  });

  describe('getQualityLabel', () => {
    it('should return High Precision for score >= 90', () => {
      const result = getQualityLabel(95);
      expect(result.label).toBe('high');
    });

    it('should return Reliable for score >= 70', () => {
      const result = getQualityLabel(75);
      expect(result.label).toBe('reliable');
    });

    it('should return Moderate for score >= 50', () => {
      const result = getQualityLabel(55);
      expect(result.label).toBe('moderate');
    });

    it('should return Low Confidence for score < 50', () => {
      const result = getQualityLabel(30);
      expect(result.label).toBe('low');
    });

    it('should return boundary value for exactly 90', () => {
      expect(getQualityLabel(90).label).toBe('high');
    });

    it('should return boundary value for exactly 70', () => {
      expect(getQualityLabel(70).label).toBe('reliable');
    });

    it('should return boundary value for exactly 50', () => {
      expect(getQualityLabel(50).label).toBe('moderate');
    });
  });
});
