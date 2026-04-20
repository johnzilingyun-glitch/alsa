import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// Mock lucide-react
vi.mock('lucide-react', () => {
  const icons = [
    'Globe', 'Settings', 'Loader2', 'ExternalLink', 'TrendingUp', 'Share2',
    'CheckCircle2', 'LayoutGrid', 'Coins', 'Star', 'Newspaper', 'Search',
    'RefreshCw', 'Calendar', 'Heart', 'Target', 'Activity', 'BarChart3', 'ChevronRight',
    'Bell', 'ShieldAlert', 'Trash2', 'ArrowRight'
  ];
  const mocks: Record<string, any> = {};
  icons.forEach(icon => {
    mocks[icon] = (props: any) => <div data-testid={`icon-${icon}`} />;
  });
  return mocks;
});

// Mock motion/react
vi.mock('motion/react', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

// Mock stores
vi.mock('../../stores/useUIStore', () => ({
  useUIStore: vi.fn((selector) => {
    const state = {
      overviewLoading: false,
      overviewError: null,
      isGeneratingReport: false,
      isSendingReport: false,
      reportStatus: null,
      autoRefreshInterval: 0,
      setAutoRefreshInterval: vi.fn(),
      setIsSettingsOpen: vi.fn(),
    };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

vi.mock('../../stores/useMarketStore', () => ({
  useMarketStore: vi.fn((selector) => {
    const state = {
      marketOverviews: {
        'A-Share': {
          indices: [
            { name: '上证综指', symbol: '000001.SS', price: 3200, change: 15, changePercent: 0.47, previousClose: 3185 },
          ],
          topNews: [],
          sectorAnalysis: [],
          commodityAnalysis: [],
          recommendations: [],
          marketSummary: '',
        },
      },
      marketLastUpdatedTimes: { 'A-Share': Date.now() },
      overviewMarket: 'A-Share',
      setOverviewMarket: vi.fn(),
      searchAlerts: [],
      alertPrices: {},
      watchlist: [],
      recentSearches: [],
      updateAlertPrice: vi.fn(),
      refreshActiveAlertStatus: vi.fn(),
    };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

vi.mock('../../stores/useAnalysisStore', () => ({
  useAnalysisStore: vi.fn((selector) => {
    const state = { setSymbol: vi.fn(), setMarket: vi.fn() };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

// Mock adminService
vi.mock('../../services/adminService', () => ({
  getMarketHistoryByDate: vi.fn().mockResolvedValue(null),
  getAvailableMarketDates: vi.fn().mockResolvedValue([]),
}));

import { MarketOverview } from '../dashboard/MarketOverview';

describe('MarketOverview', () => {
  it('renders without crashing', () => {
    const { container } = render(
      <MarketOverview
        onFetchMarketOverview={vi.fn()}
        onTriggerDailyReport={vi.fn()}
      />
    );
    expect(container).toBeTruthy();
  });

  it('renders index data when available', () => {
    render(
      <MarketOverview
        onFetchMarketOverview={vi.fn()}
        onTriggerDailyReport={vi.fn()}
      />
    );
    expect(screen.getByText('上证综指')).toBeTruthy();
    expect(screen.getByText('3,200')).toBeTruthy();
  });

  it('shows market overview title', () => {
    render(
      <MarketOverview
        onFetchMarketOverview={vi.fn()}
        onTriggerDailyReport={vi.fn()}
      />
    );
    expect(screen.getByText('market.overview')).toBeTruthy();
  });
});
