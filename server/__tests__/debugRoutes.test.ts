import { describe, expect, it } from 'vitest';
import { buildGithubTokenCandidates, getCliModelCandidates, isBadCredentialsError, normalizeCopilotModel } from '../debugRoutes';

describe('debugRoutes token recovery helpers', () => {
  it('builds token candidates in priority order and deduplicates', () => {
    const env = {
      COPILOT_GITHUB_TOKEN: 'token-a',
      GH_TOKEN: 'token-b',
      GITHUB_TOKEN: 'token-a',
    } as NodeJS.ProcessEnv;

    const tokens = buildGithubTokenCandidates(env, 'token-c');
    expect(tokens).toEqual(['token-a', 'token-b', 'token-c']);
  });

  it('filters empty token values', () => {
    const env = {
      COPILOT_GITHUB_TOKEN: '   ',
      GH_TOKEN: '',
      GITHUB_TOKEN: 'token-z',
    } as NodeJS.ProcessEnv;

    const tokens = buildGithubTokenCandidates(env, null);
    expect(tokens).toEqual(['token-z']);
  });

  it('recognizes bad credentials across common variants', () => {
    expect(isBadCredentialsError(401, 'Unauthorized')).toBe(true);
    expect(isBadCredentialsError(400, 'Bad credentials')).toBe(true);
    expect(isBadCredentialsError(403, 'invalid token')).toBe(true);
    expect(isBadCredentialsError(502, 'upstream timeout')).toBe(false);
  });

  it('uses fast CLI model sequence for auto mode', () => {
    expect(getCliModelCandidates('copilot_auto')).toEqual(['claude-opus-4.6', 'claude-sonnet-4.6', 'gpt-5.4']);
  });

  it('uses requested model for non-auto mode', () => {
    expect(getCliModelCandidates('claude-opus-4-1')).toEqual(['claude-opus-4-1']);
  });

  it('normalizes modern Copilot UI aliases to gateway model ids', () => {
    expect(normalizeCopilotModel('gpt-5')).toBe('gpt-5.4');
    expect(normalizeCopilotModel('gpt-5.4')).toBe('gpt-5.4');
    expect(normalizeCopilotModel('claude-opus-4-1')).toBe('claude-opus-4.6');
    expect(normalizeCopilotModel('claude-sonnet-4')).toBe('claude-sonnet-4.6');
  });
});
