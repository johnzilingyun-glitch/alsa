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

  const fetchMarketDashboard = useCallback(async (forceRefresh = false) => {
    const state = useMarketStore.getState();
    const currentDashboard = state.marketDashboards[overviewMarket];

    if (!forceRefresh && currentDashboard) {
      setOverviewLoading(false);
      return;
    }

    setOverviewLoading(true);
    setOverviewError(null);

    try {
      const dashboard = await fetchDashboardFromAPI(overviewMarket);
      setMarketDashboard(overviewMarket, dashboard);
      setMarketLastUpdated(overviewMarket, Date.now());
    } catch (err: any) {
      console.warn('[Market] Dashboard fetch failed:', err);
      setOverviewError(err?.message || 'Failed to load market data');
    } finally {
      setOverviewLoading(false);
    }

    // Async non-blocking: AI summary + sentiment
    void fetchMarketSummary(overviewMarket);
  }, [overviewMarket, setMarketDashboard, setMarketLastUpdated, setOverviewLoading, setOverviewError]);

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
    } catch (err) {
      console.warn('[Market] AI summary failed (page unaffected):', err);
    } finally {
      setAiLoading(market, false);
    }
  }, [setAiLoading, setMarketSummaryData]);

  useEffect(() => {
    if (_hasHydrated) {
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
