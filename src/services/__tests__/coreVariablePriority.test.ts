import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { normalizeCoreVariablesByPriority } from '../coreVariablePriority';
import type { CoreVariable, StockAnalysis, StockInfo, StockFundamentals } from '../../types';

function makeStockInfo(overrides: Partial<StockInfo> = {}): StockInfo {
  return {
    symbol: '000001',
    name: 'Test Stock',
    price: 10.5,
    change: 0.3,
    changePercent: 2.94,
    market: 'A-Share',
    currency: 'CNY',
    lastUpdated: '2026-06-24 15:00:00 CST',
    previousClose: 10.2,
    ...overrides,
  };
}

function makeFundamentals(overrides: Partial<StockFundamentals> = {}): StockFundamentals {
  return {
    pe: '15.5',
    pb: '2.1',
    roe: '12.5%',
    eps: '1.05',
    dividendYield: '3.2%',
    revenueGrowth: '8.5%',
    valuationPercentile: '45%',
    ...overrides,
  };
}

function makeStockAnalysis(overrides: Partial<StockAnalysis> = {}): StockAnalysis {
  return {
    stockInfo: makeStockInfo(),
    news: [],
    summary: 'Test summary',
    technicalAnalysis: 'Test technical analysis',
    fundamentalAnalysis: 'Test fundamental analysis',
    sentiment: 'Neutral',
    score: 60,
    recommendation: 'Hold',
    keyRisks: [],
    keyOpportunities: [],
    fundamentals: makeFundamentals(),
    ...overrides,
  };
}

function makeCoreVariable(overrides: Partial<CoreVariable> = {}): CoreVariable {
  return {
    name: 'PE',
    value: 16.0,
    unit: '倍',
    marketExpect: 15.0,
    delta: '+6.7% vs 预期',
    reason: '行业估值中枢上移',
    evidenceLevel: '财报',
    ...overrides,
  };
}

