/**
 * Unified LLM Gateway
 *
 * Provides a single `gatewayGenerate()` call that routes through a
 * priority chain of providers, trying each in order until one succeeds:
 *
 *   Copilot CLI  →  Gemini REST  →  OpenAI-compatible  →  Anthropic
 *
 * Provider availability is determined at call-time from env vars and
 * the local filesystem — no configuration beyond .env is required.
 *
 * Model routing heuristics (requestedModel → preferred provider):
 *   copilot_auto / copilot/* → CLI first, then rest
 *   gemini-*               → Gemini first, then rest
 *   gpt-* / o*             → OpenAI first, then rest
 *   claude-*               → Anthropic first, then rest
 */

import fs from 'fs';
import path from 'path';

// ── Types ──────────────────────────────────────────────────────────────────

export type GatewayProvider = 'gemini' | 'openai' | 'anthropic' | 'deepseek' | 'default';

export interface GatewayRequest {
  prompt: string;
  requestedModel: string;
  config?: {
    deepseekApiKey?: string;
    geminiApiKey?: string;
  };
}

export interface GatewayResponse {
  text: string;
  model: string;
  provider: GatewayProvider;
}

type LogFn = (event: string, data?: Record<string, unknown>) => void;

// ── Constants ──────────────────────────────────────────────────────────────

const HTTP_TIMEOUT_MS = 120_000;   // REST API calls


/** Gemini models tried in order (fast → capable) */
const GEMINI_MODELS = [
  process.env.GEMINI_GATEWAY_MODEL,   // override via env
  'gemini-3.5-flash',
  'gemini-3.1-pro-preview',
  'gemini-3.1-flash-lite-preview',
  'gemini-1.5-flash',
  'gemini-1.5-pro',
].filter(Boolean) as string[];


// ── Gemini REST provider ───────────────────────────────────────────────────

async function tryGemini(prompt: string, log: LogFn, requestedModel?: string, configApiKey?: string): Promise<string | null> {
  const apiKey = configApiKey || process.env.GEMINI_API_KEY;
  if (!apiKey) {
    log('gateway_gemini_unavailable', { reason: 'no_api_key' });
    return null;
  }

  // Strict mode: use the requested model if it's a Gemini model; otherwise use the first from list
  const isGeminiModel = requestedModel && requestedModel.startsWith('gemini-');
  const modelsToTry = isGeminiModel ? [requestedModel] : GEMINI_MODELS;

  for (const model of modelsToTry) {
    try {
      log('gateway_gemini_attempt', { model });
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), HTTP_TIMEOUT_MS);

      const res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
            generationConfig: { maxOutputTokens: 65536, temperature: 0.3 },
          }),
          signal: controller.signal,
        },
      );
      clearTimeout(timer);

      if (res.ok) {
        const data = await res.json() as any;
        const text: string = data?.candidates?.[0]?.content?.parts?.[0]?.text || '';
        if (text) {
          log('gateway_gemini_ok', { model, length: text.length });
          return text;
        }
        log('gateway_gemini_empty', { model });
        continue;
      }

      const errBody = await res.text().catch(() => '');
      log('gateway_gemini_http_error', { model, status: res.status, body: errBody.slice(0, 200) });

      // In strict mode, if the specific requested model fails with 429 or other error, we don't try others
      if (isGeminiModel) return null;

      if (res.status === 429) {
        if (errBody.includes('prepayment credits') || errBody.includes('depleted')) {
          log('gateway_gemini_billing_depleted', { reason: 'fatal_billing_error' });
          return null;
        }
        continue;
      }
      if (res.status >= 400 && res.status < 500) return null;
    } catch (err: any) {
      log('gateway_gemini_exception', { model, error: String(err?.message || err).slice(0, 200) });
      if (isGeminiModel) return null;
    }
  }

  return null;
}

// ── OpenAI-compatible REST provider ───────────────────────────────────────

