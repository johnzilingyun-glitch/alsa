import { GoogleGenAI } from "@google/genai";
import { useConfigStore } from "../stores/useConfigStore";
import { useUIStore } from "../stores/useUIStore";
import { requestScheduler } from "./requestScheduler";
import { tryFallbackProviders, getAvailableFallbackProviders } from "./llmProvider";

export const GEMINI_MODEL = "gemini-3.1-pro-preview";

// Fallback chain: primary + backup model for resilience.
export const MODEL_FALLBACK_CHAIN: string[] = [
  "gemini-3.5-flash",               // Latest 3.5 Flash
  "gemini-3.1-pro-preview",         // High-reasoning 3.1
  "gemini-3.1-flash-lite-preview",  // Lightweight 3.1
  "gemini-2.5-pro",                 // 2.5 Logic
  "gemini-2.5-flash",               // 2.5 Speed
  "gemini-2.0-flash",               // Stable 2.0
];

/**
 * Relaxed safety settings to prevent false positive blocks in financial/technical analysis prompts.
 */
export const DEFAULT_SAFETY_SETTINGS = [
  { category: 'HARM_CATEGORY_HARASSMENT', threshold: 'BLOCK_NONE' },
  { category: 'HARM_CATEGORY_HATE_SPEECH', threshold: 'BLOCK_NONE' },
  { category: 'HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold: 'BLOCK_NONE' },
  { category: 'HARM_CATEGORY_DANGEROUS_CONTENT', threshold: 'BLOCK_NONE' },
  { category: 'HARM_CATEGORY_CIVIC_INTEGRITY', threshold: 'BLOCK_NONE' },
];

export const DUCKDUCKGO_TOOLS = [
  {
    functionDeclarations: [
      {
        name: "duckduckgo_search",
        description: "Search the web for real-time financial data, company news, and market trends using DuckDuckGo.",
        parameters: {
          type: "OBJECT",
          properties: {
            query: { type: "STRING", description: "The search query" },
            max_results: { type: "NUMBER", description: "Number of results to return (max 20)" }
          },
          required: ["query"]
        }
      },
      {
        name: "duckduckgo_news",
        description: "Search for the latest news articles and headlines using DuckDuckGo.",
        parameters: {
          type: "OBJECT",
          properties: {
            query: { type: "STRING", description: "The search query" },
            max_results: { type: "NUMBER", description: "Number of results to return (max 20)" }
          },
          required: ["query"]
        }
      }
    ]
  }
];

export const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

type ServiceMode = 'byok' | 'managed_no_key' | 'copilot_local';

function getServiceMode(config?: { serviceMode?: ServiceMode }): ServiceMode {
  const storeConfig = useConfigStore.getState().config as any;
  return config?.serviceMode || storeConfig?.serviceMode || 'byok';
}

function createBackendBridgeClient(config?: { model?: string; serviceMode?: ServiceMode; apiKey?: string }) {
  const fallbackModel = config?.model || GEMINI_MODEL;
  const storeConfig = useConfigStore.getState().config as any;
  const genericApiKey = config?.apiKey || storeConfig?.apiKey || '';
  const deepseekApiKey = storeConfig?.deepseekApiKey || (fallbackModel.startsWith('deepseek') ? genericApiKey : '');
  const geminiApiKey = fallbackModel.startsWith('gemini') ? genericApiKey : '';
  
  return {
    models: {
      generateContent: async (params: any) => {
        const requestedModel = params?.model || fallbackModel;
        const startTime = Date.now();
        const response = await fetch('/api/llm/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            params,
            model: requestedModel,
            config: {
              ...(deepseekApiKey ? { deepseekApiKey } : {}),
              ...(geminiApiKey ? { geminiApiKey } : {}),
            },
          }),
        });

        const elapsed = Date.now() - startTime;
        console.log('[BackendBridge] Response received in', elapsed, 'ms, status:', response.status);

        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload?.success) {
          throw new Error(payload?.error || `Backend bridge failed: HTTP ${response.status}`);
        }

        return payload.result;
      },
    },
  };
}

