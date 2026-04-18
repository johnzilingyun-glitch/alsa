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
      intrinsicValueEstimate: 80
    },
    fundamentals: {
      debtToEquity: '250' // High debt
    }
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
        tradingPlan: { targetPrice: '200' } // 250% of intrinsic value (80)
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
