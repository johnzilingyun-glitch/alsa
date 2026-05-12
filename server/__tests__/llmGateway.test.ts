import { describe, expect, it } from 'vitest';
import { getPreferredProvider } from '../llmGateway';
import { resolveCopilotModel } from '../copilotAuth';

describe('llmGateway model routing', () => {
  // NOTE: isCopilotHostedModel and getGatewayCliModelCandidates were removed
  // during the BYOK migration. Provider routing is now handled exclusively
  // by getPreferredProvider.

  it('routes gemini models to gemini provider', () => {
    expect(getPreferredProvider('gemini-1.5-flash')).toBe('gemini');
    expect(getPreferredProvider('gemini-3.1-pro-preview')).toBe('gemini');
  });

  it('routes openai models to openai provider', () => {
    expect(getPreferredProvider('gpt-4o')).toBe('openai');
    expect(getPreferredProvider('o1-preview')).toBe('openai');
  });

  it('routes anthropic models to anthropic provider', () => {
    expect(getPreferredProvider('claude-sonnet-4')).toBe('anthropic');
    expect(getPreferredProvider('claude-opus-4-1')).toBe('anthropic');
  });

  it('routes deepseek models to deepseek provider', () => {
    expect(getPreferredProvider('deepseek-v4-pro')).toBe('deepseek');
    expect(getPreferredProvider('deepseek-v4-flash')).toBe('deepseek');
  });

  it('maps logical aliases to real Copilot model ids', () => {
    expect(resolveCopilotModel('gpt-5')).toBe('gpt-5.4');
    expect(resolveCopilotModel('claude-opus-4-1')).toBe('claude-opus-4.6');
    expect(resolveCopilotModel('claude-sonnet-4')).toBe('claude-sonnet-4.6');
  });
});