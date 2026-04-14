import { describe, it, expect, beforeEach } from 'vitest';
import { useScenarioStore } from '../../stores/useScenarioStore';
import { AgentDiscussion } from '../../types';

describe('useScenarioStore', () => {
  beforeEach(() => {
    useScenarioStore.getState().resetScenario();
  });

  it('should have correct initial state', () => {
    const state = useScenarioStore.getState();
    expect(state.scenarios).toEqual([]);
    expect(state.sensitivityFactors).toEqual([]);
    expect(state.expectationGap).toBeNull();
    expect(state.calculations).toEqual([]);
    expect(state.stressTestLogic).toBe('');
    expect(state.catalystList).toEqual([]);
    expect(state.capitalFlow).toBeNull();
    expect(state.positionManagement).toBeNull();
    expect(state.timeDimension).toBeNull();
    expect(state.dataFreshnessStatus).toBeNull();
    expect(state.backtestResult).toBeNull();
  });

  it('should set scenarios', () => {
    const scenarios = [
      { name: 'Bull', probability: 0.3, targetPrice: 40 },
      { name: 'Base', probability: 0.5, targetPrice: 32 },
      { name: 'Bear', probability: 0.2, targetPrice: 24 },
    ] as any;
    useScenarioStore.getState().setScenarios(scenarios);
    expect(useScenarioStore.getState().scenarios).toHaveLength(3);
  });

  it('should set sensitivity factors', () => {
    const factors = [{ name: '利率变化', impact: 0.05, direction: 'negative' }] as any;
    useScenarioStore.getState().setSensitivityFactors(factors);
    expect(useScenarioStore.getState().sensitivityFactors).toHaveLength(1);
  });

  it('should set expectation gap', () => {
    const gap = { marketExpectation: 35, aiTarget: 32, gapPercent: -8.6 } as any;
    useScenarioStore.getState().setExpectationGap(gap);
    expect(useScenarioStore.getState().expectationGap).not.toBeNull();
  });

  it('should set data freshness status', () => {
    useScenarioStore.getState().setDataFreshnessStatus('Stale');
    expect(useScenarioStore.getState().dataFreshnessStatus).toBe('Stale');
  });

  it('should set backtest result', () => {
    const result = { accuracy: 75, status: 'In Progress' };
    useScenarioStore.getState().setBacktestResult(result);
    expect(useScenarioStore.getState().backtestResult.accuracy).toBe(75);
  });

  it('should set scenario results from AgentDiscussion', () => {
    const discussion: Partial<AgentDiscussion> = {
      scenarios: [{ name: 'Bull', probability: 0.4, targetPrice: 50 }] as any,
      sensitivityFactors: [{ name: 'GDP增速' }] as any,
      stressTestLogic: '压力测试逻辑',
      catalystList: [{ name: '政策催化' }] as any,
      capitalFlow: { inflow: 1000, outflow: 800 } as any,
      dataFreshnessStatus: 'Fresh' as any,
      backtestResult: { previousDate: '2026-03-01', previousRecommendation: 'Buy', actualReturn: '+5%', learningPoint: '验证' },
    };
    useScenarioStore.getState().setScenarioResults(discussion as AgentDiscussion);

    const state = useScenarioStore.getState();
    expect(state.scenarios).toHaveLength(1);
    expect(state.sensitivityFactors).toHaveLength(1);
    expect(state.stressTestLogic).toBe('压力测试逻辑');
    expect(state.capitalFlow).not.toBeNull();
    expect(state.dataFreshnessStatus).toBe('Fresh');
  });

  it('should reset scenario to initial state', () => {
    useScenarioStore.getState().setScenarios([{ name: 'test' }] as any);
    useScenarioStore.getState().setDataFreshnessStatus('Warning');
    useScenarioStore.getState().resetScenario();

    const state = useScenarioStore.getState();
    expect(state.scenarios).toEqual([]);
    expect(state.dataFreshnessStatus).toBeNull();
  });
});
