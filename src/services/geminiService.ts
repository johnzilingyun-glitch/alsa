import { GoogleGenAI } from "@google/genai";
import { useConfigStore } from "../stores/useConfigStore";
import { useUIStore } from "../stores/useUIStore";
import { requestScheduler } from "./requestScheduler";
import { tryFallbackProviders, getAvailableFallbackProviders } from "./llmProvider";

export const GEMINI_MODEL = "gemini-3.1-pro-preview";

// Fallback chain: primary + backup model for resilience.
export const MODEL_FALLBACK_CHAIN: string[] = [
  "gemini-3.1-pro-preview",         // Ultimate logic engine (Primary)
  "gemini-3.1-flash-lite-preview",  // High-throughput backup
  "gemini-2.0-flash-exp",           // Cutting-edge experimental fallback
  "gemini-1.5-pro",                 // Stable logic fallback
  "gemini-1.5-flash",               // Lightweight high-speed fallback
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

export const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

type ServiceMode = 'byok' | 'managed_no_key' | 'copilot_local';

function getServiceMode(config?: { serviceMode?: ServiceMode }): ServiceMode {
  const storeConfig = useConfigStore.getState().config as any;
  return config?.serviceMode || storeConfig?.serviceMode || 'byok';
}

function createCopilotBridgeClient(config?: { model?: string; serviceMode?: ServiceMode }) {
  const fallbackModel = config?.model || 'gpt-4o-mini';
  console.log('[CopilotBridge] Bridge client created with fallbackModel:', fallbackModel);
  
  return {
    models: {
      generateContent: async (params: any) => {
        const requestedModel = params?.model || fallbackModel;
        console.log('[CopilotBridge] generateContent called with model:', requestedModel);
        console.log('[CopilotBridge] Request params length:', JSON.stringify(params).length, 'bytes');
        
        const startTime = Date.now();
        const response = await fetch('/api/diagnostics/copilot/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            params,
            model: requestedModel,
          }),
        });

        const elapsed = Date.now() - startTime;
        console.log('[CopilotBridge] Response received in', elapsed, 'ms, status:', response.status);

        const payload = await response.json().catch(() => ({}));
        
        if (!response.ok || !payload?.success) {
          console.error('[CopilotBridge] ❌ Bridge error:', payload?.error || `HTTP ${response.status}`);
          throw new Error(payload?.error || `Copilot bridge failed: HTTP ${response.status}`);
        }

        console.log('[CopilotBridge] ✅ Success via', payload?.via || 'unknown', 'using model:', payload?.model);
        return payload.result;
      },
    },
  };
}

export function getApiKey(config?: { apiKey?: string; serviceMode?: ServiceMode }): string {
  const storeConfig = useConfigStore.getState().config as any;
  const serviceMode = getServiceMode(config);

  // BYOK: explicit key has highest priority.
  if (serviceMode === 'byok') {
    if (config?.apiKey) return config.apiKey;
    const storeApiKey = storeConfig?.apiKey;
    if (storeApiKey) return storeApiKey;
  }
  
  const envKey = process.env.GEMINI_API_KEY;
  const viteKey = import.meta.env.VITE_GEMINI_API_KEY;
  const apiKey = envKey || viteKey;

  if (!apiKey || apiKey.trim() === '') {
    console.error('[GeminiService] No API key found in config, store, or environment.', {
      serviceMode,
      hasEnvKey: !!envKey,
      envKeyLength: envKey?.length,
      hasViteKey: !!viteKey,
      viteKeyLength: viteKey?.length
    });
    if (serviceMode === 'managed_no_key') {
      throw new Error('当前为免 Key 托管模式，但服务端未配置 GEMINI_API_KEY。请联系管理员配置服务端密钥，或切换回自定义 Key 模式。');
    }
    throw new Error('未配置 Gemini API Key。请在设置中填写，或在 .env 文件中设置 GEMINI_API_KEY。');
  }
  return apiKey;
}

export function createAI(config?: { apiKey?: string }) {
  const serviceMode = getServiceMode(config as any);
  console.log('[GeminiService] createAI called with serviceMode:', serviceMode, 'config:', config);
  
  if (serviceMode === 'copilot_local') {
    console.log('[GeminiService] ✅ Using Copilot local bridge mode');
    return createCopilotBridgeClient(config as any);
  }

  console.log('[GeminiService] Using Gemini API mode');
  const apiKey = getApiKey(config);
  return new GoogleGenAI({ apiKey });
}

