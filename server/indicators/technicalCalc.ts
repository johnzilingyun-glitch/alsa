/**
 * Technical indicator calculations — shared across AkShare and Yahoo data paths.
 */

export interface TechnicalIndicators {
  ma5: number | null;
  ma20: number | null;
  ma60: number | null;
  avgVolume5: number | null;
  avgVolume20: number | null;
  resistanceShort: number;
  supportShort: number;
  resistanceLong: number;
  supportLong: number;
  lastClose: number;
}

/**
 * Simple Moving Average.
 * Returns null if the array has fewer than `days` elements.
 */
export function calcMA(arr: number[], days: number): number | null {
  if (arr.length < days) return null;
  const slice = arr.slice(-days);
  return parseFloat((slice.reduce((a, b) => a + b, 0) / days).toFixed(2));
}

/**
 * Safe max — avoids RangeError from spreading into Math.max for large arrays.
 */
function safeMax(arr: number[]): number {
  return arr.reduce((a, b) => Math.max(a, b), -Infinity);
}

/**
 * Safe min — avoids RangeError from spreading into Math.min for large arrays.
 */
function safeMin(arr: number[]): number {
  return arr.reduce((a, b) => Math.min(a, b), Infinity);
}

/**
 * Calculate all technical indicators from OHLCV arrays.
 * 
 * Expects arrays sorted chronologically (oldest → newest).
 * Null-safeguards: filters out null/undefined values before calculation.
 */
export function calcIndicators(
  prices: number[],
  volumes: number[],
  highs: number[],
  lows: number[],
  options?: { roundVolume?: boolean }
): TechnicalIndicators | null {
  if (prices.length < 5) return null;

  const roundVol = options?.roundVolume ?? false;

  const avgVolume5 = calcMA(volumes, 5);
  const avgVolume20 = calcMA(volumes, 20);

  return {
    ma5: calcMA(prices, 5),
    ma20: calcMA(prices, 20),
    ma60: calcMA(prices, 60),
    avgVolume5: roundVol ? Math.round(avgVolume5 || 0) : avgVolume5,
    avgVolume20: roundVol ? Math.round(avgVolume20 || 0) : avgVolume20,
    resistanceShort: parseFloat(safeMax(highs.slice(-20)).toFixed(2)),
    supportShort: parseFloat(safeMin(lows.slice(-20)).toFixed(2)),
    resistanceLong: parseFloat(safeMax(highs.slice(-60)).toFixed(2)),
    supportLong: parseFloat(safeMin(lows.slice(-60)).toFixed(2)),
    lastClose: prices[prices.length - 1],
  };
}
