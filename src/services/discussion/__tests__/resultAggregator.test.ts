import { describe, it, expect } from 'vitest';
import { aggregateResults } from '../resultAggregator';
import type { AgentRole, ExpertOutput } from '../../../types';

function makeExpertOutput(role: AgentRole, content: string, extra?: Partial<ExpertOutput['structuredData']>): ExpertOutput {
  return {
    role,
    message: {
      role,
      content,
      timestamp: new Date().toISOString(),
      type: 'discussion',
    },
    structuredData: extra,
  };
}

describe('resultAggregator', () => {
  it('aggregates messages from all experts', () => {
    const results = new Map<AgentRole, ExpertOutput>();
    results.set('Technical Analyst', makeExpertOutput('Technical Analyst', 'Tech analysis content'));
    results.set('Risk Manager', makeExpertOutput('Risk Manager', 'Risk analysis content'));
    results.set('Chief Strategist', makeExpertOutput('Chief Strategist', 'Final conclusion here'));

    const discussion = aggregateResults(results, null);
    expect(discussion.messages).toHaveLength(3);
    expect(discussion.messages[0].role).toBe('Technical Analyst');
  });

  it('extracts finalConclusion from Chief Strategist', () => {
    const results = new Map<AgentRole, ExpertOutput>();
    results.set('Chief Strategist', makeExpertOutput('Chief Strategist', 'My final conclusion'));

    const discussion = aggregateResults(results, null);
    expect(discussion.finalConclusion).toBe('My final conclusion');
  });

  it('extracts coreVariables from Deep Research Specialist', () => {
    const results = new Map<AgentRole, ExpertOutput>();
    results.set('Deep Research Specialist', makeExpertOutput('Deep Research Specialist', 'Research', {
      coreVariables: [{ name: 'Revenue', value: '100B', unit: 'CNY', marketExpect: '95B', delta: '+5%', reason: 'Growth', evidenceLevel: '财报' }],
    }));

    const discussion = aggregateResults(results, null);
    expect(discussion.coreVariables).toHaveLength(1);
    expect(discussion.coreVariables![0].name).toBe('Revenue');
  });

  it('extracts quantifiedRisks from Risk Manager', () => {
    const results = new Map<AgentRole, ExpertOutput>();
    results.set('Risk Manager', makeExpertOutput('Risk Manager', 'Risk content', {
      quantifiedRisks: [{ name: 'Market Risk', probability: 30, impactPercent: -10, expectedLoss: -3, mitigation: 'Hedge' }],
    }));

    const discussion = aggregateResults(results, null);
    expect(discussion.quantifiedRisks).toHaveLength(1);
  });

  it('extracts tradingPlan from Chief Strategist', () => {
    const results = new Map<AgentRole, ExpertOutput>();
    results.set('Chief Strategist', makeExpertOutput('Chief Strategist', 'Plan', {
      tradingPlan: { entryPrice: '100', targetPrice: '120', stopLoss: '90', strategy: 'Buy', strategyRisks: 'Low' },
    }));

    const discussion = aggregateResults(results, null);
    expect(discussion.tradingPlan?.entryPrice).toBe('100');
  });

  it('extracts scenarios from Chief Strategist', () => {
    const results = new Map<AgentRole, ExpertOutput>();
    results.set('Chief Strategist', makeExpertOutput('Chief Strategist', 'Scenarios', {
      scenarios: [{ case: 'Bull', probability: 40, keyInputs: 'Strong', targetPrice: '130', marginOfSafety: '20%', expectedReturn: '30%', logic: 'Growth' }],
    }));

    const discussion = aggregateResults(results, null);
    expect(discussion.scenarios).toHaveLength(1);
  });

  it('includes backtest result when provided', () => {
    const results = new Map<AgentRole, ExpertOutput>();
    results.set('Chief Strategist', makeExpertOutput('Chief Strategist', 'Done'));

    const backtest = {
      previousDate: '2026-03-20',
      previousPrice: 100,
      currentPrice: 110,
      returnSincePrev: '+10%',
      previousRecommendation: 'Buy',
      previousTarget: '120',
      previousStopLoss: '90',
      status: 'In Progress' as const,
      accuracy: 70,
      learningPoint: 'On track',
    };

    const discussion = aggregateResults(results, backtest);
    expect(discussion.backtestResult).toBeDefined();
    expect(discussion.backtestResult!.actualReturn).toBe('+10%');
  });

  it('assigns unique IDs to messages', () => {
    const results = new Map<AgentRole, ExpertOutput>();
    results.set('Technical Analyst', makeExpertOutput('Technical Analyst', 'A'));
    results.set('Risk Manager', makeExpertOutput('Risk Manager', 'B'));

    const discussion = aggregateResults(results, null);
    const ids = discussion.messages.map(m => m.id);
    expect(new Set(ids).size).toBe(ids.length); // all unique
    ids.forEach(id => expect(id).toBeDefined());
  });
});
