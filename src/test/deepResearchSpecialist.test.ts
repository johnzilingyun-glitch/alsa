import { describe, it, expect, vi, beforeEach } from 'vitest';
import { startAgentDiscussion } from '../services/discussionService';
import * as geminiService from '../services/geminiService';
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

describe('Deep Research Specialist Prompt Requirements', () => {
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
    // Mock fetch — include .text() for adminService compatibility
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
        json: async () => [],
        text: async () => '[]',
      });
    });

    // Mock AI response
    (geminiService.generateAndParseJsonWithRetry as any).mockResolvedValue(mockDiscussionResult);
    (geminiService.generateContentWithUsage as any).mockResolvedValue({
      text: JSON.stringify(mockDiscussionResult)
    });
  });

  it('should contain dynamic indicator selection and cross-verification instructions', async () => {
    await startAgentDiscussion(mockAnalysis);

    const lastCall = (geminiService.generateAndParseJsonWithRetry as any).mock.calls[0];
    const prompt = lastCall[1].contents;

    expect(prompt).toContain('responsible for full-dimension data penetration');
    expect(prompt).toContain('Select 4-6 most core industry-specific quantitative indicators');
    expect(prompt).toContain('API Cross-Verification (MANDATORY)');
    expect(prompt).toContain('Industry Core Variables & Macro Anchors (DYNAMIC)');
    expect(prompt).toContain('Data Accuracy');
  });
});
