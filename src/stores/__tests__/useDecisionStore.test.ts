import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useDecisionStore } from '../../stores/useDecisionStore';

describe('useDecisionStore', () => {
  beforeEach(() => {
    useDecisionStore.setState({
      entries: [],
      stats: null,
    });
  });

  it('has correct initial state', () => {
    const state = useDecisionStore.getState();
    expect(state.entries).toEqual([]);
    expect(state.stats).toBeNull();
  });

  it('adds decision entry', () => {
    useDecisionStore.getState().addEntry({
      symbol: 'AAPL',
      name: 'Apple',
      market: 'US-Share',
      analysisId: 'analysis-1',
      action: 'buy',
      reasoning: 'Strong fundamentals',
      priceAtDecision: 150,
      confidence: 80,
    });
    const entries = useDecisionStore.getState().entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].symbol).toBe('AAPL');
    expect(entries[0].action).toBe('buy');
    expect(entries[0].id).toBeTruthy();
    expect(entries[0].createdAt).toBeTruthy();
    expect(entries[0].reviewDate).toBeTruthy();
  });

  it('sets review date to 30 days after creation', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-04-01T10:00:00Z'));

    useDecisionStore.getState().addEntry({
      symbol: 'AAPL',
      name: 'Apple',
      market: 'US-Share',
      analysisId: 'a1',
      action: 'buy',
      reasoning: 'Test',
      priceAtDecision: 150,
      confidence: 70,
    });

    vi.useRealTimers();

    const entry = useDecisionStore.getState().entries[0];
    expect(entry.reviewDate).toContain('2026-05');
  });

  it('updates entry outcome', () => {
    useDecisionStore.getState().addEntry({
      symbol: 'AAPL',
      name: 'Apple',
      market: 'US-Share',
      analysisId: 'a1',
      action: 'buy',
      reasoning: 'Test',
      priceAtDecision: 150,
      confidence: 70,
    });
    const id = useDecisionStore.getState().entries[0].id;
    useDecisionStore.getState().updateEntry(id, {
      outcome: 'correct',
      priceAtReview: 180,
      actualReturn: 20,
    });
    const entry = useDecisionStore.getState().entries[0];
    expect(entry.outcome).toBe('correct');
    expect(entry.priceAtReview).toBe(180);
  });

  it('adds reflection to entry', () => {
    useDecisionStore.getState().addEntry({
      symbol: 'GOOG',
      name: 'Google',
      market: 'US-Share',
      analysisId: 'a2',
      action: 'hold',
      reasoning: 'Uncertain',
      priceAtDecision: 2800,
      confidence: 50,
    });
    const id = useDecisionStore.getState().entries[0].id;
    useDecisionStore.getState().updateEntry(id, {
      reflection: 'Should have bought',
      lessonsLearned: ['Be more decisive'],
    });
    const entry = useDecisionStore.getState().entries[0];
    expect(entry.reflection).toBe('Should have bought');
    expect(entry.lessonsLearned).toEqual(['Be more decisive']);
  });

  it('gets pending reviews', () => {
    // Add an entry with a past review date
    useDecisionStore.setState({
      entries: [{
        id: '1',
        symbol: 'AAPL',
        name: 'Apple',
        market: 'US-Share',
        analysisId: 'a1',
        action: 'buy',
        reasoning: 'Test',
        priceAtDecision: 150,
        confidence: 70,
        createdAt: '2026-02-01',
        reviewDate: '2026-03-03', // Past date
      }],
    });
    const pending = useDecisionStore.getState().getPendingReviews();
    expect(pending).toHaveLength(1);
  });

  it('does not include future reviews in pending', () => {
    useDecisionStore.setState({
      entries: [{
        id: '1',
        symbol: 'AAPL',
        name: 'Apple',
        market: 'US-Share',
        analysisId: 'a1',
        action: 'buy',
        reasoning: 'Test',
        priceAtDecision: 150,
        confidence: 70,
        createdAt: '2026-04-01',
        reviewDate: '2026-06-01', // Future date
      }],
    });
    const pending = useDecisionStore.getState().getPendingReviews();
    expect(pending).toHaveLength(0);
  });

  it('does not include already reviewed entries in pending', () => {
    useDecisionStore.setState({
      entries: [{
        id: '1',
        symbol: 'AAPL',
        name: 'Apple',
        market: 'US-Share',
        analysisId: 'a1',
        action: 'buy',
        reasoning: 'Test',
        priceAtDecision: 150,
        confidence: 70,
        createdAt: '2026-02-01',
        reviewDate: '2026-03-03',
        outcome: 'correct', // Already reviewed
      }],
    });
    const pending = useDecisionStore.getState().getPendingReviews();
    expect(pending).toHaveLength(0);
  });
});
