import { describe, it, expect } from 'vitest';
import { calculateVolatility, calculateVolatilityAdjustedLimit } from '../indicators/riskMetrics';

describe('riskMetrics', () => {
  describe('calculateVolatility', () => {
    it('should return 0 for insufficient data', () => {
      expect(calculateVolatility([100, 101], 20)).toBe(0);
    });

    it('should calculate positive annualized volatility for a trending series', () => {
      // Create a 21-day upward series
      const prices = Array.from({ length: 25 }, (_, i) => 100 + i * 2);
      const vol = calculateVolatility(prices, 20);
      expect(vol).toBeGreaterThan(0);
      expect(vol).toBeLessThan(1.0); // Should be reasonable
    });

    it('should calculate higher volatility for a swinging series', () => {
      const steadyPrices = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100, 101];
      const erraticPrices = [100, 150, 50, 200, 10, 100, 150, 50, 200, 10, 100, 150, 50, 200, 10, 100, 150, 50, 200, 10, 100, 150];
      
      const steadyVol = calculateVolatility(steadyPrices, 20);
      const erraticVol = calculateVolatility(erraticPrices, 20);
      
      expect(erraticVol).toBeGreaterThan(steadyVol);
    });
  });

  describe('calculateVolatilityAdjustedLimit', () => {
    it('should recommend high limit for low volatility', () => {
      const result = calculateVolatilityAdjustedLimit(0.10); // 10%
      expect(result.limit).toBe(0.25);
      expect(result.regime).toBe('Low Volatility');
    });

    it('should recommend low limit for extreme volatility', () => {
      const result = calculateVolatilityAdjustedLimit(0.60); // 60%
      expect(result.limit).toBe(0.10);
      expect(result.regime).toBe('Extreme Volatility');
    });

    it('should interpolate limits for moderate and high volatility', () => {
      const moderate = calculateVolatilityAdjustedLimit(0.20);
      const high = calculateVolatilityAdjustedLimit(0.40);
      
      expect(moderate.limit).toBeLessThan(0.25);
      expect(moderate.limit).toBeGreaterThan(0.20);
      
      expect(high.limit).toBeLessThan(0.20);
      expect(high.limit).toBeGreaterThan(0.10);
    });
  });
});
