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
  accuracy: number; // 0-100 score based on closeness to target or trend direction
  learningPoint: string;
}

export function performBacktest(current: StockAnalysis, previous: StockAnalysis | null): BacktestResult | null {
  if (!previous) return null;

  // Date-aware validation: ensure previous analysis is from a different (earlier) time
  // to prevent look-ahead bias in backtesting
  const prevDate = new Date(previous.stockInfo.lastUpdated);
  const currDate = new Date(current.stockInfo.lastUpdated);
  if (!isNaN(prevDate.getTime()) && !isNaN(currDate.getTime()) && prevDate > currDate) {
    console.warn('[Backtest] Previous analysis date is after current — skipping to avoid look-ahead bias');
    return null;
  }

  const prevPrice = previous.stockInfo.price;
  const currPrice = current.stockInfo.price;

  // Validate prices are positive numbers
  if (!prevPrice || !currPrice || prevPrice <= 0 || currPrice <= 0) return null;

  const returnRaw = ((currPrice - prevPrice) / prevPrice) * 100;
  const returnStr = `${returnRaw > 0 ? "+" : ""}${returnRaw.toFixed(2)}%`;

  const prevTarget = parseFloat(previous.tradingPlan?.targetPrice || "0");
  const prevStop = parseFloat(previous.tradingPlan?.stopLoss || "0");

  let status: BacktestResult["status"] = "In Progress";
  if (prevTarget > 0 && currPrice >= prevTarget) status = "Target Hit";
  else if (prevStop > 0 && currPrice <= prevStop) status = "Stop Loss Hit";

  // Detect logic drift: if the analysis date gap is too large (>45 days),
  // mark as Logic Drift since the original thesis may no longer be relevant
  const daysBetween = (currDate.getTime() - prevDate.getTime()) / (1000 * 60 * 60 * 24);
  if (daysBetween > 45 && status === "In Progress") {
    status = "Logic Drift";
  }

  // Calculate generic accuracy (closer to target or predicted direction)
  const predictedDirection = prevTarget > prevPrice ? 1 : -1;
  const actualDirection = currPrice > prevPrice ? 1 : -1;
  let accuracy = 50; 
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
    returnSincePrev: returnStr,
    previousRecommendation: previous.recommendation,
    previousTarget: previous.tradingPlan?.targetPrice || "N/A",
    previousStopLoss: previous.tradingPlan?.stopLoss || "N/A",
    status,
    accuracy,
    learningPoint: determineInitialLearning(status, returnRaw)
  };
}

function determineInitialLearning(status: string, returnRaw: number): string {
  if (status === "Target Hit") return "核心驱动逻辑得到验证，溢价正在兑现。";
  if (status === "Stop Loss Hit") return "预期变量出现重大背离，原有逻辑证伪。";
  if (returnRaw > 0) return "趋势符合预期，正在向目标价靠拢。";
  return "目前处于逻辑考验期，需重新评估驱动变量。";
}
