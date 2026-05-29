import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { AccountMergeModal } from '../AccountMergeModal';
import { TradeTicketModal } from '../TradeTicketModal';

// Mock the API client
vi.mock('../../../services/api/mockTradingClient', () => ({
  mergeAccounts: vi.fn().mockResolvedValue({}),
  executeTrade: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../../services/api/stockClient', () => ({
  getQuotes: vi.fn().mockResolvedValue([{ symbol: 'AAPL', price: 150.0 }]),
}));

describe('MockTrading UI Components Verification', () => {
  it('should render AccountMergeModal and handle state correctly', async () => {
    const mockAccounts = [
      { account_id: '1', name: 'Global Account', market: 'Global', currency: 'CNY', current_cash: 500000, initial_balance: 500000, status: 'active', user_id: 'default_user' },
      { account_id: '2', name: 'US Account', market: 'US-Share', currency: 'USD', current_cash: 10000, initial_balance: 10000, status: 'active', user_id: 'default_user' },
    ];

    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <AccountMergeModal
        accounts={mockAccounts as any}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    // Verify it renders
    expect(screen.getByText('合并账号')).toBeDefined();
    
    // Verify target account dropdown exists and defaults to the first account
    const select = screen.getByRole('combobox');
    expect((select as HTMLSelectElement).value).toBe('1');
    
    // Check if the other account is available to be selected as a source
    expect(screen.getByText('US Account')).toBeDefined();
    
    // Select the US Account as source
    const checkbox = screen.getByRole('checkbox');
    fireEvent.click(checkbox);
    
    expect((checkbox as HTMLInputElement).checked).toBe(true);

    // Click merge
    const mergeBtn = screen.getByText('确认合并');
    fireEvent.click(mergeBtn);

    // After clicking, it should call the API (since it's mocked, it resolves)
    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('should render TradeTicketModal and handle trading input', async () => {
    const mockAccount = { account_id: '1', name: 'Global Account', market: 'Global', currency: 'CNY', current_cash: 500000, initial_balance: 500000, status: 'active', user_id: 'default_user' };
    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <TradeTicketModal
        account={mockAccount as any}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    // Ensure it renders
    expect(screen.getByText('手动交易')).toBeDefined();
    expect(screen.getByText('买入 (BUY)')).toBeDefined();

    // The symbol input
    const inputs = screen.getAllByRole('textbox');
    const symbolInput = inputs[0] as HTMLInputElement;
    const sharesInput = screen.getByPlaceholderText('0') as HTMLInputElement;

    // Type a symbol
    fireEvent.change(symbolInput, { target: { value: 'AAPL' } });
    expect(symbolInput.value).toBe('AAPL');

    // Due to debounce in component, we wait for quote mock to resolve
    await waitFor(() => {
      expect(screen.getByText('150.00')).toBeDefined();
    }, { timeout: 2000 });

    // Type shares
    fireEvent.change(sharesInput, { target: { value: '10' } });
    
    // Click buy
    const confirmBtn = screen.getByText('确认买入');
    expect((confirmBtn as HTMLButtonElement).disabled).toBe(false);
    
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled();
    });
  });
});
