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

import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { loadGithubToken, callCopilotChatApi } from './copilotAuth.js';

// ── Types ──────────────────────────────────────────────────────────────────

export type GatewayProvider = 'github_copilot_api' | 'copilot_cli' | 'gemini' | 'openai' | 'anthropic';

export interface GatewayRequest {
  prompt: string;
  requestedModel: string;
}

export interface GatewayResponse {
  text: string;
  model: string;
  provider: GatewayProvider;
}

type LogFn = (event: string, data?: Record<string, unknown>) => void;

// ── Constants ──────────────────────────────────────────────────────────────

const CLI_TIMEOUT_MS = 30_000;     // Keep Copilot fallback responsive for interactive stock analysis
const HTTP_TIMEOUT_MS = 120_000;   // REST API calls

/** Models tried by the Copilot CLI for each logical model name (from `copilot models`) */
const CLI_MODEL_CANDIDATES: Record<string, string[]> = {
  // Prefer the empirically stable premium model first; gpt-5.4 currently times out in this environment
  copilot_auto:       ['claude-opus-4.6', 'claude-sonnet-4.6', 'gpt-5.4'],
  'gpt-5':            ['gpt-5.4', 'gpt-5.2'],
  'gpt-5.4':          ['gpt-5.4'],
  'gpt-5.2':          ['gpt-5.2'],
  'gpt-5-mini':       ['gpt-5-mini', 'gpt-5.4-mini'],
  'gpt-5.4-mini':     ['gpt-5.4-mini', 'gpt-5-mini'],
  'gpt-4.1':          ['gpt-4.1'],
  'claude-opus-4-1':  ['claude-opus-4.6', 'claude-opus-4.5'],  // old UI alias
  'claude-opus-4.6':  ['claude-opus-4.6'],
  'claude-opus-4.7':  ['claude-opus-4.7', 'claude-opus-4.6'],
  'claude-opus-4.5':  ['claude-opus-4.5'],
  'claude-sonnet-4':  ['claude-sonnet-4.6', 'claude-sonnet-4.5'],
  'claude-sonnet-4.6':['claude-sonnet-4.6'],
};

export function getGatewayCliModelCandidates(model: string): string[] {
  return CLI_MODEL_CANDIDATES[model] ?? [model];
}

/** Gemini models tried in order (fast → capable) */
const GEMINI_MODELS = [
  process.env.GEMINI_GATEWAY_MODEL,   // override via env
  'gemini-3.1-flash-lite-preview',
  'gemini-1.5-flash',
  'gemini-1.5-pro',
].filter(Boolean) as string[];

// ── GitHub Copilot API provider (direct REST, no CLI) ─────────────────────

async function tryGithubCopilotAPI(prompt: string, model: string, log: LogFn): Promise<string | null> {
  const token = loadGithubToken();
  if (!token) {
    log('gateway_copilot_api_unavailable', { reason: 'no_github_token' });
    return null;
  }

  try {
    log('gateway_copilot_api_attempt', { model });
    const text = await callCopilotChatApi(token, prompt, model);
    if (text) {
      log('gateway_copilot_api_ok', { model, length: text.length });
      return text;
    }
    log('gateway_copilot_api_empty', { model });
  } catch (err: any) {
    log('gateway_copilot_api_failed', { model, error: String(err?.message || err).slice(0, 300) });
  }

  return null;
}

// ── Copilot CLI provider ───────────────────────────────────────────────────

function findCopilotCLI(): string | null {
  const explicit = process.env.COPILOT_CLI_PATH;
  if (explicit && fs.existsSync(explicit)) return explicit;

  const wingetPath = path.join(
    process.env.LOCALAPPDATA || '',
    'Microsoft', 'WinGet', 'Packages',
    'GitHub.Copilot_Microsoft.Winget.Source_8wekyb3d8bbwe',
    'copilot.exe',
  );
  if (fs.existsSync(wingetPath)) return wingetPath;

  return null;
}

async function tryCopilotCLI(prompt: string, model: string, log: LogFn): Promise<string | null> {
  const cliPath = findCopilotCLI();
  if (!cliPath) {
    log('gateway_copilot_cli_unavailable', { reason: 'binary_not_found' });
    return null;
  }

  for (const cliModel of getGatewayCliModelCandidates(model)) {
    try {
      log('gateway_copilot_cli_attempt', { cliModel, timeoutMs: CLI_TIMEOUT_MS });
      const out = execFileSync(
        cliPath,
        ['-p', prompt, '--stream', 'off', '--silent', '--allow-all-tools', '--no-color', '--model', cliModel],
        {
          encoding: 'utf8',
          stdio: ['ignore', 'pipe', 'pipe'],
          timeout: CLI_TIMEOUT_MS,
          maxBuffer: 16 * 1024 * 1024,
        },
      );
      const text = String(out || '').trim();
      if (text) {
        log('gateway_copilot_cli_ok', { cliModel, length: text.length });
        return text;
      }
      log('gateway_copilot_cli_empty', { cliModel });
    } catch (err: any) {
      const msg = String(err?.stderr || err?.message || err);
      log('gateway_copilot_cli_failed', { cliModel, error: msg.slice(0, 300) });

      // Unrecoverable auth error — stop trying CLI models entirely
      if (
        msg.toLowerCase().includes('no authentication information found') ||
        msg.toLowerCase().includes('not logged in') ||
        msg.toLowerCase().includes('authentication required')
      ) {
        log('gateway_copilot_cli_auth_error', { hint: 'run copilot login in server terminal' });
        return null;
      }
      // Timeout or other transient error — try next model candidate
    }
  }

  return null;
}