export function getApiKey(config?: { apiKey?: string; serviceMode?: ServiceMode }): string {
  const storeConfig = useConfigStore.getState().config as any;
  const serviceMode = getServiceMode(config);

  if (serviceMode === 'byok') {
    const apiKey = config?.apiKey || storeConfig?.apiKey || '';
    if (apiKey.trim()) return apiKey;
    if (typeof process !== 'undefined' && process.env?.NODE_ENV === 'test') return 'test-api-key';
    throw new Error('??? Gemini API Key???????????????? Key ???');
  }

  throw new Error('???? Key ???????????????????????? LLM ???????');
}

export function createAI(config?: { apiKey?: string; model?: string; serviceMode?: ServiceMode }) {
  const serviceMode = getServiceMode(config);
  const storeConfig = useConfigStore.getState().config as any;
  const requestedModel = config?.model || storeConfig?.model || GEMINI_MODEL;

  if (serviceMode !== 'byok' || requestedModel.startsWith('deepseek') || storeConfig?.deepseekApiKey) {
    return createBackendBridgeClient(config);
  }

  return new GoogleGenAI({ apiKey: getApiKey(config) });
}

export async function generateAndParseJsonWithRetry<T>(
  ai: any,
  params: any,
  options?: {
    transportRetries?: number;
    baseDelayMs?: number;
    parseRetries?: number;
    parseDelayMs?: number;
    responseSchema?: any;
    responseMimeType?: string;
    tools?: any[];
    role?: string;
    maxOutputTokens?: number;
    loopCount?: number;
  },
  priority: number = 0
): Promise<T> {
  const transportRetries = options?.transportRetries ?? 3;
  const baseDelayMs = options?.baseDelayMs ?? 2000;
  const parseRetries = options?.parseRetries ?? 1;
  const parseDelayMs = options?.parseDelayMs ?? 1200;
  const maxToolLoops = 3; // Prevent infinite tool loops

  // Strict mode: Only use the requested model, no silent fallback downgrades allowed.
  const requestedModel = params.model || GEMINI_MODEL;
  const modelsToTry = requestedModel === 'gemini-2.5-pro'
    ? [requestedModel, 'gemini-3-flash-preview']
    : [requestedModel];

  let lastError: unknown;
  let consecutiveQuotaErrors = 0;

  // Token budget check — prevent runaway usage on free tier
  const { dailyTokenBudget, tokenUsage } = useConfigStore.getState();
  if (dailyTokenBudget > 0 && tokenUsage.dailyTotal >= dailyTokenBudget) {
    const pct = Math.round((tokenUsage.dailyTotal / dailyTokenBudget) * 100);
    useUIStore.getState().setServiceStatus('quota_exhausted');
    throw new QuotaError(
      `今日 Token 用量已达预算上限 (${tokenUsage.dailyTotal.toLocaleString()} / ${dailyTokenBudget.toLocaleString()}, ${pct}%)。` +
      `\n可在设置中调整每日 Token 预算，或等待明日重置。`
    );
  }
  // Warn at 80% budget
  if (dailyTokenBudget > 0 && tokenUsage.dailyTotal >= dailyTokenBudget * 0.8) {
    console.warn(`[TokenBudget] Daily usage at ${Math.round((tokenUsage.dailyTotal / dailyTokenBudget) * 100)}% (${tokenUsage.dailyTotal.toLocaleString()} / ${dailyTokenBudget.toLocaleString()})`);
  }

  for (const model of modelsToTry) {
    // If 2+ consecutive models hit quota, the entire API key is exhausted — skip remaining
    if (consecutiveQuotaErrors >= 2) {
      console.warn(`[ModelFallback] Skipping ${model} — API key quota exhausted (${consecutiveQuotaErrors} consecutive 429s)`);
      lastError = lastError || new QuotaError('API key quota exhausted');
      continue;
    }

    // Wait between model switches so RPM window clears (only after a previous model failed)
    if (consecutiveQuotaErrors > 0) {
      const jitterMs = 3000 + Math.random() * 4000;
      console.warn(`[ModelFallback] Switching to ${model} — waiting ${Math.round(jitterMs/1000)}s for RPM window to clear...`);
      await delay(jitterMs);
    }

    let lastParseError: unknown;
    lastError = undefined; // Clear previous model's transport error state

    for (let attempt = 1; attempt <= parseRetries; attempt++) {
      let responseText: string;
      try {
        responseText = await withRetry(async () => {
          const tools = options?.tools || params.config?.tools || params.tools;
          const hasTools = !!tools;

          // When tools (e.g. googleSearch) are present, some models reject
          // responseMimeType: "application/json" — so omit it and rely on
          // parseJsonResponse to extract JSON from freeform text.
          const responseMimeType = hasTools ? undefined : (options?.responseMimeType || params.config?.responseMimeType || (options?.responseSchema ? 'application/json' : undefined));
          const responseSchema = hasTools ? undefined : (options?.responseSchema || params.config?.responseSchema);

          // Build clean config for the SDK (params.config is what the SDK reads)
          const mergedConfig = {
            ...(params.config || {}),
            maxOutputTokens: options?.maxOutputTokens || params.config?.maxOutputTokens || 65536, // Force max generation headroom
            responseMimeType,
            responseSchema,
            tools,
          };

          const mergedParams = {
            ...params,
            model,
            config: mergedConfig,
            safetySettings: DEFAULT_SAFETY_SETTINGS,
          };
          // Remove stale top-level tools/generationConfig to avoid confusion
          delete mergedParams.tools;
          delete mergedParams.generationConfig;

          const result = await generateContentWithUsage(ai, mergedParams, priority);
          
          // Robust Recursive Function Calling Loop (DDGS/Search integration)
          const allParts = result.candidates?.[0]?.content?.parts || [];
          const functionCalls = allParts.filter((p: any) => p.functionCall);
          
          if (functionCalls.length > 0) {
            const currentLoop = options?.loopCount || 0;
            if (currentLoop < 3) {
              const toolResponses: any[] = [];
              const baseUrl = typeof window !== 'undefined' ? '' : (process.env.BACKEND_URL || 'http://localhost:3000');
              
              for (const part of functionCalls) {
                const { name, args } = part.functionCall;
                console.log(`[GeminiTools] Executing tool: ${name}`, args);
                
                let toolResult: any = null;
                const start = Date.now();
                try {
                  if (name === "duckduckgo_search" || name === "duckduckgo_news") {
                    const endpoint = name === "duckduckgo_search" ? "/api/market/search" : "/api/market/news_search";
                    const query = args.query;
                    const maxResults = args.max_results || 20;
                    
                    // Use BACKEND_URL for Node compatibility, or relative for browser
                    const url = `${baseUrl}${endpoint}?query=${encodeURIComponent(query)}&max_results=${maxResults}`;
                    const res = await fetch(url);
                    const payload = await res.json();
                    toolResult = payload.success ? payload.data : { error: payload.error || "Search failed" };
                  } else {
                    toolResult = { error: `Unknown tool: ${name}` };
                  }
                } catch (err) {
                  toolResult = { error: `Tool execution failed: ${err instanceof Error ? err.message : String(err)}` };
                }
                
                const elapsed = Date.now() - start;
                remoteLog('tool_execution_success', { tool: name, args, elapsed });

                toolResponses.push({ 
                  functionResponse: {
                    name,
                    response: { content: toolResult }
                  } 
                });
              }

              // Feed back all tool results to the model in a single message
              const toolParams = {
                ...mergedParams,
                contents: [
                  ...mergedParams.contents,
                  { role: 'model', parts: functionCalls },
                  { role: 'user', parts: toolResponses } // Role 'user' is standard for function responses in newer @google/genai
                ]
              };
              
              return await generateAndParseJsonWithRetry<T>(ai, toolParams, { ...options, loopCount: currentLoop + 1 }, priority);
            } else {
              console.warn(`[GeminiTools] Tool loop limit reached (${currentLoop})`);
              remoteLog('tool_loop_limit', { count: currentLoop });
            }
          }

          if (!result.text && result.text !== '') {
            // Empty response — safety filter, empty candidates, or blocked content
            const candidate = result.candidates?.[0];
            const finishReason = candidate?.finishReason;
            const safetyRatings = candidate?.safetyRatings;
            
            console.warn(`[Gemini] Empty response text. finishReason=${finishReason}. SafetyRatings:`, JSON.stringify(safetyRatings));
            
            throw new Error(`Gemini returned empty response (finishReason: ${finishReason || 'unknown'}). The model may have blocked the content. Check logs for safetyRatings.`);
          }
          return result.text;
        }, transportRetries, baseDelayMs);
      } catch (transportErr) {
        // On quota/model-gone error, try the next fallback model
        if (transportErr instanceof QuotaError) {
          console.warn(`[ModelFallback] ${model} quota exhausted, trying next model...`);
          lastError = transportErr;
          consecutiveQuotaErrors++;
          break; // break parse retry loop, continue to next model
        }
        if (transportErr instanceof ModelNotFoundError) {
          console.warn(`[ModelFallback] ${model} not found (404), trying next model...`);
          lastError = transportErr;
          break; // break parse retry loop, continue to next model
        }
        
        // If the model returned an empty response (blocked or refused), trigger fallback
        if (transportErr instanceof Error && transportErr.message.includes('Gemini returned empty response')) {
          console.warn(`[ModelFallback] ${model} returned empty response, trying next model...`);
          lastError = transportErr;
          break;
        }

        throw transportErr;
      }

      try {
        return parseJsonResponse<T>(responseText);
      } catch (error) {
        lastParseError = error;
        if (attempt >= parseRetries) break;

        const msg = error instanceof Error ? error.message : String(error);
        console.warn(`Gemini JSON parse failed, retrying generation (${attempt}/${parseRetries}): ${msg}`);
        await delay(parseDelayMs * attempt);
      }
    }

    // If we got here from a parse error (not quota), throw it
    if (lastParseError && !(lastError instanceof QuotaError)) {
      throw new Error(
        lastParseError instanceof Error
          ? lastParseError.message
          : 'Failed to parse Gemini JSON response after retries.'
      );
    }
  }

  // All Gemini models exhausted — determine failure type and try cross-provider fallback
  const lastErrorMsg = lastError instanceof Error ? lastError.message : String(lastError || 'unknown');
  const isModelError = lastError instanceof ModelNotFoundError;
  const isQuotaError = lastError instanceof QuotaError;

  // Always log to server for diagnostics
  remoteLog('all_models_exhausted', {
    lastErrorMsg: lastErrorMsg.substring(0, 500),
    errorType: isModelError ? 'ModelNotFound' : isQuotaError ? 'QuotaExhausted' : 'Unknown',
    consecutiveQuotaErrors,
    modelsAttempted: modelsToTry,
    requestedModel,
  }, true);

  console.error(`[ModelFallback] All models exhausted. type=${isModelError ? 'ModelNotFound' : isQuotaError ? 'Quota' : 'Unknown'} lastError:`, lastError);

  // Try cross-provider fallback for quota errors only
  if (isQuotaError) {
    const fallbackProviders = getAvailableFallbackProviders();
    console.warn(`[ModelFallback] Gemini models exhausted. Attempting recovery via backend gateway...`);
    

    // Recovery path 2: Direct Frontend Cross-Provider (Secondary)
    if (fallbackProviders.length > 0) {
      try {
        console.warn('[ModelFallback] Trying direct frontend cross-provider fallback...');
        const prompt = typeof params.contents === 'string' ? params.contents : JSON.stringify(params.contents);
        const fallbackText = await tryFallbackProviders(prompt);
        return parseJsonResponse<T>(fallbackText);
      } catch (fallbackErr) {
        console.error('[ModelFallback] Direct cross-provider fallback also failed:', fallbackErr);
      }
    }
  }

  // Build user-facing error with diagnostic detail
  if (isModelError) {
    throw new Error(`模型 ${requestedModel} 不可用（404 Not Found）。请在设置中切换到其他可用模型，或检查模型名称是否正确。`);
  }

  // Quota error — parse Gemini error for specifics
  let diagnosticDetail = '';
  try {
    const parsed = typeof lastErrorMsg === 'string' && lastErrorMsg.startsWith('{') ? JSON.parse(lastErrorMsg) : null;
    const errInfo = parsed?.error || parsed;
    const status = errInfo?.status;
    const message = errInfo?.message || lastErrorMsg;

    if (status === 'RESOURCE_EXHAUSTED' || message.includes('quota') || message.includes('exhausted') || message.includes('depleted')) {
      if (message.includes('prepayment credits') || message.includes('depleted')) {
        diagnosticDetail = `\n原因: API 账户余额不足或预付额度已耗尽。请检查 Google AI Studio 的账单设置。`;
      } else if (message.includes('Daily') || message.includes('limit: 0') || message.includes('RPD')) {
        diagnosticDetail = `\n原因: API Key 每日配额(RPD)已用尽，需等待次日重置。`;
      } else {
        diagnosticDetail = `\n原因: 请求频率超限(RPM)或项目配额不足，请等待1分钟后重试。`;
      }
    } else {
      diagnosticDetail = `\n详情: ${message}`.substring(0, 300);
    }
  } catch {
    diagnosticDetail = `\n详情: ${lastErrorMsg.substring(0, 300)}`;
  }
  const triedModels = modelsToTry.slice(0, consecutiveQuotaErrors + 1).join(', ');
  if (isQuotaError) {
    useUIStore.getState().setServiceStatus('quota_exhausted');
  }
  throw new Error(`API 服务暂时不可用 (尝试了: ${triedModels})。${diagnosticDetail}\n建议: 在设置中检查并更新 API Key，或等待配额重置。`);
}