async function tryOpenAI(prompt: string, log: LogFn, requestedModel?: string): Promise<string | null> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    log('gateway_openai_unavailable', { reason: 'no_api_key' });
    return null;
  }

  const baseUrl = (process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1').replace(/\/$/, '');
  // Use requestedModel when it's a known OpenAI model; otherwise fall back to env/default
  const isOpenAIModel = requestedModel && (requestedModel.startsWith('gpt-') || /^o\d/.test(requestedModel));
  const model = isOpenAIModel ? requestedModel : (process.env.OPENAI_MODEL || 'gpt-4o-mini');

  try {
    log('gateway_openai_attempt', { model, baseUrl });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HTTP_TIMEOUT_MS);

    const res = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: 'You are a professional financial analyst. Return valid JSON when the user asks for structured output.' },
          { role: 'user', content: prompt },
        ],
        temperature: 0.3,
        max_tokens: 16384,
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (res.ok) {
      const data = await res.json() as any;
      const text: string = data?.choices?.[0]?.message?.content || '';
      if (text) {
        log('gateway_openai_ok', { model, length: text.length });
        return text;
      }
    }

    const errBody = await res.text().catch(() => '');
    log('gateway_openai_http_error', { model, status: res.status, body: errBody.slice(0, 200) });
  } catch (err: any) {
    log('gateway_openai_exception', { model, error: String(err?.message || err).slice(0, 200) });
  }

  return null;
}

// ── Anthropic REST provider ────────────────────────────────────────────────

async function tryAnthropic(prompt: string, log: LogFn, requestedModel?: string): Promise<string | null> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    log('gateway_anthropic_unavailable', { reason: 'no_api_key' });
    return null;
  }

  // Use requestedModel when it's a known Anthropic model; otherwise fall back to env/default
  const anthropicModelMap: Record<string, string> = {
    'claude-opus-4-1': 'claude-opus-4-5',
    'claude-sonnet-4': 'claude-sonnet-4-20250514',
  };
  const isClaudeModel = requestedModel && requestedModel.startsWith('claude-');
  const model = isClaudeModel
    ? (anthropicModelMap[requestedModel!] ?? requestedModel!)
    : (process.env.ANTHROPIC_MODEL || 'claude-sonnet-4-20250514');

  try {
    log('gateway_anthropic_attempt', { model });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HTTP_TIMEOUT_MS);

    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model,
        max_tokens: 16384,
        messages: [
          {
            role: 'user',
            content: `You are a professional financial analyst. Return valid JSON when asked.\n\n${prompt}`,
          },
        ],
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (res.ok) {
      const data = await res.json() as any;
      const text: string = data?.content?.[0]?.text || '';
      if (text) {
        log('gateway_anthropic_ok', { model, length: text.length });
        return text;
      }
    }

    const errBody = await res.text().catch(() => '');
    log('gateway_anthropic_http_error', { model, status: res.status, body: errBody.slice(0, 200) });
  } catch (err: any) {
    log('gateway_anthropic_exception', { model, error: String(err?.message || err).slice(0, 200) });
  }

  return null;
}

async function tryDeepSeek(prompt: string, log: LogFn, requestedModel?: string, configApiKey?: string): Promise<string | null> {
  const apiKey = configApiKey || process.env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    log('gateway_deepseek_unavailable', { reason: 'no_api_key' });
    return null;
  }

  const model = requestedModel || 'deepseek-v4-pro';
  const isPro = model.includes('pro');

  try {
    log('gateway_deepseek_attempt', { model, isPro });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HTTP_TIMEOUT_MS);

    const res = await fetch('https://api.deepseek.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: model,
        messages: [
          { role: 'system', content: '你是一位专业的金融分析师。请按要求返回结构化的分析内容。' },
          { role: 'user', content: prompt },
        ],
        temperature: isPro ? 0.3 : 1.0, // Pro set to 0.3 for maximum rigor, Flash remains 1.0 for natural response
        max_tokens: isPro ? 16384 : 8192,
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (res.ok) {
      const data = await res.json() as any;
      const text: string = data?.choices?.[0]?.message?.content || '';
      if (text) {
        log('gateway_deepseek_ok', { model, length: text.length });
        return text;
      }
    }

    const errBody = await res.text().catch(() => '');
    log('gateway_deepseek_http_error', { model, status: res.status, body: errBody.slice(0, 200) });
  } catch (err: any) {
    log('gateway_deepseek_exception', { model, error: String(err?.message || err).slice(0, 200) });
  }

  return null;
}

// ── Default Relay provider (中转站) ─────────────────────────────────────────

