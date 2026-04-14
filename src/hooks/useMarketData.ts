import { useCallback, useEffect } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore } from '../stores/useUIStore';
import { useMarketStore } from '../stores/useMarketStore';
import { getMarketOverview, getMarketSnapshot, getHistoryContext } from '../services/aiService';
import { getBeijingDate } from '../services/dateUtils';

export function useMarketData(fetchAdminData: () => Promise<void>) {
  const geminiConfig = useConfigStore(s => s.config);
  const { setOverviewLoading, setOverviewError } = useUIStore();
  const overviewMarket = useMarketStore(s => s.overviewMarket);
  const setMarketOverview = useMarketStore(s => s.setMarketOverview);
  const setMarketLastUpdated = useMarketStore(s => s.setMarketLastUpdated);
  const _hasHydrated = useMarketStore(s => s._hasHydrated);
  const autoRefresh = useUIStore(s => s.autoRefreshInterval);

  const fetchMarketOverview = useCallback(async (forceRefresh = false) => {
    const state = useMarketStore.getState();
    const currentCache = state.marketOverviews[overviewMarket];
    const lastUpdate = state.marketLastUpdatedTimes[overviewMarket];

    const now = new Date();
    const todayStr = getBeijingDate(now);
    
    const lastUpdateDate = lastUpdate ? getBeijingDate(new Date(lastUpdate)) : null;
    const isToday = lastUpdateDate === todayStr;

    if (!forceRefresh && currentCache && isToday) {
      console.log(`[Market] Using cached data for ${overviewMarket}`);
      setOverviewLoading(false);
      return;
    }

    console.log(`[Market] Fetching data for ${overviewMarket}`);
    setOverviewLoading(true);
    setOverviewError(null);

    // Phase 1: Instant financial API snapshot (no AI, no quota)
    try {
      const snapshot = await getMarketSnapshot(overviewMarket);
      if (snapshot.indices && snapshot.indices.length > 0) {
        // Merge snapshot into existing data (preserve AI fields if present)
        const merged = {
          ...(currentCache || {}),
          ...snapshot,
          // Preserve AI-generated fields from cache if available
          topNews: currentCache?.topNews || [],
          sectorAnalysis: currentCache?.sectorAnalysis || [],
          recommendations: currentCache?.recommendations || [],
          marketSummary: currentCache?.marketSummary || '',
        } as any;
        setMarketOverview(overviewMarket, merged);
        setMarketLastUpdated(overviewMarket, snapshot.generatedAt || Date.now());
        console.log(`[Market] Snapshot loaded for ${overviewMarket}: ${snapshot.indices.length} indices`);
      }
    } catch (err) {
      console.warn('[Market] Snapshot fetch failed, falling back to AI:', err);
    }

    // Phase 2: AI enrichment (news, sectors, recommendations, summary)
    try {
      const data = await getMarketOverview(geminiConfig, overviewMarket, forceRefresh, 1);
      setMarketOverview(overviewMarket, data);
      setMarketLastUpdated(overviewMarket, data.generatedAt || Date.now());
      void fetchAdminData();
    } catch (err) {
      console.warn('[Market] AI enrichment failed (snapshot data still available):', err);
      // Don't show error if we already have snapshot data
      const currentData = useMarketStore.getState().marketOverviews[overviewMarket];
      if (!currentData?.indices?.length) {
        setOverviewError(err instanceof Error ? err.message : '无法加载市场概览。');
      }
    } finally {
      setOverviewLoading(false);
    }
  }, [geminiConfig, overviewMarket, setMarketOverview, setMarketLastUpdated, setOverviewError, setOverviewLoading, fetchAdminData]);

  useEffect(() => {
    if (_hasHydrated) {
      void fetchMarketOverview(false);
      void fetchAdminData();
    }
  }, [_hasHydrated, fetchMarketOverview, fetchAdminData]);

  useEffect(() => {
    if (autoRefresh && autoRefresh > 0) {
      const intervalId = setInterval(() => {
        void fetchMarketOverview(true);
      }, autoRefresh * 60 * 1000);
      return () => clearInterval(intervalId);
    }
  }, [autoRefresh, fetchMarketOverview]);

  return { fetchMarketOverview };
}
