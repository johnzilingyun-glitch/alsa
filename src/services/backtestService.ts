import { StockAnalysis } from "../types";

export interface BacktestResult {
  previousDate: string;
  previousPrice: number;
  currentPrice: number;
  returnSincePrev: string; // e.g. "+5.2%"
  previousRecommendation: string;
  previousTarget: string;
  previousStopLoss: string;
  status: "Target Hit" | "Stop Loss Hit" | "In Progress" | "Logic Drift";
  accuracy: number; // 0-100 score
  sharpeRatio?: number;
  sortinoRatio?: number;
  learningPoint: string;
}

export function performBacktest(current: StockAnalysis, previous: StockAnalysis | null): BacktestResult | null {
  if (!previous) return null;

  const prevDate = new Date(previous.stockInfo.lastUpdated);
  const currDate = new Date(current.stockInfo.lastUpdated);
  
  const prevPrice = previous.stockInfo.price;
  const currPrice = current.stockInfo.price;
  const annVol = current.stockInfo.technicalIndicators?.riskMetrics?.annualizedVolatility || 0.30; // Default 30% if missing

  if (!prevPrice || !currPrice || prevPrice <= 0 || currPrice <= 0) return null;

  const returnRaw = ((currPrice - prevPrice) / prevPrice); // Decimal
  const returnPctStr = `${returnRaw > 0 ? "+" : ""}${(returnRaw * 100).toFixed(2)}%`;

  const prevTarget = parseFloat(previous.tradingPlan?.targetPrice || "0");
  const prevStop = parseFloat(previous.tradingPlan?.stopLoss || "0");

  let status: BacktestResult["status"] = "In Progress";
  if (prevTarget > 0 && currPrice >= prevTarget) status = "Target Hit";
  else if (prevStop > 0 && currPrice <= prevStop) status = "Stop Loss Hit";

  const daysBetween = (currDate.getTime() - prevDate.getTime()) / (1000 * 60 * 60 * 24);
  if (daysBetween > 45 && status === "In Progress") {
    status = "Logic Drift";
  }

  // Calculate institutional metrics
  const riskFreeRate = 0.03; // 3% assumed annualized
  const holdingPeriodYears = Math.max(0.01, daysBetween / 365);
  const annualizedReturn = Math.pow(1 + returnRaw, 1 / holdingPeriodYears) - 1;
  
  // Simplified Sharpe: (Ann. Return - Risk Free) / Ann. Volatility
  const sharpeRatio = annVol > 0 ? (annualizedReturn - riskFreeRate) / annVol : 0;
  
  // Simplified Sortino: Downside deviation used as a fraction of vol
  const sortinoRatio = returnRaw < 0 ? (annualizedReturn - riskFreeRate) / (annVol * 1.2) : sharpeRatio * 1.5;

  let accuracy = 50; 
  const predictedDirection = prevTarget > prevPrice ? 1 : -1;
  const actualDirection = currPrice > prevPrice ? 1 : -1;
  if (predictedDirection === actualDirection) {
    accuracy = 70;
    if (status === "Target Hit") accuracy = 95;
  } else {
    accuracy = 30;
    if (status === "Stop Loss Hit") accuracy = 10;
  }

  return {
    previousDate: previous.stockInfo.lastUpdated,
    previousPrice: prevPrice,
    currentPrice: currPrice,
    returnSincePrev: returnPctStr,
    previousRecommendation: previous.recommendation,
    previousTarget: previous.tradingPlan?.targetPrice || "N/A",
    previousStopLoss: previous.tradingPlan?.stopLoss || "N/A",
    status,
    accuracy,
    sharpeRatio: parseFloat(sharpeRatio.toFixed(2)),
    sortinoRatio: parseFloat(sortinoRatio.toFixed(2)),
    learningPoint: determineInitialLearning(status, returnRaw * 100)
  };
}

function determineInitialLearning(status: string, returnRaw: number): string {
  if (status === "Target Hit") return "核心驱动逻辑得到验证，溢价正在兑现。";
  if (status === "Stop Loss Hit") return "预期变量出现重大背离，原有逻辑证伪。";
  if (returnRaw > 0) return "趋势符合预期，正在向目标价靠拢。";
  return "目前处于逻辑考验期，需重新评估驱动变量。";
}
