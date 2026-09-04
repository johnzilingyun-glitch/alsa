import { describe, it, expect } from 'vitest';
import {
  normalizeSignalAction,
  parsePlanPrice,
  resolvePlanEntry,
  alertIsShort,
  buildSignalAlertFromAnalysis,
} from '../signalAction';
import type { StockAnalysis } from '../../types';

describe('normalizeSignalAction', () => {
  it('passes through canonical values (case-insensitive)', () => {
    expect(normalizeSignalAction('buy')).toBe('buy');
    expect(normalizeSignalAction('Sell')).toBe('sell');
    expect(normalizeSignalAction('HOLD')).toBe('hold');
    expect(normalizeSignalAction('watch')).toBe('watch');
  });

  it('maps broker recommendation values', () => {
    expect(normalizeSignalAction('Buy')).toBe('buy');
    expect(normalizeSignalAction('Overweight')).toBe('buy');
    expect(normalizeSignalAction('Underweight')).toBe('sell');
    expect(normalizeSignalAction('Sell')).toBe('sell');
    expect(normalizeSignalAction('Hold')).toBe('hold');
    expect(normalizeSignalAction('Neutral')).toBe('hold');
  });

  it('maps Chinese rating tokens', () => {
    expect(normalizeSignalAction('买入')).toBe('buy');
    expect(normalizeSignalAction('增持')).toBe('buy');
    expect(normalizeSignalAction('卖出')).toBe('sell');
    expect(normalizeSignalAction('减持')).toBe('sell');
    expect(normalizeSignalAction('看空')).toBe('sell');
    expect(normalizeSignalAction('持有')).toBe('hold');
    expect(normalizeSignalAction('中性')).toBe('hold');
    expect(normalizeSignalAction('观望')).toBe('watch');
  });

  it('prefix negation resolves to conservative watch', () => {
    expect(normalizeSignalAction('不建议买入')).toBe('watch');
    expect(normalizeSignalAction('Not Buy')).toBe('watch');
    expect(normalizeSignalAction('避免追高')).toBe('watch');
  });

  it('unknown / ambiguous / empty input resolves to watch', () => {
    expect(normalizeSignalAction(null)).toBe('watch');
    expect(normalizeSignalAction(undefined)).toBe('watch');
    expect(normalizeSignalAction('')).toBe('watch');
    expect(normalizeSignalAction('some random text')).toBe('watch');
    expect(normalizeSignalAction('buy or sell')).toBe('watch');
  });
});

describe('parsePlanPrice', () => {
  it('accepts numbers and plain numeric strings', () => {
    expect(parsePlanPrice(26.5)).toBe(26.5);
    expect(parsePlanPrice('26.5')).toBe(26.5);
    expect(parsePlanPrice('26.5元')).toBe(26.5);
  });

  it('rejects percentages (the old parseNum read "15%" as 15)', () => {
    expect(parsePlanPrice('15%')).toBe(0);
    expect(parsePlanPrice('+15~20%')).toBe(0);
    expect(parsePlanPrice('-8%')).toBe(0);
    expect(parsePlanPrice('预期 +15~20%')).toBe(0);
  });

  it('rejects hedged / qualifier text', () => {
    expect(parsePlanPrice('约26.5')).toBe(0);
    expect(parsePlanPrice('26.5左右')).toBe(0);
    expect(parsePlanPrice('市价附近')).toBe(0);
    expect(parsePlanPrice('现价 / 区间待定')).toBe(0);
    expect(parsePlanPrice('不推荐')).toBe(0);
  });

  it('takes the midpoint of range strings', () => {
    expect(parsePlanPrice('25.8-26.5')).toBeCloseTo(26.15);
    expect(parsePlanPrice('25.8~26.5')).toBeCloseTo(26.15);
    expect(parsePlanPrice('25.8至26.5')).toBeCloseTo(26.15);
  });

  it('rejects invalid / empty / non-positive values', () => {
    expect(parsePlanPrice('')).toBe(0);
    expect(parsePlanPrice(undefined)).toBe(0);
    expect(parsePlanPrice(0)).toBe(0);
    expect(parsePlanPrice(-5)).toBe(0);
    expect(parsePlanPrice(NaN)).toBe(0);
  });
});

describe('resolvePlanEntry', () => {
  it('prefers a directly parseable entryPrice', () => {
    expect(resolvePlanEntry({ entryPrice: '26.5' })).toBe(26.5);
  });

  it('falls back to the entryLow/entryHigh midpoint', () => {
    expect(resolvePlanEntry({ entryPrice: '市价附近', entryLow: '25.8', entryHigh: '26.5' })).toBeCloseTo(26.15);
  });

  it('uses a single-sided bound when only one side exists', () => {
    expect(resolvePlanEntry({ entryLow: '25.8' })).toBe(25.8);
    expect(resolvePlanEntry({ entryHigh: '26.5' })).toBe(26.5);
  });

  it('returns 0 when nothing is usable', () => {
    expect(resolvePlanEntry({})).toBe(0);
    expect(resolvePlanEntry(null)).toBe(0);
    expect(resolvePlanEntry({ entryPrice: '不推荐' })).toBe(0);
  });
});