/**
 * Diagnostic function — call from browser console: testGeminiApiKey()
 * Tests the API key with a minimal request, bypassing all retry/scheduler logic.
 */
export async function testGeminiApiKey(): Promise<void> {
  try {
    const apiKey = getApiKey();
    console.log(`[DiagnosticTest] API Key: ${apiKey.substring(0, 8)}...${apiKey.substring(apiKey.length - 4)}`);
    console.log(`[DiagnosticTest] Model: ${GEMINI_MODEL}`);
    console.log(`[DiagnosticTest] Sending test request...`);

    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent?key=${apiKey}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: 'Say "ok" in one word.' }] }],
        }),
      }
    );

    const body = await res.json();
    if (res.ok) {
      console.log(`[DiagnosticTest] ✅ SUCCESS — API key works. Response:`, body?.candidates?.[0]?.content?.parts?.[0]?.text);
    } else {
      console.error(`[DiagnosticTest] ❌ FAILED — HTTP ${res.status}`, JSON.stringify(body, null, 2));
      if (res.status === 429) {
        const errorStatus = body?.error?.status;
        if (errorStatus === 'RESOURCE_EXHAUSTED') {
          console.error(`[DiagnosticTest] 📊 This is RPD (daily quota) exhaustion. Need to wait until quota resets.`);
        }
        console.error(`[DiagnosticTest] 💡 Try: 1) Wait 1 min and retry. 2) Check https://aistudio.google.com/apikey for quota usage.`);
      } else if (res.status === 400) {
        console.error(`[DiagnosticTest] 💡 API Key may be invalid or the model name is wrong.`);
      } else if (res.status === 403) {
        console.error(`[DiagnosticTest] 💡 API Key is not authorized. Check if the key is enabled for Generative Language API.`);
      }
    }
  } catch (e) {
    console.error(`[DiagnosticTest] ❌ Network error:`, e);
  }
}

