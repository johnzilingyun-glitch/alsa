import type {
  StockAnalysis,
  AgentDiscussion,
  ReportPreference,
  TradingPlan,
  Scenario,
  QuantifiedRisk,
  AgentMessage,
} from '../types';

const DEFAULT_PREFERENCE: ReportPreference = {
  detailLevel: 'analyst',
  focusAreas: ['fundamental', 'technical', 'risk', 'scenario'],
  includeBacktest: true,
  includeExpertDebate: true,
  maxLength: 'standard',
};

export function generateReport(
  analysis: StockAnalysis,
  discussion: AgentDiscussion | undefined,
  preference: ReportPreference = DEFAULT_PREFERENCE
): string {
  const sections: string[] = [];

  sections.push(renderHeader(analysis));
  sections.push(renderDecisionSummary(analysis));
  if (analysis.tradingPlan) {
    sections.push(renderTradingPlan(analysis.tradingPlan));
  }

  if (preference.detailLevel === 'trader') {
    sections.push(renderPriceDistances(analysis));
    if (preference.focusAreas.includes('scenario') && analysis.scenarios?.length) {
      sections.push(renderScenariosCompact(analysis.scenarios));
    }
    return joinSections(sections, preference.maxLength);
  }

  // executive + analyst
  if (preference.focusAreas.includes('scenario') && analysis.scenarios?.length) {
    sections.push(renderScenarios(analysis.scenarios));
  }
  if (preference.focusAreas.includes('risk') && analysis.quantifiedRisks?.length) {
    sections.push(renderRiskMatrix(analysis.quantifiedRisks));
  }

  if (preference.detailLevel === 'executive') {
    return joinSections(sections, preference.maxLength);
  }

  // analyst only
  if (preference.focusAreas.includes('fundamental')) {
    sections.push(renderFundamentals(analysis));
  }
  if (preference.focusAreas.includes('technical')) {
    sections.push(renderTechnicalAnalysis(analysis));
  }
  if (preference.focusAreas.includes('sentiment') && analysis.capitalFlow) {
    sections.push(renderCapitalFlow(analysis));
  }
  if (preference.includeBacktest && analysis.backtestResult) {
    sections.push(renderBacktest(analysis));
  }
  if (preference.includeExpertDebate && discussion?.messages?.length) {
    sections.push(renderExpertDebate(discussion.messages));
  }

  return joinSections(sections, preference.maxLength);
}

function joinSections(sections: string[], maxLength: 'brief' | 'standard' | 'full'): string {
  const joined = sections.join('\n\n---\n\n');
  const limits: Record<string, number> = { brief: 3000, standard: 12000, full: 28000 };
  const limit = limits[maxLength];
  return joined.length > limit
    ? joined.slice(0, limit) + '\n\n... (已截断)'
    : joined;
}

function renderHeader(analysis: StockAnalysis): string {
  const { stockInfo } = analysis;
  return `## ${stockInfo.name} (${stockInfo.symbol})\n\n` +
    `价格: ${stockInfo.currency} ${stockInfo.price} | ` +
    `涨跌: ${stockInfo.changePercent >= 0 ? '+' : ''}${stockInfo.changePercent.toFixed(2)}% | ` +
    `市场: ${stockInfo.market}`;
}

function renderDecisionSummary(analysis: StockAnalysis): string {
  return `### 决策摘要\n\n` +
    `**评级**: ${analysis.recommendation} | **评分**: ${analysis.score}/100 | **情绪**: ${analysis.sentiment}\n\n` +
    `${analysis.summary}`;
}

function renderTradingPlan(plan: TradingPlan): string {
  const lines = [
    `### 交易计划`,
    `| 项目 | 值 |`,
    `|------|------|`,
    `| 入场价 | ${plan.entryPrice} |`,
    `| 目标价 | ${plan.targetPrice} |`,
    `| 止损价 | ${plan.stopLoss} |`,
    `| 策略 | ${plan.strategy} |`,
  ];
  if (plan.riskRewardRatio != null) {
    lines.push(`| 风险回报比 | ${plan.riskRewardRatio.toFixed(2)} |`);
  }
  if (plan.strategyRisks) {
    lines.push(`| 策略风险 | ${plan.strategyRisks} |`);
  }
  return lines.join('\n');
}

