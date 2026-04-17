import { describe, expect, it } from 'vitest';
import { getGatewayCliModelCandidates, getPreferredProvider, isCopilotHostedModel } from '../llmGateway';
import { resolveCopilotModel } from '../copilotAuth';

describe('llmGateway model routing', () => {
  it('keeps premium Copilot models on the Copilot provider path', () => {
    expect(isCopilotHostedModel('gpt-5.4')).toBe(true);
    expect(isCopilotHostedModel('claude-opus-4.6')).toBe(true);
    expect(isCopilotHostedModel('claude-sonnet-4.6')).toBe(true);
    expect(getPreferredProvider('gpt-5.4')).toBe('github_copilot_api');
    expect(getPreferredProvider('claude-opus-4.6')).toBe('github_copilot_api');
    expect(getPreferredProvider('claude-sonnet-4.6')).toBe('github_copilot_api');
  });

  it('uses premium models first for auto CLI fallback', () => {
    expect(getGatewayCliModelCandidates('copilot_auto')).toEqual(['claude-opus-4.6', 'claude-sonnet-4.6', 'gpt-5.4']);
  });

  it('maps logical aliases to real Copilot model ids', () => {
    expect(resolveCopilotModel('gpt-5')).toBe('gpt-5.4');
    expect(resolveCopilotModel('claude-opus-4-1')).toBe('claude-opus-4.6');
    expect(resolveCopilotModel('claude-sonnet-4')).toBe('claude-sonnet-4.6');
  });
});