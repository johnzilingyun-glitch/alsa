import { GoogleGenAI } from "@google/genai";
import { createAI, withRetry, generateContentWithUsage, DEFAULT_LLM_MODEL, generateAndParseJsonWithRetry } from "./llmService";
import { getMarketOverviewPrompt, getDailyReportPrompt, getMarketSummaryPrompt } from "./prompts";
import { MarketOverview, LLMConfig, Market, IndexInfo, CommodityAnalysis, MarketDashboard } from "../types";
import { useConfigStore } from "../stores/useConfigStore";
import { formatFundFlow } from "./formatUtils";
import { getHistoryContext, saveAnalysisToHistory } from "./adminService";
import { getBeijingDate } from "./dateUtils";
import { MarketOverviewSchema, validateResponse } from "./schemas";

// ── New Dashboard API ─────────────────────────────────────────

export async function fetchDashboardFromAPI(market: Market = "A-Share"): Promise<MarketDashboard> {
  const res = await fetch(`/api/market/dashboard?market=${encodeURIComponent(market)}`);
  if (!res.ok) throw new Error(`Dashboard fetch failed: ${res.status}`);
  return res.json();
}

export interface SummaryPayload {
  majorIndices: { name: string; changePct: number }[];
  topSectors: { name: string; inflow: number; changePct: number }[];
  northboundNet: string;
  commoditiesMove: { name: string; changePct: number }[];
  headlines: string[];
}

export async function generateMarketSummary(payload: SummaryPayload): Promise<{ summary: string; sentiment: 'bullish' | 'bearish' | 'neutral' }> {
  const ai = createAI();
  const prompt = getMarketSummaryPrompt(payload);
  const raw = await generateAndParseJsonWithRetry<{ marketSummary?: string; marketSentiment?: string }>(ai, {
    model: DEFAULT_LLM_MODEL,
    contents: prompt,
    config: { responseMimeType: "application/json" },
  }, { transportRetries: 1, parseRetries: 1 });
  const sentiment = (raw.marketSentiment || 'neutral').toLowerCase();
  const validSentiment = (['bullish', 'bearish', 'neutral'].includes(sentiment) ? sentiment : 'neutral') as 'bullish' | 'bearish' | 'neutral';
  return { summary: raw.marketSummary || '', sentiment: validSentiment };
}

export function compressForAI(dashboard: MarketDashboard): SummaryPayload {
  return {
    majorIndices: dashboard.indices.slice(0, 5).map(i => ({ name: i.name, changePct: i.changePercent })),
    topSectors: dashboard.hotSectors.slice(0, 5).map(s => ({ name: s.name, inflow: s.inflow, changePct: s.changePct })),
    northboundNet: dashboard.northbound.length > 0 ? JSON.stringify(dashboard.northbound[0]) : '无数据',
    commoditiesMove: dashboard.commodities.map(c => ({ name: c.name, changePct: 0 })),
    headlines: dashboard.news.slice(0, 3).map((n: any) => n.title || ''),
  };
}

/**
 * Fetches real-time market data (indices + commodities) directly from financial APIs.
 * No AI call required — always fast, no quota usage.
 */
export async function getMarketSnapshot(market: Market = "A-Share"): Promise<Partial<MarketOverview>> {
  // Use AbortController to cap initial load at 4s — don't let slow AkShare block the UI
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 4000);

  const [indicesData, commoditiesData] = await Promise.all([
    fetch(`/api/stock/indices?market=${market}`, { signal: controller.signal }).then(r => r.ok ? r.json() : []).catch(() => []),
    getCommoditiesData(controller.signal),
  ]);

  clearTimeout(timeout);

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

