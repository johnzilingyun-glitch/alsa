import { createAI, withRetry, generateContentWithUsage, GEMINI_MODEL, generateAndParseJsonWithRetry } from "./geminiService";
import { useConfigStore } from "../stores/useConfigStore";
import { getAnalyzeStockPrompt, getChatMessagePrompt, getStockReportPrompt, getDiscussionReportPrompt, getChatReportPrompt, getCorrectionPrompt, getTranslationPrompt } from "./prompts";
import { Market, StockAnalysis, AgentMessage, Scenario, AgentDiscussion, GeminiConfig } from "../types";
import { getHistoryContext, saveAnalysisToHistory } from "./adminService";
import { getBeijingDate } from "./dateUtils";
import { getCommoditiesData } from "./marketService";
import { calculateQualityScore } from "./dataQualityService";
import { StockAnalysisSchema, validateResponse } from "./schemas";
import { detectDrift, enforceGroundTruth } from "./driftDetection";
import { getBrainContext } from "./brainService";

export async function analyzeStock(
  symbol: string, 
  market: Market, 
  config?: GeminiConfig,
  onStatus?: (status: string) => void
): Promise<StockAnalysis> {
  const language = useConfigStore.getState().language;
  const isChinese = language === 'zh-CN';

  onStatus?.(isChinese ? "正在采集实时市场行情数据..." : "Extracting real-time market data...");
  const ai = createAI(config);
  const history = await getHistoryContext();
  const now = new Date();
  const beijingDate = getBeijingDate(now);
  const beijingShortDate = beijingDate.split(/[-/]/).slice(1).join('/');

  const isDebug = useConfigStore.getState().debugMode;
  const res = await fetch(`/api/stock/realtime?symbol=${encodeURIComponent(symbol)}&market=${market}${isDebug ? '&debug=true' : ''}`);
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(errData.error || `无法获取股票信息，请检查代码或拼写。`);
  }
  const data = await res.json();
  const realtimeData = data.resolvedMarket ? data : data;
  const resolvedMarket = data.resolvedMarket || market;

  onStatus?.(isChinese ? "正在并行聚合全球宏观、记忆与舆情数据..." : "Parallelizing macro, memory & sentiment aggregation...");
  
  const [commoditiesData, brainContext, newsData] = await Promise.all([
    getCommoditiesData(),
    getBrainContext(symbol),
    fetch(`/api/stock/news?symbol=${encodeURIComponent(symbol)}&market=${market}`)
      .then(res => res.ok ? res.json() : [])
      .catch(() => [])
  ]);

  onStatus?.(isChinese ? "正在拉取龙虎榜、两融与最新公告..." : "Fetching LHB, Margin & Announcements...");
  const [lhbRes, marginRes, noticesRes, socialRes] = await Promise.all([
    fetch(`/api/stock/lhb?symbol=${encodeURIComponent(symbol)}`).catch(() => null),
    fetch(`/api/stock/margin?symbol=${encodeURIComponent(symbol)}`).catch(() => null),
    fetch(`/api/stock/announcements?symbol=${encodeURIComponent(symbol)}`).catch(() => null),
    fetch(`/api/market/social-trends`).catch(() => null)
  ]);
  
  const extendedMarketData = {
    lhb: lhbRes && lhbRes.ok ? await lhbRes.json() : null,
    margin: marginRes && marginRes.ok ? await marginRes.json() : null,
    notices: noticesRes && noticesRes.ok ? await noticesRes.json() : null,
    socialTrends: socialRes && socialRes.ok ? await socialRes.json() : null
  };

  onStatus?.(isChinese ? "深度研判引擎正在思考中..." : "Deep Reasoning Engine is thinking...");
  const prompt = getAnalyzeStockPrompt(
    symbol, 
    resolvedMarket, 
    realtimeData, 
    commoditiesData, 
    newsData, 
    history, 
    beijingDate, 
    beijingShortDate, 
    now, 
    language, 
    extendedMarketData,
    brainContext // New parameter
  );

  const raw = await generateAndParseJsonWithRetry<StockAnalysis>(
    ai,
    {
      model: config?.model || GEMINI_MODEL,
      contents: prompt,
      config: {
        tools: [{ googleSearch: {} }]
      }
    },
    {
      transportRetries: 2,
      baseDelayMs: 2500,
      parseRetries: 1,
      parseDelayMs: 1200,
    }
  );

  // Pre-validation hardening: Ensure stockInfo exists and has ground truth
  const sanitizedRaw = {
    ...raw,
    stockInfo: {
      ...(raw?.stockInfo || {}),
      symbol: realtimeData?.symbol || symbol,
      name: realtimeData?.name || raw?.stockInfo?.name || symbol,
      price: realtimeData?.price ?? raw?.stockInfo?.price ?? 0,
      change: realtimeData?.change ?? raw?.stockInfo?.change ?? 0,
      changePercent: realtimeData?.changePercent ?? raw?.stockInfo?.changePercent ?? 0,
      market: resolvedMarket,
      currency: realtimeData?.currency || raw?.stockInfo?.currency || 'CNY',
      lastUpdated: realtimeData?.lastUpdated || raw?.stockInfo?.lastUpdated || new Date().toISOString(),
      previousClose: realtimeData?.previousClose ?? raw?.stockInfo?.previousClose ?? 0,
    }
  };

  let analysis = validateResponse(StockAnalysisSchema, sanitizedRaw, 'StockAnalysis') as StockAnalysis;
  
  // Anti-hallucination: multi-field drift detection and correction re-analysis
  if (realtimeData?.price != null) {
    const { hasDrift, correctedData } = detectDrift(analysis, realtimeData, commoditiesData);

    if (hasDrift) {
      onStatus?.(isChinese ? "检测到数据偏差，正在进行逻辑重构..." : "Drift detected. Re-reasoning logic...");
      const correctionPrompt = getCorrectionPrompt(analysis, correctedData, language);
      try {
        const correctedRaw = await generateAndParseJsonWithRetry<StockAnalysis>(
          ai,
          {
            model: config?.model || GEMINI_MODEL,
            contents: correctionPrompt,
            config: { responseMimeType: "application/json" }
          },
          { transportRetries: 2, baseDelayMs: 2000, parseRetries: 1, parseDelayMs: 1000 }
        );
        
        const sanitizedCorrection = {
          ...correctedRaw,
          stockInfo: {
            ...(correctedRaw?.stockInfo || analysis.stockInfo),
            price: correctedData.price ?? analysis.stockInfo.price,
            change: correctedData.change ?? analysis.stockInfo.change,
            changePercent: correctedData.changePercent ?? analysis.stockInfo.changePercent,
            previousClose: correctedData.previousClose ?? analysis.stockInfo.previousClose,
          }
        };
        
        analysis = validateResponse(StockAnalysisSchema, sanitizedCorrection, 'StockAnalysis (corrected)') as StockAnalysis;
        console.log(`[AntiHallucination] Correction re-analysis completed successfully`);
      } catch (correctionErr) {
        console.warn(`[AntiHallucination] Correction re-analysis failed, falling back to field override:`, correctionErr);
      }
    }

    // Always enforce API ground truth for core trading fields (safety net)
    enforceGroundTruth(analysis, realtimeData);
  }

  // Populate technical indicators if present in realtimeData
  if (realtimeData?.technicalIndicators) {
    analysis.technicalIndicators = realtimeData.technicalIndicators;
    if (analysis.stockInfo) {
      analysis.stockInfo.technicalIndicators = realtimeData.technicalIndicators;
    }
  }

  // Calculate and associate data quality metadata
  analysis.dataQuality = calculateQualityScore(analysis.stockInfo);
  analysis.stockInfo.dataQuality = analysis.dataQuality;

  onStatus?.(isChinese ? "研报正在定稿..." : "Finalizing report...");
  analysis.id = `stock-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  analysis.extendedMarketData = extendedMarketData;
  
  return analysis;
}

export async function sendChatMessage(userMessage: string, analysis: StockAnalysis, config?: GeminiConfig): Promise<string> {
  const ai = createAI(config);
  const commoditiesData = await getCommoditiesData();
  const language = useConfigStore.getState().language;
  const prompt = getChatMessagePrompt(userMessage, analysis, commoditiesData, language);

  const response = await withRetry(async () => {
    const result = await generateContentWithUsage(ai, {
      model: config?.model || GEMINI_MODEL,
      contents: prompt
    });
    return result.text;
  });

  return response;
}

export async function getStockReport(analysis: StockAnalysis, config?: GeminiConfig): Promise<string> {
  const ai = createAI(config);
  const language = useConfigStore.getState().language;
  const prompt = getStockReportPrompt(analysis, language);

  const response = await withRetry(async () => {
    const result = await generateContentWithUsage(ai, {
      model: config?.model || GEMINI_MODEL,
      contents: prompt
    });
    return result.text;
  });

  return response;
}

export async function getChatReport(stockName: string, chatHistory: { role: string; content: string }[], config?: GeminiConfig): Promise<string> {
  const ai = createAI(config);
  const language = useConfigStore.getState().language;
  const prompt = getChatReportPrompt(stockName, chatHistory, language);

  const response = await withRetry(async () => {
    const result = await generateContentWithUsage(ai, {
      model: config?.model || GEMINI_MODEL,
      contents: prompt
    });
    return result.text;
  });

  return response;
}

export async function getDiscussionReport(
  analysis: StockAnalysis, 
  discussion: AgentMessage[], 
  scenarios?: Scenario[], 
  backtestResult?: any,
  config?: GeminiConfig
): Promise<string> {
  const ai = createAI(config);
  const language = useConfigStore.getState().language;
  const commoditiesData = await getCommoditiesData();
  const prompt = getDiscussionReportPrompt(analysis, discussion, commoditiesData, scenarios ?? [], backtestResult, language);

  const response = await withRetry(async () => {
    const result = await generateContentWithUsage(ai, {
      model: config?.model || GEMINI_MODEL,
      contents: prompt
    });
    return result.text;
  });

  return response;
}

export async function translateAnalysis(analysis: StockAnalysis, targetLanguage: string, config?: GeminiConfig): Promise<StockAnalysis> {
  const ai = createAI(config);
  const prompt = getTranslationPrompt(targetLanguage, analysis, 'analysis');

  try {
    const translatedRaw = await generateAndParseJsonWithRetry<StockAnalysis>(
      ai,
      {
        model: config?.model || GEMINI_MODEL,
        contents: prompt,
        config: { responseMimeType: "application/json" }
      },
      {
        transportRetries: 2,
        baseDelayMs: 2000,
        parseRetries: 1,
        parseDelayMs: 1000,
      }
    );
    
    // Validate the translated schema, but be slightly more lenient in case the AI missed a field 
    // we'll merge it with the original to ensure structural integrity
    const translated = validateResponse(StockAnalysisSchema, translatedRaw, 'TranslatedAnalysis') as StockAnalysis;
    
    return {
      ...analysis,
      ...translated,
      id: analysis.id // Keep original ID
    };
  } catch (err) {
    console.error(`[TranslationService] Failed to translate analysis:`, err);
    throw err;
  }
}
