import type { AgentRole, AnalystWeight, ExpertTrackRecord } from '../types';

export interface ExpertHistoryEntry {
  role: AgentRole;
  directionCorrect: boolean;
  targetHit: boolean;
  overshoot: number;    // positive = overly bullish
  sector: string;
}

export function buildExpertTrackRecords(
  history: ExpertHistoryEntry[],
): Map<AgentRole, ExpertTrackRecord> {
  const grouped = new Map<AgentRole, ExpertHistoryEntry[]>();
  for (const entry of history) {
    const list = grouped.get(entry.role) ?? [];
    list.push(entry);
    grouped.set(entry.role, list);
  }

  const records = new Map<AgentRole, ExpertTrackRecord>();
  for (const [role, entries] of grouped) {
    const totalCalls = entries.length;
    const directionCorrectCount = entries.filter(e => e.directionCorrect).length;
    const targetHitCount = entries.filter(e => e.targetHit).length;
    const avgOvershoot = entries.reduce((s, e) => s + e.overshoot, 0) / totalCalls;

    // Sector analysis
    const sectorCounts = new Map<string, { correct: number; total: number }>();
    for (const e of entries) {
      const c = sectorCounts.get(e.sector) ?? { correct: 0, total: 0 };
      c.total++;
      if (e.directionCorrect) c.correct++;
      sectorCounts.set(e.sector, c);
    }
    let bestSector = '';
    let worstSector = '';
    let bestRate = -1;
    let worstRate = 2;
    for (const [sector, counts] of sectorCounts) {
      const rate = counts.correct / counts.total;
      if (rate > bestRate) { bestRate = rate; bestSector = sector; }
      if (rate < worstRate) { worstRate = rate; worstSector = sector; }
    }

    // Last 5 accuracy
    const last5 = entries.slice(-5).map(e => e.directionCorrect ? 1 : 0);

    // Recent trend
    const recentTrend = determineRecentTrend(last5);

    records.set(role, {
      role,
      totalCalls,
      directionAccuracy: (directionCorrectCount / totalCalls) * 100,
      targetHitRate: (targetHitCount / totalCalls) * 100,
      avgOvershoot,
      bestSector,
      worstSector,
      recentTrend,
      last5Accuracy: last5,
    });
  }

  return records;
}

function determineRecentTrend(last5: number[]): 'improving' | 'declining' | 'stable' {
  if (last5.length < 3) return 'stable';

  const firstHalf = last5.slice(0, Math.floor(last5.length / 2));
  const secondHalf = last5.slice(Math.floor(last5.length / 2));

  const firstAvg = firstHalf.reduce((s, v) => s + v, 0) / firstHalf.length;
  const secondAvg = secondHalf.reduce((s, v) => s + v, 0) / secondHalf.length;

  if (secondAvg - firstAvg > 0.2) return 'improving';
  if (firstAvg - secondAvg > 0.2) return 'declining';
  return 'stable';
}

export function calculateDynamicWeights(
  records: Map<AgentRole, ExpertTrackRecord>,
  baseWeights: AnalystWeight[],
): AnalystWeight[] {
  if (records.size === 0) return baseWeights;

  return baseWeights.map((w) => {
    const record = records.get(w.role);
    if (!record) return w;

    let weight = w.weight;

    // 3 consecutive direction errors → ×0.8
    const last3 = record.last5Accuracy.slice(-3);
    if (last3.length >= 3 && last3.every(v => v === 0)) {
      weight *= 0.8;
    }
    // 3 consecutive direction wins → ×1.1 (capped at 0.2)
    else if (last3.length >= 3 && last3.every(v => v === 1)) {
      weight = Math.min(weight * 1.1, 0.2);
    }

    // targetHitRate < 30% → ×0.7
    if (record.totalCalls >= 5 && record.targetHitRate < 30) {
      weight *= 0.7;
    }

    return { ...w, weight };
  });
}