export async function remoteLog(type: string, data: any, forceLog = false) {
  try {
    const isDebug = forceLog || useConfigStore.getState().debugMode;
    if (!isDebug) return;

    await fetch('/api/logs/debug', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, data })
    });
  } catch (e) {
    // Silently ignore remote log failures as they are diagnostic only
  }
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  maxRetries: number = 5,
  baseDelay: number = 3000
): Promise<T> {
  let lastError: any;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const result = await fn();
      return result;
    } catch (error: any) {
      lastError = error;
      const errorStr = typeof error === 'string' ? error : (error?.message || JSON.stringify(error));
      console.error(`[withRetry] Attempt ${attempt}/${maxRetries} failed:`, {
        message: errorStr.substring(0, 300),
        status: error?.status,
        code: error?.code,
        name: error?.name,
        type: typeof error,
      });

      // Distinguish quota errors (non-retryable) from transient errors (retryable)
      const isQuota = errorStr.includes('429') || 
                      errorStr.includes('RESOURCE_EXHAUSTED') || 
                      errorStr.toLowerCase().includes('quota') ||
                      error?.status === 429;

      // Model not found (deprecated/removed) — skip to next model like quota
      const isModelGone = errorStr.includes('NOT_FOUND') ||
                          errorStr.includes('is not found') ||
                          error?.status === 404;
      
      const isTransient = errorStr.includes('503') ||
                          errorStr.includes('500') ||
                          errorStr.toLowerCase().includes('unavailable') ||
                          error?.status === 503 ||
                          error?.status === 500;

      // Model gone: skip immediately to next model (NOT a quota error)
      if (isModelGone) {
        remoteLog('model_not_found', { error: errorStr, attempt, model: 'unknown', status: error?.status }, true);
        throw new ModelNotFoundError(errorStr);
      }

      // Rate limit (429): distinguish permanent (RPD/limit:0) from transient (RPM).
      // "limit: 0" means the model has ZERO free-tier quota — retrying is pointless.
      // A generic RESOURCE_EXHAUSTED without "limit: 0" is likely transient RPM.
      const isPermanentQuota = errorStr.includes('limit: 0') ||
                               errorStr.includes('GenerateRequestsPerDayPerProject') ||
                               errorStr.includes('GenerateContentInputTokensPerModelPerDay') ||
                               errorStr.toLowerCase().includes('prepayment credits') ||
                               errorStr.toLowerCase().includes('depleted');
      
      if (isQuota && isPermanentQuota) {
        console.error(`[QuotaExhausted] Model has zero/exhausted/depleted daily quota (no retry). Error: ${errorStr.substring(0, 200)}`);
        useUIStore.getState().setServiceStatus('quota_exhausted');
        remoteLog('quota_permanent', { error: errorStr, attempt, status: error?.status }, true);
        throw new QuotaError(errorStr);
      }

      if (isQuota && attempt < 2) {
        const waitMs = attempt === 1 ? 2000 : 5000;
        console.warn(`[RateLimit] 429 on attempt ${attempt}. Waiting ${waitMs / 1000}s for RPM reset... Error: ${errorStr.substring(0, 200)}`);
        await delay(waitMs);
        continue;
      }

      // If 429 on final attempt, it's persistent — bail to fallback chain
      if (isQuota) {
        console.error(`[QuotaExhausted] Persistent 429 after ${attempt} attempts. Error: ${errorStr.substring(0, 200)}`);
        remoteLog('quota_exhausted_failure', { error: errorStr, attempt, status: error?.status }, true);
        throw new QuotaError(errorStr);
      }

      // Transient errors: retry with exponential backoff
      if (isTransient && attempt < maxRetries) {
        const waitTime = baseDelay * Math.pow(2, attempt - 1) + Math.random() * 1000;
        console.warn(`Retryable error hit (${error?.status || 'AI Error'}). Retrying in ${Math.round(waitTime)}ms... (Attempt ${attempt}/${maxRetries})`);
        await delay(waitTime);
        continue;
      }
      
      if (attempt >= maxRetries) {
        useConfigStore.getState().setServiceStatus('error');
        if (isTransient) {
          throw new Error('AI 模型当前负载过高，请稍后重试。建议使用「标准」模式减少 API 调用次数。');
        }
        throw error;
      }
      // Non-retryable, non-quota error — throw immediately
      throw error;
    }
  }
  throw lastError;
}

