import { AgentRole, StockAnalysis, ExpertOutput } from '../../types';

export interface GuardrailFinding {
  rule: string;
  severity: 'info' | 'warning' | 'critical';
  finding: string;
}

/**
 * Audit Sentinel: Deterministic Guardrails
 * Checks AI expert output against deterministic financial data.
 */
export function auditExpertLogic(
  role: AgentRole, 
  output: ExpertOutput, 
  analysis: StockAnalysis
): GuardrailFinding[] {
  const findings: GuardrailFinding[] = [];
  const content = (output.message.content || '').toLowerCase();
  const info = analysis.stockInfo;
  const fundamentals = analysis.fundamentals;

  // Rule 1: Growth/ROE Mismatch logic
  // If ROE is very low but AI talks about "High Profitability" or "Hyper growth"
  if (info.fundamentalScores && info.fundamentalScores.growthScore < 30) {
    if (content.includes('爆速增长') || content.includes('hyper growth') || content.includes('爆发式')) {
      findings.push({
        rule: 'Growth Integrity',
        severity: 'warning',
        finding: 'AI asserts hyper-growth despite a low quantitative growth score (<30).'
      });
    }
  }

  // Rule 2: Valuation Outlier
  // If AI target price is extremely high compared to intrinsic value estimate
  if (output.structuredData?.tradingPlan?.targetPrice && info.intrinsicValueEstimate) {
    const aiTarget = parseFloat(output.structuredData.tradingPlan.targetPrice);
    if (aiTarget > info.intrinsicValueEstimate * 2) {
      findings.push({
        rule: 'Valuation Reality Check',
        severity: 'critical',
        finding: 'AI target price is >200% of the intrinsic value estimate without segmental justification.'
      });
    }
  }

  // Rule 3: Debt Neglect
  if (fundamentals?.debtToEquity && parseFloat(fundamentals.debtToEquity) > 200) {
    if (content.includes('财务稳健') || content.includes('strong balance sheet')) {
      findings.push({
        rule: 'Solvency Audit',
        severity: 'warning',
        finding: 'AI claims financial robustness while Debt-to-Equity is dangerously high (>200%).'
      });
    }
  }

  return findings;
}
