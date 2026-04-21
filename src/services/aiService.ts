import { StockAnalysis, Market, MarketOverview, AgentMessage, Scenario, AgentDiscussion, StockInfo } from "../types";
import { analyzeStock as _analyzeStock, sendChatMessage as _sendChatMessage, getStockReport as _getStockReport, getDiscussionReport as _getDiscussionReport, getChatReport as _getChatReport } from "./analysisService";
import { getMarketOverview as _getMarketOverview, getDailyReport as _getDailyReport, getMarketSnapshot as _getMarketSnapshot } from "./marketService";
import { startAgentDiscussion as _startAgentDiscussion, startMultiRoundDiscussion as _startMultiRoundDiscussion, answerDiscussionQuestion as _answerDiscussionQuestion, generateNewConclusion as _generateNewConclusion, routeUserQuestion as _routeUserQuestion } from "./discussionService";
import { saveAnalysisToHistory as _saveAnalysisToHistory, getHistoryContext as _getHistoryContext, deleteHistoryItem as _deleteHistoryItem } from "./adminService";

// Re-export core functions from new services
export const analyzeStock = _analyzeStock;
export const sendChatMessage = _sendChatMessage;
export const getStockReport = _getStockReport;
export const getDiscussionReport = _getDiscussionReport;
export const getChatReport = _getChatReport;
export const getMarketOverview = _getMarketOverview;
export const getMarketSnapshot = _getMarketSnapshot;
export const getDailyReport = _getDailyReport;
export const startAgentDiscussion = _startAgentDiscussion;
export const startMultiRoundDiscussion = _startMultiRoundDiscussion;
export const answerDiscussionQuestion = _answerDiscussionQuestion;
export const generateNewConclusion = _generateNewConclusion;
export const routeUserQuestion = _routeUserQuestion;
export const saveAnalysisToHistory = _saveAnalysisToHistory;
export const getHistoryContext = _getHistoryContext;
export const deleteHistoryItem = _deleteHistoryItem;

// Export helper functions for backward compatibility if needed
export { getApiKey, withRetry, parseJsonResponse, extractJsonBlock } from "./geminiService";

export function validateStockInfo(info: StockInfo): void {
  if (!info.symbol || !info.name) {
    throw new Error("Missing symbol or name");
  }
  if (info.price <= 0) {
    throw new Error("Invalid price: must be positive");
  }
  if (!info.lastUpdated.includes("CST")) {
    throw new Error("Invalid time format: must include CST");
  }

  // Calculation mismatch check
  const expectedChange = Number((info.price - info.previousClose).toFixed(2));
  if (Math.abs(info.change - expectedChange) > 0.01) {
    throw new Error(`Calculation mismatch: price(${info.price}) - prevClose(${info.previousClose}) = ${expectedChange}, but change is ${info.change}`);
  }

  // Daily range check
  if (info.dailyHigh !== undefined && info.dailyLow !== undefined) {
    if (info.price > info.dailyHigh || info.price < info.dailyLow) {
      throw new Error(`Price(${info.price}) is outside daily range [${info.dailyLow}, ${info.dailyHigh}]`);
    }
  }

  // Market limit check (A-share 10% or 20%)
  if (info.market === "A-Share") {
    const limit = info.symbol.startsWith("30") || info.symbol.startsWith("68") ? 20.1 : 10.1;
    if (Math.abs(info.changePercent) > limit) {
      throw new Error(`Change percent(${info.changePercent}%) exceeds market limit(${limit}%)`);
    }
    if (info.currency !== "CNY") {
      throw new Error(`Currency mismatch: A-Share must be CNY, but got ${info.currency}`);
    }
  }
}

export function validateMarketOverview(overview: MarketOverview): void {
  if (!overview.indices || overview.indices.length === 0) {
    throw new Error("Market overview must include indices");
  }
}
