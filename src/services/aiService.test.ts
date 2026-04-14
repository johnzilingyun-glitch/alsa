import { describe, it, expect } from 'vitest';
import { validateStockInfo, validateMarketOverview, extractJsonBlock, parseJsonResponse } from './aiService';
import { StockInfo, MarketOverview } from '../types';

describe('aiService Validation Logic', () => {
  const now = new Date();
  const beijingDate = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).format(now);

  describe('validateStockInfo', () => {
    it('should pass for valid stock info', () => {
      const validInfo: StockInfo = {
        symbol: '002532.SZ',
        name: '天山铝业',
        price: 15.13,
        change: -0.28,
        changePercent: -1.82,
        market: 'A-Share',
        currency: 'CNY',
        lastUpdated: `${beijingDate} 15:00:00 CST`,
        previousClose: 15.41
      };
      expect(() => validateStockInfo(validInfo)).not.toThrow();
    });

    it('should throw for invalid time format (missing CST)', () => {
      const invalidInfo: StockInfo = {
        symbol: '002532.SZ',
        name: '天山铝业',
        price: 15.13,
        change: -0.28,
        changePercent: -1.82,
        market: 'A-Share',
        currency: 'CNY',
        lastUpdated: `${beijingDate} 15:00:00 UTC+8`,
        previousClose: 15.41
      };
      expect(() => validateStockInfo(invalidInfo)).toThrow(/Invalid time format/);
    });

    it('should throw for non-positive price', () => {
      const invalidInfo: StockInfo = {
        symbol: '002532.SZ',
        name: '天山铝业',
        price: 0,
        change: 0,
        changePercent: 0,
        market: 'A-Share',
        currency: 'CNY',
        lastUpdated: `${beijingDate} 15:00:00 CST`,
        previousClose: 15.41
      };
      expect(() => validateStockInfo(invalidInfo)).toThrow(/Invalid price/);
    });

    it('should throw for calculation mismatch', () => {
      const invalidInfo: StockInfo = {
        symbol: '002532.SZ',
        name: '天山铝业',
        price: 15.13,
        change: 1.0, // Should be -0.28
        changePercent: -1.82,
        market: 'A-Share',
        currency: 'CNY',
        lastUpdated: `${beijingDate} 15:00:00 CST`,
        previousClose: 15.41
      };
      expect(() => validateStockInfo(invalidInfo)).toThrow(/Calculation mismatch/);
    });

    it('should throw for price outside daily range', () => {
      const invalidInfo: StockInfo = {
        symbol: '002532.SZ',
        name: '天山铝业',
        price: 16.0,
        change: 0.59,
        changePercent: 3.83,
        market: 'A-Share',
        currency: 'CNY',
        lastUpdated: `${beijingDate} 15:00:00 CST`,
        previousClose: 15.41,
        dailyHigh: 15.5,
        dailyLow: 15.0
      };
      expect(() => validateStockInfo(invalidInfo)).toThrow(/outside daily range/);
    });

    it('should throw for exceeding A-share price limit', () => {
      const invalidInfo: StockInfo = {
        symbol: '600076.SH',
        name: '康欣新材',
        price: 4.0,
        change: 0.86,
        changePercent: 27.38, // Way over 10%
        market: 'A-Share',
        currency: 'CNY',
        lastUpdated: `${beijingDate} 15:00:00 CST`,
        previousClose: 3.14
      };
      expect(() => validateStockInfo(invalidInfo)).toThrow(/exceeds market limit/);
    });

    it('should throw for currency mismatch', () => {
      const invalidInfo: StockInfo = {
        symbol: '002532.SZ',
        name: '天山铝业',
        price: 15.13,
        change: -0.28,
        changePercent: -1.82,
        market: 'A-Share',
        currency: 'USD',
        lastUpdated: `${beijingDate} 15:00:00 CST`,
        previousClose: 15.41
      };
      expect(() => validateStockInfo(invalidInfo)).toThrow(/Currency mismatch/);
    });
  });

  describe('validateMarketOverview', () => {
    it('should pass for valid market overview', () => {
      const validOverview: MarketOverview = {
        indices: [{ name: 'SSE', symbol: '000001.SS', price: 3000, change: 10, changePercent: 0.33, previousClose: 2990 }],
        topNews: [],
        sectorAnalysis: [],
        commodityAnalysis: [],
        recommendations: [],
        marketSummary: 'Market is bullish. Source: Sina Finance'
      };
      expect(() => validateMarketOverview(validOverview)).not.toThrow();
    });

    it('should throw if indices are missing', () => {
      const invalidOverview: MarketOverview = {
        indices: [],
        topNews: [],
        sectorAnalysis: [],
        commodityAnalysis: [],
        recommendations: [],
        marketSummary: 'Market is bullish.'
      };
      expect(() => validateMarketOverview(invalidOverview)).toThrow(/indices/);
    });
  });

  describe('JSON Parsing', () => {
    it('should extract JSON from markdown fences', () => {
      const raw = '```json\n{"a": 1}\n```';
      expect(extractJsonBlock(raw)).toBe('{"a": 1}');
    });

    it('should parse wrapped JSON responses', () => {
      const raw = '{"analysis": {"stockInfo": {"symbol": "AAPL"}}}';
      const parsed = parseJsonResponse<any>(raw);
      expect(parsed.stockInfo.symbol).toBe('AAPL');
    });

    it('should sanitize bad control characters inside JSON strings', () => {
      const raw = '{"summary":"第一行\n第二行","stockInfo":{"symbol":"AAPL"}}';
      const parsed = parseJsonResponse<any>(raw);
      expect(parsed.stockInfo.symbol).toBe('AAPL');
      expect(parsed.summary).toContain('第一行');
      expect(parsed.summary).toContain('第二行');
    });
  });
});
