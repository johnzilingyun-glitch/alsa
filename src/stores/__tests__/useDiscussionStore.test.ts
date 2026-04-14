import { describe, it, expect, beforeEach } from 'vitest';
import { useDiscussionStore } from '../../stores/useDiscussionStore';
import { AgentDiscussion } from '../../types';

describe('useDiscussionStore', () => {
  beforeEach(() => {
    useDiscussionStore.getState().resetDiscussion();
  });

  it('should have correct initial state', () => {
    const state = useDiscussionStore.getState();
    expect(state.discussionMessages).toEqual([]);
    expect(state.controversialPoints).toEqual([]);
    expect(state.tradingPlanHistory).toEqual([]);
    expect(state.analystWeights).toEqual([]);
  });

  it('should set discussion messages with array', () => {
    const msgs = [{ id: '1', role: 'Technical Analyst', content: 'test', timestamp: '2026-04-01' }] as any;
    useDiscussionStore.getState().setDiscussionMessages(msgs);
    expect(useDiscussionStore.getState().discussionMessages).toHaveLength(1);
  });

  it('should set discussion messages with updater', () => {
    const msg1 = { id: '1', role: 'Risk Manager', content: 'initial', timestamp: '2026-04-01' } as any;
    useDiscussionStore.getState().setDiscussionMessages([msg1]);
    useDiscussionStore.getState().setDiscussionMessages((prev) => [
      ...prev,
      { id: '2', role: 'Chief Strategist', content: 'reply', timestamp: '2026-04-01' } as any,
    ]);
    expect(useDiscussionStore.getState().discussionMessages).toHaveLength(2);
  });

  it('should set controversial points', () => {
    useDiscussionStore.getState().setControversialPoints(['估值分歧', '政策风险争议']);
    expect(useDiscussionStore.getState().controversialPoints).toEqual(['估值分歧', '政策风险争议']);
  });

  it('should set trading plan history with updater', () => {
    const plan = { version: 1, plan: { entryPrice: '30', targetPrice: '35' } } as any;
    useDiscussionStore.getState().setTradingPlanHistory([plan]);
    useDiscussionStore.getState().setTradingPlanHistory((prev) => [
      ...prev,
      { version: 2, plan: { entryPrice: '28', targetPrice: '36' } } as any,
    ]);
    expect(useDiscussionStore.getState().tradingPlanHistory).toHaveLength(2);
  });

  it('should set analyst weights', () => {
    const weights = [{ role: 'Technical Analyst', weight: 0.15 }] as any;
    useDiscussionStore.getState().setAnalystWeights(weights);
    expect(useDiscussionStore.getState().analystWeights).toHaveLength(1);
  });

  it('should set discussion results from AgentDiscussion', () => {
    const discussion: Partial<AgentDiscussion> = {
      messages: [{ id: '1', role: 'Chief Strategist', content: 'summary', timestamp: '2026-04-01' }] as any,
      controversialPoints: ['技术面 vs 基本面分歧'],
      tradingPlanHistory: [{ version: 1 }] as any,
      analystWeights: [{ role: 'Risk Manager', weight: 0.12 }] as any,
    };
    useDiscussionStore.getState().setDiscussionResults(discussion as AgentDiscussion);

    const state = useDiscussionStore.getState();
    expect(state.discussionMessages).toHaveLength(1);
    expect(state.controversialPoints).toEqual(['技术面 vs 基本面分歧']);
    expect(state.tradingPlanHistory).toHaveLength(1);
    expect(state.analystWeights).toHaveLength(1);
  });

  it('should reset discussion to initial state', () => {
    useDiscussionStore.getState().setDiscussionMessages([{ id: '1' }] as any);
    useDiscussionStore.getState().setControversialPoints(['point']);
    useDiscussionStore.getState().resetDiscussion();

    const state = useDiscussionStore.getState();
    expect(state.discussionMessages).toEqual([]);
    expect(state.controversialPoints).toEqual([]);
  });
});
