import type { SectorAnalysis, SectorRotation, MarketCycle } from '../types';

const TREND_SCORES: Record<string, number> = {
  '上涨': 1, '强势': 1, 'bullish': 1, 'up': 1,
  '下跌': -1, '弱势': -1, 'bearish': -1, 'down': -1,
  '震荡': 0, '中性': 0, 'neutral': 0, 'flat': 0,
};

function parseTrendScore(trend: string): number {
  const lower = trend.toLowerCase();
  for (const [key, score] of Object.entries(TREND_SCORES)) {
    if (lower.includes(key)) return score;
  }
  return 0;
}

export function calculateSectorMomentum(
  sector: string,
  history: SectorAnalysis[][],
): number {
  if (history.length === 0) return 0;

  let totalScore = 0;
  let count = 0;

  for (const snapshot of history) {
    const match = snapshot.find(s => s.name === sector);
    if (match) {
      totalScore += parseTrendScore(match.trend);
      count++;
    }
  }

  if (count === 0) return 0;
  return Math.round((totalScore / count) * 100);
}

export function buildSectorRotations(
  current: SectorAnalysis[],
  history: SectorAnalysis[][],
): SectorRotation[] {
  return current.map((sector) => {
    const trendScore = parseTrendScore(sector.trend);
    const momentum = calculateSectorMomentum(sector.name, history);
    const flowTrend: SectorRotation['capitalFlowTrend'] =
      trendScore > 0 ? 'inflow' : trendScore < 0 ? 'outflow' : 'neutral';

    return {
      sector: sector.name,
      capitalFlowTrend: flowTrend,
      flowMagnitude: trendScore * 50,
      clockQuadrant: 'recovery' as const, // Will be determined by determineCyclePhase
      momentum30d: momentum,
      topStocks: [],
      updatedAt: new Date().toISOString(),
    };
  });
}

interface RotationSummary {
  sector: string;
  capitalFlowTrend: SectorRotation['capitalFlowTrend'];
  flowMagnitude: number;
  momentum30d: number;
}

export function determineCyclePhase(rotations: RotationSummary[]): MarketCycle {
  if (rotations.length === 0) {
    return {
      currentPhase: 'recovery',
      phaseConfidence: 0,
      recommendedSectors: [],
      avoidSectors: [],
      logic: '数据不足，无法判断周期',
    };
  }

  const inflowCount = rotations.filter(r => r.capitalFlowTrend === 'inflow').length;
  const outflowCount = rotations.filter(r => r.capitalFlowTrend === 'outflow').length;
  const avgMagnitude = rotations.reduce((s, r) => s + r.flowMagnitude, 0) / rotations.length;
  const avgMomentum = rotations.reduce((s, r) => s + r.momentum30d, 0) / rotations.length;
  const total = rotations.length;

  let phase: MarketCycle['currentPhase'];
  let confidence: number;
  let logic: string;

  if (outflowCount > total * 0.6) {
    phase = 'stagflation';
    confidence = Math.min(90, outflowCount / total * 100);
    logic = `${outflowCount}/${total} 板块资金流出，平均动量 ${avgMomentum.toFixed(0)}%，市场整体收缩`;
  } else if (avgMagnitude > 50 && avgMomentum > 15) {
    phase = 'overheating';
    confidence = Math.min(85, avgMagnitude);
    logic = `平均资金流入强度 ${avgMagnitude.toFixed(0)}，动量 ${avgMomentum.toFixed(0)}%，市场过热信号`;
  } else if (inflowCount > total * 0.5 && avgMomentum > 5) {
    phase = 'expansion';
    confidence = Math.min(75, inflowCount / total * 100);
    logic = `${inflowCount}/${total} 板块资金流入，动量正向，市场处于扩张期`;
  } else {
    phase = 'recovery';
    confidence = 50;
    logic = `资金流向分化，动量温和，市场处于复苏/转折期`;
  }

  const sorted = [...rotations].sort((a, b) => b.flowMagnitude - a.flowMagnitude);
  const recommended = sorted.filter(r => r.capitalFlowTrend === 'inflow').slice(0, 3).map(r => r.sector);
  const avoid = sorted.filter(r => r.capitalFlowTrend === 'outflow').slice(0, 2).map(r => r.sector);

  return {
    currentPhase: phase,
    phaseConfidence: Math.round(confidence),
    recommendedSectors: recommended,
    avoidSectors: avoid,
    logic,
  };
}
