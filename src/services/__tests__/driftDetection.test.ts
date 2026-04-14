import { describe, it, expect } from 'vitest';
import {
  relDrift,
  priceDriftThreshold,
  extractFromFundamentalTable,
  detectDrift,
  enforceGroundTruth,
} from '../driftDetection';
import type { StockAnalysis } from '../../types';

// ─── Minimal mock factory ─────────────────────────────────────────────────────

const makeAnalysis = (overrides: Record<string, any> = {}): StockAnalysis => ({
  stockInfo: {
    symbol: 'AAPL',
    name: 'Apple Inc.',
    price: 180,
    change: 2.5,
    changePercent: 1.4,
    market: 'US-Share',
    currency: 'USD',
    lastUpdated: '2026-04-10 10:00 CST',
    previousClose: 177.5,
    ...overrides.stockInfo,
  },
  news: [],
  summary: '',
  technicalAnalysis: '',
  fundamentalAnalysis: '',
  sentiment: 'Neutral',
  score: 50,
  recommendation: 'Hold',
  keyRisks: [],
  keyOpportunities: [],
  ...overrides,
});

// ─── relDrift ─────────────────────────────────────────────────────────────────

describe('relDrift', () => {
  it('returns 0 when api is 0', () => {
    expect(relDrift(100, 0)).toBe(0);
  });

  it('calculates correct relative drift', () => {
    expect(relDrift(105, 100)).toBeCloseTo(0.05);
    expect(relDrift(95, 100)).toBeCloseTo(0.05);
  });

  it('handles equal values', () => {
    expect(relDrift(50, 50)).toBe(0);
  });
});

// ─── priceDriftThreshold ──────────────────────────────────────────────────────

describe('priceDriftThreshold', () => {
  it('returns 5% for penny stocks (<5)', () => {
    expect(priceDriftThreshold(2)).toBe(0.05);
  });

  it('returns 3% for low-price stocks (<20)', () => {
    expect(priceDriftThreshold(15)).toBe(0.03);
  });

  it('returns 2% for mid-price stocks (<100)', () => {
    expect(priceDriftThreshold(50)).toBe(0.02);
  });

  it('returns 1.5% for high-price stocks (>=100)', () => {
    expect(priceDriftThreshold(300)).toBe(0.015);
  });
});

// ─── extractFromFundamentalTable ──────────────────────────────────────────────

describe('extractFromFundamentalTable', () => {
  const table = [
    { indicator: 'P/E Ratio', value: '25.3x', consensus: '', deviation: '', remark: '' },
    { indicator: '成交量', value: '12,345,678', consensus: '', deviation: '', remark: '' },
    { indicator: 'Market Cap', value: '$2.8T', consensus: '', deviation: '', remark: '' },
  ];

  it('extracts numeric value by keyword', () => {
    expect(extractFromFundamentalTable(table, 'p/e')).toBeCloseTo(25.3);
    expect(extractFromFundamentalTable(table, '成交量')).toBe(12345678);
  });

  it('tries multiple keywords in order', () => {
    expect(extractFromFundamentalTable(table, 'not_found', 'market cap')).toBeCloseTo(2.8);
  });

  it('returns null for undefined table', () => {
    expect(extractFromFundamentalTable(undefined, 'pe')).toBeNull();
  });

  it('returns null if no match', () => {
    expect(extractFromFundamentalTable(table, 'xyz_no_match')).toBeNull();
  });
});

// ─── detectDrift ──────────────────────────────────────────────────────────────