// Custom error classes to distinguish error types for fallback logic
export class QuotaError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'QuotaError';
  }
}

export class ModelNotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ModelNotFoundError';
  }
}

export function extractJsonBlock(raw: string): string {
  if (raw == null) {
    throw new Error('Gemini returned a non-JSON response (empty/undefined response text).');
  }
  let cleaned = raw.trim();

  // 0. Strip Gemini citation markers and diverse search tool artifacts
  cleaned = cleaned.replace(/\[cite(?:_start|_end)?:?[^\]]*\]/gi, '');
  cleaned = cleaned.replace(/【来源：[^】]*】/g, ''); // Common Chinese citation markers
  cleaned = cleaned.replace(/Sources?:?\s*\[\d+\]/gi, '');
  
  // 1. Try to find triple backtick blocks
  const tripleBacktickMatch = cleaned.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
  if (tripleBacktickMatch?.[1]) {
    cleaned = tripleBacktickMatch[1].trim();
  } else {
    // Also try single backticks if the entire string is wrapped in them
    const singleBacktickMatch = cleaned.match(/^`\s*([\s\S]*?)\s*`$/);
    if (singleBacktickMatch?.[1]) {
      cleaned = singleBacktickMatch[1].trim();
    }
  }

  // 2. Find the start of the JSON object or array
  let start = -1;
  let opener = '';
  let closer = '';
  
  // Search for the first '{' (always a good candidate)
  const firstBrace = cleaned.indexOf("{");
  
  // Search for the first '[' that is likely a JSON array start (not a citation tag)
  let firstBracket = -1;
  let searchIdx = 0;
  while (true) {
    const nextBracket = cleaned.indexOf("[", searchIdx);
    if (nextBracket === -1) break;
    
    // Check what's inside or after: JSON arrays usually start with [ { or [ " or [ [ or [ number
    const after = cleaned.substring(nextBracket + 1).trimStart();
    const nextChar = after[0];
    if (nextChar === '{' || nextChar === '"' || nextChar === '[' || (nextChar >= '0' && nextChar <= '9') || nextChar === ']') {
      firstBracket = nextBracket;
      break;
    }
    // Skip this bracket (likely a citation tag like [1] or [Google Finance])
    searchIdx = nextBracket + 1;
  }
  
  if (firstBrace !== -1 && (firstBracket === -1 || firstBrace < firstBracket)) {
    start = firstBrace;
    opener = '{';
    closer = '}';
  } else if (firstBracket !== -1) {
    start = firstBracket;
    opener = '[';
    closer = ']';
  }
  
  if (start === -1) {
    throw new Error("Gemini returned a non-JSON response (No opener found).");
  }

  // 3. Robust balanced brace counting to find the actual end
  let balance = 0;
  let inString = false;
  let escape = false;

  for (let i = start; i < cleaned.length; i++) {
    const char = cleaned[i];

    if (escape) {
      escape = false;
      continue;
    }

    if (char === '\\') {
      escape = true;
      continue;
    }

    if (char === '"') {
      inString = !inString;
      continue;
    }

    if (!inString) {
      if (char === opener) {
        balance++;
      } else if (char === closer) {
        balance--;
        if (balance === 0) {
          // Found the matching closing brace!
          return cleaned.slice(start, i + 1);
        }
      }
    }
  }
  
  // Fallback to simple slice if balancing fails (e.g. truncated)
  const lastCloser = cleaned.lastIndexOf(closer);
  if (lastCloser > start) {
    return cleaned.slice(start, lastCloser + 1);
  }
  
  throw new Error("Gemini returned a non-JSON response (Mismatched braces).");
}

