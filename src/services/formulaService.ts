/**
 * Calculation Layer: Standardized Formula Library
 */
export const formulaLibrary = {
  calculateDCF(fcf: number, growthRate: number, discountRate: number, terminalGrowth: number) {
    const years = 5;
    let totalPV = 0;
    let currentFCF = fcf;
    for (let i = 1; i <= years; i++) {
      currentFCF *= (1 + growthRate);
      totalPV += currentFCF / Math.pow(1 + discountRate, i);
    }
    const terminalValue = (currentFCF * (1 + terminalGrowth)) / (discountRate - terminalGrowth);
    const terminalPV = terminalValue / Math.pow(1 + discountRate, years);
    return totalPV + terminalPV;
  },
  calculateVaR(portfolioValue: number, confidence: number, volatility: number) {
    const zScore = confidence === 0.95 ? 1.645 : 2.326;
    return portfolioValue * zScore * volatility;
  }
};