// Expose to browser console for diagnostics
if (typeof window !== 'undefined') {
  (window as any).testGeminiApiKey = testGeminiApiKey;

  // Auto-run diagnostic on module load (fires once when app starts)
  setTimeout(async () => {
    try {
      const apiKey = getApiKey();
      if (!apiKey) return;

      const res = await fetch('/api/diagnostics/test-gemini', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ apiKey, model: GEMINI_MODEL }),
      });
      const result = await res.json();
      if (!result.success) {
        console.error(`[AutoDiagnostic] ❌ API test FAILED:`, result);
      } else {
        console.log(`[AutoDiagnostic] ✅ API key and model are working.`);
      }
    } catch (e) {
      // getApiKey() throws if no key configured — that's expected on first load
      console.warn(`[AutoDiagnostic] Skipped (no API key configured or server not ready).`);
    }
  }, 3000); // Wait 3s for store hydration
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
  },
  priority: number = 0
): Promise<T> {
  const transportRetries = options?.transportRetries ?? 3;
  const baseDelayMs = options?.baseDelayMs ?? 2000;
  const parseRetries = options?.parseRetries ?? 1;
  const parseDelayMs = options?.parseDelayMs ?? 1200;

  // Build fallback model list: start with the requested model, then add alternatives
  const requestedModel = params.model || GEMINI_MODEL;
  const modelsToTry = [requestedModel, ...MODEL_FALLBACK_CHAIN.filter(m => m !== requestedModel)];

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
    
    // Recovery path 1: Backend Copilot Bridge (Highly resilient)
    const { enableCopilotFallback } = useConfigStore.getState().config;
    if (enableCopilotFallback) {
      try {
        const bridge = createCopilotBridgeClient({ model: requestedModel });
        const bridgeResult = await bridge.models.generateContent({
          contents: params.contents,
          generationConfig: params.config,
        });
        const text = typeof bridgeResult === 'string' ? bridgeResult : bridgeResult?.text || '';
        if (text) {
          console.log('[ModelFallback] ✅ Recovery SUCCESS via backend gateway.');
          return parseJsonResponse<T>(text);
        }
      } catch (bridgeErr) {
        console.error('[ModelFallback] Backend gateway recovery attempt failed:', bridgeErr);
      }
    } else {
      console.info('[ModelFallback] Copilot fallback is disabled by user settings.');
    }

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

    await fetch('/api/diagnostics/logs/debug', {
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

      if (isQuota && attempt < maxRetries) {
        const waitMs = attempt === 1 ? 5000 : 10000;
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
  const firstBrace = cleaned.indexOf("{");
  const firstBracket = cleaned.indexOf("[");
  
  let start = -1;
  let opener = '';
  let closer = '';
  
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
  const serviceMode = getServiceMode(config);
  if (serviceMode === 'copilot_local') {
    return [
      {
        id: 'copilot_auto',
        name: 'Copilot Auto (Recommended)',
        description: '自动轮询本地 Copilot 模型可用性（无需在设置中填写 Gemini Key）。',
        status: 'available',
      },
      {
        id: 'gpt-5',
        name: 'Copilot Local Bridge (GPT 5.4 alias -> gpt-5)',
        description: '新一代高性能候选模型。',
        status: 'available',
      },
      {
        id: 'gpt-5-mini',
        name: 'Copilot Local Bridge (GPT 5.4 Mini alias -> gpt-5-mini)',
        description: '更快的 GPT-5 轻量候选。',
        status: 'available',
      },
      {
        id: 'claude-opus-4-1',
        name: 'Copilot Local Bridge (Claude Ops 4.6 alias -> claude-opus-4-1)',
        description: '按用户别名映射的 Claude 高性能候选。',
        status: 'available',
      },
      {
        id: 'claude-sonnet-4',
        name: 'Copilot Local Bridge (claude-sonnet-4)',
        description: '均衡速度与质量候选。',
        status: 'available',
      },
      {
        id: 'gpt-4.1-mini',
        name: 'Copilot Local Bridge (gpt-4.1-mini)',
        description: '速度与质量平衡的默认候选。',
        status: 'available',
      },
      {
        id: 'gpt-4o-mini',
        name: 'Copilot Local Bridge (gpt-4o-mini)',
        description: '高性价比候选。实际可用性取决于本机 GitHub 登录态与配额。',
        status: 'available',
      },
      {
        id: 'o4-mini',
        name: 'Copilot Local Bridge (o4-mini)',
        description: '推理型候选模型。',
        status: 'available',
      },
      {
        id: 'gpt-4.1',
        name: 'Copilot Local Bridge (gpt-4.1)',
        description: '更强推理能力，响应可能更慢。',
        status: 'available',
      },
    ];
  }

  const apiKey = getApiKey(config);
  
  const modelsToCheck = [
    { id: 'gemini-3.1-flash-lite-preview', name: 'Gemini 3.1 Flash Lite (Default)', description: 'Free Tier 最强高吞吐引擎，官方赋予 15 RPM 超高配额。' },
    { id: 'gemini-3-flash-preview', name: 'Gemini 3.0 Flash (Next-Gen)', description: '下一代核心快速模型。' },
    { id: 'gemini-1.5-flash', name: 'Gemini 1.5 Flash (Stable)', description: '高稳定性容灾备用模型。' },
    { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', description: '高稳定性容灾备用模型。' },
    { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', description: '强逻辑模型。' },
    { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro (Advanced Reasoning)', description: '极强的上下文推理，适用于极客深研。' },
    // Paid / Extreme Tier -------------------------
    { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro (Ultimate Engine)', description: '[受限 API 专属] 地表最强金融逻辑穿透引擎。' }
  ];

  // Use lightweight models.get REST call (no RPM/RPD cost) instead of generateContent("ping")
  const results: ModelInfo[] = [];

  for (const m of modelsToCheck) {
    try {
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m.id}?key=${apiKey}`);
      if (res.ok) {
        results.push({ ...m, status: 'available' });
      } else if (res.status === 404) {
        results.push({ ...m, status: 'unavailable', statusMessage: '模型不存在或已下线' });
      } else if (res.status === 429) {
        results.push({ ...m, status: 'quota_exhausted', statusMessage: '配额已耗尽，请稍后重试' });
      } else {
        results.push({ ...m, status: 'unavailable', statusMessage: `HTTP ${res.status}` });
      }
    } catch (e: any) {
      console.warn(`Model ${m.id} check failed:`, e?.message);
      results.push({ ...m, status: 'unavailable', statusMessage: e?.message || 'Network error' });
    }
  }

  if (results.every(m => m.status !== 'available')) {
    throw new Error("无可用模型 — 所有模型配额已耗尽或不可用，请稍后重试或检查计费设置。");
  }

  return results;
}