describe('alertIsShort', () => {
  it('explicit action wins over price geometry', () => {
    // sell with target ABOVE entry (weird geometry) is still short
    expect(alertIsShort({ action: 'sell', entry_price: 25, target_price: 30 })).toBe(true);
    // buy with target BELOW entry is still long
    expect(alertIsShort({ action: 'buy', entry_price: 25, target_price: 20 })).toBe(false);
  });

  it('hold/watch and legacy rows fall back to target<entry geometry', () => {
    expect(alertIsShort({ entry_price: 30, target_price: 25 })).toBe(true);
    expect(alertIsShort({ entry_price: 25, target_price: 30 })).toBe(false);
    expect(alertIsShort({ action: 'hold', entry_price: 30, target_price: 25 })).toBe(true);
    expect(alertIsShort({ action: 'watch', entry_price: 25, target_price: 30 })).toBe(false);
  });
});

function makeAnalysis(overrides: Partial<StockAnalysis>): StockAnalysis {
  return {
    stockInfo: {
      symbol: '600378',
      name: '昊华科技',
      market: 'A-Share',
      price: 24.5,
      change: 0,
      changePercent: 0,
      currency: 'CNY',
      lastUpdated: '2026-09-01 10:00:00 CST',
      previousClose: 24.5,
    },
    news: [],
    summary: '',
    technicalAnalysis: '',
    fundamentalAnalysis: '',
    sentiment: 'Bearish',
    score: 50,
    recommendation: 'Sell',
    keyRisks: [],
    keyOpportunities: [],
    ...overrides,
  } as StockAnalysis;
}

describe('buildSignalAlertFromAnalysis', () => {
  it('builds a draft with the normalized action for a complete plan', () => {
    const built = buildSignalAlertFromAnalysis(makeAnalysis({
      tradingPlan: {
        action: 'buy',
        entryPrice: '25.0',
        targetPrice: '30.0',
        stopLoss: '23.0',
        strategy: 's',
        strategyRisks: 'r',
      },
    }));
    expect(built.ok).toBe(true);
    if (built.ok) {
      expect(built.draft.action).toBe('buy');
      expect(built.draft.entry_price).toBe(25.0);
      expect(built.draft.target_price).toBe(30.0);
      expect(built.draft.stop_loss).toBe(23.0);
    }
  });

  it('derives action from recommendation when tradingPlan.action is absent (frontend-direct path)', () => {
    const built = buildSignalAlertFromAnalysis(makeAnalysis({
      recommendation: 'Sell',
      tradingPlan: {
        entryPrice: '26.0',
        targetPrice: '21.0',
        stopLoss: '28.5',
        strategy: 's',
        strategyRisks: 'r',
      },
    }));
    expect(built.ok).toBe(true);
    if (built.ok) expect(built.draft.action).toBe('sell');
  });

  it('REFUSES to fabricate prices for a Sell plan without entry (昊华科技 regression)', () => {
    // Old code: entry = parseNum('不推荐') || 24.5, target = ... || entry*1.15,
    // stop = ... || entry*0.92 → a fabricated LONG signal. New code must refuse.
    const built = buildSignalAlertFromAnalysis(makeAnalysis({
      tradingPlan: {
        action: 'sell',
        entryPrice: '不推荐',
        targetPrice: '21.0',
        stopLoss: '26.5',
        strategy: 's',
        strategyRisks: 'r',
      },
    }));
    expect(built.ok).toBe(false);
    if (!built.ok) expect(built.reason).toContain('入场价');
  });

  it('refuses when target or stop is not a usable absolute price', () => {
    const base = {
      action: 'buy',
      entryPrice: '25.0',
      strategy: 's',
      strategyRisks: 'r',
    } as const;
    const noTarget = buildSignalAlertFromAnalysis(makeAnalysis({
      tradingPlan: { ...base, targetPrice: '预期 +15~20%', stopLoss: '23' },
    }));
    expect(noTarget.ok).toBe(false);
    if (!noTarget.ok) expect(noTarget.reason).toContain('目标价');

    const noStop = buildSignalAlertFromAnalysis(makeAnalysis({
      tradingPlan: { ...base, targetPrice: '30', stopLoss: '技术面破位 -8%' },
    }));
    expect(noStop.ok).toBe(false);
    if (!noStop.ok) expect(noStop.reason).toContain('止损价');
  });

  it('hold/watch without entry may anchor tracking on the live price', () => {
    const built = buildSignalAlertFromAnalysis(makeAnalysis({
      tradingPlan: {
        action: 'hold',
        entryPrice: '',
        targetPrice: '30.0',
        stopLoss: '22.0',
        strategy: 's',
        strategyRisks: 'r',
      },
    }));
    expect(built.ok).toBe(true);
    if (built.ok) {
      expect(built.draft.action).toBe('hold');
      expect(built.draft.entry_price).toBe(24.5); // live price as tracking anchor
    }
  });

  it('refuses hold/watch when neither entry nor live price exists', () => {
    const analysis = makeAnalysis({
      stockInfo: {
        symbol: 'X', name: 'X', market: 'A-Share', price: 0,
        change: 0, changePercent: 0, currency: 'CNY', lastUpdated: 'CST', previousClose: 0,
      },
      tradingPlan: {
        action: 'watch',
        entryPrice: '',
        targetPrice: '30.0',
        stopLoss: '22.0',
        strategy: 's',
        strategyRisks: 'r',
      },
    });
    const built = buildSignalAlertFromAnalysis(analysis);
    expect(built.ok).toBe(false);
  });
});
