/**
 * Server-side LLM fallback client.
 *
 * Browser code must never hold third-party provider keys. This module keeps the
 * previous API surface but routes fallback generation through the backend BFF.
 */

export type LLMProvider = 'server';

export interface LLMProviderConfig {
  provider: LLMProvider;
  model: string;
}

export function getAvailableFallbackProviders(): LLMProviderConfig[] {
  return [{ provider: 'server', model: 'managed-fallback' }];
}

export async function callFallbackProvider(
  config: LLMProviderConfig,
  prompt: string,
): Promise<string> {
  const response = await fetch('/api/llm/fallback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: config.model, prompt }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Backend LLM fallback error (${response.status}): ${errorText}`);
  }

  const payload = await response.json();
  return payload?.data?.text || payload?.text || '';
}

export async function tryFallbackProviders(prompt: string): Promise<string> {
  let lastError: Error | null = null;

  for (const provider of getAvailableFallbackProviders()) {
    try {
      return await callFallbackProvider(provider, prompt);
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
    }
  }

  throw new Error(`All server-side fallback providers failed. Last error: ${lastError?.message}`);
}
