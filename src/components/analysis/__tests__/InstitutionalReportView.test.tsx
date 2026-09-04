import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mutable shared mocks (vi.hoisted keeps them available inside vi.mock factories)
const mocks = vi.hoisted(() => {
  return {
    analysis: null as any,
    showToast: vi.fn(),
    create: vi.fn().mockResolvedValue({ alert_id: 'alt_test1', symbol: '600378' }),
    list: vi.fn().mockResolvedValue({ items: [] }),
    setAlerts: vi.fn(),
    fetchMock: vi.fn(),
  };
});

vi.mock('lucide-react', () => {
  const icons = ['Loader2', 'FileText', 'AlertCircle', 'Target', 'CheckCircle2', 'Bell', 'BellRing'];
  const out: Record<string, unknown> = {};
  icons.forEach((icon) => {
    out[icon] = () => <div data-testid={`icon-${icon}`} />;
  });
  return out;
});

vi.mock('motion/react', () => ({
  motion: { div: ({ children }: any) => <div>{children}</div> },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../../services/api/alertsClient', () => ({
  alertsClient: {
    create: mocks.create,
    list: mocks.list,
    enableMonitoring: vi.fn().mockResolvedValue({ success: true }),
  },
}));

vi.mock('../../../stores/useUIStore', () => ({
  useUIStore: (selector?: (s: any) => any) =>
    selector ? selector({ showToast: mocks.showToast }) : { showToast: mocks.showToast },
}));

vi.mock('../../../stores/useAnalysisStore', () => ({
  useAnalysisStore: (selector?: (s: any) => any) =>
    selector
      ? selector({
          lastJobId: 'job_test_1',
          cachedReportHtml: null,
          cachedReportJobId: null,
          setCachedReport: vi.fn(),
          analysis: mocks.analysis,
        })
      : { analysis: mocks.analysis },
}));

vi.mock('../../../stores/useConfigStore', () => {
  const state = { config: {}, feishuWebhookUrl: '', addTokenUsage: vi.fn() };
  return {
    useConfigStore: Object.assign((selector?: (s: any) => any) => (selector ? selector(state) : state), {
      getState: () => state,
    }),
  };
});

vi.mock('../../../stores/useMarketStore', () => {
  const state = { searchAlerts: [], setAlerts: mocks.setAlerts };
  return {
    useMarketStore: Object.assign((selector?: (s: any) => any) => (selector ? selector(state) : state), {
      getState: () => state,
    }),
  };
});

// Import component AFTER mocks
import { InstitutionalReportView } from '../InstitutionalReportView';

const REPORT_HTML = '<!DOCTYPE html><html><body><h1>Mock institutional report</h1></body></html>';

function makeAnalysis(overrides: Record<string, unknown>) {
  return {
    stockInfo: {
      symbol: '600378',
      name: '昊华科技',
      market: 'A-Share',
      price: 24.5,
      currency: 'CNY',
      lastUpdated: '2026-09-01 10:00:00 CST',
    },
    summary: 'summary',
    sentiment: 'Bearish',
    score: 50,
    recommendation: 'Sell',
    keyRisks: [],
    keyOpportunities: [],
    news: [],
    technicalAnalysis: '',
    fundamentalAnalysis: '',
    ...overrides,
  };
}

async function renderWithReport() {
  mocks.fetchMock.mockImplementation(() =>
    Promise.resolve({ ok: true, text: () => Promise.resolve(REPORT_HTML) })
  );
  vi.stubGlobal('fetch', mocks.fetchMock);
  render(<InstitutionalReportView />);
  // Wait for the report fetch + signal card to appear
  await waitFor(() => {
    expect(screen.getByText('智能信号监控与执行计划')).toBeInTheDocument();
  });
}

describe('InstitutionalReportView handleAddToSignalCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.analysis = null;
  });

  it('REFUSES to create an alert for a Sell plan without an entry price (no fabricated levels)', async () => {
    // Regression: 昊华科技 Sell signal used to become a fabricated long signal
    // with entry=currentPrice, target=entry*1.15, stop=entry*0.92.
    // NOTE: entryPrice deliberately avoids the "不推荐" marker so the button
    // still renders and we exercise the refusal path itself.
    mocks.analysis = makeAnalysis({
      tradingPlan: {
        action: 'sell',
        entryPrice: '市价附近',
        targetPrice: '21.0',
        stopLoss: '26.5',
        strategy: '等待反弹后减持',
        strategyRisks: 'r',
      },
    });
    await renderWithReport();

    const addButton = screen.getByRole('button', { name: /执行计划并启动信号监控/ });
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(mocks.showToast).toHaveBeenCalledWith(
        expect.stringContaining('入场价'),
        'error'
      );
    });
    expect(mocks.create).not.toHaveBeenCalled();
    expect(mocks.setAlerts).not.toHaveBeenCalled();
  });

  it('REFUSES to create an alert when target/stop are percentages instead of prices', async () => {
    mocks.analysis = makeAnalysis({
      recommendation: 'Buy',
      tradingPlan: {
        entryPrice: '25.8',
        targetPrice: '预期 +15~20%',
        stopLoss: '技术面破位 -8%',
        strategy: 's',
        strategyRisks: 'r',
      },
    });
    await renderWithReport();

    fireEvent.click(screen.getByRole('button', { name: /执行计划并启动信号监控/ }));

    await waitFor(() => {
      expect(mocks.showToast).toHaveBeenCalledWith(
        expect.stringContaining('目标价'),
        'error'
      );
    });
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('creates the alert with the action field for a valid plan', async () => {
    mocks.analysis = makeAnalysis({
      recommendation: 'Buy',
      tradingPlan: {
        action: 'buy',
        entryPrice: '25.8-26.5',
        targetPrice: '32.0',
        stopLoss: '23.5',
        strategy: '分批建仓',
        strategyRisks: 'r',
      },
    });
    await renderWithReport();

    fireEvent.click(screen.getByRole('button', { name: /执行计划并启动信号监控/ }));

    await waitFor(() => {
      expect(mocks.create).toHaveBeenCalledTimes(1);
    });
    const payload = mocks.create.mock.calls[0][0];
    expect(payload.action).toBe('buy');
    // Range entry resolves to its midpoint (26.15), never a fabricated value
    expect(payload.entry_price).toBeCloseTo(26.15);
    expect(payload.target_price).toBe(32.0);
    expect(payload.stop_loss).toBe(23.5);
    expect(mocks.showToast).toHaveBeenCalledWith(
      expect.stringContaining('已添加至信号中心'),
      'success'
    );
  });

  it('anchors hold signals on the live price and passes action=hold', async () => {
    mocks.analysis = makeAnalysis({
      recommendation: 'Hold',
      tradingPlan: {
        action: 'hold',
        entryPrice: '',
        targetPrice: '30.0',
        stopLoss: '22.0',
        strategy: '持有观察',
        strategyRisks: 'r',
      },
    });
    await renderWithReport();

    fireEvent.click(screen.getByRole('button', { name: /执行计划并启动信号监控/ }));

    await waitFor(() => {
      expect(mocks.create).toHaveBeenCalledTimes(1);
    });
    const payload = mocks.create.mock.calls[0][0];
    expect(payload.action).toBe('hold');
    expect(payload.entry_price).toBe(24.5); // live price as tracking anchor
  });
});
