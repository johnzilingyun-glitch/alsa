import { describe, it, expect } from 'vitest';
import { detectBiases } from '../biasDetector';
import type { DecisionEntry } from '../../types';

function makeEntry(overrides: Partial<DecisionEntry> = {}): DecisionEntry {
  return {
    id: 'test-1',
    symbol: 'AAPL',
    name: 'Apple',
    market: 'US-Share',
    analysisId: 'a1',
    action: 'buy',
    reasoning: 'Test',
    priceAtDecision: 100,
    confidence: 80,
    createdAt: '2026-01-01',
    reviewDate: '2026-02-01',
    ...overrides,
  };
}

describe('biasDetector', () => {
  it('returns empty array when no entries', () => {
    expect(detectBiases([])).toEqual([]);
  });

  it('returns empty when fewer than 5 entries (sample-size guard)', () => {
    const entries = Array.from({ length: 4 }, (_, i) =>
      makeEntry({ id: `e-${i}`, confidence: 90, outcome: 'incorrect' }),
    );
    const biases = detectBiases(entries);
    expect(biases).toEqual([]);
  });

  it('detects overconfidence bias when avg confidence far exceeds correct rate', () => {
    // 6 entries: all high confidence (90), only 2 correct → correctRate=0.333, avgConf=0.9
    // gap = 0.9 - 0.333 = 0.567 > 0.2
    const entries = Array.from({ length: 6 }, (_, i) =>
      makeEntry({
        id: `e-${i}`,
        confidence: 90,
        outcome: i < 2 ? 'correct' : 'incorrect',
      }),
    );
    const biases = detectBiases(entries);
    const overconfidence = biases.find(b => b.name === 'overconfidence');
    expect(overconfidence).toBeDefined();
    expect(overconfidence!.severity).toBe('warning');
  });

  it('does not detect overconfidence when correct rate is high', () => {
    // 6 entries: all high confidence (80), 5 correct → correctRate=0.833, avgConf=0.8
    // gap = 0.8 - 0.833 = -0.033 < 0.2
    const entries = Array.from({ length: 6 }, (_, i) =>
      makeEntry({
        id: `e-${i}`,
        confidence: 80,
        outcome: i < 5 ? 'correct' : 'incorrect',
      }),
    );
    const biases = detectBiases(entries);
    const overconfidence = biases.find(b => b.name === 'overconfidence');
    expect(overconfidence).toBeUndefined();
  });

  it('detects loss aversion when holding losers too long', () => {
    // 3 holds with outcome=incorrect and return < -10%
    const entries = Array.from({ length: 5 }, (_, i) =>
      makeEntry({
        id: `e-${i}`,
        action: i < 3 ? 'hold' : 'buy',
        outcome: i < 3 ? 'incorrect' : 'correct',
        actualReturn: i < 3 ? -15 : 10,
        confidence: 50,
      }),
    );
    const biases = detectBiases(entries);
    const lossAversion = biases.find(b => b.name === 'loss_aversion');
    expect(lossAversion).toBeDefined();
    expect(lossAversion!.severity).toBe('critical');
  });

  it('does not detect loss aversion with fewer than 3 bad holds', () => {
    const entries = Array.from({ length: 5 }, (_, i) =>
      makeEntry({
        id: `e-${i}`,
        action: i < 2 ? 'hold' : 'buy',
        outcome: i < 2 ? 'incorrect' : 'correct',
        actualReturn: i < 2 ? -15 : 10,
        confidence: 50,
      }),
    );
    const biases = detectBiases(entries);
    const lossAversion = biases.find(b => b.name === 'loss_aversion');
    expect(lossAversion).toBeUndefined();
  });

  it('detects recency bias when buy incorrect rate exceeds 60%', () => {
    // 5 buy entries, 4 incorrect → 80% incorrect > 60%
    const entries = Array.from({ length: 5 }, (_, i) =>
      makeEntry({
        id: `e-${i}`,
        action: 'buy',
        outcome: i < 1 ? 'correct' : 'incorrect',
        confidence: 50,
      }),
    );
    const biases = detectBiases(entries);
    const recency = biases.find(b => b.name === 'recency_bias');
    expect(recency).toBeDefined();
    expect(recency!.severity).toBe('warning');
  });

  it('can detect multiple biases simultaneously', () => {
    // High confidence + mostly incorrect buys + some bad holds
    const entries: DecisionEntry[] = [
      ...Array.from({ length: 5 }, (_, i) =>
        makeEntry({
          id: `buy-${i}`,
          action: 'buy',
          confidence: 95,
          outcome: 'incorrect',
        }),
      ),
      ...Array.from({ length: 3 }, (_, i) =>
        makeEntry({
          id: `hold-${i}`,
          action: 'hold',
          confidence: 90,
          outcome: 'incorrect',
          actualReturn: -20,
        }),
      ),
    ];
    const biases = detectBiases(entries);
    expect(biases.length).toBeGreaterThanOrEqual(2);
    const names = biases.map(b => b.name);
    expect(names).toContain('overconfidence');
    expect(names).toContain('recency_bias');
    expect(names).toContain('loss_aversion');
  });
});