describe('detectDrift', () => {
  it('returns hasDrift=false when all fields match', () => {
    const analysis = makeAnalysis();
    const realtimeData = { price: 180, change: 2.5, changePercent: 1.4, previousClose: 177.5 };
    const result = detectDrift(analysis, realtimeData, []);
    expect(result.hasDrift).toBe(false);
    expect(result.signals).toHaveLength(0);
  });

  it('detects price drift for high-price stock (>1.5%)', () => {
    const analysis = makeAnalysis({ stockInfo: { price: 200 } }); // AI says 200
    const realtimeData = { price: 180 }; // API says 180 — 11% drift
    const result = detectDrift(analysis, realtimeData, []);
    expect(result.hasDrift).toBe(true);
    expect(result.signals.some(s => s.field === 'Price')).toBe(true);
  });

  it('does NOT flag price drift within threshold', () => {
    const analysis = makeAnalysis({ stockInfo: { price: 181 } }); // 0.56% drift
    const realtimeData = { price: 180 };
    const result = detectDrift(analysis, realtimeData, []);
    expect(result.signals.some(s => s.field === 'Price')).toBe(false);
  });

  it('detects PE drift (>15%)', () => {
    const analysis = makeAnalysis({ fundamentals: { pe: '30x' } });
    const realtimeData = { price: 180, pe: 25 }; // 20% drift
    const result = detectDrift(analysis, realtimeData, []);
    expect(result.hasDrift).toBe(true);
    expect(result.signals.some(s => s.field === 'PE')).toBe(true);
  });

  it('detects commodity variable drift in coreVariables', () => {
    const analysis = makeAnalysis({
      coreVariables: [
        { name: '黄金价格', value: 2600, unit: '$/oz', marketExpect: 2500, delta: '+4%', reason: '', evidenceLevel: '第三方监控' },
      ],
    });
    const realtimeData = { price: 180 };
    const commodities = [
      { symbol: 'GC=F', name: '伦敦金 (XAU)', price: 2350, changePercent: 0.5, unit: '$/oz' },
    ];
    const result = detectDrift(analysis, realtimeData, commodities);
    expect(result.hasDrift).toBe(true);
    expect(result.commodityDrifts).toHaveLength(1);
    expect(result.commodityDrifts[0].varName).toBe('黄金价格');
    expect(result.correctedData._commodityDrifts).toBeDefined();
  });

  it('detects commodity drift in industryAnchors', () => {
    const analysis = makeAnalysis({
      industryAnchors: [
        { variable: 'WTI原油', currentValue: '$90/bbl', weight: '高', monthlyChange: '+5%', logic: '成本' },
      ],
    });
    const realtimeData = { price: 180 };
    const commodities = [
      { symbol: 'CL=F', name: '原油 (WTI)', price: 72, changePercent: -1, unit: '$/bbl' },
    ];
    const result = detectDrift(analysis, realtimeData, commodities);
    expect(result.hasDrift).toBe(true);
    expect(result.commodityDrifts.some(d => d.varName === 'WTI原油')).toBe(true);
  });

  it('ignores commodities that do not match any variable', () => {
    const analysis = makeAnalysis({
      coreVariables: [
        { name: '碳酸锂价格', value: 150000, unit: '元/吨', marketExpect: 160000, delta: '', reason: '', evidenceLevel: '第三方监控' },
      ],
    });
    const realtimeData = { price: 180 };
    const commodities = [
      { symbol: 'GC=F', name: '伦敦金 (XAU)', price: 2350, changePercent: 0.5, unit: '$/oz' },
    ];
    const result = detectDrift(analysis, realtimeData, commodities);
    // 碳酸锂 not in commodity API, so no commodity drift
    expect(result.commodityDrifts).toHaveLength(0);
  });

  it('builds correctedData with all API fields', () => {
    const analysis = makeAnalysis({ stockInfo: { price: 200 } });
    const realtimeData = {
      price: 180, change: 2.5, changePercent: 1.4, previousClose: 177.5,
      dayHigh: 182, dayLow: 178, open: 179, volume: 50000000,
      marketCap: 2800000000000, pe: 28, lastUpdated: 'now', currency: 'USD',
    };
    const result = detectDrift(analysis, realtimeData, []);
    expect(result.hasDrift).toBe(true);
    expect(result.correctedData.price).toBe(180);
    expect(result.correctedData.volume).toBe(50000000);
    expect(result.correctedData.pe).toBe(28);
    expect(result.correctedData.open).toBe(179);
  });
});

// ─── enforceGroundTruth ───────────────────────────────────────────────────────

describe('enforceGroundTruth', () => {
  it('overrides all stockInfo fields from realtimeData', () => {
    const analysis = makeAnalysis();
    const realtimeData = {
      price: 185, change: 7.5, changePercent: 4.2,
      previousClose: 177.5, dayHigh: 186, dayLow: 179,
      lastUpdated: '2026-04-10 12:00 CST', currency: 'USD',
    };
    enforceGroundTruth(analysis, realtimeData);
    expect(analysis.stockInfo.price).toBe(185);
    expect(analysis.stockInfo.change).toBe(7.5);
    expect(analysis.stockInfo.changePercent).toBe(4.2);
    expect(analysis.stockInfo.dailyHigh).toBe(186);
    expect(analysis.stockInfo.dailyLow).toBe(179);
  });

  it('skips fields not in realtimeData', () => {
    const analysis = makeAnalysis();
    enforceGroundTruth(analysis, { price: 185 });
    expect(analysis.stockInfo.price).toBe(185);
    // Other fields unchanged
    expect(analysis.stockInfo.change).toBe(2.5);
  });
});
