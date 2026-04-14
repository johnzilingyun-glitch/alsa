import { describe, it, expect } from 'vitest';
import { performBacktest } from '../services/backtestService';
import { calculateQualityScore, getQualityLabel } from '../services/dataQualityService';
import { calculateExpectedValue } from '../services/mathService';
import { StockAnalysis, Scenario, SensitivityMatrixRow } from '../types';

describe('Decision Engine: Backtest Service', () => {
  const currentAnalysis = {
    stockInfo: { price: 150, lastUpdated: new Date().toISOString() }
  } as StockAnalysis;

  it('should detect a Target Hit correctly', () => {
    const previousAnalysis = {
      stockInfo: { price: 100, lastUpdated: '2026-03-01T00:00:00Z' },
      recommendation: 'Buy',
      tradingPlan: { targetPrice: '145', stopLoss: '90' }
    } as any as StockAnalysis;

    const result = performBacktest(currentAnalysis, previousAnalysis);
    expect(result?.status).toBe('Target Hit');
    expect(result?.returnSincePrev).toBe('+50.00%');
    expect(result?.accuracy).toBeGreaterThan(90);
  });

  it('should detect a Stop Loss Hit correctly', () => {
    const previousAnalysis = {
      stockInfo: { price: 200, lastUpdated: '2026-03-01T00:00:00Z' },
      recommendation: 'Buy',
      tradingPlan: { targetPrice: '250', stopLoss: '180' }
    } as any as StockAnalysis;

    const result = performBacktest(currentAnalysis, previousAnalysis); // current is 150
    expect(result?.status).toBe('Stop Loss Hit');
    expect(result?.returnSincePrev).toBe('-25.00%');
    expect(result?.accuracy).toBeLessThan(20);
  });

  it('should calculate "In Progress" correctly', () => {
    const previousAnalysis = {
      stockInfo: { price: 140, lastUpdated: '2026-03-01T00:00:00Z' },
      recommendation: 'Buy',
      tradingPlan: { targetPrice: '200', stopLoss: '120' }
    } as any as StockAnalysis;

    const result = performBacktest(currentAnalysis, previousAnalysis); // current is 150
    expect(result?.status).toBe('In Progress');
    expect(result?.accuracy).toBe(70); // Direction matches (up)
  });
});

describe('Decision Engine: Data Quality Service', () => {
  it('should grant 100 score for perfect fresh official data', () => {
    const now = new Date();
    const info = {
      price: 100,
      previousClose: 99,
      dataSource: 'Official API',
      lastUpdated: now.toISOString()
    } as any;

    const quality = calculateQualityScore(info);
    expect(quality.score).toBe(100);
    expect(quality.isStale).toBe(false);
    expect(quality.sourcePriority).toBe('Official API');
  });

  it('should penalize search-based and stale data', () => {
    const tenHoursAgo = new Date(Date.now() - 10 * 60 * 60 * 1000);
    const info = {
      price: 100,
      previousClose: 99,
      dataSource: 'Google Search',
      lastUpdated: tenHoursAgo.toISOString()
    } as any;

    const quality = calculateQualityScore(info);
    // 100 - 10 (Search) - 15 (Stale) = 75
    expect(quality.score).toBe(75);
    expect(quality.isStale).toBe(true);
    expect(quality.sourcePriority).toBe('Search/Scraped');
  });

  it('should identify missing critical fields', () => {
    const info = {
      price: 0, // Invalid
      previousClose: 0, // Missing
      dataSource: 'Official API',
      lastUpdated: new Date().toISOString()
    } as any;

    const quality = calculateQualityScore(info);
    expect(quality.missingFields).toContain('Price');
    expect(quality.missingFields).toContain('Previous Close');
    expect(quality.score).toBeLessThan(70);
  });

  it('should provide correct quality labels', () => {
    expect(getQualityLabel(95).label).toBe('high');
    expect(getQualityLabel(75).label).toBe('reliable');
    expect(getQualityLabel(55).label).toBe('moderate');
    expect(getQualityLabel(30).label).toBe('low');
  });
});

describe('Decision Engine: Math Service (Phase 6)', () => {
  it('should calculate Expected Value (EV) correctly from scenarios', () => {
    const scenarios: Scenario[] = [
      { case: "Bull", probability: 30, targetPrice: "32", keyInputs: "", marginOfSafety: "", expectedReturn: "", logic: "" },
      { case: "Base", probability: 50, targetPrice: "27", keyInputs: "", marginOfSafety: "", expectedReturn: "", logic: "" },
      { case: "Stress", probability: 20, targetPrice: "21", keyInputs: "", marginOfSafety: "", expectedReturn: "", logic: "" },
    ];

    const result = calculateExpectedValue(scenarios);
    // Calculation: (0.3 * 32) + (0.5 * 27) + (0.2 * 21) = 9.6 + 13.5 + 4.2 = 27.3
    expect(result.expectedPrice).toBe(27.3);
    expect(result.confidenceInterval).toBe('[21, 32]');
    expect(result.calculationLogic).toContain('30% * 32');
  });

  it('should handle non-numeric target prices gracefully', () => {
    const scenarios: Scenario[] = [
      { case: "Bull", probability: 100, targetPrice: "$100.50 (Optimistic)", keyInputs: "", marginOfSafety: "", expectedReturn: "", logic: "" }
    ];
    const result = calculateExpectedValue(scenarios);
    expect(result.expectedPrice).toBe(100.5);
  });
});

describe('Decision Engine: Advanced Quant Structural Integrity', () => {
  it('should enforce Sensitivity Matrix structure', () => {
    const matrix: SensitivityMatrixRow[] = [
      { variable: "Silicon", change: "-10%", profitImpact: "-1.2B", timeLag: "Immediate" }
    ];
    
    expect(matrix[0]).toHaveProperty('variable');
    expect(matrix[0]).toHaveProperty('profitImpact');
    expect(matrix[0]).toHaveProperty('timeLag');
  });
});
