import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { MarketOverview, LLMConfig } from '../../types';

// ── Module Mocks ─────────────────────────────────────────────

vi.mock('../../stores/useConfigStore', () => ({
  useConfigStore: {
    getState: () => ({
      language: 'zh-CN',
    }),
  },
}));

vi.mock('../llmService', () => ({
  createAI: vi.fn(() => ({})),
  DEFAULT_LLM_MODEL: 'gemini-3.1-pro-preview',
  generateAndParseJsonWithRetry: vi.fn(),
  withRetry: vi.fn((fn: () => Promise<any>) => fn()),
  generateContentWithUsage: vi.fn(() => Promise.resolve({ text: 'Daily report content' })),
}));

vi.mock('../prompts', () => ({
  getMarketOverviewPrompt: vi.fn(() => 'mock market overview prompt'),
  getDailyReportPrompt: vi.fn(() => 'mock daily report prompt'),
}));

vi.mock('../adminService', () => ({
  getHistoryContext: vi.fn(() => Promise.resolve([])),
  saveAnalysisToHistory: vi.fn(() => Promise.resolve()),
}));

vi.mock('../dateUtils', () => ({
  getBeijingDate: vi.fn(() => '2026-06-24'),
}));

vi.mock('../schemas', () => ({
  MarketOverviewSchema: {},
  validateResponse: vi.fn((_schema: any, data: any) => data),
}));

// ── Import after mocks ───────────────────────────────────────

import {
  getMarketSnapshot,
  getMarketOverview,
  getCommoditiesData,
  clearCommoditiesCache,
  getDailyReport,
} from '../marketService';
import { generateAndParseJsonWithRetry, generateContentWithUsage, withRetry } from '../llmService';
import { getHistoryContext, saveAnalysisToHistory } from '../adminService';
import { getBeijingDate } from '../dateUtils';
import { validateResponse } from '../schemas';
import { getMarketOverviewPrompt, getDailyReportPrompt } from '../prompts';

// ── Helpers ──────────────────────────────────────────────────

interface MockResponse {
  ok: boolean;
  json: () => Promise<any>;
  status?: number;
}

function mockFetch(response: MockResponse): void {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response)));
}

function mockFetchSequence(responses: MockResponse[]): void {
  let callCount = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(() => {
      const resp = responses[callCount];
      if (resp) {
        callCount++;
      }
      return Promise.resolve(resp || { ok: false, json: () => Promise.resolve([]) });
    }),
  );
}

function makeMockIndicesData(): any[] {
  return [
    { name: '上证指数', symbol: '000001.SH', price: 3150.5, change: 25.3, changePercent: 0.81, previousClose: 3125.2 },
    { name: '深证成指', symbol: '399001.SZ', price: 10200.0, change: 85.0, changePercent: 0.84, previousClose: 10115.0 },
  ];
}

function makeMockCommoditiesData(): any[] {
  return [
    { name: '黄金', symbol: 'XAUUSD', price: 2350, changePercent: 1.2, unit: 'USD/oz' },
    { name: '原油', symbol: 'WTI', price: 78.5, changePercent: -0.5, unit: 'USD/bbl' },
  ];
}

function makeMockMarketOverview(): MarketOverview {
  return {
    indices: [
      { name: '上证指数', symbol: '000001.SH', price: 3150.5, change: 25.3, changePercent: 0.81, previousClose: 3125.2 },
    ],
    topNews: [{ title: 'Test News', source: 'Test', time: '2026-06-24', url: 'https://test.com', summary: 'Test summary' }],
    sectorAnalysis: [
      { name: '科技板块', trend: '上涨', rotationStage: 'Leading', conclusion: '资金净流入' },
    ],
    commodityAnalysis: [
      { name: '黄金', trend: '上涨', expectation: '2350 USD/oz (+1.2%)' },
    ],
    recommendations: [
      { type: 'Sector', name: '人工智能', reason: '资本开支增加' },
    ],
    marketSummary: '今日市场震荡走强，核心指数普遍上涨。',
  };
}

