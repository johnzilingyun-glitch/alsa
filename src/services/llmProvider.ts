/**
 * Multi-Provider LLM Fallback
 * 
 * When all Gemini models are quota-exhausted, this module provides
 * cross-provider fallback to OpenAI or Anthropic via their REST APIs.
 * No additional SDK dependencies required.
 * 
 * API keys are read from environment variables:
 * - VITE_OPENAI_API_KEY / OPENAI_API_KEY
 * - VITE_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY
 */

export type LLMProvider = 'google' | 'openai' | 'anthropic';

export interface LLMProviderConfig {
  provider: LLMProvider;
  model: string;
  apiKey: string;
  baseUrl?: string;
}

// ── Provider detection ─────────────────────────────────────────────

function getEnvKey(name: string): string | undefined {
  try {
    return import.meta.env[`VITE_${name}`] || process.env[name];
  } catch {
    return undefined;
  }
}

export function getAvailableFallbackProviders(): LLMProviderConfig[] {
  const providers: LLMProviderConfig[] = [];

  const openaiKey = getEnvKey('OPENAI_API_KEY');
  if (openaiKey) {
    providers.push({
      provider: 'openai',
      model: 'gpt-4o-mini',
      apiKey: openaiKey,
      baseUrl: 'https://api.openai.com/v1',
    });
  }

  const anthropicKey = getEnvKey('ANTHROPIC_API_KEY');
  if (anthropicKey) {
    providers.push({
      provider: 'anthropic',
      model: 'claude-sonnet-4-20250514',
      apiKey: anthropicKey,
      baseUrl: 'https://api.anthropic.com/v1',
    });
  }

  return providers;
}

// ── OpenAI REST call ───────────────────────────────────────────────

async function callOpenAI(config: LLMProviderConfig, prompt: string): Promise<string> {
  const response = await fetch(`${config.baseUrl}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${config.apiKey}`,
    },
    body: JSON.stringify({
      model: config.model,
      messages: [
        { role: 'system', content: 'You are a professional financial analyst. Return valid JSON only.' },
        { role: 'user', content: prompt },
      ],
      temperature: 0.3,
      max_tokens: 16384,
      response_format: { type: 'json_object' },
    }),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`OpenAI API error (${response.status}): ${err}`);
  }

  const data = await response.json();
  return data.choices?.[0]?.message?.content || '';
}

// ── Anthropic REST call ────────────────────────────────────────────

async function callAnthropic(config: LLMProviderConfig, prompt: string): Promise<string> {
  const response = await fetch(`${config.baseUrl}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': config.apiKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: config.model,
      max_tokens: 16384,
      messages: [
        { role: 'user', content: `You are a professional financial analyst. Return valid JSON only.\n\n${prompt}` },
      ],
    }),
  });

  if (!response.ok) {
    const err = await response.text();
    throw new Error(`Anthropic API error (${response.status}): ${err}`);
  }

  const data = await response.json();
  return data.content?.[0]?.text || '';
}

// ── Unified fallback call ──────────────────────────────────────────

export async function callFallbackProvider(
  config: LLMProviderConfig,
  prompt: string,
): Promise<string> {
  switch (config.provider) {
    case 'openai':
      return callOpenAI(config, prompt);
    case 'anthropic':
      return callAnthropic(config, prompt);
    default:
      throw new Error(`Unsupported fallback provider: ${config.provider}`);
  }
}

/**
 * Try all available fallback providers sequentially.
 * Returns the first successful response text.
 * Throws if all providers fail.
 */
export async function tryFallbackProviders(prompt: string): Promise<string> {
  const providers = getAvailableFallbackProviders();
  
  if (providers.length === 0) {
    throw new Error('No fallback LLM providers configured. Set VITE_OPENAI_API_KEY or VITE_ANTHROPIC_API_KEY in .env');
  }

  let lastError: Error | null = null;

  for (const provider of providers) {
    try {
      console.info(`[LLM Fallback] Trying ${provider.provider}/${provider.model}...`);
      const result = await callFallbackProvider(provider, prompt);
      console.info(`[LLM Fallback] ${provider.provider} succeeded.`);
      return result;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      console.warn(`[LLM Fallback] ${provider.provider} failed:`, lastError.message);
    }
  }

  throw new Error(`All fallback providers failed. Last error: ${lastError?.message}`);
}
