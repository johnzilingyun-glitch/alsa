import { describe, expect, it } from 'vitest';
import { getPreferredProvider } from '../llmGateway';

describe('DeepSeek Integration Routing', () => {
  // NOTE: isCopilotHostedModel was removed during the BYOK migration.
  // The routing now uses getPreferredProvider which is the canonical way
  // to determine which provider handles a model.

  it('correctly assigns deepseek provider for deepseek models', () => {
    expect(getPreferredProvider('deepseek-v4-pro')).toBe('deepseek');
    expect(getPreferredProvider('deepseek-v4-flash')).toBe('deepseek');
  });

  it('does not assign deepseek provider for non-deepseek models', () => {
    expect(getPreferredProvider('gemini-1.5-flash')).toBe('gemini');
    expect(getPreferredProvider('gpt-4o')).toBe('openai');
    expect(getPreferredProvider('claude-sonnet-4')).toBe('anthropic');
  });
});
