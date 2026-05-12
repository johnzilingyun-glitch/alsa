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

export type GatewayProvider = 'gemini' | 'openai' | 'anthropic' | 'deepseek';

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

// ── Provider chain builder ─────────────────────────────────────────────────

type ProviderEntry = { name: GatewayProvider; fn: () => Promise<string | null> };


export function getPreferredProvider(requestedModel: string): GatewayProvider | null {
  const m = requestedModel.toLowerCase();
  if (m.startsWith('gemini')) return 'gemini';
  if (m.startsWith('gpt-') || /^o\d/.test(m)) return 'openai';
  if (m.startsWith('claude')) return 'anthropic';
  if (m.startsWith('deepseek')) return 'deepseek';
  return null;
}

/**
 * Build a prioritised provider list based on the requested model name.
 * Preferred provider comes first; remaining available providers follow as
 * fallbacks. Providers without configured credentials are skipped entirely.
 */
function buildProviderChain(
  prompt: string,
  requestedModel: string,
  log: LogFn,
  config?: { deepseekApiKey?: string; geminiApiKey?: string }
): ProviderEntry[] {
  const all: ProviderEntry[] = [
    { name: 'gemini',             fn: () => tryGemini(prompt, log, requestedModel, config?.geminiApiKey) },
    { name: 'openai',             fn: () => tryOpenAI(prompt, log, requestedModel) },
    { name: 'anthropic',          fn: () => tryAnthropic(prompt, log, requestedModel) },
    { name: 'deepseek',           fn: () => tryDeepSeek(prompt, log, requestedModel, config?.deepseekApiKey) },
  ];

  // Filter to providers that have credentials/capability
  const available = all.filter(({ name }) => {
    if (name === 'gemini')             return !!(process.env.GEMINI_API_KEY || config?.geminiApiKey);
    if (name === 'openai')             return !!process.env.OPENAI_API_KEY;
    if (name === 'anthropic')          return !!process.env.ANTHROPIC_API_KEY;
    if (name === 'deepseek')           return !!(process.env.DEEPSEEK_API_KEY || config?.deepseekApiKey);
    return false;
  });

  // Promote preferred provider to front based on model name heuristic.
  const preferredName = getPreferredProvider(requestedModel);

  if (preferredName) {
    const idx = available.findIndex(p => p.name === preferredName);
    if (idx > 0) {
      const [preferred] = available.splice(idx, 1);
      available.unshift(preferred);
    }
  }

  return available;
}

// ── Public API ─────────────────────────────────────────────────────────────

/**
 * Try each provider in priority order until one returns a non-empty response.
 * Throws only when every provider has been exhausted.
 */
export async function gatewayGenerate(
  prompt: string,
  requestedModel: string,
  log: LogFn = () => {},
  config?: { deepseekApiKey?: string; geminiApiKey?: string }
): Promise<GatewayResponse> {
  const preferredProvider = getPreferredProvider(requestedModel);
  const chain = buildProviderChain(prompt, requestedModel, log, config);

  // If deepseek key is present, and no explicit model is gemini/claude/gpt, we can prefer deepseek
  let finalChain = chain;
  if (config?.deepseekApiKey && !preferredProvider) {
    const dsIdx = finalChain.findIndex(p => p.name === 'deepseek');
    if (dsIdx > -1) {
      const [ds] = finalChain.splice(dsIdx, 1);
      finalChain.unshift(ds);
    } else {
       finalChain.unshift({ name: 'deepseek', fn: () => tryDeepSeek(prompt, log, requestedModel, config.deepseekApiKey) });
    }
  }

  const strictChain = preferredProvider 
    ? finalChain.filter(p => p.name === preferredProvider)
    : finalChain;

  if (strictChain.length === 0) {
    throw new Error(
      `模型 "${requestedModel}" 没有可用的提供商。请检查 .env 中的 API Key 配置。`
    );
  }

  log('gateway_chain_strict', { providers: strictChain.map(p => p.name), requestedModel });

  let lastErr: any = null;
  for (const { name, fn } of strictChain) {
    try {
      const text = await fn();
      if (text) {
        return { text, model: requestedModel, provider: name };
      }
    } catch (err: any) {
      lastErr = err;
      log('gateway_provider_error', { provider: name, error: String(err?.message || err).slice(0, 300) });
      // In strict mode, we don't fall back to other *providers* if the primary one fails with a terminal error
      if (preferredProvider) break; 
    }
  }

  throw new Error(
    `请求模型 "${requestedModel}" 失败。原因: ${lastErr?.message || '提供商未返回内容'}。` +
    '（已启用严格模式，禁止自动降级/切换模型）'
  );
}

/** Health snapshot: which providers are currently configured */
export function gatewayStatus(): Record<GatewayProvider, boolean> {
  return {
    gemini:             !!process.env.GEMINI_API_KEY,
    openai:             !!process.env.OPENAI_API_KEY,
    anthropic:          !!process.env.ANTHROPIC_API_KEY,
    deepseek:           !!process.env.DEEPSEEK_API_KEY,
  };
}
