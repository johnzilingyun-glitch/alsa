import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { SignalCenter } from '../SignalCenter';
import { useMarketStore } from '../../../stores/useMarketStore';

// Mock the API client
vi.mock('../../../services/api/alertsClient', () => ({
  alertsClient: {
    listClosed: vi.fn().mockResolvedValue({ items: [] }),
    delete: vi.fn().mockResolvedValue({ success: true }),
    create: vi.fn().mockResolvedValue({ success: true }),
    list: vi.fn().mockResolvedValue({ items: [] }),
  }
}));

// Mock Translation
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key })
}));

describe('SignalCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMarketStore.setState({
      searchAlerts: [
        { alert_id: 'test_123', symbol: '0700.HK', market: 'HK-Share', entry_price: 300, target_price: 350, stop_loss: 280, name: 'Tencent', currency: 'HKD' }
      ],
      alertPrices: {
        '0700.HK': 310
      },
      historyItems: []
    });
  });

  it('renders active alerts', () => {
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.getByText('智能交易信号中心')).toBeInTheDocument();
    expect(screen.getByText('Tencent')).toBeInTheDocument();
    expect(screen.getByText('0700.HK · HK-Share')).toBeInTheDocument();
  });

  it('renders the trading plan text from tradingPlan.strategy (actionPlan/summary never existed)', () => {
    useMarketStore.setState({
      searchAlerts: [
        { alert_id: 'test_strat', symbol: '0700.HK', market: 'HK-Share', entry_price: 300, target_price: 350, stop_loss: 280, name: 'Tencent', currency: 'HKD' }
      ],
      alertPrices: { '0700.HK': 310 },
      historyItems: [
        { stockInfo: { symbol: '0700.HK' }, tradingPlan: { strategy: '分批建仓策略原文' } }
      ]
    });
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.getByText(/分批建仓策略原文/)).toBeInTheDocument();
  });

  it('shows action badges (买入/卖出/持有/观望)', () => {
    useMarketStore.setState({
      searchAlerts: [
        { alert_id: 'a1', symbol: 'S1', market: 'A-Share', entry_price: 10, target_price: 12, stop_loss: 9, name: 'N1', currency: 'CNY', action: 'buy' },
        { alert_id: 'a2', symbol: 'S2', market: 'A-Share', entry_price: 10, target_price: 12, stop_loss: 9, name: 'N2', currency: 'CNY', action: 'sell' },
        { alert_id: 'a3', symbol: 'S3', market: 'A-Share', entry_price: 10, target_price: 12, stop_loss: 9, name: 'N3', currency: 'CNY', action: 'hold' },
        { alert_id: 'a4', symbol: 'S4', market: 'A-Share', entry_price: 10, target_price: 12, stop_loss: 9, name: 'N4', currency: 'CNY', action: 'watch' },
      ],
      alertPrices: {},
      historyItems: []
    });
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.getByText('买入')).toBeInTheDocument();
    expect(screen.getByText('卖出')).toBeInTheDocument();
    expect(screen.getByText('持有')).toBeInTheDocument();
    expect(screen.getByText('观望')).toBeInTheDocument();
  });

  it('buy signal: price >= target → 目标达成 (long semantics, unchanged)', () => {
    useMarketStore.setState({
      searchAlerts: [
        { alert_id: 'long_hit', symbol: 'S1', market: 'A-Share', entry_price: 10, target_price: 12, stop_loss: 9, name: 'N1', currency: 'CNY', action: 'buy' }
      ],
      alertPrices: { S1: 12.5 },
      historyItems: []
    });
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.getByText('目标达成！🚀 建议考虑止盈')).toBeInTheDocument();
  });

  it('sell signal: price <= target → 空头目标达成 (short semantics)', () => {
    useMarketStore.setState({
      searchAlerts: [
        { alert_id: 'short_hit', symbol: 'S2', market: 'A-Share', entry_price: 30, target_price: 25, stop_loss: 32, name: 'N2', currency: 'CNY', action: 'sell' }
      ],
      alertPrices: { S2: 24.0 },
      historyItems: []
    });
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.getByText('空头目标达成！🚀 建议考虑止盈')).toBeInTheDocument();
  });

  it('sell signal: price >= stop → 涨破止损位 (short stop-loss)', () => {
    useMarketStore.setState({
      searchAlerts: [
        { alert_id: 'short_stop', symbol: 'S2', market: 'A-Share', entry_price: 30, target_price: 25, stop_loss: 32, name: 'N2', currency: 'CNY', action: 'sell' }
      ],
      alertPrices: { S2: 33.0 },
      historyItems: []
    });
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.getByText('涨破止损位！⚠️ 建议按计划回补离场')).toBeInTheDocument();
  });

  it('legacy row without action: target < entry infers short (mirrors backend monitor)', () => {
    useMarketStore.setState({
      searchAlerts: [
        { alert_id: 'legacy_short', symbol: 'S5', market: 'A-Share', entry_price: 30, target_price: 25, stop_loss: 32, name: 'N5', currency: 'CNY' }
      ],
      alertPrices: { S5: 24.0 },
      historyItems: []
    });
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.getByText('空头目标达成！🚀 建议考虑止盈')).toBeInTheDocument();
  });

  it('hold signal: neutral monitoring copy, never bullish 目标达成/止盈 verdicts', () => {
    useMarketStore.setState({
      searchAlerts: [
        { alert_id: 'hold1', symbol: 'S6', market: 'A-Share', entry_price: 30, target_price: 25, stop_loss: 32, name: 'N6', currency: 'CNY', action: 'hold' }
      ],
      alertPrices: { S6: 24.0 }, // price <= target, but hold must stay neutral
      historyItems: []
    });
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.getByText('持有观察中 · 价格运行中')).toBeInTheDocument();
    expect(screen.queryByText('空头目标达成！🚀 建议考虑止盈')).toBeNull();
    expect(screen.queryByText('目标达成！🚀 建议考虑止盈')).toBeNull();
  });

  it('watch signal: neutral 观望跟踪中 copy', () => {
    useMarketStore.setState({
      searchAlerts: [
        { alert_id: 'watch1', symbol: 'S7', market: 'A-Share', entry_price: 10, target_price: 12, stop_loss: 9, name: 'N7', currency: 'CNY', action: 'watch' }
      ],
      alertPrices: { S7: 12.5 }, // price >= target, but watch must stay neutral
      historyItems: []
    });
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.getByText('观望跟踪中 · 价格运行中')).toBeInTheDocument();
    expect(screen.queryByText('目标达成！🚀 建议考虑止盈')).toBeNull();
  });

  it('opens manual add modal when clicking add button', () => {
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    const addButton = screen.getByText(/手动添加/i);
    fireEvent.click(addButton);
    
    expect(screen.getByText('手动添加监控信号')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('e.g. AAPL / 腾讯')).toBeInTheDocument();
  });

  it('shows delete button on active alert', () => {
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    const deleteBtn = screen.getByText('删除');
    expect(deleteBtn).toBeInTheDocument();
  });

  it('does not crash when store fields are null (stale persisted localStorage)', () => {
    // Older persist schema merged these back as null, which previously threw
    // during the initial render and surfaced the ErrorBoundary fallback.
    useMarketStore.setState({
      searchAlerts: null as any,
      alertPrices: null as any,
      historyItems: null as any,
    });
    render(<SignalCenter isOpen={true} onClose={() => {}} />);
    expect(screen.queryByText('信号中心加载失败，请关闭后重试')).toBeNull();
    expect(screen.getByText('智能交易信号中心')).toBeInTheDocument();
  });
});
