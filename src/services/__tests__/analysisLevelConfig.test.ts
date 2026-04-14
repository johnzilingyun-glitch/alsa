import { describe, it, expect } from 'vitest';
import { getAnalysisLevelConfig, type AnalysisLevelConfig } from '../analysisLevelConfig';

describe('analysisLevelConfig', () => {
  describe('quick level', () => {
    it('returns quick scan config', () => {
      const config = getAnalysisLevelConfig('quick');
      expect(config.level).toBe('quick');
      expect(config.includeDiscussion).toBe(false);
      expect(config.includeBacktest).toBe(false);
      expect(config.includeCommodities).toBe(false);
      expect(config.saveHistory).toBe(false);
      expect(config.estimatedTokens).toBe(500);
    });
  });

  describe('standard level', () => {
    it('returns standard analysis config', () => {
      const config = getAnalysisLevelConfig('standard');
      expect(config.level).toBe('standard');
      expect(config.includeDiscussion).toBe(false);
      expect(config.includeBacktest).toBe(false);
      expect(config.includeCommodities).toBe(true);
      expect(config.saveHistory).toBe(true);
      expect(config.historyLookback).toBe(1);
      expect(config.estimatedTokens).toBe(3000);
    });
  });

  describe('deep level', () => {
    it('returns deep research config', () => {
      const config = getAnalysisLevelConfig('deep');
      expect(config.level).toBe('deep');
      expect(config.includeDiscussion).toBe(true);
      expect(config.includeBacktest).toBe(true);
      expect(config.includeCommodities).toBe(true);
      expect(config.saveHistory).toBe(true);
      expect(config.historyLookback).toBe(3);
      expect(config.expertCount).toBe(8);
      expect(config.estimatedTokens).toBe(8000);
    });
  });

  describe('field outputs', () => {
    it('quick scan returns minimal fields', () => {
      const config = getAnalysisLevelConfig('quick');
      expect(config.outputFields).toContain('stockInfo');
      expect(config.outputFields).toContain('score');
      expect(config.outputFields).toContain('sentiment');
      expect(config.outputFields).toContain('recommendation');
      expect(config.outputFields).toContain('summary');
      expect(config.outputFields).not.toContain('fundamentals');
    });

    it('standard includes most fields', () => {
      const config = getAnalysisLevelConfig('standard');
      expect(config.outputFields).toContain('stockInfo');
      expect(config.outputFields).toContain('fundamentals');
      expect(config.outputFields).toContain('technicalAnalysis');
    });

    it('deep includes all fields', () => {
      const config = getAnalysisLevelConfig('deep');
      expect(config.outputFields).toContain('discussion');
      expect(config.outputFields).toContain('backtestResult');
    });
  });

  describe('estimated latency', () => {
    it('quick: ~3s', () => {
      expect(getAnalysisLevelConfig('quick').estimatedLatencyMs).toBe(3000);
    });

    it('standard: ~15s', () => {
      expect(getAnalysisLevelConfig('standard').estimatedLatencyMs).toBe(15000);
    });

    it('deep: ~45s', () => {
      expect(getAnalysisLevelConfig('deep').estimatedLatencyMs).toBe(45000);
    });
  });
});
