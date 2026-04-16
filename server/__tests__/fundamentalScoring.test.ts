import { describe, it, expect } from 'vitest';
import { calculateFundamentalScores, calculateIntrinsicValueEstimate } from '../indicators/fundamentalScoring';

describe('fundamentalScoring', () => {
  describe('calculateFundamentalScores', () => {
    it('should identify Deep Value Opportunity with low metrics and high safety', () => {
      const result = calculateFundamentalScores({
        pe: 10,
        pb: 1.1,
        roe: 18,
        debtToEquity: 0.3,
        netProfitGrowth: 5,
        grossMargin: 35
      });
      expect(result.valueScore).toBeGreaterThan(70);
      expect(result.safetyScore).toBeGreaterThan(70);
      expect(result.verdict).toContain('Deep Value');
      expect(result.moatRating).toBe('Narrow');
    });

    it('should identify Quality Growth with high growth and high moat indicators', () => {
      const result = calculateFundamentalScores({
        pe: 35, // Premium price
        pb: 8,
        roe: 25,
        debtToEquity: 0.1,
        netProfitGrowth: 30,
        grossMargin: 55
      });
      expect(result.growthScore).toBeGreaterThan(70);
      expect(result.safetyScore).toBeGreaterThan(70);
      expect(result.moatRating).toBe('Wide');
      expect(result.verdict).toContain('Quality Growth');
    });

    it('should warn for High Risk/Distressed fundamentals', () => {
      const result = calculateFundamentalScores({
        pe: -5,
        pb: 12,
        roe: -10,
        debtToEquity: 2.5, // High debt
        netProfitGrowth: -20,
        grossMargin: 5
      });
      expect(result.safetyScore).toBeLessThan(40);
      expect(result.moatRating).toBe('None');
      expect(result.verdict).toContain('High Risk');
    });
  });

  describe('calculateIntrinsicValueEstimate', () => {
    it('should return 0 for zero/negative ROE', () => {
      expect(calculateIntrinsicValueEstimate(100, 0, 10)).toBe(0);
      expect(calculateIntrinsicValueEstimate(100, -5, 10)).toBe(0);
    });

    it('should estimate value higher than price for high ROE/Growth combinations', () => {
      const price = 100;
      const estimate = calculateIntrinsicValueEstimate(price, 20, 15);
      expect(estimate).toBeGreaterThan(price);
    });

    it('should cap the multiplier between 0.5 and 2.0', () => {
      const lowEstimate = calculateIntrinsicValueEstimate(100, 1, 1);
      const highEstimate = calculateIntrinsicValueEstimate(100, 100, 100);
      
      expect(lowEstimate).toBeCloseTo(100 * 0.5);
      expect(highEstimate).toBeCloseTo(100 * 2.0);
    });
  });
});
