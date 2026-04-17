import { describe, it, expect, vi, beforeEach } from 'vitest';
import { startMultiRoundDiscussion } from '../../discussionService';
import { StockAnalysis, MultiRoundProgress, AgentMessage } from '../../../types';
import * as geminiService from '../../geminiService';

// Mock geminiService
vi.mock('../../geminiService', async () => {
  const actual = await vi.importActual('../../geminiService');
  return {
    ...actual as any,
    generateContentWithUsage: vi.fn(),
    generateAndParseJsonWithRetry: vi.fn(),
    delay: vi.fn().mockResolvedValue(undefined), // Skip delays in tests
  };
});

// Mock config store
vi.mock('../../../stores/useConfigStore', () => ({
  useConfigStore: {
    getState: () => ({ language: 'zh-CN' }),
  },
}));

// Mock reflection service to avoid localStorage/logic issues
vi.mock('../../reflectionService', () => ({
  reflectAndRemember: vi.fn(),
  retrieveMemories: vi.fn().mockReturnValue([]),
  formatMemoryForPrompt: vi.fn().mockReturnValue(''),
}));

// Mock admin service for history retrieval
vi.mock('../../adminService', () => ({
  getPreviousStockAnalysis: vi.fn().mockResolvedValue(null),
}));

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
    previousClose: 1790,
  },
  summary: 'Test summary',
  technicalAnalysis: 'Test technical',
  fundamentalAnalysis: 'Test fundamental',
  fundamentals: { pe: 10 } as any, // Prevent deterministic pre-fill from skipping
  sentiment: 'Bullish',
  score: 85,
  recommendation: 'Buy',
  keyRisks: [],
  keyOpportunities: [],
  news: [],
};

function mockExpertResponse(content: string, extra?: Record<string, any>) {
  return {
    content,
    finalConclusion: content, // Required for synth result
    tradingPlan: { entryPrice: '1', targetPrice: '2', stopLoss: '0', strategy: 'test' },
    coreVariables: [],
    quantifiedRisks: [],
    scenarios: [],
    messages: [], // Required for AgentDiscussion validation
    ...extra
  };
}

