import { describe, it, expect } from 'vitest';
import {
  StockAnalysisSchema,
  AgentDiscussionSchema,
  MarketOverviewSchema,
  validateResponse,
} from '../schemas';

describe('schemas', () => {
  describe('StockAnalysisSchema', () => {
    const validAnalysis = {
      stockInfo: {
        symbol: '600519.SS',
        name: '贵州茅台',
        price: 1680,
        change: 15.5,
        changePercent: 0.93,
        market: 'A-Share',
        currency: 'CNY',
        lastUpdated: '2026-04-01 15:00:00 CST',
      },
      summary: '茅台表现稳健',
      technicalAnalysis: '均线多头排列',
      fundamentalAnalysis: '盈利增长稳定',
      sentiment: 'Bullish',
      score: 82,
      recommendation: 'Buy',
      keyRisks: ['政策风险'],
      keyOpportunities: ['消费复苏'],
      news: [],
    };

    it('should validate a complete valid analysis', () => {
      const result = StockAnalysisSchema.safeParse(validAnalysis);
      expect(result.success).toBe(true);
    });

    it('should passthrough unknown fields', () => {
      const data = { ...validAnalysis, customField: 'extra' };
      const result = StockAnalysisSchema.safeParse(data);
      expect(result.success).toBe(true);
      if (result.success) {
        expect((result.data as any).customField).toBe('extra');
      }
    });

    it('should use catch defaults for missing sentiment', () => {
      const data = { ...validAnalysis, sentiment: 'InvalidValue' };
      const result = StockAnalysisSchema.safeParse(data);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.sentiment).toBe('Neutral');
      }
    });

    it('should use catch default for out-of-range score', () => {
      const data = { ...validAnalysis, score: 999 };
      const result = StockAnalysisSchema.safeParse(data);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.score).toBe(50); // catch default
      }
    });

    it('should use catch default for invalid recommendation', () => {
      const data = { ...validAnalysis, recommendation: 'Maybe' };
      const result = StockAnalysisSchema.safeParse(data);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.recommendation).toBe('Hold');
      }
    });

    it('should fail when stockInfo is missing', () => {
      const data = { summary: 'no stock info' };
      const result = StockAnalysisSchema.safeParse(data);
      expect(result.success).toBe(false);
    });

    it('should fail when stockInfo.symbol is missing', () => {
      const data = { ...validAnalysis, stockInfo: { ...validAnalysis.stockInfo, symbol: undefined } };
      const result = StockAnalysisSchema.safeParse(data);
      expect(result.success).toBe(false);
    });
  });

  describe('AgentDiscussionSchema', () => {
    it('should validate a valid discussion', () => {
      const data = {
        messages: [
          { role: 'Technical Analyst', content: '技术面分析', timestamp: '2026-04-01' },
        ],
        finalConclusion: '综合结论',
        tradingPlan: { entryPrice: '30.5', targetPrice: '35', stopLoss: '28' },
      };
      const result = AgentDiscussionSchema.safeParse(data);
      expect(result.success).toBe(true);
    });

    it('should passthrough extra discussion fields', () => {
      const data = {
        messages: [{ role: 'Risk Manager', content: '风险评估', timestamp: '2026-04-01' }],
        finalConclusion: '',
        scenarios: [{ name: 'Bull', probability: 0.4 }],
      };
      const result = AgentDiscussionSchema.safeParse(data);
      expect(result.success).toBe(true);
      if (result.success) {
        expect((result.data as any).scenarios).toHaveLength(1);
      }
    });

    it('should fail when messages array is missing', () => {
      const result = AgentDiscussionSchema.safeParse({ finalConclusion: 'test' });
      expect(result.success).toBe(false);
    });
  });

  describe('MarketOverviewSchema', () => {
    it('should validate a valid market overview', () => {
      const data = {
        indices: [
          { name: '上证综指', symbol: '000001.SS', price: 3200, change: 15, changePercent: 0.47 },
        ],
        marketSummary: '市场整体平稳',
      };
      const result = MarketOverviewSchema.safeParse(data);
      expect(result.success).toBe(true);
    });

    it('should NOT fail when indices is empty (due to catch default)', () => {
      const data = { indices: [], marketSummary: 'test' };
      const result = MarketOverviewSchema.safeParse(data);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.indices).toHaveLength(0);
      }
    });

    it('should use catch defaults for missing arrays', () => {
      const data = {
        indices: [{ name: 'SSE', symbol: '000001.SS', price: 3200, change: 10, changePercent: 0.3 }],
      };
      const result = MarketOverviewSchema.safeParse(data);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.commodityAnalysis).toEqual([]);
        expect(result.data.recommendations).toEqual([]);
        expect(result.data.sectorAnalysis).toEqual([]);
      }
    });
  });

  describe('validateResponse', () => {
    it('should return data on successful validation', () => {
      const data = {
        indices: [{ name: 'Test', symbol: 'T', price: 100, change: 1, changePercent: 1 }],
      };
      const result = validateResponse(MarketOverviewSchema, data, 'Test');
      expect(result.indices).toHaveLength(1);
    });

    it('should NOT throw on failed validation for indices (due to catch default)', () => {
      // MarketOverviewSchema has .catch([]) for indices, so it should succeed even with invalid indices
      const result = validateResponse(MarketOverviewSchema, { indices: 'invalid' }, 'Test');
      expect(result.indices).toEqual([]);
    });
  });
});
