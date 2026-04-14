import { GoogleGenAI } from "@google/genai";
import { createAI, withRetry, generateContentWithUsage, GEMINI_MODEL, generateAndParseJsonWithRetry } from "./geminiService";
import { getMarketOverviewPrompt, getDailyReportPrompt } from "./prompts";
import { MarketOverview, GeminiConfig, Market, IndexInfo, CommodityAnalysis } from "../types";
import { useConfigStore } from "../stores/useConfigStore";
import { getHistoryContext, saveAnalysisToHistory } from "./adminService";
import { getBeijingDate } from "./dateUtils";
import { MarketOverviewSchema, validateResponse } from "./schemas";

/**
 * Fetches real-time market data (indices + commodities) directly from financial APIs.
 * No AI call required — always fast, no quota usage.
 */
export async function getMarketSnapshot(market: Market = "A-Share"): Promise<Partial<MarketOverview>> {
  const [indicesData, commoditiesData] = await Promise.all([
    fetch(`/api/stock/indices?market=${market}`).then(r => r.ok ? r.json() : []).catch(() => []),
    getCommoditiesData(),
  ]);

  const indices: IndexInfo[] = (indicesData || []).map((d: any) => ({
    name: d.name,
    symbol: d.symbol,
    price: d.price ?? 0,
    change: d.change ?? 0,
    changePercent: d.changePercent ?? 0,
    previousClose: d.previousClose ?? 0,
  }));

  // Convert raw commodity data into CommodityAnalysis shape for display
  const commodityAnalysis: CommodityAnalysis[] = (commoditiesData || []).map((d: any) => ({
    name: d.name,
    trend: d.changePercent > 0 ? '上涨' : d.changePercent < 0 ? '下跌' : '持平',
    expectation: `${d.price} ${d.unit || ''} (${d.changePercent > 0 ? '+' : ''}${d.changePercent}%)`,
  }));

  return {
    indices,
    commodityAnalysis,
    generatedAt: Date.now(),
    market,
  };
}