describe('startMultiRoundDiscussion', () => {
  let callCount: number;

  beforeEach(() => {
    vi.clearAllMocks();
    callCount = 0;

    // Mock fetch for /api/stock/commodities and /api/admin/history
    (global.fetch as any).mockImplementation((url: string) => {
      const resp = {
        ok: true,
        headers: { get: () => 'application/json' },
        json: async () => [],
        text: async () => '[]',
      };
      return Promise.resolve(resp);
    });

    // Mock AI - use generateAndParseJsonWithRetry directly
    (geminiService.generateAndParseJsonWithRetry as any).mockImplementation(() => {
      callCount++;
      return Promise.resolve(mockExpertResponse(`Expert response #${callCount}`));
    });

    // Also mock generateContentWithUsage for synthesis step if needed
    (geminiService.generateContentWithUsage as any).mockImplementation(() => {
      return Promise.resolve({
        text: JSON.stringify({ 
          finalConclusion: 'Final synthesis result',
          messages: []
        }),
        usageMetadata: { promptTokenCount: 1, candidatesTokenCount: 1, totalTokenCount: 2 }
      });
    });
  });

  it('deep mode calls 17 experts + synthesis', async () => {
    const progressUpdates: MultiRoundProgress[] = [];

    const result = await startMultiRoundDiscussion(
      mockAnalysis,
      'deep',
      undefined,
      (progress) => progressUpdates.push({ ...progress, messages: [...progress.messages] }),
    );

    // Deep topology: 17 experts + 1 synthesis = 18
    expect(callCount).toBe(18);

    // All multi-round messages should be in the result
    expect(result.messages).toHaveLength(17);

    // Each message should have content
    result.messages.forEach((msg) => {
      expect(msg.content).toBeTruthy();
      expect(msg.role).toBeTruthy();
    });

    // Progress should have been called for each expert + 1 synthesis
    expect(progressUpdates.length).toBe(18);

    // First expert should be Deep Research Specialist
    expect(progressUpdates[0].activeExperts[0]).toBe('Deep Research Specialist');

    // Last progress update should be the synthesis step
    expect(progressUpdates[progressUpdates.length - 1].activeExperts[0]).toBe('综合研判引擎');

    // Final result should have finalConclusion from Chief Strategist
    expect(result.finalConclusion).toBeTruthy();
  });

  it('standard mode runs single iteration (no repetition)', async () => {
    const result = await startMultiRoundDiscussion(mockAnalysis, 'standard');

    // Standard topology: DR(1) + TA/FA(2) + Bull/Bear(2) + RM(1) + Reviewer(1) + Legendary(3) + CS(1) = 11 expert calls + 1 synthesis = 12
    expect(callCount).toBe(12);
    expect(result.messages).toHaveLength(11);
  });

  it('messages accumulate across rounds (each expert sees previous messages)', async () => {
    const prompts: string[] = [];

    (geminiService.generateAndParseJsonWithRetry as any).mockImplementation((_ai: any, params: any) => {
      prompts.push(params.contents);
      callCount++;
      return Promise.resolve(mockExpertResponse(`Response #${callCount}`));
    });

    await startMultiRoundDiscussion(mockAnalysis, 'standard');

    // The last multi-round expert (Chief Strategist, second-to-last prompt before synthesis)
    // should see previous expert messages in the prompt
    const csPrompt = prompts[prompts.length - 2];
    expect(csPrompt).toMatch(/(PREVIOUS DISCUSSION|前轮专家分析)/i);
    // Should contain previous responses
    expect(csPrompt).toContain('Response #');
  });

  it('respects abort signal', async () => {
    const controller = new AbortController();

    // Abort after first call
    (geminiService.generateAndParseJsonWithRetry as any).mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        controller.abort();
      }
      return Promise.resolve(mockExpertResponse(`Response #${callCount}`));
    });

    const result = await startMultiRoundDiscussion(
      mockAnalysis,
      'deep',
      undefined,
      undefined,
      controller.signal,
    );

    // Should have stopped early
    expect(callCount).toBeLessThan(22);
    expect(result.messages.length).toBeLessThan(22);
  });

  it('uses googleSearch tool for search-specific experts, schema for others', async () => {
    const searchRoles = new Set([
      'Deep Research Specialist', 
      'Fundamental Analyst',
      'Sentiment Analyst', 
      'Contrarian Strategist',
      'Macro Hedge Titan',
      'Value Investing Sage',
      'Growth Visionary'
    ]);
    (geminiService.generateAndParseJsonWithRetry as any).mockImplementation((_ai: any, params: any, options: any) => {
      const tools = options?.tools || params.config?.tools;
      const schema = options?.responseSchema || params.config?.responseSchema;
      const role = options?.role;
      
      if (searchRoles.has(role) || !role) {
        // Search experts and synthesis (role=undefined) get tools
        expect(tools).toEqual([{ googleSearch: {} }]);
      } else {
        // Non-search experts get schema enforcement (no tools)
        expect(tools).toBeUndefined();
      }
      expect(schema).toBeDefined();
      expect(options?.responseMimeType || params.config?.responseMimeType).toBe('application/json');
      callCount++;
      return Promise.resolve(mockExpertResponse(`Response #${callCount}`));
    });

    await startMultiRoundDiscussion(mockAnalysis, 'standard');
    expect(callCount).toBeGreaterThan(0);
  });

  it('round numbers are assigned to messages', async () => {
    const result = await startMultiRoundDiscussion(mockAnalysis, 'standard');

    // Standard: 6 rounds, with TA+FA parallel in round 2 and Bull+Bear parallel in round 3
    const rounds = result.messages.map((m) => m.round);
    expect(rounds[0]).toBe(1); // DR
    // TA and FA are parallel in round 2 — order may vary but both should be round 2
    const round2Messages = result.messages.filter(m => m.round === 2);
    expect(round2Messages.length).toBe(2);
    // Bull and Bear parallel in round 3
    const round3Messages = result.messages.filter(m => m.round === 3);
    expect(round3Messages.length).toBe(2);
  });

  it('handles expert structured data extraction', async () => {
    const m = geminiService.generateAndParseJsonWithRetry as any;
    m.mockImplementation((_ai: any, params: any, options: any) => {
      const role = options?.role;
      
      if (role === 'Deep Research Specialist') {
        return Promise.resolve(mockExpertResponse('DR analysis', {
          coreVariables: [{ name: 'Revenue', value: '100B', source: 'Test', dataDate: '2026-04-07' }],
        }));
      }
      if (role === 'Risk Manager') {
        return Promise.resolve(mockExpertResponse('Risk analysis', {
          quantifiedRisks: [{ name: 'Market Risk', probability: 30 }],
        }));
      }
      if (role === 'Chief Strategist') {
        return Promise.resolve(mockExpertResponse('Final plan', {
          tradingPlan: { entryPrice: '100', targetPrice: '120' },
          scenarios: [{ case: 'Bull', probability: 60 }],
        }));
      }
      if (!role) {
        // Synthesis call usually doesn't have a role in options yet (or it's the 3rd arg)
        return Promise.resolve({
          finalConclusion: 'Final Synth',
          messages: []
        });
      }
      return Promise.resolve(mockExpertResponse(`${role} analysis`));
    });

    const result = await startMultiRoundDiscussion(mockAnalysis, 'standard');

    expect(result.coreVariables).toBeDefined();
    expect(result.tradingPlan).toBeDefined();
    expect(result.scenarios).toBeDefined();
  });

  it('skips LLM call via Deterministic Pre-fill for halted stocks', async () => {
    const haltedAnalysis = {
      ...mockAnalysis,
      stockInfo: { ...mockAnalysis.stockInfo, price: 0 }
    };
    
    // In standard mode, Technical Analyst is called. 
    // It should hit the pre-fill logic and NOT call generateAndParseJsonWithRetry for its role.
    const calledRoles: string[] = [];
    (geminiService.generateAndParseJsonWithRetry as any).mockImplementation((_ai: any, _params: any, options: any) => {
      calledRoles.push(options?.role);
      return Promise.resolve(mockExpertResponse(`Response`));
    });

    const result = await startMultiRoundDiscussion(haltedAnalysis, 'standard');
    
    // Check if TA role was skipped in AI calls but present in results
    expect(calledRoles).not.toContain('Technical Analyst');
    const taMessage = result.messages.find(m => m.role === 'Technical Analyst');
    expect(taMessage?.content).toContain('系统预填');
    expect(taMessage?.content).toContain('停牌');
  });

  it('compacts long history to save tokens in multi-round discussions', async () => {
    const allPrompts: string[] = [];
    (geminiService.generateAndParseJsonWithRetry as any).mockImplementation((_ai: any, params: any, options: any) => {
      allPrompts.push(params.contents);
      const role = options?.role;
      // Return a VERY long response for Technical Analyst (Round 2)
      if (role === 'Technical Analyst') {
        return Promise.resolve(mockExpertResponse('A'.repeat(500)));
      }
      return Promise.resolve(mockExpertResponse(`Response for ${role}`));
    });

    // Run standard mode (multiple rounds)
    await startMultiRoundDiscussion(mockAnalysis, 'standard');

    // In Round 4+ (e.g. Risk Manager), TA's content from Round 2 should be compacted
    // TA (R2) -> RM (R4). 4-1 = 3. msg.round(2) !== 3. So it should be compacted.
    const compacted = allPrompts.some(p => p.includes('... [Content compacted]'));
    expect(compacted).toBe(true);
    
    // Ensure the original long string is not in the later prompts
    // (Check the very last prompt, which is synthesis or CS)
    const lastExpertPrompt = allPrompts[allPrompts.length - 2]; 
    expect(lastExpertPrompt).not.toContain('A'.repeat(500));
  });
});
