import { describe, it, expect, beforeEach } from 'vitest';
import { useMarketStore } from '../stores/useMarketStore';
import { MarketOverview } from '../types';

const mockOverview: MarketOverview = {
  marketSummary: "Test Summary",
  indices: [],
  sectorAnalysis: [],
  commodityAnalysis: [],
  recommendations: [],
  topNews: []
};

describe('MarketStore Caching Logic', () => {
  beforeEach(() => {
    // Reset Zustand store manually if needed, but here we just reset for each test
    const store = useMarketStore.getState();
    store.setMarketOverview('A-Share', null);
    store.setMarketLastUpdated('A-Share', null);
  });

  it('should store separate data for different markets', () => {
    const { setMarketOverview, marketOverviews } = useMarketStore.getState();
    
    setMarketOverview('A-Share', { ...mockOverview, marketSummary: 'A-Share Summary' });
    setMarketOverview('HK-Share', { ...mockOverview, marketSummary: 'HK-Share Summary' });
    
    const state = useMarketStore.getState();
    expect(state.marketOverviews['A-Share']?.marketSummary).toBe('A-Share Summary');
    expect(state.marketOverviews['HK-Share']?.marketSummary).toBe('HK-Share Summary');
    expect(state.marketOverviews['US-Share']).toBeNull();
  });

  it('should track update times per market', () => {
    const { setMarketLastUpdated } = useMarketStore.getState();
    const now = Date.now();
    
    setMarketLastUpdated('A-Share', now);
    setMarketLastUpdated('US-Share', now - 10000);
    
    const state = useMarketStore.getState();
    expect(state.marketLastUpdatedTimes['A-Share']).toBe(now);
    expect(state.marketLastUpdatedTimes['US-Share']).toBe(now - 10000);
  });
});
