import axios from 'axios';

// Configure axios for the python service
const pythonService = axios.create({
  baseURL: process.env.PYTHON_SERVICE_URL || 'http://127.0.0.1:8001',
  timeout: 5000,
});

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
 * Calculate all technical indicators from OHLCV arrays by offloading to Python/Polars service.
 */
export async function calcIndicators(
  prices: number[],
  volumes: number[],
  highs: number[],
  lows: number[],
  options?: { roundVolume?: boolean }
): Promise<TechnicalIndicators | null> {
  if (prices.length < 5) return null;

  try {
    // 1. Prepare data for Polars (chronological order)
    const data = prices.map((price, i) => ({
      trade_date: i, // Placeholder date index
      close: price,
      volume: volumes[i],
      high: highs[i],
      low: lows[i]
    }));

    // 2. Call Python Service
    const response = await pythonService.post('/api/indicators/calculate', { data });

    if (!response.data.success) {
      console.error('Indicator calculation failed in Python:', response.data.error);
      return null;
    }

    const res = response.data.data;
    const last = res[res.length - 1];

    // 3. Map Polars result to expected format
    return {
      ma5: last.ma_5,
      ma20: last.ma_20,
      ma60: last.ma_60,
      avgVolume5: last.avg_volume_5,
      avgVolume20: last.avg_volume_20,
      resistanceShort: last.resistance_short,
      supportShort: last.support_short,
      resistanceLong: last.resistance_long,
      supportLong: last.support_long,
      lastClose: prices[prices.length - 1],
    };
  } catch (err) {
    console.error('Error calling indicators service:', err);
    return null;
  }
}
