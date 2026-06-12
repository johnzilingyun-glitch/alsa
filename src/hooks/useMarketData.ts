import { useCallback, useEffect } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore } from '../stores/useUIStore';
import { useMarketStore } from '../stores/useMarketStore';
import { getMarketOverview, getMarketSnapshot, getHistoryContext } from '../services/aiService';
import { getBeijingDate } from '../services/dateUtils';

export function useMarketData(fetchAdminData: () => Promise<void>) {
  const setOverviewLoading = useUIStore(s => s.setOverviewLoading);
  const setOverviewError = useUIStore(s => s.setOverviewError);
  const overviewMarket = useMarketStore(s => s.overviewMarket);
  const setMarketOverview = useMarketStore(s => s.setMarketOverview);
  const setMarketLastUpdated = useMarketStore(s => s.setMarketLastUpdated);
  const _hasHydrated = useMarketStore(s => s._hasHydrated);
  const autoRefresh = useUIStore(s => s.autoRefreshInterval);

  const fetchMarketOverview = useCallback(async (forceRefresh = false, allowAI = true) => {
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
    let snapshotLoaded = false;
    try {
      const snapshot = await getMarketSnapshot(overviewMarket);
      if (snapshot && snapshot.indices && snapshot.indices.length > 0) {
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
        snapshotLoaded = true;
        setOverviewLoading(false); // Reveal UI as soon as indices are here
      } else {
        console.warn(`[Market] Snapshot empty for ${overviewMarket}.`);
      }
    } catch (err) {
      console.warn('[Market] Snapshot fetch failed, falling back to AI:', err);
    }

    // Phase 2: AI enrichment (news, sectors, recommendations, summary)
    // Only run AI if explicitly allowed (e.g. force refresh, model change, or auto-refresh)
    if (!allowAI) {
      console.log(`[Market] AI enrichment skipped (Initial load/Passive update)`);
      setOverviewLoading(false);
      return;
    }

    try {
      const geminiConfig = useConfigStore.getState().config;
      const data = await getMarketOverview(geminiConfig, overviewMarket, forceRefresh, 1);
      
      // Preserve fresh API indices from Phase 1 if available, 
      // preventing stale AI history from overwriting real-time quotes (e.g. 0 prices)
      if (snapshotLoaded) {
        const freshIndices = useMarketStore.getState().marketOverviews[overviewMarket]?.indices;
        if (freshIndices && freshIndices.length > 0) {
          data.indices = freshIndices;
        }
      }
      
      setMarketOverview(overviewMarket, data);
      setMarketLastUpdated(overviewMarket, data.generatedAt || Date.now());
      void fetchAdminData();
    } catch (err) {
      console.warn('[Market] AI enrichment failed (snapshot data still available):', err);
      
      const errorStr = String(err);
      if (errorStr.includes('quota') || errorStr.includes('exhausted') || errorStr.includes('429')) {
        useUIStore.getState().setServiceStatus('quota_exhausted');
      }

      // If we don't even have a snapshot, show the error
      if (!snapshotLoaded && !currentCache) {
        setOverviewError(err instanceof Error ? err.message : '无法加载市场概览。');
      }
    } finally {
      setOverviewLoading(false);
    }
  }, [overviewMarket, setMarketOverview, setMarketLastUpdated, setOverviewError, setOverviewLoading, fetchAdminData]);

  useEffect(() => {
    if (_hasHydrated) {
      // Initial load: Only fetch snapshot (allowAI = false) to save quota and speed up entry
      void fetchMarketOverview(false, false);
      // Defer admin data load — not needed for first paint
      setTimeout(() => void fetchAdminData(), 2000);
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
