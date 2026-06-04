import { describe, expect, it } from 'vitest';
import { generateQuantitativeBaseline } from '../quantitativeModeling';
import type { StockAnalysis } from '../../types';

describe('generateQuantitativeBaseline', () => {
  it('uses the numeric intrinsic value estimate when projecting scenarios', () => {
    const result = generateQuantitativeBaseline({
      stockInfo: {
        symbol: 'TEST',
        name: 'Test Co',
        price: 100,
        change: 0,
        changePercent: 0,
        market: 'US-Share',
        currency: 'USD',
        lastUpdated: '2026-06-01T00:00:00.000Z',
        previousClose: 100,
      },
      fundamentals: {
        pe: '12',
        pb: '1.2',
        roe: '20',
        eps: '1',
        revenueGrowth: '8',
        valuationPercentile: '40',
        netProfitGrowth: '5',
        debtToEquity: '0.3',
        grossMargin: '35',
      },
      technicalIndicators: {
        ma5: null,
        ma20: null,
        ma60: null,
        avgVolume5: null,
        avgVolume20: null,
        resistanceShort: null,
        supportShort: null,
        resistanceLong: null,
        supportLong: null,
      },
      news: [],
      summary: '',
      technicalAnalysis: '',
      fundamentalAnalysis: '',
      sentiment: 'Neutral',
      score: 0,
      recommendation: 'Hold',
      keyRisks: [],
      keyOpportunities: [],
    } satisfies StockAnalysis);

    expect(result.scenarios).toHaveLength(3);
    expect(result.scenarios?.[1].targetPrice).toBe('150.00');
    expect(result.expectedValueOutcome?.expectedPrice).toBeCloseTo(142.625, 3);
  });
});