export async function getMarketOverview(config?: GeminiConfig, market: Market = "A-Share", forceRefresh: boolean = false, priority: number = 0): Promise<MarketOverview> {
  const now = new Date();
  const today = getBeijingDate(now);
  const language = useConfigStore.getState().language;
  
  const ai = createAI(config);
  const history = await getHistoryContext();
  const beijingDate = today;

  // 1. Check history for existing overview from today
  if (!forceRefresh) {
    const todayStr = beijingDate; // YYYY/MM/DD or YYYY-MM-DD
    const existing = history.find(h => {
      // Robust identification:
      // A. Check type field (now added by server)
      // B. Fallback to checking for "indices" field if it looks like a market overview
      const isMarketType = h.type === 'market' || (h.indices && !h.stockInfo);
      if (!isMarketType) return false;

      // Handle market names (e.g. A-Share). Fallback to case-insensitive comparison.
      const hMarket = h.market || '';
      if (hMarket.toLowerCase() !== market.toLowerCase()) return false;

      const hDate = h.generatedAt ? getBeijingDate(new Date(h.generatedAt)) : null;
      
      const isMatch = hDate === todayStr;
      if (isMatch) console.log(`[Market] Robust match found in history for ${market} on ${todayStr}`);
      return isMatch;
    });

    if (existing) {
      console.log(`[Market] Recovered ${market} overview from history:`, existing.id);
      return existing as MarketOverview;
    } else {
      console.log(`[Market] No matching today (${todayStr}) overview found in history for ${market}. Found ${history.length} items.`);
    }
  }

  // Fetch all market data in parallel — these endpoints are independent
  const needsSectors = market === 'A-Share' || market === 'HK-Share';
  const needsNorthbound = market === 'A-Share';

  const [indicesData, newsData, sectorsData, northboundData, commoditiesData] = await Promise.all([
    fetch(`/api/stock/indices?market=${market}`).then(r => r.ok ? r.json() : []).catch(() => []),
    fetch(`/api/stock/news?market=${market}`).then(r => r.ok ? r.json() : []).catch(() => []),
    needsSectors ? fetch('/api/stock/sectors').then(r => r.ok ? r.json() : null).catch(() => null) : Promise.resolve(null),
    needsNorthbound ? fetch('/api/stock/northbound').then(r => r.ok ? r.json() : null).catch(() => null) : Promise.resolve(null),
    getCommoditiesData(),
  ]);
  const prompt = getMarketOverviewPrompt(indicesData, commoditiesData, newsData, sectorsData, northboundData, history, beijingDate, now, market, language);

  const raw = await generateAndParseJsonWithRetry<MarketOverview>(ai, {
    model: config?.model || GEMINI_MODEL,
    contents: prompt,
    config: { 
      responseMimeType: "application/json"
    }
  }, { transportRetries: 1, parseRetries: 1 }, priority);

  const overview = validateResponse(MarketOverviewSchema, raw, 'MarketOverview') as MarketOverview;

  // Anti-hallucination: enforce API indices data over AI-generated values
  if (indicesData.length > 0 && overview.indices) {
    const apiMap = new Map<string, any>(indicesData.map((idx: any) => [idx.symbol, idx]));
    let driftDetected = false;
    for (const aiIdx of overview.indices) {
      const apiIdx: any = apiMap.get(aiIdx.symbol);
      if (apiIdx && apiIdx.price != null && apiIdx.price > 0) {
        const indexDriftPct = Math.abs(aiIdx.price - apiIdx.price) / apiIdx.price;
        if (indexDriftPct > 0.02) { // 2% threshold for indices (large numbers, qualitative context)
          console.warn(`[AntiHallucination] Market index ${aiIdx.symbol}: AI=${aiIdx.price}, API=${apiIdx.price} (${(indexDriftPct * 100).toFixed(2)}%). Correcting.`);
          driftDetected = true;
        }
        aiIdx.price = Number(apiIdx.price);
        if (apiIdx.change != null) aiIdx.change = Number(apiIdx.change);
        if (apiIdx.changePercent != null) aiIdx.changePercent = Number(apiIdx.changePercent);
        if (apiIdx.previousClose != null) aiIdx.previousClose = Number(apiIdx.previousClose);
      }
    }
    if (driftDetected && overview.marketSummary) {
      overview.marketSummary += '\n\n⚠️ 注意：AI分析中的部分指数数据已由实时API数据修正。';
    }
  }

  overview.id = `market-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  overview.generatedAt = Date.now();
  overview.market = market; // Tag market type for history recovery
  
  if (overview.indices && overview.indices.length > 0) {
    await saveAnalysisToHistory('market', overview);
  }

  return overview;
}

// Cache commodities data for 5 minutes — it's fetched by analysisService,
// discussionService, and marketService within the same analysis session.
let _commoditiesCache: { data: any[]; expiry: number } = { data: [], expiry: 0 };

/** Reset commodities cache (for testing) */
export function clearCommoditiesCache() {
  _commoditiesCache = { data: [], expiry: 0 };
}

export async function getCommoditiesData(): Promise<any[]> {
  const now = Date.now();
  if (_commoditiesCache.expiry > now && _commoditiesCache.data.length > 0) {
    return _commoditiesCache.data;
  }
  try {
    const res = await fetch('/api/stock/commodities');
    if (res.ok) {
      const data = await res.json();
      _commoditiesCache = { data, expiry: now + 5 * 60 * 1000 };
      return data;
    }
  } catch (e) {
    console.warn('Commodities fetch failed:', e);
  }
  return [];
}

export async function getDailyReport(marketOverview: MarketOverview, config?: GeminiConfig): Promise<string> {
  const ai = createAI(config);
  const now = new Date();
  const beijingDate = getBeijingDate(now);
  const language = useConfigStore.getState().language;
  const commoditiesData = await getCommoditiesData();
  const prompt = getDailyReportPrompt(marketOverview, commoditiesData, now, beijingDate, language);

  const response = await withRetry(async () => {
    const result = await generateContentWithUsage(ai, {
      model: config?.model || GEMINI_MODEL,
      contents: prompt,
      config: {
        tools: [{ googleSearch: {} }]
      }
    });
    return result.text;
  });

  return response;
}
