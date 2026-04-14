import { describe, it, expect } from 'vitest';
import { buildExpertTrackRecords, calculateDynamicWeights } from '../expertTracker';
import type { AgentRole, AnalystWeight } from '../../types';

// Helper to create mock expert history entries
function makeEntry(role: AgentRole, directionCorrect: boolean, targetHit: boolean, overshoot: number) {
  return { role, directionCorrect, targetHit, overshoot, sector: 'Tech' };
}

describe('expertTracker', () => {
  describe('buildExpertTrackRecords', () => {
    it('returns empty map for empty history', () => {
      const records = buildExpertTrackRecords([]);
      expect(records.size).toBe(0);
    });

    it('calculates direction accuracy correctly', () => {
      const history = [
        makeEntry('Technical Analyst', true, false, 0),
        makeEntry('Technical Analyst', true, false, 0),
        makeEntry('Technical Analyst', false, false, 0),
      ];
      const records = buildExpertTrackRecords(history);
      const record = records.get('Technical Analyst');
      expect(record).toBeDefined();
      expect(record!.totalCalls).toBe(3);
      expect(record!.directionAccuracy).toBeCloseTo(66.67, 0);
    });

    it('calculates target hit rate', () => {
      const history = [
        makeEntry('Risk Manager', true, true, 0),
        makeEntry('Risk Manager', true, false, 0),
        makeEntry('Risk Manager', false, false, 0),
        makeEntry('Risk Manager', true, true, 0),
      ];
      const records = buildExpertTrackRecords(history);
      expect(records.get('Risk Manager')!.targetHitRate).toBe(50);
    });

    it('calculates average overshoot', () => {
      const history = [
        makeEntry('Chief Strategist', true, false, 5),
        makeEntry('Chief Strategist', true, false, 10),
        makeEntry('Chief Strategist', true, false, -3),
      ];
      const records = buildExpertTrackRecords(history);
      expect(records.get('Chief Strategist')!.avgOvershoot).toBe(4);
    });

    it('determines recent trend as improving', () => {
      const history = [
        makeEntry('Technical Analyst', false, false, 0),
        makeEntry('Technical Analyst', false, false, 0),
        makeEntry('Technical Analyst', false, false, 0),
        makeEntry('Technical Analyst', true, false, 0),
        makeEntry('Technical Analyst', true, true, 0),
      ];
      const records = buildExpertTrackRecords(history);
      expect(records.get('Technical Analyst')!.recentTrend).toBe('improving');
    });

    it('determines recent trend as declining', () => {
      const history = [
        makeEntry('Technical Analyst', true, true, 0),
        makeEntry('Technical Analyst', true, true, 0),
        makeEntry('Technical Analyst', true, false, 0),
        makeEntry('Technical Analyst', false, false, 0),
        makeEntry('Technical Analyst', false, false, 0),
      ];
      const records = buildExpertTrackRecords(history);
      expect(records.get('Technical Analyst')!.recentTrend).toBe('declining');
    });

    it('tracks last5Accuracy', () => {
      const history = Array.from({ length: 7 }, (_, i) =>
        makeEntry('Risk Manager', i % 2 === 0, false, 0)
      );
      const records = buildExpertTrackRecords(history);
      expect(records.get('Risk Manager')!.last5Accuracy).toHaveLength(5);
    });
  });

  describe('calculateDynamicWeights', () => {
    const baseWeights: AnalystWeight[] = [
      { role: 'Technical Analyst', weight: 0.15, isExpert: true },
      { role: 'Risk Manager', weight: 0.15, isExpert: true },
      { role: 'Chief Strategist', weight: 0.15, isExpert: true },
    ];

    it('returns base weights when no track records', () => {
      const result = calculateDynamicWeights(new Map(), baseWeights);
      expect(result).toEqual(baseWeights);
    });

    it('reduces weight for 3 consecutive direction errors (×0.8)', () => {
      const records = buildExpertTrackRecords([
        makeEntry('Technical Analyst', false, false, 0),
        makeEntry('Technical Analyst', false, false, 0),
        makeEntry('Technical Analyst', false, false, 0),
      ]);
      const result = calculateDynamicWeights(records, baseWeights);
      const ta = result.find(w => w.role === 'Technical Analyst');
      expect(ta!.weight).toBeCloseTo(0.15 * 0.8, 4);
    });

    it('increases weight for 3 consecutive direction wins (×1.1, capped at 0.2)', () => {
      const records = buildExpertTrackRecords([
        makeEntry('Technical Analyst', true, true, 0),
        makeEntry('Technical Analyst', true, true, 0),
        makeEntry('Technical Analyst', true, true, 0),
      ]);
      const result = calculateDynamicWeights(records, baseWeights);
      const ta = result.find(w => w.role === 'Technical Analyst');
      expect(ta!.weight).toBeCloseTo(Math.min(0.15 * 1.1, 0.2), 4);
    });

    it('caps increased weight at 0.2', () => {
      const weights: AnalystWeight[] = [
        { role: 'Chief Strategist', weight: 0.19, isExpert: true },
      ];
      const records = buildExpertTrackRecords([
        makeEntry('Chief Strategist', true, true, 0),
        makeEntry('Chief Strategist', true, true, 0),
        makeEntry('Chief Strategist', true, true, 0),
      ]);
      const result = calculateDynamicWeights(records, weights);
      expect(result[0].weight).toBe(0.2);
    });

    it('reduces weight for targetHitRate < 30% (×0.7)', () => {
      // 10 calls, only 2 target hits = 20%
      const history = Array.from({ length: 10 }, (_, i) =>
        makeEntry('Risk Manager', true, i < 2, 0)
      );
      const records = buildExpertTrackRecords(history);
      const result = calculateDynamicWeights(records, baseWeights);
      const rm = result.find(w => w.role === 'Risk Manager');
      // Direction all correct → ×1.1 (capped 0.2), but targetHitRate < 30% → ×0.7
      expect(rm!.weight).toBeLessThan(0.15);
    });
  });
});
