import type { StockInfo, MarketOverview } from "../types";
export { getApiKey, withRetry, parseJsonResponse, extractJsonBlock } from "./llmService";

type AnalysisModule = typeof import('./analysisService');
type MarketModule = typeof import('./marketService');
type DiscussionModule = typeof import('./discussionService');
type AdminModule = typeof import('./adminService');

const loadAnalysisService = (): Promise<AnalysisModule> => import('./analysisService');
const loadMarketService = (): Promise<MarketModule> => import('./marketService');
const loadDiscussionService = (): Promise<DiscussionModule> => import('./discussionService');
const loadAdminService = (): Promise<AdminModule> => import('./adminService');

type AsyncReturn<T> = T extends (...args: any[]) => Promise<infer R> ? Promise<R> : never;

export async function analyzeStock(...args: Parameters<AnalysisModule['analyzeStock']>): AsyncReturn<AnalysisModule['analyzeStock']> {
  const service = await loadAnalysisService();
  return service.analyzeStock(...args) as AsyncReturn<AnalysisModule['analyzeStock']>;
}

export async function sendChatMessage(...args: Parameters<AnalysisModule['sendChatMessage']>): AsyncReturn<AnalysisModule['sendChatMessage']> {
  const service = await loadAnalysisService();
  return service.sendChatMessage(...args) as AsyncReturn<AnalysisModule['sendChatMessage']>;
}

export async function getStockReport(...args: Parameters<AnalysisModule['getStockReport']>): AsyncReturn<AnalysisModule['getStockReport']> {
  const service = await loadAnalysisService();
  return service.getStockReport(...args) as AsyncReturn<AnalysisModule['getStockReport']>;
}

export async function getDiscussionReport(...args: Parameters<AnalysisModule['getDiscussionReport']>): AsyncReturn<AnalysisModule['getDiscussionReport']> {
  const service = await loadAnalysisService();
  return service.getDiscussionReport(...args) as AsyncReturn<AnalysisModule['getDiscussionReport']>;
}

export async function getChatReport(...args: Parameters<AnalysisModule['getChatReport']>): AsyncReturn<AnalysisModule['getChatReport']> {
  const service = await loadAnalysisService();
  return service.getChatReport(...args) as AsyncReturn<AnalysisModule['getChatReport']>;
}

export async function getMarketOverview(...args: Parameters<MarketModule['getMarketOverview']>): AsyncReturn<MarketModule['getMarketOverview']> {
  const service = await loadMarketService();
  return service.getMarketOverview(...args) as AsyncReturn<MarketModule['getMarketOverview']>;
}

export async function getMarketSnapshot(...args: Parameters<MarketModule['getMarketSnapshot']>): AsyncReturn<MarketModule['getMarketSnapshot']> {
  const service = await loadMarketService();
  return service.getMarketSnapshot(...args) as AsyncReturn<MarketModule['getMarketSnapshot']>;
}

export async function getDailyReport(...args: Parameters<MarketModule['getDailyReport']>): AsyncReturn<MarketModule['getDailyReport']> {
  const service = await loadMarketService();
  return service.getDailyReport(...args) as AsyncReturn<MarketModule['getDailyReport']>;
}

export async function startAgentDiscussion(...args: Parameters<DiscussionModule['startAgentDiscussion']>): AsyncReturn<DiscussionModule['startAgentDiscussion']> {
  const service = await loadDiscussionService();
  return service.startAgentDiscussion(...args) as AsyncReturn<DiscussionModule['startAgentDiscussion']>;
}

export async function startMultiRoundDiscussion(...args: Parameters<DiscussionModule['startMultiRoundDiscussion']>): AsyncReturn<DiscussionModule['startMultiRoundDiscussion']> {
  const service = await loadDiscussionService();
  return service.startMultiRoundDiscussion(...args) as AsyncReturn<DiscussionModule['startMultiRoundDiscussion']>;
}

export async function answerDiscussionQuestion(...args: Parameters<DiscussionModule['answerDiscussionQuestion']>): AsyncReturn<DiscussionModule['answerDiscussionQuestion']> {
  const service = await loadDiscussionService();
  return service.answerDiscussionQuestion(...args) as AsyncReturn<DiscussionModule['answerDiscussionQuestion']>;
}

export async function generateNewConclusion(...args: Parameters<DiscussionModule['generateNewConclusion']>): AsyncReturn<DiscussionModule['generateNewConclusion']> {
  const service = await loadDiscussionService();
  return service.generateNewConclusion(...args) as AsyncReturn<DiscussionModule['generateNewConclusion']>;
}

export async function routeUserQuestion(...args: Parameters<DiscussionModule['routeUserQuestion']>): AsyncReturn<DiscussionModule['routeUserQuestion']> {
  const service = await loadDiscussionService();
  return service.routeUserQuestion(...args) as AsyncReturn<DiscussionModule['routeUserQuestion']>;
}

export async function saveAnalysisToHistory(...args: Parameters<AdminModule['saveAnalysisToHistory']>): AsyncReturn<AdminModule['saveAnalysisToHistory']> {
  const service = await loadAdminService();
  return service.saveAnalysisToHistory(...args) as AsyncReturn<AdminModule['saveAnalysisToHistory']>;
}

export async function getHistoryContext(...args: Parameters<AdminModule['getHistoryContext']>): AsyncReturn<AdminModule['getHistoryContext']> {
  const service = await loadAdminService();
  return service.getHistoryContext(...args) as AsyncReturn<AdminModule['getHistoryContext']>;
}

export async function deleteHistoryItem(...args: Parameters<AdminModule['deleteHistoryItem']>): AsyncReturn<AdminModule['deleteHistoryItem']> {
  const service = await loadAdminService();
  return service.deleteHistoryItem(...args) as AsyncReturn<AdminModule['deleteHistoryItem']>;
}

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