async function tryDefault(prompt: string, log: LogFn, requestedModel?: string): Promise<string | null> {
  const apiKey = process.env.DEFAULT_LLM_API_KEY;
  if (!apiKey) {
    log('gateway_default_unavailable', { reason: 'no_api_key' });
    return null;
  }

  const baseUrl = (process.env.DEFAULT_LLM_BASE_URL || 'http://xbrain-dify-service-test.xiaopeng.link/llm_api').replace(/\/$/, '');
  const model = requestedModel || process.env.DEFAULT_LLM_MODEL || 'deepseek-v4-pro';

  try {
    log('gateway_default_attempt', { model, baseUrl });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HTTP_TIMEOUT_MS);

    const res = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: '你是一位专业的金融分析师。请按要求返回结构化的分析内容。' },
          { role: 'user', content: prompt },
        ],
        temperature: 0.3,
        max_tokens: 16384,
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (res.ok) {
      const data = await res.json() as any;
      const text: string = data?.choices?.[0]?.message?.content || '';
      if (text) {
        log('gateway_default_ok', { model, length: text.length });
        return text;
      }
    }

    const errBody = await res.text().catch(() => '');
    log('gateway_default_http_error', { model, status: res.status, body: errBody.slice(0, 200) });
  } catch (err: any) {
    log('gateway_default_exception', { model, error: String(err?.message || err).slice(0, 200) });
  }

  return null;
}

// ── Provider routing ───────────────────────────────────────────────────────

export function getPreferredProvider(requestedModel: string): GatewayProvider | null {
  const m = requestedModel.toLowerCase();
  
  if (m.startsWith('gemini') && process.env.GEMINI_API_KEY) return 'gemini';
  if ((m.startsWith('gpt-') || /^o\d/.test(m)) && process.env.OPENAI_API_KEY) return 'openai';
  if (m.startsWith('claude') && process.env.ANTHROPIC_API_KEY) return 'anthropic';
  if (m.startsWith('deepseek') && process.env.DEEPSEEK_API_KEY) return 'deepseek';
  
  // Route all models through xbrain by default (supports qwen, kimi, glm, etc.)
  if (process.env.DEFAULT_LLM_API_KEY) return 'default';
  
  // Fallbacks if no default API key is configured
  if (m.startsWith('gemini')) return 'gemini';
  if (m.startsWith('gpt-') || /^o\d/.test(m)) return 'openai';
  if (m.startsWith('claude')) return 'anthropic';
  if (m.startsWith('deepseek')) return 'deepseek';
  
  return null;
}

// ── Public API ─────────────────────────────────────────────────────────────

/** Default model from env — used when user has not explicitly selected a model */
export function getDefaultModel(): string {
  return process.env.DEFAULT_LLM_MODEL || 'deepseek-v4-pro';
}

/**
 * Generate a response using the specified model. No fallback/degradation:
 * - If user explicitly selects a model, only the matching provider is tried.
 * - If no model is specified, uses the default from DEFAULT_LLM_MODEL env.
 * - If the provider fails, an error is thrown (no automatic model switching).
 */
export async function gatewayGenerate(
  prompt: string,
  requestedModel: string,
  log: LogFn = () => {},
  config?: { deepseekApiKey?: string; geminiApiKey?: string }
): Promise<GatewayResponse> {
  // Resolve to default model if empty/unspecified
  const model = requestedModel || getDefaultModel();
  const provider = getPreferredProvider(model);

  if (!provider) {
    throw new Error(
      `模型 "${model}" 没有可用的提供商。请检查 .env 中的 API Key 配置。`
    );
  }

  // Build single-provider call (no chain, no degradation)
  const providerFns: Record<GatewayProvider, () => Promise<string | null>> = {
    default:    () => tryDefault(prompt, log, model),
    gemini:    () => tryGemini(prompt, log, model, config?.geminiApiKey),
    openai:    () => tryOpenAI(prompt, log, model),
    anthropic: () => tryAnthropic(prompt, log, model),
    deepseek:  () => tryDeepSeek(prompt, log, model, config?.deepseekApiKey),
  };

  const fn = providerFns[provider];
  log('gateway_call_strict', { provider, model });

  try {
    const text = await fn();
    if (text) {
      return { text, model, provider };
    }
  } catch (err: any) {
    throw new Error(
      `请求模型 "${model}" (${provider}) 失败: ${err?.message || '未知错误'}。不允许降级到其他模型。`
    );
  }

  throw new Error(
    `请求模型 "${model}" (${provider}) 未返回内容。不允许降级到其他模型。`
  );
}

/** Health snapshot: which providers are currently configured */
export function gatewayStatus(): Record<GatewayProvider, boolean> {
  return {
    default:             !!process.env.DEFAULT_LLM_API_KEY,
    gemini:             !!process.env.GEMINI_API_KEY,
    openai:             !!process.env.OPENAI_API_KEY,
    anthropic:          !!process.env.ANTHROPIC_API_KEY,
    deepseek:           !!process.env.DEEPSEEK_API_KEY,
  };
}
