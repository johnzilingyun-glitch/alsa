import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';

// Mock lucide-react comprehensively
vi.mock('lucide-react', () => {
  const icons = [
    'ExternalLink', 'CheckCircle2', 'AlertCircle', 'Loader2', 'ArrowLeft',
    'BarChart3', 'Info', 'MessageSquare', 'Newspaper', 'PieChart', 'Send',
    'Shield', 'ShieldAlert', 'TrendingDown', 'TrendingUp', 'Zap', 'Share2', 'Download',
    'AlertTriangle', 'Cpu', 'Award', 'Target', 'RefreshCcw', 'Clock', 'Layers',
    'Database', 'History', 'Coins', 'ShieldCheck', 'Search', 'LayoutGrid', 'User',
    'UserCheck', 'X', 'Maximize2', 'Minimize2', 'RotateCcw', 'Calculator', 'Table',
    'Activity', 'ArrowRight', 'Brain', 'PenTool', 'Database', 'ShieldCheck', 'Check'
  ];
  const mocks: Record<string, any> = {};
  icons.forEach(icon => {
    mocks[icon] = () => <div data-testid={`icon-${icon}`} />;
  });
  return mocks;
});

// Mock motion/react
vi.mock('motion/react', () => ({
  motion: {
    main: ({ children }: any) => <main>{children}</main>,
    div: ({ children }: any) => <div>{children}</div>,
    button: ({ children }: any) => <button>{children}</button>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
  useDragControls: () => ({})
}));

// Mock react-i18next
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' }
  }),
}));

// Import component AFTER mocks
import { AnalysisResult } from '../components/analysis/AnalysisResult';

// Mock stores
vi.mock('../../stores/useUIStore', () => ({
  useUIStore: vi.fn((selector) => selector({
    isChatting: false,
    isDiscussing: false,
    isReviewing: false,
    isGeneratingReport: false,
    isSendingReport: false,
    reportStatus: 'idle',
    showDiscussion: false,
    setShowDiscussion: vi.fn(),
  })),
  selectIsChatting: (state: any) => state.isChatting,
  selectIsDiscussing: (state: any) => state.isDiscussing,
  selectIsReviewing: (state: any) => state.isReviewing,
}));

vi.mock('../../stores/useAnalysisStore', () => ({
  useAnalysisStore: () => ({
    analysis: {
      stockInfo: { symbol: 'AAPL', name: 'Apple' },
      finalConclusion: 'Test conclusion',
      tradingPlan: { entryPrice: '150', targetPrice: '180', stopLoss: '140', strategy: 'Test strategy' },
    },
    chatMessage: '',
    setChatMessage: vi.fn(),
    chatHistory: [],
  }),
}));

vi.mock('../../stores/useDiscussionStore', () => ({
  useDiscussionStore: () => ({
    discussionMessages: [],
    controversialPoints: [],
    tradingPlanHistory: [],
  }),
}));

vi.mock('../../stores/useScenarioStore', () => ({
  useScenarioStore: () => ({
    scenarios: [],
    sensitivityFactors: [],
    expectationGap: null,
    calculations: [],
    dataFreshnessStatus: 'Fresh',
    stressTestLogic: null,
    catalystList: [],
    verificationMetrics: [],
    capitalFlow: null,
    positionManagement: null,
    timeDimension: null,
  }),
}));

describe('AnalysisResult Regression Test', () => {
  const mockProps = {
    onResetToHome: vi.fn(),
    onExportFullReport: vi.fn(),
    onSendStockReport: vi.fn(),
    onSendDiscussionReport: vi.fn(),
    onSendChatReport: vi.fn(),
    onDiscussionQuestion: vi.fn(),
    onGenerateNewConclusion: vi.fn(),
    onChat: vi.fn(),
  };

  it('should render without crashing (Syntax/Structural Check)', () => {
    // This test will fail if the component has syntax errors or major structural regressions
    render(<AnalysisResult {...mockProps} />);
    expect(true).toBe(true);
  });
});
