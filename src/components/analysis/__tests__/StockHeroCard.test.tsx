import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { StockHeroCard } from '../StockHeroCard';
import type { StockAnalysis } from '../../../types';

// Mock translation hook
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key })
}));

describe('StockHeroCard - AI Data Resilience Tests', () => {
  const baseAnalysis: StockAnalysis = {
    stockInfo: {
      symbol: 'TEST.SS',
      name: 'Test Stock',
      price: 100,
      change: 5,
      changePercent: 5,
      market: 'A-Share',
      currency: 'CNY',
      lastUpdated: '2026-04-09 10:00:00 CST',
      previousClose: 95
    },
    summary: 'Testing',
    technicalAnalysis: 'Tech OK',
    fundamentalAnalysis: 'Fund OK',
    sentiment: 'Bullish',
    score: 80,
    recommendation: 'Buy',
    keyRisks: [],
    keyOpportunities: [],
    news: [],
    tradingPlan: { 
      entryPrice: '100', 
      targetPrice: '120', 
      stopLoss: '90', 
      strategy: 'Test',
      strategyRisks: 'None'
    }
  };

  it('OK Scenario: Renders successfully with core stock information', () => {
    const { container } = render(<StockHeroCard analysis={baseAnalysis} />);
    expect(container).toBeInTheDocument();
    expect(screen.getByText('Test Stock')).toBeInTheDocument();
    expect(screen.getByText('TEST.SS')).toBeInTheDocument();
    expect(screen.getByText('100.00')).toBeInTheDocument();
  });

  it('Resilience Scenario: Renders successfully even if moat analysis is missing', () => {
    const noMoatAnalysis = { ...baseAnalysis, moatAnalysis: undefined };
    const { container } = render(<StockHeroCard analysis={noMoatAnalysis} />);
    expect(container).toBeInTheDocument();
    expect(screen.queryByText(/护城河/)).not.toBeInTheDocument();
  });
});