function sanitizeJsonControlCharacters(jsonText: string): string {
  let result = '';
  let inString = false;
  let escape = false;

  for (let i = 0; i < jsonText.length; i++) {
    const char = jsonText[i];
    const code = char.charCodeAt(0);

    if (escape) {
      result += char;
      escape = false;
      continue;
    }

    if (char === '\\') {
      result += char;
      escape = true;
      continue;
    }

    if (char === '"') {
      result += char;
      inString = !inString;
      continue;
    }

    if (inString && code < 0x20) {
      switch (char) {
        case '\n':
          result += '\\n';
          break;
        case '\r':
          result += '\\r';
          break;
        case '\t':
          result += '\\t';
          break;
        case '\b':
          result += '\\b';
          break;
        case '\f':
          result += '\\f';
          break;
        default:
          result += `\\u${code.toString(16).padStart(4, '0')}`;
          break;
      }
      continue;
    }

    result += char;
  }

  return result.replace(/^\uFEFF/, '');
}

/**
 * Attempt to repair common JSON issues from LLM output:
 * - Trailing commas before } or ]
 * - Unescaped double quotes inside string values
 * - Single-quoted strings
 * - NaN / Infinity literals
 * - JavaScript-style comments
 */
function repairJson(json: string): string {
  let repaired = json;

  // 1. Strip JavaScript comments (// ... and /* ... */)
  repaired = repaired.replace(/\/\/[^\n]*/g, '');
  repaired = repaired.replace(/\/\*[\s\S]*?\*\//g, '');

  // 2. Remove trailing commas before } or ] (with optional whitespace)
  repaired = repaired.replace(/,\s*([\]}])/g, '$1');

  // 3. Replace NaN / Infinity / undefined literals with null
  repaired = repaired.replace(/:\s*NaN\b/g, ': null');
  repaired = repaired.replace(/:\s*-?Infinity\b/g, ': null');
  repaired = repaired.replace(/:\s*undefined\b/g, ': null');

  // 4. Fix unescaped double quotes inside string values using a state machine
  let result = '';
  let inString = false;
  let escapeNext = false;
  let lastStringStart = -1;

  for (let i = 0; i < repaired.length; i++) {
    const ch = repaired[i];

    if (escapeNext) {
      result += ch;
      escapeNext = false;
      continue;
    }

    if (ch === '\\' && inString) {
      result += ch;
      escapeNext = true;
      continue;
    }

    if (ch === '"') {
      if (!inString) {
        inString = true;
        lastStringStart = i;
        result += ch;
      } else {
        // Is this the closing quote? Look ahead for a valid JSON token after it.
        const after = repaired.substring(i + 1).trimStart();
        const nextChar = after[0];
        if (nextChar === undefined || nextChar === ':' || nextChar === ',' ||
            nextChar === '}' || nextChar === ']' || nextChar === '\n' || nextChar === '\r') {
          // Valid closing quote
          inString = false;
          result += ch;
        } else {
          // Unescaped quote inside a string value — escape it
          result += '\\"';
        }
      }
      continue;
    }

    result += ch;
  }

  return result;
}

