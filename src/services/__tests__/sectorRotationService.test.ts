import { describe, it, expect } from 'vitest';
import { calculateSectorMomentum, determineCyclePhase, buildSectorRotations } from '../sectorRotationService';
import type { SectorAnalysis } from '../../types';

describe('sectorRotationService', () => {
  describe('calculateSectorMomentum', () => {
    it('returns 0 for empty history', () => {
      expect(calculateSectorMomentum('Tech', [])).toBe(0);
    });

    it('calculates positive momentum when trend is bullish across history', () => {
      const history = [
        [{ name: 'Tech', trend: '上涨', conclusion: 'Strong' }],
        [{ name: 'Tech', trend: '上涨', conclusion: 'Strong' }],
        [{ name: 'Tech', trend: '上涨', conclusion: 'Strong' }],
      ];
      const result = calculateSectorMomentum('Tech', history);
      expect(result).toBeGreaterThan(0);
    });

    it('calculates negative momentum when trend is bearish', () => {
      const history = [
        [{ name: 'Tech', trend: '下跌', conclusion: 'Weak' }],
        [{ name: 'Tech', trend: '下跌', conclusion: 'Weak' }],
      ];
      const result = calculateSectorMomentum('Tech', history);
      expect(result).toBeLessThan(0);
    });

    it('returns 0 when sector not found in history', () => {
      const history = [
        [{ name: 'Finance', trend: '上涨', conclusion: 'Ok' }],
      ];
      expect(calculateSectorMomentum('Tech', history)).toBe(0);
    });
  });

  describe('determineCyclePhase', () => {
    it('detects recovery when most sectors show inflow with low confidence', () => {
      const rotations = [
        { sector: 'Tech', capitalFlowTrend: 'inflow' as const, flowMagnitude: 20, momentum30d: 5 },
        { sector: 'Consumer', capitalFlowTrend: 'inflow' as const, flowMagnitude: 15, momentum30d: 3 },
        { sector: 'Finance', capitalFlowTrend: 'neutral' as const, flowMagnitude: 0, momentum30d: 1 },
      ];
      const phase = determineCyclePhase(rotations);
      expect(['recovery', 'expansion']).toContain(phase.currentPhase);
      expect(phase.phaseConfidence).toBeGreaterThan(0);
      expect(phase.recommendedSectors.length).toBeGreaterThan(0);
    });

    it('detects overheating when all sectors show strong inflow', () => {
      const rotations = [
        { sector: 'Tech', capitalFlowTrend: 'inflow' as const, flowMagnitude: 80, momentum30d: 30 },
        { sector: 'Consumer', capitalFlowTrend: 'inflow' as const, flowMagnitude: 70, momentum30d: 25 },
        { sector: 'Energy', capitalFlowTrend: 'inflow' as const, flowMagnitude: 60, momentum30d: 20 },
      ];
      const phase = determineCyclePhase(rotations);
      expect(phase.currentPhase).toBe('overheating');
    });

    it('detects stagflation when most sectors show outflow', () => {
      const rotations = [
        { sector: 'Tech', capitalFlowTrend: 'outflow' as const, flowMagnitude: -50, momentum30d: -10 },
        { sector: 'Consumer', capitalFlowTrend: 'outflow' as const, flowMagnitude: -40, momentum30d: -8 },
        { sector: 'Finance', capitalFlowTrend: 'outflow' as const, flowMagnitude: -30, momentum30d: -5 },
      ];
      const phase = determineCyclePhase(rotations);
      expect(phase.currentPhase).toBe('stagflation');
    });

    it('returns logic explanation', () => {
      const rotations = [
        { sector: 'Tech', capitalFlowTrend: 'neutral' as const, flowMagnitude: 0, momentum30d: 0 },
      ];
      const phase = determineCyclePhase(rotations);
      expect(phase.logic).toBeTruthy();
    });
  });

  describe('buildSectorRotations', () => {
    it('builds rotation data from sector analyses', () => {
      const current: SectorAnalysis[] = [
        { name: '科技', trend: '上涨', conclusion: '强势' },
        { name: '消费', trend: '下跌', conclusion: '弱势' },
      ];
      const history: SectorAnalysis[][] = [
        [{ name: '科技', trend: '上涨', conclusion: '强势' }],
      ];

      const rotations = buildSectorRotations(current, history);
      expect(rotations).toHaveLength(2);
      expect(rotations[0].sector).toBe('科技');
      expect(rotations[0].capitalFlowTrend).toBe('inflow');
      expect(rotations[1].capitalFlowTrend).toBe('outflow');
    });

    it('returns empty array for empty input', () => {
      expect(buildSectorRotations([], [])).toEqual([]);
    });
  });
});
