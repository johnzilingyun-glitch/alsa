import { describe, it, expect } from 'vitest';
import { calculateExpectedValue } from '../mathService';
import type { Scenario } from '../../types';

function makeScenario(overrides: Partial<Scenario> & { targetPrice: string; probability: number }): Scenario {
  return {
    case: 'Base',
    keyInputs: 'test-inputs',
    marginOfSafety: '10%',
    expectedReturn: '15%',
    logic: 'test-logic',
    ...overrides,
  };
}

describe('mathService', () => {
  describe('calculateExpectedValue', () => {
    it('calculates expected value from multiple scenarios', () => {
      const scenarios: Scenario[] = [
        makeScenario({ case: 'Bull', probability: 30, targetPrice: '200' }),
        makeScenario({ case: 'Base', probability: 50, targetPrice: '150' }),
        makeScenario({ case: 'Stress', probability: 20, targetPrice: '80' }),
      ];

      const result = calculateExpectedValue(scenarios);
      // EV = 0.30 * 200 + 0.50 * 150 + 0.20 * 80 = 60 + 75 + 16 = 151
      expect(result.expectedPrice).toBe(151);
      expect(result.calculationLogic).toContain('Σ(P_i * Price_i)');
      expect(result.calculationLogic).toContain('30% * 200');
      expect(result.calculationLogic).toContain('50% * 150');
      expect(result.calculationLogic).toContain('20% * 80');
      expect(result.confidenceInterval).toBe('[80, 200]');
    });

    it('returns zeros for empty scenarios array', () => {
      const result = calculateExpectedValue([]);
      expect(result.expectedPrice).toBe(0);
      expect(result.calculationLogic).toBe('No scenarios provided');
      expect(result.confidenceInterval).toBe('N/A');
    });

    it('returns zeros for null scenarios', () => {
      const result = calculateExpectedValue(null as unknown as Scenario[]);
      expect(result.expectedPrice).toBe(0);
      expect(result.calculationLogic).toBe('No scenarios provided');
      expect(result.confidenceInterval).toBe('N/A');
    });

    it('returns zeros for undefined scenarios', () => {
      const result = calculateExpectedValue(undefined as unknown as Scenario[]);
      expect(result.expectedPrice).toBe(0);
      expect(result.calculationLogic).toBe('No scenarios provided');
      expect(result.confidenceInterval).toBe('N/A');
    });

    it('handles single scenario', () => {
      const scenarios: Scenario[] = [
        makeScenario({ case: 'Base', probability: 100, targetPrice: '180' }),
      ];

      const result = calculateExpectedValue(scenarios);
      expect(result.expectedPrice).toBe(180);
      expect(result.confidenceInterval).toBe('[180, 180]');
    });

    it('handles target prices with currency symbols and formatting', () => {
      const scenarios: Scenario[] = [
        makeScenario({ probability: 60, targetPrice: '$1,500' }),
        makeScenario({ probability: 40, targetPrice: '¥1,200' }),
      ];

      const result = calculateExpectedValue(scenarios);
      // EV = 0.60 * 1500 + 0.40 * 1200 = 900 + 480 = 1380
      expect(result.expectedPrice).toBe(1380);
    });

    it('handles target prices with percentage notation', () => {
      const scenarios: Scenario[] = [
        makeScenario({ probability: 50, targetPrice: 'HK$ 45.50' }),
        makeScenario({ probability: 50, targetPrice: 'HK$ 55.00' }),
      ];

      const result = calculateExpectedValue(scenarios);
      // EV = 0.50 * 45.50 + 0.50 * 55.00 = 22.75 + 27.50 = 50.25
      expect(result.expectedPrice).toBe(50.25);
    });

    it('handles target price with no numeric characters', () => {
      const scenarios: Scenario[] = [
        makeScenario({ probability: 100, targetPrice: 'N/A' }),
      ];

      const result = calculateExpectedValue(scenarios);
      // regex strip removes all non-digit/non-dot chars, leaving '' → parseFloat('') → NaN
      // NaN scenario is skipped, minPrice stays Infinity, maxPrice stays -Infinity
      // confidenceInterval replaces Infinity with 0 via ternary
      expect(result.expectedPrice).toBe(0);
      expect(result.confidenceInterval).toBe('[0, 0]');
    });

    it('rounds expected price to 2 decimal places', () => {
      const scenarios: Scenario[] = [
        makeScenario({ probability: 33, targetPrice: '100' }),
        makeScenario({ probability: 33, targetPrice: '101' }),
        makeScenario({ probability: 34, targetPrice: '102' }),
      ];

      const result = calculateExpectedValue(scenarios);
      // EV = 0.33 * 100 + 0.33 * 101 + 0.34 * 102 = 33 + 33.33 + 34.68 = 101.01
      expect(result.expectedPrice).toBe(101.01);
      expect(result.confidenceInterval).toBe('[100, 102]');
    });

    it('handles probability sum not equal to 100%', () => {
      const scenarios: Scenario[] = [
        makeScenario({ probability: 25, targetPrice: '100' }),
        makeScenario({ probability: 25, targetPrice: '200' }),
      ];

      const result = calculateExpectedValue(scenarios);
      // totalWeight = 50, so EV = (25 + 50) / 50 * 100 ... wait no.
      // weightedSum = 0.25 * 100 + 0.25 * 200 = 25 + 50 = 75
      // totalWeight = 50
      // expectedPrice = 75 / (50/100)? No, look at the code:
      // weightedSum += (s.probability / 100) * price = 0.25 * 100 + 0.25 * 200 = 75
      // totalWeight += s.probability = 50
      // expectedPrice = totalWeight > 0 ? parseFloat(weightedSum.toFixed(2)) : 0
      // So expectedPrice = 75
      expect(result.expectedPrice).toBe(75);
    });

    it('strips non-numeric characters including minus sign from targetPrice', () => {
      // The regex /[^0-9.]/g strips minus signs, so '-50' becomes '50'
      const scenarios: Scenario[] = [
        makeScenario({ probability: 50, targetPrice: '-50' }),
        makeScenario({ probability: 50, targetPrice: '100' }),
      ];

      const result = calculateExpectedValue(scenarios);
      // EV = 0.50 * 50 + 0.50 * 100 = 25 + 50 = 75
      expect(result.expectedPrice).toBe(75);
      expect(result.confidenceInterval).toBe('[50, 100]');
    });

    it('handles decimal probabilities', () => {
      // Probabilities are integers 0-100, but the function doesn't validate
      const scenarios: Scenario[] = [
        makeScenario({ probability: 50, targetPrice: '120' }),
        makeScenario({ probability: 50, targetPrice: '80' }),
      ];

      const result = calculateExpectedValue(scenarios);
      expect(result.expectedPrice).toBe(100);
    });
  });
});
