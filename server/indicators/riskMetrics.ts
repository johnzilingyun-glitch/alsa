/**
 * Quantitative Risk Management Metrics
 * ───────────────────────────────────
 * Pure numerical risk calculations including volatility, position limits,
 * and correlation metrics based on virattt/ai-hedge-fund logic.
 */

/**
 * Calculates historical volatility (standard deviation of log returns).
 * @param prices Array of prices (oldest to newest)
 * @param window Rolling window (default 20 days)
 * @returns Annualized volatility (e.g., 0.25 for 25%)
 */
export function calculateVolatility(prices: number[], window: number = 20): number {
  if (prices.length < window + 1) return 0;

  const slice = prices.slice(-(window + 1));
  const returns: number[] = [];
  for (let i = 1; i < slice.length; i++) {
    // Log returns: ln(p_t / p_{t-1})
    returns.push(Math.log(slice[i] / slice[i - 1]));
  }

  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance = returns.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / (returns.length - 1);
  const stdDev = Math.sqrt(variance);

  // Annualize: σ_annual = σ_daily * sqrt(252 trading days)
  return stdDev * Math.sqrt(252);
}

/**
 * Determines a recommended position size limit based on volatility regime.
 * Formula inspired by ai-hedge-fund risk_management.py
 * 
 * Low Vol (<15%) -> High limit (up to 25%)
 * High Vol (>50%) -> Low limit (down to 10%)
 */
export function calculateVolatilityAdjustedLimit(annualizedVol: number): { limit: number; regime: string } {
  let limit = 0.20; // Default 20%
  let regime = "Normal";

  if (annualizedVol < 0.15) {
    limit = 0.25;
    regime = "Low Volatility";
  } else if (annualizedVol < 0.30) {
    // Linear interpolation between 0.15 (25%) and 0.30 (20%)
    limit = 0.25 - (annualizedVol - 0.15) * 0.33;
    regime = "Moderate Volatility";
  } else if (annualizedVol < 0.50) {
    // Linear interpolation between 0.30 (20%) and 0.50 (10%)
    limit = 0.20 - (annualizedVol - 0.30) * 0.50;
    regime = "High Volatility";
  } else {
    limit = 0.10;
    regime = "Extreme Volatility";
  }

  return { limit: Math.max(0.05, limit), regime };
}

/**
 * Calculates a simple correlation multiplier.
 * If multiple assets are being analyzed, this reduces position if average correlation is high.
 */
export function calculateCorrelationMultiplier(avgCorrelation: number): number {
  if (avgCorrelation >= 0.80) return 0.70; // High correlation -> Cut 30%
  if (avgCorrelation >= 0.60) return 0.85; // Moderate -> Cut 15%
  if (avgCorrelation >= 0.40) return 1.00; // Normal
  if (avgCorrelation >= 0.20) return 1.05; // Diversified -> Boost 5%
  return 1.10; // Low correlation -> Boost 10%
}
