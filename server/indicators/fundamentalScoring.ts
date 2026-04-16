/**
 * Fundamental Scoring Engine
 * ──────────────────────────
 * Quantitative evaluation of financial health, moat strength, 
 * and intrinsic value based on Graham/Buffett principles.
 */

export interface FundamentalScores {
  valueScore: number;       // 0-100
  growthScore: number;      // 0-100
  safetyScore: number;      // 0-100
  intrinsicValue?: number;
  moatRating: "Wide" | "Narrow" | "None";
  verdict: string;
}

/**
 * Calculates scores based on raw fundamental indicators.
 * Expects normalized numeric inputs.
 */
export function calculateFundamentalScores(data: {
  pe: number;
  pb: number;
  roe: number;
  debtToEquity: number;
  netProfitGrowth: number;
  grossMargin: number;
}): FundamentalScores {
  let valueScore = 0;
  let growthScore = 0;
  let safetyScore = 0;

  // 1. Value Scoring (Graham style)
  // Low PE (<15) and Low PB (<1.5) preferred
  if (data.pe > 0 && data.pe < 15) valueScore += 50;
  else if (data.pe > 0 && data.pe < 25) valueScore += 30;
  
  if (data.pb > 0 && data.pb < 1.5) valueScore += 50;
  else if (data.pb > 0 && data.pb < 3) valueScore += 25;

  // 2. Growth Scoring
  if (data.netProfitGrowth > 20) growthScore = 90;
  else if (data.netProfitGrowth > 10) growthScore = 70;
  else if (data.netProfitGrowth > 0) growthScore = 40;
  else growthScore = 10;

  // 3. Quality/Safety Scoring (Buffett style)
  // High ROE (>15%) and Low Debt Preferred
  if (data.roe > 15) safetyScore += 40;
  else if (data.roe > 10) safetyScore += 20;

  if (data.debtToEquity < 0.5) safetyScore += 40;
  else if (data.debtToEquity < 1.0) safetyScore += 20;

  if (data.grossMargin > 30) safetyScore += 20;

  // Moat Determination
  let moatRating: "Wide" | "Narrow" | "None" = "None";
  if (data.roe > 20 && data.grossMargin > 40) moatRating = "Wide";
  else if (data.roe > 12 && data.grossMargin > 20) moatRating = "Narrow";

  return {
    valueScore: Math.min(100, valueScore),
    growthScore: Math.min(100, growthScore),
    safetyScore: Math.min(100, safetyScore),
    moatRating,
    verdict: generateVerdict(valueScore, growthScore, safetyScore, moatRating)
  };
}

function generateVerdict(v: number, g: number, s: number, m: string): string {
  if (s > 70 && v > 70) return "Deep Value Opportunity (High Safety + Undervalued)";
  if (g > 70 && s > 70) return "Quality Growth (High Growth + High Moat/Safety)";
  if (v > 70) return "Value Play (Reasonable Price)";
  if (g > 80) return "High Growth Momentum";
  if (s < 40) return "High Risk / Distressed Fundamentals";
  return "Balanced Fundamental Outlook";
}

/**
 * Simplified Owner Earnings / DCF
 */
export function calculateIntrinsicValueEstimate(currentPrice: number, roe: number, growth: number): number {
  // Very simplified: Benjamin Graham Formula approx: V = EPS * (8.5 + 2g)
  // Here we use a simpler yield-based approach for AI grounding
  if (roe <= 0) return 0;
  const discountRate = 0.10; // 10% Hurdle rate
  const terminalGrowth = 0.03; // 3% Perpetual growth
  
  // Estimate intrinsic value relative to price based on ROE/Growth
  // This is a heuristic for the AI to have a number to debate
  const intrinsicMultiplier = (roe / 100) / (discountRate - (growth / 100 > 0.08 ? 0.08 : growth / 100));
  return currentPrice * Math.min(2.0, Math.max(0.5, intrinsicMultiplier));
}
