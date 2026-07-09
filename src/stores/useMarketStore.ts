import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { MarketOverview, MarketDashboard, Market } from '../types';

interface MarketState {
  marketOverviews: Record<string, MarketOverview | null>;
  marketLastUpdatedTimes: Record<string, number | null>;
  dailyReport: string | null;
  historyItems: any[];
  recentSearches: { symbol: string; name: string; market: Market }[];
  watchlist: { symbol: string; name: string; market: Market }[];
  optimizationLogs: any[];
  overviewMarket: Market;
  searchAlerts: any[];
  alertPrices: Record<string, number>;
  activeAlertStatus: 'gold' | 'red' | 'indigo' | 'neutral';

  // New dashboard store
  marketDashboards: Record<string, MarketDashboard | null>;
  marketSummary: Record<string, string>;
  marketSentiment: Record<string, 'bullish' | 'bearish' | 'neutral' | ''>;
  aiLoading: Record<string, boolean>;

  setMarketOverview: (market: string, overview: MarketOverview | null) => void;
  setMarketLastUpdated: (market: string, timestamp: number | null) => void;
  setMarketDashboard: (market: string, dashboard: MarketDashboard | null) => void;
  setMarketSummaryData: (market: string, summary: string, sentiment: 'bullish' | 'bearish' | 'neutral') => void;
  setAiLoading: (market: string, loading: boolean) => void;
  setDailyReport: (report: string | null) => void;
  setHistoryItems: (items: any[]) => void;
  setWatchlist: (items: any[]) => void;
  setRecentSearches: (items: any[]) => void;
  addRecentSearch: (search: { symbol: string; name: string; market: Market }) => void;
  removeRecentSearch: (symbol: string) => void;
  setOptimizationLogs: (logs: any[]) => void;
  setOverviewMarket: (market: Market) => void;
  setAlerts: (alerts: any[]) => void;
  updateAlertPrice: (symbol: string, price: number) => void;
  refreshActiveAlertStatus: () => void;
  _hasHydrated: boolean;
  setHasHydrated: (state: boolean) => void;
}

export const useMarketStore = create<MarketState>()(
  persist(
    (set, get) => ({
      marketOverviews: {
        "A-Share": null,
        "HK-Share": null,
        "US-Share": null
      },
      marketLastUpdatedTimes: {
        "A-Share": null,
        "HK-Share": null,
        "US-Share": null
      },
      dailyReport: null,
      historyItems: [],
      recentSearches: [],
      watchlist: [],
      optimizationLogs: [],
      overviewMarket: "A-Share",
      searchAlerts: [],
      alertPrices: {},
      activeAlertStatus: 'neutral',
      _hasHydrated: false,

      marketDashboards: { "A-Share": null, "HK-Share": null, "US-Share": null },
      marketSummary: { "A-Share": "", "HK-Share": "", "US-Share": "" },
      marketSentiment: { "A-Share": "", "HK-Share": "", "US-Share": "" },
      aiLoading: { "A-Share": false, "HK-Share": false, "US-Share": false },

      setMarketOverview: (market, overview) =>
        set((state) => ({
          marketOverviews: { ...state.marketOverviews, [market]: overview }
        })),
      setMarketLastUpdated: (market, timestamp) =>
        set((state) => ({
          marketLastUpdatedTimes: { ...state.marketLastUpdatedTimes, [market]: timestamp }
        })),
      setMarketDashboard: (market, dashboard) =>
        set((state) => ({
          marketDashboards: { ...state.marketDashboards, [market]: dashboard }
        })),
      setMarketSummaryData: (market, summary, sentiment) =>
        set((state) => ({
          marketSummary: { ...state.marketSummary, [market]: summary },
          marketSentiment: { ...state.marketSentiment, [market]: sentiment },
        })),
      setAiLoading: (market, loading) =>
        set((state) => ({
          aiLoading: { ...state.aiLoading, [market]: loading }
        })),
      setDailyReport: (dailyReport) => set({ dailyReport }),
      setHistoryItems: (historyItems) => set({ historyItems }),
      setWatchlist: (watchlist) => set({ watchlist }),
      setRecentSearches: (recentSearches) => set({ recentSearches }),
      addRecentSearch: (search) => set((state) => {
        if (!search || typeof search.symbol !== 'string' || typeof search.name !== 'string') return state;
        const filtered = state.recentSearches.filter(s => s.symbol !== search.symbol);
        return { recentSearches: [search, ...filtered].slice(0, 10) };
      }),
      removeRecentSearch: (symbol) => set((state) => ({
        recentSearches: state.recentSearches.filter(s => s.symbol !== symbol)
      })),
      setOptimizationLogs: (optimizationLogs) => set({ optimizationLogs }),
      setOverviewMarket: (overviewMarket) => set({ overviewMarket }),
      setAlerts: (searchAlerts) => {
        set({ searchAlerts });
        get().refreshActiveAlertStatus();
      },
      updateAlertPrice: (symbol, price) => {
        set((state) => ({ 
          alertPrices: { ...state.alertPrices, [symbol]: price } 
        }));
        get().refreshActiveAlertStatus();
      },
      refreshActiveAlertStatus: () => {
        const { searchAlerts, alertPrices } = get();
        if (!searchAlerts.length) {
          set({ activeAlertStatus: 'neutral' });
          return;
        }

        let highestStatus: 'gold' | 'red' | 'indigo' | 'neutral' = 'neutral';

        for (const alert of searchAlerts) {
          const price = alertPrices[alert.symbol];
          if (!price) continue;

          const isShort = alert.target_price < alert.entry_price;
          const targetHit = isShort ? price <= alert.target_price : price >= alert.target_price;
          const stopHit = isShort ? price >= alert.stop_loss : price <= alert.stop_loss;
          if (targetHit) {
            highestStatus = 'gold'; // Gold takes priority
            break; 
          }
          if (stopHit) {
            if ((highestStatus as string) !== 'gold') highestStatus = 'red';
          } else {
            const entryDiff = Math.abs(price - alert.entry_price) / alert.entry_price;
            if (entryDiff <= 0.02 && highestStatus === 'neutral') {
              highestStatus = 'indigo';
            }
          }
        }
        set({ activeAlertStatus: highestStatus });
      },
      setHasHydrated: (state) => set({ _hasHydrated: state }),
    }),
    {
      name: 'market-storage',
      partialize: (state) => ({
        watchlist: state.watchlist,
        recentSearches: state.recentSearches,
        overviewMarket: state.overviewMarket,
        marketOverviews: state.marketOverviews,
        marketDashboards: state.marketDashboards,
        marketSummary: state.marketSummary,
        marketSentiment: state.marketSentiment,
        marketLastUpdatedTimes: state.marketLastUpdatedTimes,
        // Exclude historyItems, optimizationLogs to keep localStorage small and hydration fast
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.setHasHydrated(true);
          if (Array.isArray(state.recentSearches)) {
            const valid = state.recentSearches.filter(s => s && typeof s.symbol === 'string' && typeof s.name === 'string');
            if (valid.length !== state.recentSearches.length) {
              // Defer state update until hydration is complete
              setTimeout(() => state.setRecentSearches(valid), 0);
            }
          }
        }
      },
    }
  )
);
