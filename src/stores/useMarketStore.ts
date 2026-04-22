import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { MarketOverview, Market } from '../types';

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

  setMarketOverview: (market: string, overview: MarketOverview | null) => void;
  setMarketLastUpdated: (market: string, timestamp: number | null) => void;
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

      setMarketOverview: (market, overview) => 
        set((state) => ({ 
          marketOverviews: { ...state.marketOverviews, [market]: overview } 
        })),
      setMarketLastUpdated: (market, timestamp) => 
        set((state) => ({ 
          marketLastUpdatedTimes: { ...state.marketLastUpdatedTimes, [market]: timestamp } 
        })),
      setDailyReport: (dailyReport) => set({ dailyReport }),
      setHistoryItems: (historyItems) => set({ historyItems }),
      setWatchlist: (watchlist) => set({ watchlist }),
      setRecentSearches: (recentSearches) => set({ recentSearches }),
      addRecentSearch: (search) => set((state) => {
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

          if (price >= alert.target_price) {
            highestStatus = 'gold'; // Gold takes priority
            break; 
          }
          if (price <= alert.stop_loss) {
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
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    }
  )
);
