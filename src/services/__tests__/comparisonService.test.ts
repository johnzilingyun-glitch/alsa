import { describe, it, expect } from 'vitest';
import { buildComparisonResult, rankStocks } from '../comparisonService';
import type { StockAnalysis, ComparisonStock } from '../../types';

function makeQuickAnalysis(symbol: string, score: number, recommendation: string, pe?: string): StockAnalysis {
  return {
    stockInfo: {
      symbol,
      name: `${symbol} Inc`,
      price: 100,
      change: 1,
      changePercent: 1,
      market: 'A-Share',
      currency: 'CNY',
      lastUpdated: '2026-04-01',
      previousClose: 99,
    },
    news: [],
    summary: `Summary for ${symbol}`,
    technicalAnalysis: 'Tech',
    fundamentalAnalysis: 'Fund',
    sentiment: 'Neutral',
    score,
    recommendation: recommendation as StockAnalysis['recommendation'],
    keyRisks: [],
    keyOpportunities: [],
    fundamentals: pe ? { pe, pb: '3.0', roe: '15%', eps: '5.0', revenueGrowth: '10%', valuationPercentile: '50%' } : undefined,
  };
}

describe('comparisonService', () => {
  describe('buildComparisonResult', () => {
    it('builds comparison from analysis results', () => {
      const analyses = [
        makeQuickAnalysis('AAPL', 80, 'Buy', '25'),
        makeQuickAnalysis('GOOG', 70, 'Hold', '30'),
      ];
      const result = buildComparisonResult(analyses);
      expect(result.stocks).toHaveLength(2);
      expect(result.stocks[0].symbol).toBe('AAPL');
      expect(result.generatedAt).toBeTruthy();
    });

    it('extracts PE from fundamentals', () => {
      const analyses = [makeQuickAnalysis('AAPL', 80, 'Buy', '25.5')];
      const result = buildComparisonResult(analyses);
      expect(result.stocks[0].pe).toBe('25.5');
    });

    it('handles missing fundamentals gracefully', () => {
      const analyses = [makeQuickAnalysis('AAPL', 80, 'Buy')];
      const result = buildComparisonResult(analyses);
      expect(result.stocks[0].pe).toBeUndefined();
    });
  });

  describe('rankStocks', () => {
    it('ranks stocks by score descending', () => {
      const stocks: ComparisonStock[] = [
        { symbol: 'A', name: 'A', market: 'A-Share', score: 60, recommendation: 'Hold', riskLevel: 'Medium' },
        { symbol: 'B', name: 'B', market: 'A-Share', score: 90, recommendation: 'Buy', riskLevel: 'Low' },
        { symbol: 'C', name: 'C', market: 'A-Share', score: 75, recommendation: 'Buy', riskLevel: 'Medium' },
      ];
      const ranked = rankStocks(stocks);
      expect(ranked[0].symbol).toBe('B');
      expect(ranked[1].symbol).toBe('C');
      expect(ranked[2].symbol).toBe('A');
    });

    it('returns empty array for empty input', () => {
      expect(rankStocks([])).toEqual([]);
    });
  });
});
