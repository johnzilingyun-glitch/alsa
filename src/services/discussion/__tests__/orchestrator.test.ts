import { describe, it, expect } from 'vitest';
import { buildTopology } from '../orchestrator';
import type { OrchestratorConfig } from '../../../types';

describe('Discussion Orchestrator', () => {
  describe('buildTopology - deep level', () => {
    const deepConfig: OrchestratorConfig = {
      level: 'deep',
      assetType: 'stock',
      maxConcurrency: 3,
    };

    it('generates 9 rounds for deep analysis (with parallel groups)', () => {
      const rounds = buildTopology(deepConfig);
      expect(rounds).toHaveLength(9);
    });

    it('starts with Deep Research Specialist in round 1', () => {
      const rounds = buildTopology(deepConfig);
      expect(rounds[0].round).toBe(1);
      expect(rounds[0].experts).toEqual(['Deep Research Specialist']);
      expect(rounds[0].parallel).toBe(false);
      expect(rounds[0].dependsOn).toEqual([]);
    });

    it('parallelizes Technical Analyst & Fundamental Analyst in round 2', () => {
      const rounds = buildTopology(deepConfig);
      expect(rounds[1].round).toBe(2);
      expect(rounds[1].experts).toEqual(['Technical Analyst', 'Fundamental Analyst']);
      expect(rounds[1].parallel).toBe(true);
      expect(rounds[1].dependsOn).toEqual([1]);
    });

    it('has Professional Reviewer in round 7', () => {
      const rounds = buildTopology(deepConfig);
      expect(rounds[6].round).toBe(7);
      expect(rounds[6].experts).toContain('Professional Reviewer');
    });

    it('ends with Chief Strategist in round 9', () => {
      const rounds = buildTopology(deepConfig);
      expect(rounds[8].round).toBe(9);
      expect(rounds[8].experts).toEqual(['Chief Strategist']);
    });

    it('parallelizes risk management triad in round 5', () => {
      const rounds = buildTopology(deepConfig);
      expect(rounds[4].round).toBe(5);
      expect(rounds[4].experts).toEqual(['Aggressive Risk Analyst', 'Conservative Risk Analyst', 'Neutral Risk Analyst']);
      expect(rounds[4].parallel).toBe(true);
    });

    it('parallelizes Bull & Bear revision in round 8', () => {
      const rounds = buildTopology(deepConfig);
      expect(rounds[7].round).toBe(8);
      expect(rounds[7].experts).toEqual(['Bull Researcher', 'Bear Researcher']);
      expect(rounds[7].parallel).toBe(true);
    });
  });

  describe('buildTopology - quick level', () => {
    const quickConfig: OrchestratorConfig = {
      level: 'quick',
      assetType: 'stock',
      maxConcurrency: 3,
    };

    it('generates 3 rounds for quick scan', () => {
      const rounds = buildTopology(quickConfig);
      expect(rounds).toHaveLength(3);
    });

    it('starts with Deep Research Specialist', () => {
      const rounds = buildTopology(quickConfig);
      expect(rounds[0].experts).toEqual(['Deep Research Specialist']);
    });

    it('has Risk Manager in round 2', () => {
      const rounds = buildTopology(quickConfig);
      expect(rounds[1].experts).toContain('Risk Manager');
    });

    it('ends with Chief Strategist', () => {
      const rounds = buildTopology(quickConfig);
      expect(rounds[2].experts).toEqual(['Chief Strategist']);
    });
  });

  describe('buildTopology - standard level', () => {
    it('generates 6 rounds for standard analysis (with parallel groups)', () => {
      const config: OrchestratorConfig = {
        level: 'standard',
        assetType: 'stock',
        maxConcurrency: 3,
      };
      const rounds = buildTopology(config);
      expect(rounds).toHaveLength(6);
    });

    it('parallelizes TA & FA in standard mode', () => {
      const config: OrchestratorConfig = {
        level: 'standard',
        assetType: 'stock',
        maxConcurrency: 3,
      };
      const rounds = buildTopology(config);
      expect(rounds[1].experts).toEqual(['Technical Analyst', 'Fundamental Analyst']);
      expect(rounds[1].parallel).toBe(true);
    });
  });

  describe('buildTopology - ETF skip rules', () => {
    it('skips Deep Research and Fundamental Analyst for ETF', () => {
      const config: OrchestratorConfig = {
        level: 'deep',
        assetType: 'etf',
        maxConcurrency: 3,
      };
      const rounds = buildTopology(config);
      const allExperts = rounds.flatMap(r => r.experts);
      expect(allExperts).not.toContain('Deep Research Specialist');
      expect(allExperts).not.toContain('Fundamental Analyst');
    });

    it('skips Deep Research and Fundamental Analyst for index', () => {
      const config: OrchestratorConfig = {
        level: 'deep',
        assetType: 'index',
        maxConcurrency: 3,
      };
      const rounds = buildTopology(config);
      const allExperts = rounds.flatMap(r => r.experts);
      expect(allExperts).not.toContain('Deep Research Specialist');
      expect(allExperts).not.toContain('Fundamental Analyst');
    });
  });

  describe('buildTopology - custom skipRoles', () => {
    it('removes specified roles from topology', () => {
      const config: OrchestratorConfig = {
        level: 'deep',
        assetType: 'stock',
        skipRoles: ['Sentiment Analyst'],
        maxConcurrency: 3,
      };
      const rounds = buildTopology(config);
      const allExperts = rounds.flatMap(r => r.experts);
      expect(allExperts).not.toContain('Sentiment Analyst');
    });

    it('removes empty rounds after skipping', () => {
      const config: OrchestratorConfig = {
        level: 'quick',
        assetType: 'stock',
        skipRoles: ['Risk Manager'],
        maxConcurrency: 3,
      };
      const rounds = buildTopology(config);
      // All rounds should have at least one expert
      rounds.forEach(r => {
        expect(r.experts.length).toBeGreaterThan(0);
      });
    });
  });
});
