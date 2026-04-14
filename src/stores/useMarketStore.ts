import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { MarketOverview, Market } from '../types';

interface MarketState {
  marketOverviews: Record<string, MarketOverview | null>;
  marketLastUpdatedTimes: Record<string, number | null>;
  dailyReport: string | null;
  historyItems: any[];
  optimizationLogs: any[];
  overviewMarket: Market;

  setMarketOverview: (market: string, overview: MarketOverview | null) => void;
  setMarketLastUpdated: (market: string, timestamp: number | null) => void;
  setDailyReport: (report: string | null) => void;
  setHistoryItems: (items: any[]) => void;
  setOptimizationLogs: (logs: any[]) => void;
  setOverviewMarket: (market: Market) => void;
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
      optimizationLogs: [],
      overviewMarket: "A-Share",
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
      setOptimizationLogs: (optimizationLogs) => set({ optimizationLogs }),
      setOverviewMarket: (overviewMarket) => set({ overviewMarket }),
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