function renderPriceDistances(analysis: StockAnalysis): string {
  const price = analysis.stockInfo.price;
  const plan = analysis.tradingPlan;
  if (!plan) return '### 价格距离\n\n无交易计划';

  const entry = parseFloat(plan.entryPrice);
  const target = parseFloat(plan.targetPrice);
  const stop = parseFloat(plan.stopLoss);

  const toEntry = ((entry - price) / price * 100).toFixed(2);
  const toTarget = ((target - price) / price * 100).toFixed(2);
  const toStop = ((stop - price) / price * 100).toFixed(2);

  return `### 价格距离\n\n` +
    `| 方向 | 价格 | 距离 |\n` +
    `|------|------|------|\n` +
    `| 入场 | ${plan.entryPrice} | ${toEntry}% |\n` +
    `| 目标 | ${plan.targetPrice} | ${toTarget}% |\n` +
    `| 止损 | ${plan.stopLoss} | ${toStop}% |`;
}

function renderScenarios(scenarios: Scenario[]): string {
  const rows = scenarios.map(s =>
    `| ${s.case} | ${s.probability}% | ${s.targetPrice} | ${s.expectedReturn} | ${s.keyInputs} |`
  );
  return `### 情景分析\n\n` +
    `| 情景 | 概率 | 目标价 | 预期回报 | 关键假设 |\n` +
    `|------|------|--------|----------|----------|\n` +
    rows.join('\n');
}

function renderScenariosCompact(scenarios: Scenario[]): string {
  const rows = scenarios.map(s =>
    `- **${s.case}** (${s.probability}%): ${s.targetPrice} → ${s.expectedReturn}`
  );
  return `### 情景\n\n` + rows.join('\n');
}

function renderRiskMatrix(risks: QuantifiedRisk[]): string {
  const rows = risks.map(r =>
    `| ${r.name} | ${r.probability}% | ${r.impactPercent}% | ${r.expectedLoss.toFixed(2)} | ${r.mitigation} |`
  );
  return `### 风险矩阵\n\n` +
    `| 风险 | 概率 | 影响 | 期望损失 | 对冲 |\n` +
    `|------|------|------|----------|------|\n` +
    rows.join('\n');
}

function renderFundamentals(analysis: StockAnalysis): string {
  return `### 基本面分析\n\n${analysis.fundamentalAnalysis}`;
}

function renderTechnicalAnalysis(analysis: StockAnalysis): string {
  return `### 技术分析\n\n${analysis.technicalAnalysis}`;
}

function renderCapitalFlow(analysis: StockAnalysis): string {
  const cf = analysis.capitalFlow;
  if (!cf) return '';
  return `### 资金流向\n\n` +
    `- 北向资金: ${cf.northboundFlow}\n` +
    `- 机构持仓: ${cf.institutionalHoldings}\n` +
    (cf.ahPremium ? `- AH溢价: ${cf.ahPremium}\n` : '') +
    `- 市场情绪: ${cf.marketSentiment}`;
}

function renderBacktest(analysis: StockAnalysis): string {
  const bt = analysis.backtestResult;
  if (!bt) return '';
  return `### 回测结果\n\n` +
    `- 前次日期: ${bt.previousDate}\n` +
    `- 前次建议: ${bt.previousRecommendation}\n` +
    `- 实际回报: ${bt.actualReturn}\n` +
    `- 经验总结: ${bt.learningPoint}`;
}

function renderExpertDebate(messages: AgentMessage[]): string {
  const lines = messages.slice(-5).map(m =>
    `**${m.role}** (${m.timestamp}):\n> ${m.content.slice(0, 300)}${m.content.length > 300 ? '...' : ''}`
  );
  return `### 专家讨论（最近 ${Math.min(messages.length, 5)} 条）\n\n` + lines.join('\n\n');
}
