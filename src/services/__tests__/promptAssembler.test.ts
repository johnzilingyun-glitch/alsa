import { describe, it, expect } from 'vitest';
import { assembleExpertPrompt } from '../discussion/promptAssembler';
import { AgentRole, StockAnalysis } from '../../types';

describe('PromptAssembler', () => {
  const mockAnalysis: Partial<StockAnalysis> = {
    stockInfo: {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      price: 150.25,
      change: 1.25,
      changePercent: 0.85,
      market: 'US-Share',
      currency: 'USD',
      lastUpdated: '2026-04-18',
      previousClose: 149.00
    },
    recommendation: 'Buy',
    score: 85,
    sentiment: 'Bullish'
  };

  it('should assemble a prompt containing the role persona', async () => {
    const prompt = await assembleExpertPrompt('Technical Analyst', mockAnalysis as StockAnalysis, [], []);
    expect(prompt).toContain('Technical Analyst');
    expect(prompt).toContain('trends, support, resistance');
  });

  it('should inject mandatory temporal alignment protocols', async () => {
    const prompt = await assembleExpertPrompt('Technical Analyst', mockAnalysis as StockAnalysis, [], []);
    expect(prompt).toContain('TEMPORAL ALIGNMENT');
    expect(prompt).toContain('Current Date Time');
  });

  it('should inject data source priority protocols', async () => {
    const prompt = await assembleExpertPrompt('Technical Analyst', mockAnalysis as StockAnalysis, [], []);
    expect(prompt).toContain('DATA SOURCE PRIORITY');
  });

  it('should include few-shot examples when requested', async () => {
    const prompt = await assembleExpertPrompt('Technical Analyst', mockAnalysis as StockAnalysis, [], [], { includeExamples: true });
    expect(prompt).toContain('EXAMPLE OUTPUT');
    expect(prompt).toContain('JSON');
  });

  it('should respect language settings', async () => {
    const promptZh = await assembleExpertPrompt('Technical Analyst', mockAnalysis as StockAnalysis, [], [], { language: 'zh-CN' });
    expect(promptZh).toContain('技术分析师');
    expect(promptZh).toContain('简体中文');
  });
});
