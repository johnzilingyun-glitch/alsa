import { describe, it, expect } from 'vitest';
import { getExpertPrompt, getExpertResponseSchema } from '../expertPrompts';
import type { StockAnalysis, AgentMessage, AgentRole } from '../../../types';

const mockAnalysis: StockAnalysis = {
  stockInfo: {
    symbol: '600519',
    name: '贵州茅台',
    price: 1800,
    change: 20,
    changePercent: 1.1,
    market: 'A-Share',
    currency: 'CNY',
    lastUpdated: '2026-03-27T10:00:00Z',
    previousClose: 1780,
  },
  news: [],
  summary: 'Test summary',
  technicalAnalysis: 'Test tech analysis',
  fundamentalAnalysis: 'Test fundamental analysis',
  sentiment: 'Bullish',
  score: 75,
  recommendation: 'Buy',
  keyRisks: ['Risk1'],
  keyOpportunities: ['Opp1'],
};

const previousRounds: AgentMessage[] = [
  {
    role: 'Deep Research Specialist',
    content: 'Deep research findings on 600519.',
    timestamp: '2026-03-27T10:00:00Z',
  },
];

describe('expertPrompts', () => {
  const roles: AgentRole[] = [
    'Deep Research Specialist',
    'Technical Analyst',
    'Fundamental Analyst',
    'Sentiment Analyst',
    'Risk Manager',
    'Contrarian Strategist',
    'Professional Reviewer',
    'Chief Strategist',
  ];

  describe('getExpertPrompt', () => {
    it.each(roles)('generates prompt for %s', (role) => {
      const prompt = getExpertPrompt(role, mockAnalysis, [], []);
      expect(prompt).toContain(mockAnalysis.stockInfo.symbol);
      expect(prompt.length).toBeGreaterThan(50);
    });

    it('includes previous round context when available', () => {
      const prompt = getExpertPrompt('Technical Analyst', mockAnalysis, previousRounds, []);
      expect(prompt).toContain('Deep Research Specialist');
    });

    it('includes commodities data when provided', () => {
      const commodities = [{ name: '伦敦金', price: 2000, trend: 'up' }];
      const prompt = getExpertPrompt('Deep Research Specialist', mockAnalysis, [], commodities);
      expect(prompt).toContain('伦敦金');
    });

    it('includes backtest context when provided', () => {
      const backtest = {
        previousDate: '2026-03-20',
        previousPrice: 1750,
        currentPrice: 1800,
        returnSincePrev: '+2.86%',
        previousRecommendation: 'Buy',
        previousTarget: '1900',
        previousStopLoss: '1650',
        status: 'In Progress' as const,
        accuracy: 70,
        learningPoint: '趋势符合预期',
      };
      const prompt = getExpertPrompt('Chief Strategist', mockAnalysis, previousRounds, [], backtest);
      expect(prompt).toContain('1750');
    });

    it('returns different prompts for different roles', () => {
      const p1 = getExpertPrompt('Technical Analyst', mockAnalysis, [], []);
      const p2 = getExpertPrompt('Risk Manager', mockAnalysis, [], []);
      expect(p1).not.toBe(p2);
    });
  });

  describe('getExpertResponseSchema', () => {
    it.each(roles)('returns schema for %s', (role) => {
      const schema = getExpertResponseSchema(role);
      expect(schema).toBeDefined();
      expect(schema.type).toBe('OBJECT');
      expect(schema.properties).toBeDefined();
    });

    it('Deep Research Specialist schema includes coreVariables', () => {
      const schema = getExpertResponseSchema('Deep Research Specialist');
      expect(schema.properties).toHaveProperty('coreVariables');
    });

    it('Chief Strategist schema includes tradingPlan', () => {
      const schema = getExpertResponseSchema('Chief Strategist');
      expect(schema.properties).toHaveProperty('tradingPlan');
    });

    it('Risk Manager schema includes quantifiedRisks', () => {
      const schema = getExpertResponseSchema('Risk Manager');
      expect(schema.properties).toHaveProperty('quantifiedRisks');
    });
  });
});
