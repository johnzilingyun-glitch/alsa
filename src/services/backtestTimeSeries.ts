import type { StockAnalysis, BacktestTimeSeries, BacktestEntry, SystematicBias } from '../types';

const BULLISH_RECS = new Set(['Buy', 'Overweight']);
const BEARISH_RECS = new Set(['Sell', 'Underweight']);

export function buildBacktestTimeSeries(
  symbol: string,
  current: StockAnalysis,
  history: StockAnalysis[],
): BacktestTimeSeries {
  if (history.length === 0) {
    return {
      symbol,
      entries: [],
      overallAccuracy: 0,
      directionAccuracy: 0,
      avgHoldingPeriodDays: 0,
      profitFactor: 0,
      maxConsecutiveLosses: 0,
      longestWinStreak: 0,
      sharpeRatio: 0,
    };
  }

  // Ensure history is sorted chronologically (oldest first) for correct streak calculations
  const sortedHistory = [...history].sort((a, b) => {
    const timeA = new Date(a.stockInfo.lastUpdated || 0).getTime();
    const timeB = new Date(b.stockInfo.lastUpdated || 0).getTime();
    return timeA - timeB;
  });

  const currentPrice = current.stockInfo.price;
  const entries: BacktestEntry[] = sortedHistory.map((prev) => {
    const prevPrice = prev.stockInfo.price;
    const targetPrice = parseFloat(prev.tradingPlan?.targetPrice ?? '0');
    const stopLoss = parseFloat(prev.tradingPlan?.stopLoss ?? '0');
    const returnPercent = ((currentPrice - prevPrice) / prevPrice) * 100;

    const predictedUp = BULLISH_RECS.has(prev.recommendation) || targetPrice > prevPrice;
    const predictedDown = BEARISH_RECS.has(prev.recommendation) || targetPrice < prevPrice;
    const actualUp = currentPrice > prevPrice;

    const directionCorrect = predictedUp ? actualUp : predictedDown ? !actualUp : false;
    const targetHit = targetPrice > 0
      ? (predictedUp ? currentPrice >= targetPrice : currentPrice <= targetPrice)
      : false;

    return {
      date: prev.stockInfo.lastUpdated,
      recommendation: prev.recommendation,
      targetPrice,
      stopLoss,
      actualPrice: currentPrice,
      returnPercent: Math.round(returnPercent * 100) / 100,
      directionCorrect,
      targetHit,
    };
  });

  const correctCount = entries.filter(e => e.directionCorrect).length;
  const directionAccuracy = (correctCount / entries.length) * 100;

  // Profit factor
  const gains = entries.filter(e => e.returnPercent > 0).reduce((s, e) => s + e.returnPercent, 0);
  const losses = Math.abs(entries.filter(e => e.returnPercent < 0).reduce((s, e) => s + e.returnPercent, 0));
  const profitFactor = losses > 0 ? gains / losses : gains > 0 ? 999 : 0;

  // Streaks
  let maxLosses = 0;
  let maxWins = 0;
  let curLosses = 0;
  let curWins = 0;
  for (const e of entries) {
    if (e.returnPercent < 0) {
      curLosses++;
      curWins = 0;
      maxLosses = Math.max(maxLosses, curLosses);
    } else {
      curWins++;
      curLosses = 0;
      maxWins = Math.max(maxWins, curWins);
    }
  }

  // Avg holding period (approximate from date differences)
  let totalDays = 0;
  for (const e of entries) {
    const days = (Date.now() - new Date(e.date).getTime()) / (1000 * 60 * 60 * 24);
    totalDays += days;
  }
  const avgHoldingPeriodDays = Math.round(totalDays / entries.length);

  // Sharpe ratio (simplified)
  const avgReturn = entries.reduce((s, e) => s + e.returnPercent, 0) / entries.length;
  const variance = entries.reduce((s, e) => s + (e.returnPercent - avgReturn) ** 2, 0) / entries.length;
  const stdDev = Math.sqrt(variance);
  const sharpeRatio = stdDev > 0 ? Math.round((avgReturn / stdDev) * 100) / 100 : 0;

  // Overall accuracy (weighted: direction 60% + target hit 40%)
  const targetHitRate = entries.filter(e => e.targetHit).length / entries.length;
  const overallAccuracy = Math.round(directionAccuracy * 0.6 + targetHitRate * 100 * 0.4);

  return {
    symbol,
    entries,
    overallAccuracy,
    directionAccuracy,
    avgHoldingPeriodDays,
    profitFactor: Math.round(profitFactor * 100) / 100,
    maxConsecutiveLosses: maxLosses,
    longestWinStreak: maxWins,
    sharpeRatio,
  };
}

export function detectSystematicBias(timeSeries: BacktestTimeSeries): SystematicBias {
  const { entries } = timeSeries;
  if (entries.length < 3) {
    return { hasBias: false, biasType: null, severity: 'low', consecutiveCount: 0 };
  }

  // Check bullish drift: consecutive bullish calls with price dropping
  let consecutiveBullishWrong = 0;
  for (const e of entries) {
    if (BULLISH_RECS.has(e.recommendation) && !e.directionCorrect) {
      consecutiveBullishWrong++;
    } else {
      consecutiveBullishWrong = 0;
    }
  }
  if (consecutiveBullishWrong >= 3) {
    return {
      hasBias: true,
      biasType: 'bullish_drift',
      severity: consecutiveBullishWrong >= 5 ? 'high' : consecutiveBullishWrong >= 4 ? 'medium' : 'low',
      consecutiveCount: consecutiveBullishWrong,
    };
  }

  // Check bearish drift
  let consecutiveBearishWrong = 0;
  for (const e of entries) {
    if (BEARISH_RECS.has(e.recommendation) && !e.directionCorrect) {
      consecutiveBearishWrong++;
    } else {
      consecutiveBearishWrong = 0;
    }
  }
  if (consecutiveBearishWrong >= 3) {
    return {
      hasBias: true,
      biasType: 'bearish_drift',
      severity: consecutiveBearishWrong >= 5 ? 'high' : 'low',
      consecutiveCount: consecutiveBearishWrong,
    };
  }

  // Check target overshoot: direction correct but targets never hit
  const directionCorrectButNoTarget = entries.filter(e => e.directionCorrect && !e.targetHit);
  if (directionCorrectButNoTarget.length >= 3 && directionCorrectButNoTarget.length === entries.length) {
    return {
      hasBias: true,
      biasType: 'target_overshoot',
      severity: entries.length >= 5 ? 'high' : 'low',
      consecutiveCount: directionCorrectButNoTarget.length,
    };
  }

  return { hasBias: false, biasType: null, severity: 'low', consecutiveCount: 0 };
}
