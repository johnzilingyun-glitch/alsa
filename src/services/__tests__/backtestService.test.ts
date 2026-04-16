import { describe, it, expect } from 'vitest';
import { performBacktest, BacktestResult } from '../backtestService';
import { StockAnalysis } from '../../types';

function makeAnalysis(overrides: Partial<StockAnalysis> = {}): StockAnalysis {
  return {
    stockInfo: {
      symbol: '600519.SS',
      name: '贵州茅台',
      price: 1700,
      change: 10,
      changePercent: 0.59,
      market: 'A-Share',
      currency: 'CNY',
      lastUpdated: '2026-04-01 15:00:00 CST',
      previousClose: 1690,
    },
    summary: 'test',
    technicalAnalysis: '',
    fundamentalAnalysis: '',
    sentiment: 'Bullish',
    score: 80,
    recommendation: 'Buy',
    keyRisks: [],
    keyOpportunities: [],
    news: [],
    tradingPlan: {
      entryPrice: '1680',
      targetPrice: '1800',
      stopLoss: '1600',
      strategy: 'trend following',
      strategyRisks: '',
    },
    ...overrides,
  } as StockAnalysis;
}

describe('backtestService', () => {
  describe('performBacktest', () => {
    it('should return null when no previous analysis', () => {
      const current = makeAnalysis();
      expect(performBacktest(current, null)).toBeNull();
    });

    it('should detect Target Hit when current price >= previous target', () => {
      const previous = makeAnalysis({
        stockInfo: { ...makeAnalysis().stockInfo, price: 1600 },
        tradingPlan: { entryPrice: '1580', targetPrice: '1700', stopLoss: '1500', strategy: 'test', strategyRisks: '' },
      });
      const current = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 1720 } });
      const result = performBacktest(current, previous)!;
      expect(result.status).toBe('Target Hit');
      expect(result.accuracy).toBe(95);
    });

    it('should detect Stop Loss Hit when current price <= previous stop', () => {
      const previous = makeAnalysis({
        stockInfo: { ...makeAnalysis().stockInfo, price: 1700 },
        tradingPlan: { entryPrice: '1680', targetPrice: '1850', stopLoss: '1650', strategy: 'test', strategyRisks: '' },
      });
      const current = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 1640 } });
      const result = performBacktest(current, previous)!;
      expect(result.status).toBe('Stop Loss Hit');
      expect(result.accuracy).toBe(10);
    });

    it('should detect In Progress with correct direction', () => {
      const previous = makeAnalysis({
        stockInfo: { ...makeAnalysis().stockInfo, price: 1600 },
        tradingPlan: { entryPrice: '1580', targetPrice: '1800', stopLoss: '1500', strategy: 'test', strategyRisks: '' },
      });
      const current = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 1680 } });
      const result = performBacktest(current, previous)!;
      expect(result.status).toBe('In Progress');
      expect(result.accuracy).toBe(70); // direction matches
    });

    it('should detect In Progress with wrong direction', () => {
      const previous = makeAnalysis({
        stockInfo: { ...makeAnalysis().stockInfo, price: 1700 },
        tradingPlan: { entryPrice: '1680', targetPrice: '1850', stopLoss: '1600', strategy: 'test', strategyRisks: '' },
      });
      // Price went down but hasn't hit stop loss
      const current = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 1620 } });
      const result = performBacktest(current, previous)!;
      expect(result.status).toBe('In Progress');
      expect(result.accuracy).toBe(30); // direction wrong
    });

    it('should calculate return percentage', () => {
      const previous = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 1000 } });
      const current = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 1050 } });
      const result = performBacktest(current, previous)!;
      expect(result.returnSincePrev).toBe('+5.00%');
    });

    it('should handle negative returns', () => {
      const previous = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 1000 } });
      const current = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 950 } });
      const result = performBacktest(current, previous)!;
      expect(result.returnSincePrev).toBe('-5.00%');
    });

    it('should include learning point', () => {
      const previous = makeAnalysis({
        stockInfo: { ...makeAnalysis().stockInfo, price: 1600 },
        tradingPlan: { entryPrice: '1580', targetPrice: '1700', stopLoss: '1500', strategy: 'test', strategyRisks: '' },
      });
      const current = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 1720 } });
      const result = performBacktest(current, previous)!;
      expect(result.learningPoint).toContain('验证');
    });

    it('should calculate Sharpe and Sortino ratios when riskMetrics are available', () => {
      const previous = makeAnalysis({
        stockInfo: { ...makeAnalysis().stockInfo, price: 1000, lastUpdated: '2026-01-01 15:00:00 CST' },
        tradingPlan: { entryPrice: '980', targetPrice: '1200', stopLoss: '900', strategy: 'test', strategyRisks: '' },
      });
      const current = makeAnalysis({
        stockInfo: { 
          ...makeAnalysis().stockInfo, 
          price: 1100, 
          lastUpdated: '2026-04-01 15:00:00 CST',
          technicalIndicators: {
            ma5: 0, ma20: 0, ma60: 0, avgVolume5: 0, avgVolume20: 0,
            resistanceShort: 0, supportShort: 0, resistanceLong: 0, supportLong: 0,
            lastClose: 0,
            riskMetrics: { annualizedVolatility: 0.20, maxPositionLimit: 0.20, volatilityRegime: 'Normal' }
          } as any
        }
      });
      const result = performBacktest(current, previous)!;
      expect(result.sharpeRatio).toBeDefined();
      expect(result.sortinoRatio).toBeDefined();
      expect(result.sharpeRatio).toBeGreaterThan(0); // Pos return -> Pos Sharpe
    });

    it('should handle missing trading plan gracefully', () => {
      const previous = makeAnalysis({
        stockInfo: { ...makeAnalysis().stockInfo, price: 1600 },
        tradingPlan: undefined,
      });
      const current = makeAnalysis({ stockInfo: { ...makeAnalysis().stockInfo, price: 1650 } });
      const result = performBacktest(current, previous)!;
      expect(result.status).toBe('In Progress');
      expect(result.previousTarget).toBe('N/A');
      expect(result.previousStopLoss).toBe('N/A');
    });
  });
});
