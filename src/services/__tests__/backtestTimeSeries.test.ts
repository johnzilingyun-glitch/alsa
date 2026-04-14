import { describe, it, expect } from 'vitest';
import { buildBacktestTimeSeries, detectSystematicBias } from '../backtestTimeSeries';
import type { StockAnalysis, BacktestEntry } from '../../types';

function makeAnalysis(
  symbol: string,
  price: number,
  recommendation: string,
  targetPrice: string,
  stopLoss: string,
  lastUpdated: string,
): Partial<StockAnalysis> {
  return {
    stockInfo: {
      symbol,
      name: symbol,
      price,
      change: 0,
      changePercent: 0,
      market: 'A-Share',
      currency: 'CNY',
      lastUpdated,
      previousClose: price,
    },
    recommendation: recommendation as StockAnalysis['recommendation'],
    tradingPlan: { entryPrice: String(price), targetPrice, stopLoss, strategy: 'test', strategyRisks: '' },
  };
}

describe('backtestTimeSeries', () => {
  describe('buildBacktestTimeSeries', () => {
    it('returns empty series for no history', () => {
      const current = makeAnalysis('AAPL', 150, 'Buy', '170', '130', '2026-03-27T10:00:00Z') as StockAnalysis;
      const result = buildBacktestTimeSeries('AAPL', current, []);
      expect(result.symbol).toBe('AAPL');
      expect(result.entries).toHaveLength(0);
      expect(result.overallAccuracy).toBe(0);
    });

    it('builds entries from history comparing to current price', () => {
      const current = makeAnalysis('AAPL', 160, 'Buy', '180', '140', '2026-03-27') as StockAnalysis;
      const history = [
        makeAnalysis('AAPL', 150, 'Buy', '170', '130', '2026-03-20') as StockAnalysis,
        makeAnalysis('AAPL', 145, 'Buy', '165', '125', '2026-03-13') as StockAnalysis,
      ];
      const result = buildBacktestTimeSeries('AAPL', current, history);
      expect(result.entries).toHaveLength(2);
    });

    it('marks direction as correct when buy recommendation and price went up', () => {
      const current = makeAnalysis('AAPL', 160, 'Buy', '180', '140', '2026-03-27') as StockAnalysis;
      const history = [
        makeAnalysis('AAPL', 150, 'Buy', '170', '130', '2026-03-20') as StockAnalysis,
      ];
      const result = buildBacktestTimeSeries('AAPL', current, history);
      expect(result.entries[0].directionCorrect).toBe(true);
    });

    it('marks direction as incorrect when buy but price went down', () => {
      const current = makeAnalysis('AAPL', 140, 'Buy', '180', '130', '2026-03-27') as StockAnalysis;
      const history = [
        makeAnalysis('AAPL', 150, 'Buy', '170', '130', '2026-03-20') as StockAnalysis,
      ];
      const result = buildBacktestTimeSeries('AAPL', current, history);
      expect(result.entries[0].directionCorrect).toBe(false);
    });

    it('marks target hit when current price >= target', () => {
      const current = makeAnalysis('AAPL', 175, 'Buy', '180', '130', '2026-03-27') as StockAnalysis;
      const history = [
        makeAnalysis('AAPL', 150, 'Buy', '170', '130', '2026-03-20') as StockAnalysis,
      ];
      const result = buildBacktestTimeSeries('AAPL', current, history);
      expect(result.entries[0].targetHit).toBe(true);
    });

    it('calculates overall and direction accuracy', () => {
      const current = makeAnalysis('AAPL', 160, 'Buy', '180', '140', '2026-03-27') as StockAnalysis;
      const history = [
        makeAnalysis('AAPL', 150, 'Buy', '170', '130', '2026-03-24') as StockAnalysis,
        makeAnalysis('AAPL', 165, 'Sell', '140', '175', '2026-03-20') as StockAnalysis,
      ];
      const result = buildBacktestTimeSeries('AAPL', current, history);
      // First: bought at 150, now 160 → direction correct
      // Second: sold at 165, now 160 → direction correct (predicted down, went down)
      expect(result.directionAccuracy).toBe(100);
    });

    it('calculates max consecutive losses', () => {
      const current = makeAnalysis('AAPL', 100, 'Buy', '180', '80', '2026-03-27') as StockAnalysis;
      const history = [
        makeAnalysis('AAPL', 120, 'Buy', '140', '100', '2026-03-26') as StockAnalysis,
        makeAnalysis('AAPL', 130, 'Buy', '150', '110', '2026-03-25') as StockAnalysis,
        makeAnalysis('AAPL', 140, 'Buy', '160', '120', '2026-03-24') as StockAnalysis,
      ];
      const result = buildBacktestTimeSeries('AAPL', current, history);
      // All bought high, price dropped to 100 → all losses
      expect(result.maxConsecutiveLosses).toBe(3);
    });
  });

  describe('detectSystematicBias', () => {
    it('detects no bias for empty series', () => {
      const bias = detectSystematicBias({
        symbol: 'AAPL', entries: [], overallAccuracy: 0,
        directionAccuracy: 0, avgHoldingPeriodDays: 0, profitFactor: 0,
        maxConsecutiveLosses: 0, longestWinStreak: 0, sharpeRatio: 0,
      });
      expect(bias.hasBias).toBe(false);
      expect(bias.biasType).toBeNull();
    });

    it('detects bullish drift when consistently overestimates', () => {
      const entries: BacktestEntry[] = [
        { date: '2026-03-20', recommendation: 'Buy', targetPrice: 170, stopLoss: 130, actualPrice: 140, returnPercent: -6.7, directionCorrect: false, targetHit: false },
        { date: '2026-03-21', recommendation: 'Overweight', targetPrice: 180, stopLoss: 140, actualPrice: 145, returnPercent: -3.3, directionCorrect: false, targetHit: false },
        { date: '2026-03-22', recommendation: 'Buy', targetPrice: 175, stopLoss: 135, actualPrice: 142, returnPercent: -5, directionCorrect: false, targetHit: false },
      ];
      const bias = detectSystematicBias({
        symbol: 'AAPL', entries, overallAccuracy: 20,
        directionAccuracy: 0, avgHoldingPeriodDays: 7, profitFactor: 0,
        maxConsecutiveLosses: 3, longestWinStreak: 0, sharpeRatio: -1,
      });
      expect(bias.hasBias).toBe(true);
      expect(bias.biasType).toBe('bullish_drift');
      expect(bias.consecutiveCount).toBe(3);
    });

    it('detects target overshoot when targets systematically too ambitious', () => {
      const entries: BacktestEntry[] = [
        { date: '2026-03-20', recommendation: 'Buy', targetPrice: 200, stopLoss: 130, actualPrice: 165, returnPercent: 10, directionCorrect: true, targetHit: false },
        { date: '2026-03-21', recommendation: 'Buy', targetPrice: 210, stopLoss: 140, actualPrice: 170, returnPercent: 8, directionCorrect: true, targetHit: false },
        { date: '2026-03-22', recommendation: 'Buy', targetPrice: 220, stopLoss: 145, actualPrice: 175, returnPercent: 7, directionCorrect: true, targetHit: false },
      ];
      const bias = detectSystematicBias({
        symbol: 'AAPL', entries, overallAccuracy: 60,
        directionAccuracy: 100, avgHoldingPeriodDays: 7, profitFactor: 1.5,
        maxConsecutiveLosses: 0, longestWinStreak: 3, sharpeRatio: 1,
      });
      expect(bias.hasBias).toBe(true);
      expect(bias.biasType).toBe('target_overshoot');
    });

    it('returns no bias for well-calibrated predictions', () => {
      const entries: BacktestEntry[] = [
        { date: '2026-03-20', recommendation: 'Buy', targetPrice: 160, stopLoss: 140, actualPrice: 162, returnPercent: 8, directionCorrect: true, targetHit: true },
        { date: '2026-03-21', recommendation: 'Sell', targetPrice: 145, stopLoss: 165, actualPrice: 143, returnPercent: -5, directionCorrect: true, targetHit: true },
      ];
      const bias = detectSystematicBias({
        symbol: 'AAPL', entries, overallAccuracy: 90,
        directionAccuracy: 100, avgHoldingPeriodDays: 7, profitFactor: 2,
        maxConsecutiveLosses: 0, longestWinStreak: 2, sharpeRatio: 2,
      });
      expect(bias.hasBias).toBe(false);
    });
  });
});
