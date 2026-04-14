import { describe, it, expect, vi, beforeEach } from 'vitest';
import { startAgentDiscussion } from '../services/discussionService';
import * as geminiService from '../services/geminiService';
import { clearCommoditiesCache } from '../services/marketService';
import { StockAnalysis } from '../types';

// Mock geminiService
vi.mock('../services/geminiService', async () => {
  const actual = await vi.importActual('../services/geminiService');
  return {
    ...actual as any,
    generateContentWithUsage: vi.fn(),
    generateAndParseJsonWithRetry: vi.fn(),
  };
});

describe('AI Discussion Commodity Data Integration', () => {
  const mockAnalysis: StockAnalysis = {
    stockInfo: {
      symbol: '600519.SS',
      name: '贵州茅台',
      price: 1800,
      change: 10,
      changePercent: 0.56,
      market: 'A-Share',
      currency: 'CNY',
      lastUpdated: '2026-03-30 15:00:00 CST',
      previousClose: 1790
    },
    summary: 'Test summary',
    technicalAnalysis: 'Test technical',
    fundamentalAnalysis: 'Test fundamental',
    sentiment: 'Bullish',
    score: 85,
    recommendation: 'Buy',
    keyRisks: [],
    keyOpportunities: [],
    news: []
  };

  const mockCommodities = [
    { name: '伦敦金 (XAU)', symbol: 'GC=F', price: 2588.5, changePercent: 1.2, unit: '$/oz', lastUpdated: '2026-03-30 15:00:00 CST' },
    { name: 'LME铜 (HG)', symbol: 'HG=F', price: 10450.2, changePercent: 0.8, unit: '$/lb', lastUpdated: '2026-03-30 15:00:00 CST' }
  ];

  const mockDiscussionResult = {
    messages: [],
    dataVerification: [],
    finalConclusion: 'Test conclusion',
    tradingPlan: {},
    scenarios: [],
    sensitivityFactors: [],
    expectationGap: {},
    controversialPoints: [],
    calculations: []
  };

  beforeEach(() => {
    vi.clearAllMocks();
    clearCommoditiesCache();
    // Mock fetch for commodities API — include .text() for adminService compatibility
    (global.fetch as any).mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('history')) {
        return Promise.resolve({ 
          ok: true, 
          headers: { get: () => 'application/json' },
          json: async () => [],
          text: async () => '[]',
        });
      }
      return Promise.resolve({ 
        ok: true, 
        json: async () => mockCommodities,
        text: async () => JSON.stringify(mockCommodities),
      });
    });
    
    // Mock AI response — mock generateAndParseJsonWithRetry directly
    (geminiService.generateAndParseJsonWithRetry as any).mockResolvedValue(mockDiscussionResult);
    
    // Also mock generateContentWithUsage for prompt capture
    (geminiService.generateContentWithUsage as any).mockResolvedValue({
      text: JSON.stringify(mockDiscussionResult)
    });
  });

  it('should include real-time commodity data in the prompt', async () => {
    await startAgentDiscussion(mockAnalysis);
    
    const lastCall = (geminiService.generateAndParseJsonWithRetry as any).mock.calls[0];
    const prompt = lastCall[1].contents;
    
    expect(prompt).toContain('**REAL-TIME COMMODITY DATA (GROUND TRUTH -');
    expect(prompt).toMatch(/\*\*REAL-TIME COMMODITY DATA \(GROUND TRUTH - \d{4}-\d{2}-\d{2}\)\*\*/);
    expect(prompt).toContain('| 商品种类 | 实时价格 | 24h 涨跌幅 | 单位 | 最后更新 |');
    expect(prompt).toContain('| --- | --- | --- | --- | --- |');
    expect(prompt).toContain('伦敦金 (XAU) (GC=F)');
    expect(prompt).toContain('$2588.5');
    expect(prompt).toContain('LME铜 (HG) (HG=F)');
    expect(prompt).toContain('$10450.2');
    expect(prompt).toContain('- **STRICT RELEVANCE CONSTRAINT (CRITICAL)**: Use commodity data ONLY if it is a DIRECT and MATERIAL driver');
  });

  it('should fetch commodities from the correct API endpoint', async () => {
    await startAgentDiscussion(mockAnalysis);
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('commodities'));
  });
});
