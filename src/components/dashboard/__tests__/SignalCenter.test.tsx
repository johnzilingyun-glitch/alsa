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
});