describe('coreVariablePriority', () => {
  describe('normalizeCoreVariablesByPriority', () => {
    it('returns undefined when coreVariables is undefined', () => {
      const analysis = makeStockAnalysis();
      const result = normalizeCoreVariablesByPriority(undefined, analysis);
      expect(result).toBeUndefined();
    });

    it('returns null when coreVariables is null', () => {
      const analysis = makeStockAnalysis();
      const result = normalizeCoreVariablesByPriority(null as unknown as CoreVariable[], analysis);
      // The function returns the input as-is when !coreVariables is true
      expect(result).toBeNull();
    });

    it('returns empty array when coreVariables is empty', () => {
      const analysis = makeStockAnalysis();
      const result = normalizeCoreVariablesByPriority([], analysis);
      expect(result).toEqual([]);
    });

    it('passes through unique variables unchanged (with audit enrichment)', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', source: 'Wind', dataDate: '2026-06-23' }),
        makeCoreVariable({ name: 'PB', source: 'Wind', dataDate: '2026-06-23' }),
        makeCoreVariable({ name: 'ROE', source: 'Bloomberg', dataDate: '2026-06-22' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(3);
      expect(result!.map(v => v.name)).toEqual(['PE', 'PB', 'ROE']);
    });

    it('deduplicates variables with the same normalized name, keeping the better source tier', () => {
      const analysis = makeStockAnalysis();
      // 'PE' normalizes to 'pe', ' P/E ' normalizes to 'pe' (whitespace stripped, / stripped)
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 14.0, source: 'Google', dataDate: '2026-06-20' }),
        makeCoreVariable({ name: ' P/E ', value: 15.5, source: 'Wind', dataDate: '2026-06-23' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      // Wind is Tier 1, Google is Tier 2, so Wind should win
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe(15.5);
      expect(result![0].source).toContain('Wind');
    });

    it('deduplicates by normalized name (ignoring case, spaces, parentheses)', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 14.0, source: 'Wind' }),
        makeCoreVariable({ name: ' P-E ', value: 15.0, source: 'Google' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      // Both normalize to 'pe', Wind (Tier 1) beats Google (Tier 2)
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe(14.0);
    });

    it('when same tier, keeps the one with newer date', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'EPS', value: 1.0, source: 'Reuters', dataDate: '2026-06-20' }),
        makeCoreVariable({ name: 'EPS', value: 1.2, source: 'Reuters', dataDate: '2026-06-23' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe(1.2);
    });

    it('when same tier and same date, keeps the first encountered', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'EPS', value: 1.0, source: 'Reuters', dataDate: '2026-06-23' }),
        makeCoreVariable({ name: 'EPS', value: 1.5, source: 'Reuters', dataDate: '2026-06-23' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe(1.0);
    });

    it('handles missing dataDate by returning 0 score (first item wins)', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'EPS', value: 1.0, source: 'Reuters' }),
        makeCoreVariable({ name: 'EPS', value: 1.5, source: 'Reuters' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe(1.0);
    });

    it('treats empty source as Tier 3', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'EPS', value: 1.0, source: 'SomeUnknownSource' }),
        makeCoreVariable({ name: 'EPS', value: 2.0, source: '' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      // Both are Tier 3 → first one wins
      // But since tier > 1, enrichFromApi runs: 'EPS' matches EPS mapping
      // so value is enriched to fundamentals.eps = '1.05'
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe('1.05');
      expect(result![0].source).toBe('API');
    });

    it('skips variables with empty normalized name', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: '' }),
        makeCoreVariable({ name: 'EPS', value: 2.0, source: 'Wind' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].name).toBe('EPS');
    });

    it('skips variables with whitespace-only name', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: '   ' }),
        makeCoreVariable({ name: 'EPS', value: 2.0, source: 'Wind' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].name).toBe('EPS');
    });

    it('enriches PE variable from fundamentals when source is low tier', () => {
      const analysis = makeStockAnalysis({
        fundamentals: makeFundamentals({ pe: '18.2' }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 16.0, source: 'Google' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe('18.2');
      expect(result![0].source).toBe('API');
    });

    it('enriches PB variable from fundamentals when source is low tier', () => {
      const analysis = makeStockAnalysis({
        fundamentals: makeFundamentals({ pb: '3.5' }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: '市净率', value: 2.0, source: 'Search' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe('3.5');
    });

    it('enriches ROE variable from fundamentals', () => {
      const analysis = makeStockAnalysis({
        fundamentals: makeFundamentals({ roe: '15.2%' }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'ROE', value: '12%', source: 'Yahoo' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe('15.2%');
    });

    it('enriches EPS variable from fundamentals', () => {
      const analysis = makeStockAnalysis({
        fundamentals: makeFundamentals({ eps: '2.50' }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'EPS', value: '2.00', source: 'Investing' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe('2.50');
    });

    it('enriches 股息率 (dividend yield) from fundamentals', () => {
      const analysis = makeStockAnalysis({
        fundamentals: makeFundamentals({ dividendYield: '4.5%' }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: '股息率', value: '3.0%', source: 'Search' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe('4.5%');
    });

    it('enriches price variable from stockInfo when key contains "price"', () => {
      const analysis = makeStockAnalysis({
        stockInfo: makeStockInfo({ price: 15.75 }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'targetPrice', value: 14.0, source: 'Search' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].value).toBe(15.75);
    });

    it('does not enrich when source is Tier 1 (authoritative)', () => {
      const analysis = makeStockAnalysis({
        fundamentals: makeFundamentals({ pe: '18.2' }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 16.0, source: 'Wind' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      // Wind is Tier 1, should NOT be enriched
      expect(result![0].value).toBe(16.0);
    });

    it('does not enrich when fundamental value is null', () => {
      const analysis = makeStockAnalysis({
        fundamentals: makeFundamentals({ pe: undefined as unknown as string }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 16.0, source: 'Google' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result![0].value).toBe(16.0);
    });

    it('does not enrich when fundamental value is empty string', () => {
      const analysis = makeStockAnalysis({
        fundamentals: makeFundamentals({ pe: '' }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 16.0, source: 'Google' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result![0].value).toBe(16.0);
    });

    it('adds "Other" as default source when source is missing and no enrichment match', () => {
      const analysis = makeStockAnalysis();
      // Use a name that does NOT match any enrichFromApi mapping
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'CustomMetric', value: 16.0, source: undefined }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result![0].source).toBe('Other');
    });

    it('falls back to stockInfo.lastUpdated for missing dataDate', () => {
      const analysis = makeStockAnalysis({
        stockInfo: makeStockInfo({ lastUpdated: '2026-06-24 15:00:00 CST' }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 16.0, source: 'Wind', dataDate: undefined }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result![0].dataDate).toBe('2026-06-24');
    });

    it('falls back to current date for missing dataDate and stockInfo.lastUpdated', () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2026-07-01T12:00:00Z'));

      const analysis = makeStockAnalysis({
        stockInfo: makeStockInfo({ lastUpdated: undefined as unknown as string }),
      });
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 16.0, source: 'Wind', dataDate: undefined }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result![0].dataDate).toBe('2026-07-01');

      vi.useRealTimers();
    });

    it('adds audit note to reason field', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 16.0, source: 'Wind', reason: '估值偏高' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result![0].reason).toContain('估值偏高');
      expect(result![0].reason).toContain('口径:');
      expect(result![0].reason).toContain('优先级1');
    });

    it('does not duplicate audit note if already present', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({
          name: 'PE',
          value: 16.0,
          source: 'Wind',
          reason: '估值偏高 | 口径: Wind 优先级1',
        }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      // The audit note should appear only once
      const auditCount = (result![0].reason!.match(/口径:/g) || []).length;
      expect(auditCount).toBe(1);
    });

    it('handles null/undefined variable values', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: null as unknown as number, source: 'Wind' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      // With null value and Wind as source (Tier 1), enrichFromApi won't run (tier > 1 check fails)
      expect(result![0].value).toBeNull();
    });

    it('handles mixed valid and invalid variables', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 15.0, source: 'Wind' }),
        makeCoreVariable({ name: '', value: 99.0, source: 'Wind' }),
        makeCoreVariable({ name: '  ', value: 88.0, source: 'Wind' }),
        makeCoreVariable({ name: 'PB', value: 2.5, source: 'Reuters' }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(2);
    });

    it('handles sourceTier for various sources correctly', () => {
      const analysis = makeStockAnalysis();

      // Test various source tier mappings via enrichment behavior
      // Tier 1 sources should NOT be enriched (they're already authoritative)
      const tier1Sources = ['Wind', 'Bloomberg', 'Reuters', '交易所', '路透', '上交所', '中国外汇交易中心'];
      const tier2Sources = ['Google', 'Yahoo', '东方财富', '同花顺', 'Investing'];
      const tier3Sources = ['SomeMedia', 'UnknownSource', 'UserInput'];

      for (const source of tier1Sources) {
        const variables: CoreVariable[] = [
          makeCoreVariable({ name: 'PE', value: 15.0, source, dataDate: '2026-06-23' }),
        ];
        // Tier 1 should NOT be enriched (tier ≤ 1 check prevents enrichFromApi)
        // The value should stay as 15.0
        const result = normalizeCoreVariablesByPriority(variables, analysis);
        expect(result![0].value).toBe(15.0);
      }

      // Tier 2 sources SHOULD be enriched - meaning value would change if fundamentals match
      for (const source of tier2Sources) {
        const variables: CoreVariable[] = [
          makeCoreVariable({ name: 'PE', value: 15.0, source, dataDate: '2026-06-23' }),
        ];
        const result = normalizeCoreVariablesByPriority(variables, analysis);
        // PE value from fundamentals would be used if matched
        expect(result![0].value).toBe('15.5'); // from makeFundamentals().pe
      }
    });

    it('handles undefined reason gracefully (no audit added)', () => {
      const analysis = makeStockAnalysis();
      const variables: CoreVariable[] = [
        makeCoreVariable({ name: 'PE', value: 16.0, source: 'Wind', reason: undefined }),
      ];

      const result = normalizeCoreVariablesByPriority(variables, analysis);
      expect(result).toHaveLength(1);
      expect(result![0].reason).toBeUndefined();
    });
  });
});
