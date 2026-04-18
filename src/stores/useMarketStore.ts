import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { MarketOverview, Market } from '../types';

interface MarketState {
  marketOverviews: Record<string, MarketOverview | null>;
  marketLastUpdatedTimes: Record<string, number | null>;
  dailyReport: string | null;
  historyItems: any[];
  recentSearches: { symbol: string; name: string; market: Market }[];
  optimizationLogs: any[];
  overviewMarket: Market;
  searchAlerts: any[];
  alertPrices: Record<string, number>;

  setMarketOverview: (market: string, overview: MarketOverview | null) => void;
  setMarketLastUpdated: (market: string, timestamp: number | null) => void;
  setDailyReport: (report: string | null) => void;
  setHistoryItems: (items: any[]) => void;
  addRecentSearch: (search: { symbol: string; name: string; market: Market }) => void;
  setOptimizationLogs: (logs: any[]) => void;
  setOverviewMarket: (market: Market) => void;
  setAlerts: (alerts: any[]) => void;
  updateAlertPrice: (symbol: string, price: number) => void;
  _hasHydrated: boolean;
  setHasHydrated: (state: boolean) => void;
}

export const useMarketStore = create<MarketState>()(
  persist(
    (set) => ({
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
      optimizationLogs: [],
      overviewMarket: "A-Share",
      searchAlerts: [],
      alertPrices: {},
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
      addRecentSearch: (search) => set((state) => {
        const filtered = state.recentSearches.filter(s => s.symbol !== search.symbol);
        return { recentSearches: [search, ...filtered].slice(0, 10) };
      }),
      setOptimizationLogs: (optimizationLogs) => set({ optimizationLogs }),
      setOverviewMarket: (overviewMarket) => set({ overviewMarket }),
      setAlerts: (searchAlerts) => set({ searchAlerts }),
      updateAlertPrice: (symbol, price) => set((state) => ({ 
        alertPrices: { ...state.alertPrices, [symbol]: price } 
      })),
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
