import { useCallback, useEffect } from 'react';
import { useUIStore } from '../stores/useUIStore';
import { useMarketStore } from '../stores/useMarketStore';
import { fetchDashboardFromAPI, generateMarketSummary, compressForAI } from '../services/marketService';

export function useMarketData(_fetchAdminData: () => Promise<void>) {
  const setOverviewLoading = useUIStore(s => s.setOverviewLoading);
  const setOverviewError = useUIStore(s => s.setOverviewError);
  const overviewMarket = useMarketStore(s => s.overviewMarket);
  const setMarketDashboard = useMarketStore(s => s.setMarketDashboard);
  const setMarketLastUpdated = useMarketStore(s => s.setMarketLastUpdated);
  const setMarketSummaryData = useMarketStore(s => s.setMarketSummaryData);
  const setAiLoading = useMarketStore(s => s.setAiLoading);
  const _hasHydrated = useMarketStore(s => s._hasHydrated);
  const autoRefresh = useUIStore(s => s.autoRefreshInterval);

  const fetchMarketSummary = useCallback(async (market: string) => {
    const state = useMarketStore.getState();
    if (state.aiLoading[market]) return;

    const dashboard = state.marketDashboards[market];
    if (!dashboard) return;

    setAiLoading(market, true);
    try {
      const payload = compressForAI(dashboard);
      const result = await generateMarketSummary(payload);
      setMarketSummaryData(market, result.summary, result.sentiment);
      setOverviewError(null); // clear any previous error on success
    } catch (err) {
      console.warn('[Market] AI summary failed:', err);
      setOverviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setAiLoading(market, false);
    }
  }, [setAiLoading, setMarketSummaryData, setOverviewError]);

  const fetchMarketDashboard = useCallback(async (forceRefresh = false) => {
    console.log('[Market][DEBUG] fetchMarketDashboard called, forceRefresh:', forceRefresh, 'market:', overviewMarket);
    const state = useMarketStore.getState();
    const currentDashboard = state.marketDashboards[overviewMarket];

    if (!forceRefresh && currentDashboard) {
      console.log('[Market][DEBUG] Skipped — already have dashboard for', overviewMarket);
      setOverviewLoading(false);
      return;
    }

    console.log('[Market][DEBUG] Fetching dashboard from API for', overviewMarket);
    setOverviewLoading(true);
    setOverviewError(null);

    try {
      const dashboard = await fetchDashboardFromAPI(overviewMarket);
      console.log('[Market][DEBUG] Dashboard fetched OK, indices:', dashboard?.indices?.length, 'news:', dashboard?.news?.length);
      setMarketDashboard(overviewMarket, dashboard);
      setMarketLastUpdated(overviewMarket, Date.now());
    } catch (err: any) {
      console.warn('[Market] Dashboard fetch failed:', err);
      setOverviewError(err?.message || 'Failed to load market data');
    } finally {
      setOverviewLoading(false);
    }

    // AI summary only on explicit force refresh
    if (forceRefresh) {
      void fetchMarketSummary(overviewMarket);
    }
  }, [overviewMarket, setMarketDashboard, setMarketLastUpdated, setOverviewLoading, setOverviewError, fetchMarketSummary]);
  useEffect(() => {
    console.log('[Market][DEBUG] Hydration effect — _hasHydrated:', _hasHydrated);
    if (_hasHydrated) {
      console.log('[Market][DEBUG] Hydrated, triggering fetchMarketDashboard(false)');
      void fetchMarketDashboard(false);
    }
  }, [_hasHydrated, fetchMarketDashboard]);

  useEffect(() => {
    if (autoRefresh && autoRefresh > 0) {
      const intervalId = setInterval(() => {
        void fetchMarketDashboard(true);
      }, autoRefresh * 60 * 1000);
      return () => clearInterval(intervalId);
    }
  }, [autoRefresh, fetchMarketDashboard]);

  return { fetchMarketDashboard };
}
