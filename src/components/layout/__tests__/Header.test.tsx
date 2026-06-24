import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

const { lucideMock } = vi.hoisted(() => {
  const icons = [
    'Download', 'Bell', 'History', 'Clock', 'Settings', 'Loader2', 'Search',
    'TrendingUp', 'Zap', 'BarChart3', 'Microscope', 'Languages', 'Menu', 'X',
    'Target', 'Activity', 'BrainCircuit', 'Wrench', 'BarChart2', 'Users', 'LogOut',
  ];
  const m: Record<string, any> = {};
  icons.forEach(n => { m[n] = () => null; });
  return { lucideMock: m };
});
vi.mock('lucide-react', () => lucideMock);

vi.mock('motion/react', () => ({
  motion: { div: ({ children, ...props }: any) => <div {...props}>{children}</div> },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en', changeLanguage: vi.fn() } }),
}));

import { useUIStore } from '../../../stores/useUIStore';
import { useMarketStore } from '../../../stores/useMarketStore';
import { useAuthStore } from '../../../stores/useAuthStore';

vi.mock('../../shared/StockSearchInput', () => ({
  StockSearchInput: (props: any) => <input data-testid="StockSearchInput" value={props.value} onChange={() => {}} />,
}));

import { Header } from '../Header';

const defaultProps = {
  onSearch: vi.fn(), onResetToHome: vi.fn(), onTriggerDailyReport: vi.fn(),
  onOpenHistory: vi.fn(), onOpenSignals: vi.fn(), onFetchAdminData: vi.fn(),
};

beforeEach(() => {
  useUIStore.setState({
    loading: false, isTriggeringReport: false, showAdminPanel: false,
    analysisLevel: 'standard', serviceStatus: 'available',
  });
  useMarketStore.setState({ dailyReport: null, activeAlertStatus: 'neutral' });
  useAuthStore.setState({ user: null });
});

describe('Header', () => {
  it('renders the brand and title', () => {
    render(<Header {...defaultProps} />);
    expect(screen.getByText('header.brand')).toBeTruthy();
    expect(screen.getByText('header.title')).toBeTruthy();
    expect(screen.getByText('header.subtitle')).toBeTruthy();
  });

  it('renders search form elements', () => {
    render(<Header {...defaultProps} />);
    expect(screen.getByTestId('StockSearchInput')).toBeTruthy();
    expect(screen.getByText('levels.quick')).toBeTruthy();
    expect(screen.getByText('levels.standard')).toBeTruthy();
    expect(screen.getByText('levels.deep')).toBeTruthy();
  });

  it('shows loading state on search button', async () => {
    render(<Header {...defaultProps} />);
    useUIStore.setState({ loading: true });
    await waitFor(() => {
      expect(screen.getByText('header.addToQueue')).toBeTruthy();
    });
  });

  it('shows quota exhausted banner', () => {
    useUIStore.setState({ serviceStatus: 'quota_exhausted' });
    render(<Header {...defaultProps} />);
    expect(screen.getByText('errors.quota_exhausted_title')).toBeTruthy();
  });

  it('renders language toggle button', () => {
    render(<Header {...defaultProps} />);
    expect(screen.getByLabelText('header.toggleLanguage')).toBeTruthy();
  });

  it('shows download button when daily report exists', () => {
    useMarketStore.setState({ dailyReport: '# Market Report' });
    render(<Header {...defaultProps} />);
    expect(screen.getByLabelText('header.downloadReport')).toBeTruthy();
  });

  it('shows mobile menu when hamburger clicked', () => {
    render(<Header {...defaultProps} />);
    fireEvent.click(screen.getByLabelText('Menu'));
    expect(screen.getByText('header.sysLogs')).toBeTruthy();
  });

  it('shows toolbox dropdown', () => {
    render(<Header {...defaultProps} />);
    fireEvent.click(screen.getByLabelText('Toolbox'));
    expect(screen.getByText('header.sysLogs')).toBeTruthy();
  });

  it('shows user avatar when logged in', () => {
    useAuthStore.setState({ user: { username: 'testuser', role: 'user', display_name: 'Test User' } });
    render(<Header {...defaultProps} />);
    fireEvent.click(screen.getByTitle('Test User'));
    expect(screen.getByText('登出')).toBeTruthy();
  });
});
