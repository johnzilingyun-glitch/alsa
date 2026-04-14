import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// Mock component for testing
const TradingPlan = ({ plan }: { plan: any }) => {
  if (!plan) return null;
  return (
    <div data-testid="trading-plan">
      <h3>交易计划</h3>
      <div data-testid="entry-price">{plan.entryPrice}</div>
      <div data-testid="target-price">{plan.targetPrice}</div>
      <div data-testid="stop-loss">{plan.stopLoss}</div>
      <p>{plan.strategy}</p>
    </div>
  );
};

describe('TradingPlan Component', () => {
  it('should render trading plan details correctly', () => {
    const mockPlan = {
      entryPrice: '150.00',
      targetPrice: '180.00',
      stopLoss: '140.00',
      strategy: '逢低买入，长期持有'
    };

    render(<TradingPlan plan={mockPlan} />);

    expect(screen.getByTestId('trading-plan')).toBeInTheDocument();
    expect(screen.getByTestId('entry-price')).toHaveTextContent('150.00');
    expect(screen.getByTestId('target-price')).toHaveTextContent('180.00');
    expect(screen.getByTestId('stop-loss')).toHaveTextContent('140.00');
    expect(screen.getByText('逢低买入，长期持有')).toBeInTheDocument();
  });

  it('should not render if plan is missing', () => {
    render(<TradingPlan plan={null} />);
    expect(screen.queryByTestId('trading-plan')).not.toBeInTheDocument();
  });
});