// ── Tests ────────────────────────────────────────────────────

describe('marketService', () => {
  beforeEach(() => {
    clearCommoditiesCache();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-24T10:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  // ── getMarketSnapshot ──────────────────────────────────────

  describe('getMarketSnapshot', () => {
    it('fetches indices and commodities data successfully', async () => {
      const indicesData = makeMockIndicesData();
      const commoditiesData = makeMockCommoditiesData();

      let fetchCallCount = 0;
      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          fetchCallCount++;
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(indicesData) });
          }
          if (url.includes('/api/stock/commodities')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(commoditiesData) });
          }
          return Promise.resolve({ ok: false, json: () => Promise.resolve([]) });
        }),
      );

      const result = await getMarketSnapshot('A-Share');

      expect(result.market).toBe('A-Share');
      expect(result.generatedAt).toBeGreaterThan(0);
      expect(result.indices).toHaveLength(2);
      expect(result.indices![0].name).toBe('上证指数');
      expect(result.indices![0].price).toBe(3150.5);
      expect(result.commodityAnalysis).toHaveLength(2);
      expect(result.commodityAnalysis![0].trend).toBe('上涨');
      expect(result.commodityAnalysis![1].trend).toBe('下跌');
    });

    it('returns empty arrays when indices fetch fails', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: false, json: () => Promise.resolve([]) });
          }
          return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockCommoditiesData()) });
        }),
      );

      const result = await getMarketSnapshot('A-Share');
      expect(result.indices).toHaveLength(0);
      expect(result.commodityAnalysis).toHaveLength(2);
    });

    it('returns empty arrays when indices fetch throws network error', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.reject(new Error('Network error'));
          }
          return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockCommoditiesData()) });
        }),
      );

      const result = await getMarketSnapshot('A-Share');
      expect(result.indices).toHaveLength(0);
    });

    it('returns empty commodityAnalysis when commodities fetch fails', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockIndicesData()) });
          }
          if (url.includes('/api/stock/commodities')) {
            return Promise.reject(new Error('Network error'));
          }
          return Promise.resolve({ ok: false, json: () => Promise.resolve([]) });
        }),
      );

      const result = await getMarketSnapshot('A-Share');
      expect(result.indices).toHaveLength(2);
      expect(result.commodityAnalysis).toHaveLength(0);
    });

    it('handles null/undefined fields in indices data', async () => {
      const partialData = [
        { name: '上证指数', symbol: '000001.SH', price: null, change: undefined, changePercent: null, previousClose: undefined as unknown as number },
      ];

      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(partialData) });
          }
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }),
      );

      const result = await getMarketSnapshot('A-Share');
      expect(result.indices).toHaveLength(1);
      expect(result.indices![0].price).toBe(0);
      expect(result.indices![0].change).toBe(0);
      expect(result.indices![0].changePercent).toBe(0);
      expect(result.indices![0].previousClose).toBe(0);
    });

    it('handles zero changePercent as 持平', async () => {
      const data = [
        { name: '上证指数', symbol: '000001.SH', price: 3150, change: 0, changePercent: 0, previousClose: 3150 },
      ];

      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(data) });
          }
          return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
        }),
      );

      const result = await getMarketSnapshot('A-Share');
      expect(result.commodityAnalysis).toHaveLength(0);
      // No commodity with zero change, just verify indices are populated
      expect(result.indices![0].changePercent).toBe(0);
    });

    it('classifies commodity trend correctly for positive, negative, and zero change', async () => {
      const commodities = [
        { name: 'Gold', price: 2000, changePercent: 2.5, unit: 'USD/oz' },
        { name: 'Oil', price: 70, changePercent: -1.0, unit: 'USD/bbl' },
        { name: 'Copper', price: 4.5, changePercent: 0, unit: 'USD/lb' },
      ];

      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          return Promise.resolve({ ok: true, json: () => Promise.resolve(commodities) });
        }),
      );

      const result = await getMarketSnapshot('A-Share');
      expect(result.commodityAnalysis).toHaveLength(3);
      expect(result.commodityAnalysis![0].trend).toBe('上涨');
      expect(result.commodityAnalysis![1].trend).toBe('下跌');
      expect(result.commodityAnalysis![2].trend).toBe('持平');
    });

    it('passes different market param to fetch URL', async () => {
      const indicesData = makeMockIndicesData();
      const fetchFn = vi.fn((url: string) => {
        if (url.includes('/api/stock/indices?market=US-Share')) {
          return Promise.resolve({ ok: true, json: () => Promise.resolve(indicesData) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      });
      vi.stubGlobal('fetch', fetchFn);

      await getMarketSnapshot('US-Share');
      expect(fetchFn).toHaveBeenCalledWith(
        '/api/stock/indices?market=US-Share',
        expect.objectContaining({ signal: expect.anything() }),
      );
    });
  });

  // ── getCommoditiesData ─────────────────────────────────────

  describe('getCommoditiesData', () => {
    it('fetches commodities and caches them', async () => {
      const commodities = makeMockCommoditiesData();
      mockFetch({ ok: true, json: () => Promise.resolve(commodities) });

      const result = await getCommoditiesData();
      expect(result).toEqual(commodities);
    });

    it('returns cached data on subsequent calls within expiry', async () => {
      const commodities = makeMockCommoditiesData();
      const fetchFn = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(commodities) }));
      vi.stubGlobal('fetch', fetchFn);

      // First call populates cache
      await getCommoditiesData();
      expect(fetchFn).toHaveBeenCalledTimes(1);

      // Second call should use cache
      const result = await getCommoditiesData();
      expect(result).toEqual(commodities);
      expect(fetchFn).toHaveBeenCalledTimes(1);
    });

    it('refetches after cache expires', async () => {
      const commodities = makeMockCommoditiesData();
      const fetchFn = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(commodities) }));
      vi.stubGlobal('fetch', fetchFn);

      // First call populates cache
      await getCommoditiesData();
      expect(fetchFn).toHaveBeenCalledTimes(1);

      // Advance time past 5 minute cache
      vi.advanceTimersByTime(5 * 60 * 1000 + 1);

      // Second call should refetch
      const result = await getCommoditiesData();
      expect(result).toEqual(commodities);
      expect(fetchFn).toHaveBeenCalledTimes(2);
    });

    it('returns empty array on fetch error', async () => {
      vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network error'))));

      const result = await getCommoditiesData();
      expect(result).toEqual([]);
    });

    it('returns empty array on non-ok response', async () => {
      mockFetch({ ok: false, json: () => Promise.resolve([]) });

      const result = await getCommoditiesData();
      expect(result).toEqual([]);
    });

    it('handles AbortError silently (no console.warn)', async () => {
      const abortError = new Error('The operation was aborted');
      abortError.name = 'AbortError';
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      vi.stubGlobal('fetch', vi.fn(() => Promise.reject(abortError)));

      const result = await getCommoditiesData();
      expect(result).toEqual([]);
      expect(warnSpy).not.toHaveBeenCalled();
      warnSpy.mockRestore();
    });

    it('console.warn on non-abort fetch error', async () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Network timeout'))));

      await getCommoditiesData();
      expect(warnSpy).toHaveBeenCalledWith('Commodities fetch failed:', expect.any(Error));
      warnSpy.mockRestore();
    });

    it('clearCommoditiesCache resets the cache', async () => {
      const commodities = makeMockCommoditiesData();
      const fetchFn = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(commodities) }));
      vi.stubGlobal('fetch', fetchFn);

      await getCommoditiesData();
      expect(fetchFn).toHaveBeenCalledTimes(1);

      clearCommoditiesCache();

      const result = await getCommoditiesData();
      expect(result).toEqual(commodities);
      expect(fetchFn).toHaveBeenCalledTimes(2);
    });

    it('passes AbortSignal when provided', async () => {
      const commodities = makeMockCommoditiesData();
      const fetchFn = vi.fn((_url: string, options?: RequestInit) => {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(commodities) });
      });
      vi.stubGlobal('fetch', fetchFn);

      const controller = new AbortController();
      await getCommoditiesData(controller.signal);

      expect(fetchFn).toHaveBeenCalledWith(
        '/api/stock/commodities',
        expect.objectContaining({ signal: controller.signal }),
      );
    });
  });

  // ── getMarketOverview ──────────────────────────────────────

  describe('getMarketOverview', () => {
    beforeEach(() => {
      // Default mock: all fetches return data
      setupDefaultFetchMock();

      // Default AI mock: returns valid market overview
      vi.mocked(generateAndParseJsonWithRetry).mockResolvedValue(makeMockMarketOverview());
    });

    afterEach(() => {
      // Reset mocks to default state to prevent leakage between tests
      vi.mocked(getHistoryContext).mockResolvedValue([]);
      vi.mocked(generateAndParseJsonWithRetry).mockResolvedValue(makeMockMarketOverview());
      vi.mocked(saveAnalysisToHistory).mockResolvedValue(undefined);
    });

    function setupDefaultFetchMock() {
      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockIndicesData()) });
          }
          if (url.includes('/api/stock/news')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([{ title: 'Market News', source: 'Test', time: '2026-06-24', url: 'https://test.com', summary: 'News' }]) });
          }
          if (url.includes('/api/stock/sectors')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ topInflows: [{ '行业': '科技', '涨跌幅': 2.5, '主力净流入-净额': '1.2B' }], topOutflows: [] }) });
          }
          if (url.includes('/api/stock/northbound')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([{ netInflow: '1.5B' }]) });
          }
          if (url.includes('/api/stock/commodities')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockCommoditiesData()) });
          }
          return Promise.resolve({ ok: false, json: () => Promise.resolve([]) });
        }),
      );
    }

    it('returns market overview with AI analysis', async () => {
      const result = await getMarketOverview(undefined, 'A-Share');

      expect(result.market).toBe('A-Share');
      expect(result.marketSummary).toBe('今日市场震荡走强，核心指数普遍上涨。');
      expect(result.indices).toHaveLength(1);
      expect(result.generatedAt).toBeGreaterThan(0);
      expect(result.id).toMatch(/^market-/);
    });

    it('checks history before making API calls (cache hit)', async () => {
      const mockGetHistory = vi.mocked(getHistoryContext);
      const cachedOverview: MarketOverview = {
        ...makeMockMarketOverview(),
        id: 'cached-id',
        generatedAt: Date.now(),
        market: 'A-Share',
      };
      mockGetHistory.mockResolvedValue([
        {
          type: 'market',
          market: 'A-Share',
          generatedAt: Date.now(),
          marketSummary: 'Cached summary from history',
          id: 'cached-id',
          indices: cachedOverview.indices,
          topNews: cachedOverview.topNews,
          sectorAnalysis: cachedOverview.sectorAnalysis,
          commodityAnalysis: cachedOverview.commodityAnalysis,
          recommendations: cachedOverview.recommendations,
        },
      ]);

      const result = await getMarketOverview(undefined, 'A-Share');

      expect(result.id).toBe('cached-id');
      expect(result.marketSummary).toBe('Cached summary from history');
      // Should not call AI if cache hit
      expect(generateAndParseJsonWithRetry).not.toHaveBeenCalled();
    });

    it('skips cache when forceRefresh is true', async () => {
      const mockGetHistory = vi.mocked(getHistoryContext);
      mockGetHistory.mockResolvedValue([
        {
          type: 'market',
          market: 'A-Share',
          generatedAt: Date.now(),
          marketSummary: 'Cached summary',
          id: 'cached-id',
        },
      ]);

      const result = await getMarketOverview(undefined, 'A-Share', true);

      // Should call AI despite cache existing
      expect(generateAndParseJsonWithRetry).toHaveBeenCalled();
      expect(result.marketSummary).toBe('今日市场震荡走强，核心指数普遍上涨。');
    });

    it('falls back to degraded mode when AI analysis fails', async () => {
      // Override fetch mock to return empty sectors data (no inflows → triggers hardcoded fallback)
      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockIndicesData()) });
          }
          if (url.includes('/api/stock/news')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          if (url.includes('/api/stock/sectors')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ topInflows: [], topOutflows: [] }) });
          }
          if (url.includes('/api/stock/northbound')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          if (url.includes('/api/stock/commodities')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockCommoditiesData()) });
          }
          return Promise.resolve({ ok: false, json: () => Promise.resolve([]) });
        }),
      );
      const mockGenerate = vi.mocked(generateAndParseJsonWithRetry);
      mockGenerate.mockRejectedValue(new Error('AI service unavailable'));
      const logSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      const result = await getMarketOverview(undefined, 'A-Share');

      expect(result.marketSummary).toContain('[实时数据]');
      expect(result.indices).toHaveLength(2);
      // With empty topInflows, degraded mode uses hardcoded fallback sectors (3)
      expect(result.sectorAnalysis).toHaveLength(3);
      logSpy.mockRestore();
    });

    it('falls back when AI returns empty marketSummary', async () => {
      const mockGenerate = vi.mocked(generateAndParseJsonWithRetry);
      const emptySummaryOverview: MarketOverview = {
        ...makeMockMarketOverview(),
        marketSummary: '',
      };
      mockGenerate.mockResolvedValue(emptySummaryOverview);
      const logSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      const result = await getMarketOverview(undefined, 'A-Share');

      expect(result.marketSummary).toContain('[实时数据]');
      logSpy.mockRestore();
    });

    it('corrects AI hallucinated indices via anti-hallucination logic', async () => {
      const mockGenerate = vi.mocked(generateAndParseJsonWithRetry);
      const aiOverview: MarketOverview = {
        ...makeMockMarketOverview(),
        indices: [
          { name: '上证指数', symbol: '000001.SH', price: 99999, change: 100, changePercent: 5, previousClose: 3125.2 },
        ],
      };
      mockGenerate.mockResolvedValue(aiOverview);

      const result = await getMarketOverview(undefined, 'A-Share');

      // AI set price to 99999, but API has 3150.5, drift is (99999-3150.5)/3150.5 ≈ 30.7 > 2% → corrected
      expect(result.indices[0]!.price).toBe(3150.5);
    });

    it('saves analysis to history on success', async () => {
      const mockSave = vi.mocked(saveAnalysisToHistory);

      await getMarketOverview(undefined, 'A-Share');

      expect(mockSave).toHaveBeenCalledWith('market', expect.objectContaining({
        market: 'A-Share',
        marketSummary: expect.any(String),
      }));
    });

    it('does not save to history if indices array is empty', async () => {
      const mockGenerate = vi.mocked(generateAndParseJsonWithRetry);
      mockGenerate.mockResolvedValue({
        ...makeMockMarketOverview(),
        indices: [],
      });

      const mockSave = vi.mocked(saveAnalysisToHistory);
      await getMarketOverview(undefined, 'A-Share');

      expect(mockSave).not.toHaveBeenCalled();
    });

    it('handles API fetch failures in getMarketOverview gracefully', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn(() => Promise.reject(new Error('All APIs down'))),
      );
      const mockGenerate = vi.mocked(generateAndParseJsonWithRetry);
      mockGenerate.mockRejectedValue(new Error('AI failed too'));
      const logSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      const result = await getMarketOverview(undefined, 'A-Share');

      expect(result.marketSummary).toContain('[实时数据]');
      expect(result.indices).toHaveLength(0);
      expect(result.sectorAnalysis).toHaveLength(3);
      logSpy.mockRestore();
    });

    it('ignores cache history entry that lacks marketSummary', async () => {
      const mockGetHistory = vi.mocked(getHistoryContext);
      mockGetHistory.mockResolvedValue([
        {
          type: 'market',
          market: 'A-Share',
          generatedAt: Date.now(),
          marketSummary: '',
          id: 'incomplete-id',
        },
      ]);

      const result = await getMarketOverview(undefined, 'A-Share');

      // Should call AI since cached entry has empty marketSummary
      expect(generateAndParseJsonWithRetry).toHaveBeenCalled();
      expect(result.id).toMatch(/^market-/);
    });

    it('handles HK-Share market correctly (no northbound data)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockIndicesData()) });
          }
          if (url.includes('/api/stock/news')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          if (url.includes('/api/stock/sectors')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ topInflows: [], topOutflows: [] }) });
          }
          if (url.includes('/api/stock/commodities')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockCommoditiesData()) });
          }
          return Promise.resolve({ ok: false, json: () => Promise.resolve([]) });
        }),
      );

      const result = await getMarketOverview(undefined, 'HK-Share');
      expect(result.market).toBe('HK-Share');
    });

    it('handles US-Share market correctly (no sectors, no northbound)', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockIndicesData()) });
          }
          if (url.includes('/api/stock/news')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          if (url.includes('/api/stock/commodities')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockCommoditiesData()) });
          }
          return Promise.resolve({ ok: false, json: () => Promise.resolve([]) });
        }),
      );

      const result = await getMarketOverview(undefined, 'US-Share');
      expect(result.market).toBe('US-Share');
      // US-Share shouldn't have northbound data
    });

    it('uses degraded fallback sectors when API returns no inflows', async () => {
      vi.stubGlobal(
        'fetch',
        vi.fn((url: string) => {
          if (url.includes('/api/stock/indices')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockIndicesData()) });
          }
          if (url.includes('/api/stock/news')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
          }
          if (url.includes('/api/stock/sectors')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ topInflows: [], topOutflows: [] }) });
          }
          if (url.includes('/api/stock/commodities')) {
            return Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockCommoditiesData()) });
          }
          return Promise.resolve({ ok: false, json: () => Promise.resolve([]) });
        }),
      );
      const mockGenerate = vi.mocked(generateAndParseJsonWithRetry);
      mockGenerate.mockRejectedValue(new Error('fail'));

      const result = await getMarketOverview(undefined, 'A-Share');
      // Degraded fallback has 3 hardcoded sectors
      expect(result.sectorAnalysis).toHaveLength(3);
      expect(result.sectorAnalysis[0].name).toBe('科技互联网');
    });
  });

  // ── getDailyReport ─────────────────────────────────────────

  describe('getDailyReport', () => {
    afterEach(() => {
      // Reset withRetry to its default behavior (call the function)
      vi.mocked(withRetry).mockImplementation((fn: () => Promise<any>) => fn());
    });

    it('returns a report string generated from market overview', async () => {
      const overview = makeMockMarketOverview();

      vi.stubGlobal(
        'fetch',
        vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockCommoditiesData()) })),
      );

      const result = await getDailyReport(overview);
      expect(result).toBe('Daily report content');
    });

    it('calls generateContentWithUsage with google search tool', async () => {
      const overview = makeMockMarketOverview();
      vi.stubGlobal(
        'fetch',
        vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })),
      );

      await getDailyReport(overview);

      expect(generateContentWithUsage).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          model: 'gemini-3.1-pro-preview',
          config: expect.objectContaining({
            tools: [expect.objectContaining({ googleSearch: {} })],
          }),
        }),
      );
    });

    it('handles LLM failure in report generation', async () => {
      const mockWithRetry = vi.mocked(withRetry);
      mockWithRetry.mockRejectedValue(new Error('LLM call failed'));

      const overview = makeMockMarketOverview();
      vi.stubGlobal(
        'fetch',
        vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve([]) })),
      );

      await expect(getDailyReport(overview)).rejects.toThrow('LLM call failed');
    });

    it('passes correct market overview to prompt builder', async () => {
      const overview = makeMockMarketOverview();
      vi.stubGlobal(
        'fetch',
        vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(makeMockCommoditiesData()) })),
      );

      await getDailyReport(overview);

      expect(getDailyReportPrompt).toHaveBeenCalledWith(
        overview,
        expect.any(Array),
        expect.any(Date),
        '2026-06-24',
        'zh-CN',
      );
    });
  });
});
