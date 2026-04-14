import type { StockAnalysis, ComparisonResult, ComparisonStock } from '../types';

export function buildComparisonResult(analyses: StockAnalysis[]): ComparisonResult {
  const stocks: ComparisonStock[] = analyses.map((a) => {
    const riskLevel: ComparisonStock['riskLevel'] =
      a.score >= 70 ? 'Low' : a.score >= 40 ? 'Medium' : 'High';

    return {
      symbol: a.stockInfo.symbol,
      name: a.stockInfo.name,
      market: a.stockInfo.market,
      score: a.score,
      recommendation: a.recommendation,
      pe: a.fundamentals?.pe,
      pb: a.fundamentals?.pb,
      roe: a.fundamentals?.roe,
      riskLevel,
    };
  });

  return {
    stocks,
    sharedIndustry: '',
    verdict: '',
    generatedAt: new Date().toISOString(),
  };
}

export function rankStocks(stocks: ComparisonStock[]): ComparisonStock[] {
  return [...stocks].sort((a, b) => b.score - a.score);
}
