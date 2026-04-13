import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ScorePanel } from '../ScorePanel';
import type { StockAnalysis } from '../../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key })
}));

describe('ScorePanel - AI Data Resilience Tests', () => {
  const baseAnalysis: StockAnalysis = {
    stockInfo: { 
      symbol: 'TEST', 
      name: 'Test', 
      price: 100, 
      change: 0, 
      changePercent: 0, 
      market: 'US-Share', 
      currency: 'USD', 
      lastUpdated: 'Now',
      previousClose: 100
    },
    summary: 'OK',
    technicalAnalysis: 'OK',
    fundamentalAnalysis: 'OK',
    sentiment: 'Bullish',
    score: 85,
    recommendation: 'Buy',
    keyRisks: [],
    keyOpportunities: [],
    news: [],
    tradingPlan: { 
      entryPrice: '1', 
      targetPrice: '2', 
      stopLoss: '0.5', 
      strategy: 'Hold',
      strategyRisks: 'None'
    }
  };

  it('OK Scenario: Safely renders proper text items within keyOpportunities & keyRisks', () => {
    const analysis = { ...baseAnalysis, keyOpportunities: ['Strong Growth'], keyRisks: ['High Volatility'] };
    const { container } = render(<ScorePanel analysis={analysis} />);
    expect(container).toBeInTheDocument();
    expect(screen.getByText('Strong Growth')).toBeInTheDocument();
    expect(screen.getByText('High Volatility')).toBeInTheDocument();
  });

  it('NG Scenario: Gracefully catches and strings improperly formatted AI objects passing through the boundary', () => {
    const analysis = { 
      ...baseAnalysis, 
      keyOpportunities: [{ narrative: 'AI Hallucinated Object 1' }], 
      keyRisks: [{ warning: 'AI Hallucinated Object 2' }] 
    } as any;
    
    // Renders without crashing ("Objects are not valid as a React child")
    const { container } = render(<ScorePanel analysis={analysis} />);
    expect(container).toBeInTheDocument();
    
    // Renders the stringified object
    expect(screen.getByText(/AI Hallucinated Object 1/i)).toBeInTheDocument();
    expect(screen.getByText(/AI Hallucinated Object 2/i)).toBeInTheDocument();
  });
});
