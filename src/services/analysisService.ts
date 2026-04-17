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

export async function analyzeStock(symbol: string, market: Market, config?: GeminiConfig): Promise<StockAnalysis> {
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

  const language = useConfigStore.getState().language;
  const commoditiesData = await getCommoditiesData();
  
  // Pre-fetch ticker-specific news to feed the AI context
  const newsRes = await fetch(`/api/stock/news?symbol=${encodeURIComponent(symbol)}&market=${market}`).catch(() => null);
  const newsData = newsRes && newsRes.ok ? await newsRes.json() : [];

  const prompt = getAnalyzeStockPrompt(symbol, resolvedMarket, realtimeData, commoditiesData, newsData, history, beijingDate, beijingShortDate, now, language);

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
  let analysis = validateResponse(StockAnalysisSchema, raw, 'StockAnalysis') as StockAnalysis;
  
  // Anti-hallucination: multi-field drift detection and correction re-analysis
  if (realtimeData?.price != null) {
    const { hasDrift, correctedData } = detectDrift(analysis, realtimeData, commoditiesData);

    if (hasDrift) {
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
        analysis = validateResponse(StockAnalysisSchema, correctedRaw, 'StockAnalysis (corrected)') as StockAnalysis;
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

  analysis.id = `stock-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  
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