// ── Gemini REST provider ───────────────────────────────────────────────────

async function tryGemini(prompt: string, log: LogFn): Promise<string | null> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    log('gateway_gemini_unavailable', { reason: 'no_api_key' });
    return null;
  }

  for (const model of GEMINI_MODELS) {
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

      // 429 quota exhausted — try next Gemini model
      if (res.status === 429) continue;
      // 4xx other than 429 → key issue, stop trying Gemini
      if (res.status >= 400 && res.status < 500) return null;
    } catch (err: any) {
      log('gateway_gemini_exception', { model, error: String(err?.message || err).slice(0, 200) });
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

// ── Provider chain builder ─────────────────────────────────────────────────

type ProviderEntry = { name: GatewayProvider; fn: () => Promise<string | null> };

const COPILOT_HOSTED_MODELS = new Set([
  'gpt-5',
  'gpt-5.4',
  'gpt-5.2',
  'gpt-5-mini',
  'gpt-5.4-mini',
  'gpt-4.1',
  'gpt-4.1-mini',
  'gpt-4o',
  'gpt-4o-mini',
  'o4-mini',
  'o3',
  'claude-opus-4-1',
  'claude-opus-4.5',
  'claude-opus-4.6',
  'claude-opus-4.7',
  'claude-sonnet-4',
  'claude-sonnet-4.5',
  'claude-sonnet-4.6',
  'claude-haiku-4.5',
]);

export function isCopilotHostedModel(requestedModel: string): boolean {
  const normalized = requestedModel.toLowerCase();
  return normalized.startsWith('copilot') || normalized === 'copilot_auto' || COPILOT_HOSTED_MODELS.has(normalized);
}

export function getPreferredProvider(requestedModel: string): GatewayProvider | null {
  const m = requestedModel.toLowerCase();
  if (isCopilotHostedModel(m)) return 'github_copilot_api';
  if (m.startsWith('gemini')) return 'gemini';
  if (m.startsWith('gpt-') || /^o\d/.test(m)) return 'openai';
  if (m.startsWith('claude')) return 'anthropic';
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
): ProviderEntry[] {
  const all: ProviderEntry[] = [
    { name: 'github_copilot_api', fn: () => tryGithubCopilotAPI(prompt, requestedModel, log) },
    { name: 'copilot_cli',        fn: () => tryCopilotCLI(prompt, requestedModel, log) },
    { name: 'gemini',             fn: () => tryGemini(prompt, log) },
    { name: 'openai',             fn: () => tryOpenAI(prompt, log, requestedModel) },
    { name: 'anthropic',          fn: () => tryAnthropic(prompt, log, requestedModel) },
  ];

  // Filter to providers that have credentials/capability
  const available = all.filter(({ name }) => {
    if (name === 'github_copilot_api') return !!loadGithubToken();
    if (name === 'copilot_cli')        return !!findCopilotCLI();
    if (name === 'gemini')             return !!process.env.GEMINI_API_KEY;
    if (name === 'openai')             return !!process.env.OPENAI_API_KEY;
    if (name === 'anthropic')          return !!process.env.ANTHROPIC_API_KEY;
    return false;
  });

  // Promote preferred provider to front based on model name heuristic.
  // NOTE: copilot_auto / copilot_* / known Copilot models prefer the REST API first.
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
): Promise<GatewayResponse> {
  const chain = buildProviderChain(prompt, requestedModel, log);

  if (chain.length === 0) {
    throw new Error(
      '没有可用的 LLM 提供商。请在服务端 .env 中配置 GEMINI_API_KEY、OPENAI_API_KEY 或 ANTHROPIC_API_KEY，或确保本地 Copilot CLI 已通过 copilot login 认证。',
    );
  }

  log('gateway_chain', { providers: chain.map(p => p.name), requestedModel });

  for (const { name, fn } of chain) {
    try {
      const text = await fn();
      if (text) {
        return { text, model: requestedModel, provider: name };
      }
    } catch (err: any) {
      log('gateway_provider_error', { provider: name, error: String(err?.message || err).slice(0, 300) });
    }
  }

  throw new Error(
    `所有 LLM 提供商均失败（已尝试: ${chain.map(p => p.name).join(' → ')}）。` +
    '请检查 .env 中的 API Key 配置，或确认网络可达 Gemini/OpenAI/Anthropic API。',
  );
}

/** Health snapshot: which providers are currently configured */
export function gatewayStatus(): Record<GatewayProvider, boolean> {
  return {
    github_copilot_api: !!loadGithubToken(),
    copilot_cli:        !!findCopilotCLI(),
    gemini:             !!process.env.GEMINI_API_KEY,
    openai:             !!process.env.OPENAI_API_KEY,
    anthropic:          !!process.env.ANTHROPIC_API_KEY,
  };
}