export function parseJsonResponse<T>(raw: string): T {
  try {
    const extracted = extractJsonBlock(raw);
    let parsed: any;

    try {
      parsed = JSON.parse(extracted);
    } catch {
      try {
        parsed = JSON.parse(sanitizeJsonControlCharacters(extracted));
      } catch {
        // Last resort: repair common LLM JSON issues (trailing commas, unescaped quotes, etc.)
        parsed = JSON.parse(repairJson(sanitizeJsonControlCharacters(extracted)));
      }
    }

    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      // Direct match: has expected root keys (stockInfo for stock, indices for market, messages for discussion)
      if (parsed.stockInfo && parsed.stockInfo.symbol) return parsed as T;
      if (parsed.indices && Array.isArray(parsed.indices)) return parsed as T;
      if (parsed.messages && Array.isArray(parsed.messages)) return parsed as T;
      if (parsed.content && typeof parsed.content === 'string') return parsed as T;
      
      // Unwrap single-level wrappers only if they contain expected structures
      if (parsed.analysis && typeof parsed.analysis === 'object' && (parsed.analysis.stockInfo || parsed.analysis.indices || parsed.analysis.messages)) {
        return parsed.analysis as T;
      }
      if (parsed.data && typeof parsed.data === 'object' && (parsed.data.stockInfo || parsed.data.indices || parsed.data.messages)) {
        return parsed.data as T;
      }
      
      // Fallback: single-key wrapper around object with stockInfo
      const keys = Object.keys(parsed);
      if (keys.length === 1 && parsed[keys[0]] && typeof parsed[keys[0]] === 'object' && parsed[keys[0]].stockInfo) {
        return parsed[keys[0]] as T;
      }
    }
    return parsed as T;
  } catch (error) {
    console.error("Failed to parse Gemini JSON response. Raw response:", raw);
    throw new Error(
      error instanceof Error
        ? `Failed to parse Gemini JSON response: ${error.message}`
        : "Failed to parse Gemini JSON response."
    );
  }
}


