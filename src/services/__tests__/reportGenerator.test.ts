import { describe, it, expect } from 'vitest';
import { generateReport } from '../reportGenerator';
import type { StockAnalysis, AgentDiscussion, ReportPreference } from '../../types';

function makeAnalysis(overrides: Partial<StockAnalysis> = {}): StockAnalysis {
  return {
    stockInfo: {
      symbol: '600519',
      name: '贵州茅台',
      price: 1680,
      change: 15,
      changePercent: 0.9,
      market: 'A-Share',
      currency: 'CNY',
      lastUpdated: '2026-03-27',
      previousClose: 1665,
    },
    news: [],
    summary: '茅台基本面稳健',
    technicalAnalysis: 'MACD金叉',
    fundamentalAnalysis: '净利润增长10%',
    sentiment: 'Bullish',
    score: 82,
    recommendation: 'Buy',
    keyRisks: ['消费降级'],
    keyOpportunities: ['出口增长'],
    tradingPlan: {
      entryPrice: '1650',
      targetPrice: '1800',
      stopLoss: '1550',
      strategy: '趋势跟踪',
      strategyRisks: '回调风险',
    },
    scenarios: [
      { case: 'Bull', probability: 40, keyInputs: '高端消费恢复', targetPrice: '2000', marginOfSafety: '15%', expectedReturn: '19%', logic: '' },
      { case: 'Base', probability: 45, keyInputs: '维持现状', targetPrice: '1750', marginOfSafety: '5%', expectedReturn: '4%', logic: '' },
      { case: 'Stress', probability: 15, keyInputs: '消费税调整', targetPrice: '1400', marginOfSafety: '-15%', expectedReturn: '-17%', logic: '' },
    ],
    quantifiedRisks: [
      { name: '消费升级', probability: 30, impactPercent: -10, expectedLoss: -3, mitigation: '多元化' },
    ],
    capitalFlow: {
      northboundFlow: '净买入5亿',
      institutionalHoldings: '增持',
      marketSentiment: '乐观',
    },
    backtestResult: {
      previousDate: '2026-02-27',
      previousRecommendation: 'Buy',
      actualReturn: '+5.2%',
      learningPoint: '趋势判断准确',
    },
    ...overrides,
  };
}

function makeDiscussion(): AgentDiscussion {
  return {
    messages: [
      { role: 'Fundamental Analyst', content: '基本面良好', timestamp: '10:00', type: 'discussion' },
      { role: 'Technical Analyst', content: '技术面偏多', timestamp: '10:05', type: 'discussion' },
    ],
    finalConclusion: '建议买入',
  };
}

describe('generateReport', () => {
  const analystPref: ReportPreference = {
    detailLevel: 'analyst',
    focusAreas: ['fundamental', 'technical', 'risk', 'scenario', 'sentiment'],
    includeBacktest: true,
    includeExpertDebate: true,
    maxLength: 'standard',
  };

  const executivePref: ReportPreference = {
    detailLevel: 'executive',
    focusAreas: ['scenario', 'risk'],
    includeBacktest: false,
    includeExpertDebate: false,
    maxLength: 'standard',
  };

  const traderPref: ReportPreference = {
    detailLevel: 'trader',
    focusAreas: ['scenario'],
    includeBacktest: false,
    includeExpertDebate: false,
    maxLength: 'standard',
  };

  it('should include header and summary for all levels', () => {
    const report = generateReport(makeAnalysis(), makeDiscussion(), analystPref);
    expect(report).toContain('贵州茅台');
    expect(report).toContain('600519');
    expect(report).toContain('决策摘要');
    expect(report).toContain('Buy');
  });

  it('analyst level includes all sections', () => {
    const report = generateReport(makeAnalysis(), makeDiscussion(), analystPref);
    expect(report).toContain('交易计划');
    expect(report).toContain('情景分析');
    expect(report).toContain('风险矩阵');
    expect(report).toContain('基本面分析');
    expect(report).toContain('技术分析');
    expect(report).toContain('资金流向');
    expect(report).toContain('回测结果');
    expect(report).toContain('专家讨论');
  });

  it('executive level excludes analyst-only sections', () => {
    const report = generateReport(makeAnalysis(), makeDiscussion(), executivePref);
    expect(report).toContain('决策摘要');
    expect(report).toContain('情景分析');
    expect(report).toContain('风险矩阵');
    expect(report).not.toContain('基本面分析');
    expect(report).not.toContain('技术分析');
    expect(report).not.toContain('专家讨论');
    expect(report).not.toContain('回测结果');
  });

  it('trader level includes price distances and compact scenarios', () => {
    const report = generateReport(makeAnalysis(), makeDiscussion(), traderPref);
    expect(report).toContain('价格距离');
    expect(report).toContain('情景');
    expect(report).not.toContain('风险矩阵');
    expect(report).not.toContain('基本面分析');
  });

  it('respects focusAreas filter', () => {
    const pref: ReportPreference = {
      detailLevel: 'analyst',
      focusAreas: ['fundamental'],
      includeBacktest: false,
      includeExpertDebate: false,
      maxLength: 'standard',
    };
    const report = generateReport(makeAnalysis(), undefined, pref);
    expect(report).toContain('基本面分析');
    expect(report).not.toContain('情景分析');
    expect(report).not.toContain('风险矩阵');
    expect(report).not.toContain('回测结果');
    expect(report).not.toContain('专家讨论');
  });

  it('truncates when exceeding brief limit', () => {
    const longAnalysis = makeAnalysis({
      fundamentalAnalysis: 'x'.repeat(4000),
    });
    const briefPref: ReportPreference = {
      detailLevel: 'analyst',
      focusAreas: ['fundamental', 'technical', 'risk', 'scenario'],
      includeBacktest: true,
      includeExpertDebate: true,
      maxLength: 'brief',
    };
    const report = generateReport(longAnalysis, makeDiscussion(), briefPref);
    expect(report).toContain('已截断');
    expect(report.length).toBeLessThanOrEqual(3020);
  });

  it('uses default preference when none provided', () => {
    const report = generateReport(makeAnalysis(), makeDiscussion());
    expect(report).toContain('决策摘要');
    expect(report).toContain('交易计划');
  });

  it('handles missing optional fields gracefully', () => {
    const minimal = makeAnalysis({
      tradingPlan: undefined,
      scenarios: undefined,
      quantifiedRisks: undefined,
      capitalFlow: undefined,
      backtestResult: undefined,
    });
    const report = generateReport(minimal, undefined, analystPref);
    expect(report).toContain('决策摘要');
    expect(report).not.toContain('交易计划');
    expect(report).not.toContain('情景分析');
  });

  it('renders price distances correctly for trader', () => {
    const report = generateReport(makeAnalysis(), undefined, traderPref);
    expect(report).toContain('入场');
    expect(report).toContain('目标');
    expect(report).toContain('止损');
    expect(report).toContain('%');
  });

  it('limits expert debate to 5 messages', () => {
    const longDiscussion: AgentDiscussion = {
      messages: Array.from({ length: 10 }, (_, i) => ({
        role: 'Technical Analyst' as const,
        content: `消息 ${i + 1}`,
        timestamp: `10:${String(i).padStart(2, '0')}`,
      })),
      finalConclusion: '结论',
    };
    const report = generateReport(makeAnalysis(), longDiscussion, analystPref);
    expect(report).toContain('最近 5 条');
  });
});
