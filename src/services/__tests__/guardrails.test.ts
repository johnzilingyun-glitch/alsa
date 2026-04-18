import { describe, it, expect } from 'vitest';
import { auditExpertLogic } from '../discussion/guardrails';
import { AgentRole, StockAnalysis, ExpertOutput } from '../../types';

describe('Guardrails (Audit Sentinel)', () => {
  const mockAnalysis: Partial<StockAnalysis> = {
    stockInfo: {
      symbol: 'TEST',
      name: 'Test Corp',
      price: 100,
      fundamentalScores: {
        growthScore: 10, // Very low growth
        valueScore: 50,
        safetyScore: 50,
        moatRating: 'None',
        verdict: 'Neutral'
      },
      intrinsicValueEstimate: 80,
      change: 0,
      changePercent: 0,
      market: 'A-Share',
      currency: 'CNY',
      lastUpdated: '2026-04-18 20:00:00 CST',
      previousClose: 100
    },
    fundamentals: { 
      pe: "15", 
      pb: "3", 
      roe: "20", 
      eps: "5", 
      revenueGrowth: "10", 
      valuationPercentile: "50", 
      debtToEquity: "250" // High debt ratio (>200% for audit trigger)
    } as any
  };

  it('should flag Growth Integrity warning if AI claims hyper-growth on low scores', () => {
    const output: ExpertOutput = {
      role: 'Fundamental Analyst',
      message: { content: 'This company is seeing hyper growth in AI sector.', role: 'Fundamental Analyst', id: '1', timestamp: '', type: 'discussion', round: 1 },
      structuredData: {}
    };

    const findings = auditExpertLogic('Fundamental Analyst', output, mockAnalysis as StockAnalysis);
    expect(findings.some(f => f.rule === 'Growth Integrity')).toBe(true);
  });

  it('should flag Valuation Reality Check for extreme target prices', () => {
    const output: ExpertOutput = {
      role: 'Chief Strategist',
      message: { content: 'Bullish case.', role: 'Chief Strategist', id: '2', timestamp: '', type: 'discussion', round: 2 },
      structuredData: {
        tradingPlan: { 
          entryPrice: "1800", 
          targetPrice: "1200", // > 100% gap vs 100 price for testing
          stopLoss: "1700", 
          strategy: "Buy low", 
          strategyRisks: "Volatility" 
        } as any
      }
    };

    const findings = auditExpertLogic('Chief Strategist', output, mockAnalysis as StockAnalysis);
    expect(findings.some(f => f.rule === 'Valuation Reality Check')).toBe(true);
  });

  it('should flag Solvency Audit if AI claims robustness on high debt', () => {
    const output: ExpertOutput = {
      role: 'Fundamental Analyst',
      message: { content: 'The company has a strong balance sheet.', role: 'Fundamental Analyst', id: '3', timestamp: '', type: 'discussion', round: 1 },
      structuredData: {}
    };

    const findings = auditExpertLogic('Fundamental Analyst', output, mockAnalysis as StockAnalysis);
    expect(findings.some(f => f.rule === 'Solvency Audit')).toBe(true);
  });
});