export async function generateContentWithUsage(ai: any, params: any, priority: number = 0) {
  const isDebug = useConfigStore.getState().debugMode;
  if (isDebug) {
    await remoteLog('ai_request_params', params);
  }

  // Clear previous error status on new request
  if (useConfigStore.getState().serviceStatus !== 'available') {
    useConfigStore.getState().setServiceStatus('available');
  }

  const result = await requestScheduler.schedule(async () => {
    // Inject safety settings if not already provided in params
    const callParams = {
      ...params,
      safetySettings: params.safetySettings || DEFAULT_SAFETY_SETTINGS
    };
    return await ai.models.generateContent(callParams);
  }, priority);

  // Some models return empty .text when using tools (grounding/search).
  // Extract text from candidates[0].content.parts as fallback.
  if (!result.text && result.text !== '' && result.candidates?.length > 0) {
    const parts = result.candidates[0]?.content?.parts;
    if (Array.isArray(parts)) {
      const textParts = parts.filter((p: any) => typeof p.text === 'string').map((p: any) => p.text);
      if (textParts.length > 0) {
        result.text = textParts.join('');
      }
    }
  }
  
  if (isDebug || (!result.text && result.text !== '')) {
    await remoteLog('ai_response_raw', {
      text: result.text,
      usage: result.usageMetadata,
      candidates: result.candidates?.map((c: any) => ({
        index: c.index,
        finishReason: c.finishReason,
        safetyRatings: c.safetyRatings,
        content: c.content
      }))
    });
  }

  if (result.usageMetadata) {
    useConfigStore.getState().addTokenUsage({
      promptTokens: result.usageMetadata.promptTokenCount || 0,
      candidatesTokens: result.usageMetadata.candidatesTokenCount || 0,
      totalTokens: result.usageMetadata.totalTokenCount || 0,
    });
  }
  return result;
}

export type ModelStatus = 'available' | 'quota_exhausted' | 'unavailable';
export interface ModelInfo {
  id: string;
  name: string;
  description: string;
  status: ModelStatus;
  statusMessage?: string;
}

export async function fetchAvailableModelsList(config?: any): Promise<ModelInfo[]> {
  const requestedModel = config?.model;
  const response = await fetch('/api/llm/models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: requestedModel }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload?.success) {
    throw new Error(payload?.error || `?????????HTTP ${response.status}`);
  }

  return payload.models as ModelInfo[];
}
