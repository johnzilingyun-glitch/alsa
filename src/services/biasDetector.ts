import type { DecisionEntry } from '../types';

export interface BiasPattern {
  name: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
}

const MIN_SAMPLE_SIZE = 5;

function detectOverconfidence(entries: DecisionEntry[]): BiasPattern | null {
  const withOutcome = entries.filter(e => e.outcome);
  if (withOutcome.length < MIN_SAMPLE_SIZE) return null;

  const avgConfidence = withOutcome.reduce((sum, e) => sum + e.confidence, 0) / withOutcome.length / 100;
  const correctRate = withOutcome.filter(e => e.outcome === 'correct').length / withOutcome.length;

  if (avgConfidence - correctRate > 0.2) {
    return {
      name: 'overconfidence',
      message: `平均置信度 (${(avgConfidence * 100).toFixed(0)}%) 远高于正确率 (${(correctRate * 100).toFixed(0)}%)，建议降低仓位或增加验证`,
      severity: 'warning',
    };
  }
  return null;
}

function detectLossAversion(entries: DecisionEntry[]): BiasPattern | null {
  const badHolds = entries.filter(
    e => e.action === 'hold' && e.outcome === 'incorrect' && e.actualReturn !== undefined && e.actualReturn < -10,
  );

  if (badHolds.length >= 3) {
    return {
      name: 'loss_aversion',
      message: `检测到 ${badHolds.length} 次持有亏损超过10%的错误决策，可能存在损失厌恶倾向`,
      severity: 'critical',
    };
  }
  return null;
}

function detectRecencyBias(entries: DecisionEntry[]): BiasPattern | null {
  const buys = entries.filter(e => e.action === 'buy' && e.outcome);
  if (buys.length < MIN_SAMPLE_SIZE) return null;

  const incorrectRate = buys.filter(e => e.outcome === 'incorrect').length / buys.length;
  if (incorrectRate > 0.6) {
    return {
      name: 'recency_bias',
      message: `买入决策错误率 ${(incorrectRate * 100).toFixed(0)}% 超过 60%，可能受近期市场情绪影响过大`,
      severity: 'warning',
    };
  }
  return null;
}

export function detectBiases(entries: DecisionEntry[]): BiasPattern[] {
  if (entries.length < MIN_SAMPLE_SIZE) return [];

  const detectors = [detectOverconfidence, detectLossAversion, detectRecencyBias];
  const results: BiasPattern[] = [];

  for (const detector of detectors) {
    const bias = detector(entries);
    if (bias) results.push(bias);
  }

  return results;
}
