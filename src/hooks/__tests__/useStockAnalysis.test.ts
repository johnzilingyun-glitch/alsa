import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useStockAnalysis } from '../useStockAnalysis';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { useUIStore } from '../../stores/useUIStore';
import { useMarketStore } from '../../stores/useMarketStore';
import { useDiscussionStore } from '../../stores/useDiscussionStore';
import { useScenarioStore } from '../../stores/useScenarioStore';
import { useJobQueueStore } from '../../stores/useJobQueueStore';

const mockStartAnalysis = vi.fn();
const mockStatus = { current: 'idle' as string };
const mockResult = { current: null as any };
const mockError = { current: null as string | null };
const mockInsufficientBalance = { current: false };

vi.mock('../useAnalysisJob', () => ({
  useAnalysisJob: vi.fn(() => ({
    startAnalysis: mockStartAnalysis,
    status: mockStatus.current,
    result: mockResult.current,
    error: mockError.current,
    jobId: 'job_1',
    insufficientBalance: mockInsufficientBalance.current,
  })),
}));

function resetStores() {
  useAnalysisStore.setState({
    symbol: '',
    market: 'A-Share',
    analysis: null,
    chatMessage: '',
    chatHistory: [],
    lastJobId: null,
  });
  useUIStore.setState({
    analysisActivity: 'idle',
    analysisError: null,
    showDiscussion: false,
    analysisLevel: 'standard',
    analysisTarget: null,
  });
  useMarketStore.setState({
    historyItems: [],
    optimizationLogs: [],
    watchlist: [],
    recentSearches: [],
    marketOverviews: {},
    searchAlerts: [],
  });
  useDiscussionStore.setState({
    discussionMessages: [],
    controversialPoints: [],
    tradingPlanHistory: [],
    analystWeights: [],
    currentRound: 0,
    totalRounds: 0,
  });
  useScenarioStore.setState({
    scenarios: [],
    sensitivityFactors: [],
    verificationMetrics: [],
  });
  useJobQueueStore.setState({
    jobs: [],
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  resetStores();
  mockStatus.current = 'idle';
  mockResult.current = null;
  mockError.current = null;
  mockInsufficientBalance.current = false;
});

describe('useStockAnalysis', () => {
  describe('handleSearch', () => {
    it('does nothing when symbol is empty', async () => {
      const { result } = renderHook(() => useStockAnalysis());
      const originalFetch = global.fetch;
      global.fetch = vi.fn();

      try {
        await act(async () => {
          await result.current.handleSearch();
        });
        expect(global.fetch).not.toHaveBeenCalled();
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('checks history and opens dialog when history exists', async () => {
      useAnalysisStore.setState({ symbol: '00700', market: 'HK-Share' });
      const { result } = renderHook(() => useStockAnalysis());

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          success: true,
          data: [{ analysisId: 'ana_1', symbol: '00700' }],
        }),
      });

      try {
        await act(async () => {
          await result.current.handleSearch();
        });
        expect(result.current.historyDialogOpen).toBe(true);
        expect(result.current.historyDialogItems).toHaveLength(1);
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('starts fresh analysis when no history exists', async () => {
      useAnalysisStore.setState({ symbol: 'AAPL', market: 'US-Share' });
      const { result } = renderHook(() => useStockAnalysis());

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          success: true,
          data: [],
        }),
      });

      try {
        await act(async () => {
          await result.current.handleSearch();
        });
        expect(mockStartAnalysis).toHaveBeenCalledWith('AAPL', 'US-Share', 'standard', 'gemini-3.1-pro-preview', { model: 'gemini-3.1-pro-preview' });
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('queues background job when already analyzing', async () => {
      useUIStore.setState({ analysisActivity: 'analyzing' });
      useAnalysisStore.setState({ symbol: 'BABA', market: 'US-Share' });
      const { result } = renderHook(() => useStockAnalysis());

      const originalFetch = global.fetch;
      let fetchCount = 0;
      global.fetch = vi.fn().mockImplementation(async (url: string) => {
        fetchCount++;
        if (url === '/api/analysis/jobs' && fetchCount === 1) {
          return {
            json: vi.fn().mockResolvedValue({ success: true, data: { job_id: 'bg_job_1' } }),
          };
        }
        return { json: vi.fn().mockResolvedValue({}) };
      });

      try {
        await act(async () => {
          await result.current.handleSearch();
        });
        expect(fetchCount).toBeGreaterThanOrEqual(1);
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('job completion effect', () => {
    it('updates analysis on job completion', async () => {
      const analysisResult = {
        stockInfo: { symbol: '00700', name: 'Tencent', market: 'HK-Share', price: 400 },
        discussion: [{ role: 'analyst', content: 'bullish' }],
        score: 85,
      };

      mockStatus.current = 'completed';
      mockResult.current = analysisResult;

      const { result } = renderHook(() => useStockAnalysis());

      await waitFor(() => {
        const state = useAnalysisStore.getState();
        expect(state.analysis).not.toBeNull();
      });

      expect(useAnalysisStore.getState().analysis?.stockInfo?.symbol).toBe('00700');
      expect(useAnalysisStore.getState().analysis?.score).toBe(85);
    });

    it('shows error and stops loading on failure', async () => {
      mockStatus.current = 'failed';
      mockError.current = 'Something went wrong';

      const { result } = renderHook(() => useStockAnalysis());

      await waitFor(() => {
        expect(useUIStore.getState().analysisActivity).toBe('idle');
      });
    });

    it('shows insufficient balance message when flagged', async () => {
      mockStatus.current = 'running';
      mockInsufficientBalance.current = true;

      renderHook(() => useStockAnalysis());

      await waitFor(() => {
        expect(useUIStore.getState().analysisError).toContain('API 余额不足');
      });
    });
  });

  describe('fetchAdminData', () => {
    it('fetches history and optimization logs', async () => {
      const { result } = renderHook(() => useStockAnalysis());

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockImplementation(async (url: string) => {
        if (url.includes('/api/history/context')) {
          return {
            ok: true,
            json: vi.fn().mockResolvedValue([{ id: 'h1', symbol: 'AAPL' }]),
          };
        }
        if (url.includes('/api/logs/optimization')) {
          return {
            ok: true,
            json: vi.fn().mockResolvedValue([{ log: 'optimized' }]),
          };
        }
        return { ok: false, json: vi.fn() };
      });

      try {
        await act(async () => {
          await result.current.fetchAdminData();
        });
        expect(useMarketStore.getState().historyItems).toHaveLength(1);
        expect(useMarketStore.getState().optimizationLogs).toHaveLength(1);
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('toggleWatchlist', () => {
    it('adds item to watchlist', async () => {
      const { result } = renderHook(() => useStockAnalysis());
      const stock = { symbol: '00700', name: 'Tencent', market: 'HK-Share' as const };

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue(stock),
      });

      try {
        await act(async () => {
          await result.current.toggleWatchlist(stock);
        });
        expect(useMarketStore.getState().watchlist).toHaveLength(1);
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('removes item from watchlist', async () => {
      useMarketStore.setState({
        watchlist: [{ symbol: '00700', name: 'Tencent', market: 'HK-Share' }],
      });
      const { result } = renderHook(() => useStockAnalysis());

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({ ok: true });

      try {
        await act(async () => {
          await result.current.toggleWatchlist({ symbol: '00700', name: 'Tencent', market: 'HK-Share' as const });
        });
        expect(useMarketStore.getState().watchlist).toHaveLength(0);
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('resetToHome', () => {
    it('resets analysis, discussion, and scenario', () => {
      useAnalysisStore.setState({ analysis: { stockInfo: {} } as any });
      useDiscussionStore.setState({ discussionMessages: [{ id: '1', role: 'Technical Analyst' as const, content: 'test', timestamp: new Date().toISOString() }], currentRound: 3 });
      useScenarioStore.setState({ scenarios: [{ name: 'test' } as any], sensitivityFactors: [{ factor: 'risk' } as any] });

      const { result } = renderHook(() => useStockAnalysis());
      act(() => { result.current.resetToHome(); });

      expect(useAnalysisStore.getState().analysis).toBeNull();
      expect(useDiscussionStore.getState().discussionMessages).toEqual([]);
      expect(useDiscussionStore.getState().currentRound).toBe(0);
      expect(useScenarioStore.getState().scenarios).toEqual([]);
    });
  });

  describe('loadHistoryResult', () => {
    it('loads analysis from history', async () => {
      const { result } = renderHook(() => useStockAnalysis());

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        json: vi.fn().mockResolvedValue({
          success: true,
          data: {
            stockInfo: { symbol: '00700', name: 'Tencent', market: 'HK-Share', price: 400 },
            discussion: [],
          },
        }),
      });

      try {
        await act(async () => {
          await result.current.loadHistoryResult('ana_123');
        });
        expect(useAnalysisStore.getState().analysis?.stockInfo?.symbol).toBe('00700');
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('sets error when history fetch fails', async () => {
      const { result } = renderHook(() => useStockAnalysis());

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        json: vi.fn().mockResolvedValue({ success: false }),
      });

      try {
        await act(async () => {
          await result.current.loadHistoryResult('ana_fail');
        });
        expect(useUIStore.getState().analysisError).toBe('加载历史记录失败');
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('doStartAnalysis', () => {
    it('starts analysis with explicit parameters', async () => {
      const { result } = renderHook(() => useStockAnalysis());

      await act(async () => {
        result.current.doStartAnalysis('BABA', 'US-Share');
      });

      expect(mockStartAnalysis).toHaveBeenCalledWith('BABA', 'US-Share', 'standard', 'gemini-3.1-pro-preview', { model: 'gemini-3.1-pro-preview' });
    });

    it('uses stored symbol and market when no explicit params', async () => {
      useAnalysisStore.setState({ symbol: '600519', market: 'A-Share' });
      const { result } = renderHook(() => useStockAnalysis());

      await act(async () => {
        result.current.doStartAnalysis();
      });

      expect(mockStartAnalysis).toHaveBeenCalledWith('600519', 'A-Share', 'standard', 'gemini-3.1-pro-preview', { model: 'gemini-3.1-pro-preview' });
    });
  });
});