export async function getMarketOverview(config?: LLMConfig, market: Market = "A-Share", forceRefresh: boolean = false, priority: number = 0): Promise<MarketOverview> {
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

    if (existing && existing.marketSummary && existing.marketSummary.trim() !== '') {
      console.log(`[Market] Recovered ${market} overview from history:`, existing.id);
      return existing as MarketOverview;
    } else if (existing) {
      console.log(`[Market] Found history for ${market} but it lacks marketSummary. Ignoring cache.`);
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
    needsSectors ? fetch('/api/stock/sectors').then(r => (r.ok ? r.json() : { topInflows: [], topOutflows: [] })).catch(() => ({ topInflows: [], topOutflows: [] })) : Promise.resolve(null),
    needsNorthbound ? fetch('/api/stock/northbound').then(r => (r.ok ? r.json() : [])).catch(() => []) : Promise.resolve(null),
    getCommoditiesData(),
  ]);
  const prompt = getMarketOverviewPrompt(indicesData, commoditiesData, newsData, sectorsData, northboundData, history, beijingDate, now, market, language);

  let overview: MarketOverview;
  
  try {
    const raw = await generateAndParseJsonWithRetry<MarketOverview>(ai, {
      model: config?.model || DEFAULT_LLM_MODEL,
      contents: prompt,
      config: { 
        responseMimeType: "application/json"
      }
    }, { transportRetries: 1, parseRetries: 1 }, priority);

    overview = validateResponse(MarketOverviewSchema, raw, 'MarketOverview') as MarketOverview;
    
    // Force fallback if AI returned an empty summary (often happens for HK/US when data is sparse)
    if (!overview.marketSummary || overview.marketSummary.trim() === '') {
      throw new Error('AI returned empty marketSummary');
    }
  } catch (e) {
    console.warn('[Market] AI Analysis failed, falling back to Degraded Mode (Raw Data Only):', e);
    
    // Construct robust degraded overview using all fetched raw data
    overview = {
      indices: indicesData.map((d: any) => ({
        name: d.name,
        symbol: d.symbol,
        price: d.price ?? 0,
        change: d.change ?? 0,
        changePercent: d.changePercent ?? 0,
        previousClose: d.previousClose ?? 0,
      })),
      topNews: newsData || [],
      sectorAnalysis: sectorsData?.topInflows?.length ? sectorsData.topInflows.slice(0, 3).map((s: any) => ({
        name: s['行业'],
        trend: Number(s['涨跌幅']) > 0 ? '上涨' : '下跌',
        rotationStage: 'Leading',
        conclusion: `资金净流入: ${s['主力净流入-净额'] ?? 0}, 涨跌幅: ${s['涨跌幅'] ?? 0}%`,
      })) : [
        { name: '科技互联网', trend: '上涨', rotationStage: 'Leading', conclusion: '基于市场整体热度，科技板块持续受到关注。' },
        { name: '金融地产', trend: '震荡', rotationStage: 'Improving', conclusion: '宏观政策预期对金融地产板块形成支撑。' },
        { name: '消费文娱', trend: '持平', rotationStage: 'Lagging', conclusion: '消费需求复苏迹象显现，板块处于估值修复期。' }
      ],
      commodityAnalysis: (commoditiesData || []).map((d: any) => ({
        name: d.name,
        trend: d.changePercent > 0 ? '上涨' : d.changePercent < 0 ? '下跌' : '持平',
        expectation: `${d.price} (${d.changePercent}%)`,
      })),
      recommendations: sectorsData?.topInflows?.length ? sectorsData.topInflows.slice(0, 3).map((s: any) => ({
        type: 'Sector',
        name: s['行业'],
        reason: `资金大幅流入 (${formatFundFlow(s['主力净流入-净额'], 'A-Share')})`,
        riskLevel: 'Medium'
      })) : [
        { type: 'Sector', name: '人工智能产业链', reason: '全球AI资本开支增加，算力需求旺盛', riskLevel: 'High' },
        { type: 'Sector', name: '高股息/红利', reason: '市场震荡环境下的防御性配置优选', riskLevel: 'Low' }
      ],
      marketSummary: (() => {
        const upCount = (indicesData || []).filter((d: any) => (d.changePercent ?? 0) > 0).length;
        const downCount = (indicesData || []).filter((d: any) => (d.changePercent ?? 0) < 0).length;
        const totalCount = (indicesData || []).length;
        const mainIndex = (indicesData || [])[0];
        const trend = upCount > downCount ? '震荡走强' : downCount > upCount ? '承压回调' : '横盘整理';
        const mainTrend = mainIndex ? `${mainIndex.name}${mainIndex.changePercent > 0 ? '上涨' : mainIndex.changePercent < 0 ? '下跌' : '持平'}${Math.abs(mainIndex.changePercent ?? 0)}%` : '';
        const newsHint = (newsData || []).length > 0 ? `近期关注${(newsData as any[])[0]?.title?.slice(0, 20) || '热点资讯'}` : '';
        return `[实时数据] ${market}市场今日${trend}，${totalCount}个核心指数中${upCount}个上涨、${downCount}个下跌。${mainTrend}。${newsHint}。建议投资者结合实时数据关注市场动向，控制仓位风险。`;
      })(),
    } as MarketOverview;
  }

  // Anti-hallucination: enforce API indices data over AI-generated values
  if (indicesData.length > 0 && overview.indices) {
    const apiMap = new Map<string, any>(indicesData.map((idx: any) => [idx.symbol, idx]));
    let driftDetected = false;
    for (const aiIdx of overview.indices) {
      const apiIdx: any = apiMap.get(aiIdx.symbol);
      if (apiIdx && apiIdx.price != null && apiIdx.price > 0) {
        const indexDriftPct = Math.abs(aiIdx.price - apiIdx.price) / apiIdx.price;
        if (indexDriftPct > 0.02) { 
          console.warn(`[AntiHallucination] Market index ${aiIdx.symbol}: AI=${aiIdx.price}, API=${apiIdx.price}. Correcting.`);
          driftDetected = true;
        }
        aiIdx.price = Number(apiIdx.price);
        if (apiIdx.change != null) aiIdx.change = Number(apiIdx.change);
        if (apiIdx.changePercent != null) aiIdx.changePercent = Number(apiIdx.changePercent);
        if (apiIdx.previousClose != null) aiIdx.previousClose = Number(apiIdx.previousClose);
      }
    }
    if (driftDetected && overview.marketSummary && !overview.marketSummary.includes('不可用')) {
      overview.marketSummary += '\n\n⚠️ 注意：部分指数数据已由实时 API 修正。';
    }
  }

  overview.id = `market-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  overview.generatedAt = Date.now();
  overview.market = market; 
  
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

export async function getCommoditiesData(signal?: AbortSignal): Promise<any[]> {
  const now = Date.now();
  if (_commoditiesCache.expiry > now && _commoditiesCache.data.length > 0) {
    return _commoditiesCache.data;
  }
  try {
    const res = await fetch('/api/stock/commodities', signal ? { signal } : undefined);
    if (res.ok) {
      const data = await res.json();
      _commoditiesCache = { data, expiry: now + 5 * 60 * 1000 };
      return data;
    }
  } catch (e) {
    if ((e as Error).name !== 'AbortError') {
      console.warn('Commodities fetch failed:', e);
    }
  }
  return [];
}

export async function getDailyReport(marketOverview: MarketOverview, config?: LLMConfig): Promise<string> {
  const ai = createAI(config);
  const now = new Date();
  const beijingDate = getBeijingDate(now);
  const language = useConfigStore.getState().language;
  const commoditiesData = await getCommoditiesData();
  const prompt = getDailyReportPrompt(marketOverview, commoditiesData, now, beijingDate, language);

  const response = await withRetry(async () => {
    const result = await generateContentWithUsage(ai, {
      model: config?.model || DEFAULT_LLM_MODEL,
      contents: prompt,
      config: {
        tools: [{ googleSearch: {} }]
      }
    });
    return result.text;
  });

  return response;
}
