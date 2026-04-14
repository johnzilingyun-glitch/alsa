import { describe, it, expect, beforeEach } from 'vitest';
import { initializePromptRegistry, PROMPT_NAMES, resetPromptRegistration } from '../promptRegistration';
import { getActivePrompt, getPromptMetrics, clearRegistry, recordPromptMetrics } from '../promptRegistry';

describe('promptRegistration', () => {
  beforeEach(() => {
    clearRegistry();
    resetPromptRegistration();
  });

  it('registers all prompt versions on initialization', () => {
    initializePromptRegistry();
    for (const name of Object.values(PROMPT_NAMES) as string[]) {
      expect(() => getActivePrompt(name)).not.toThrow();
    }
  });

  it('registers stock-analysis prompt', () => {
    initializePromptRegistry();
    const prompt = getActivePrompt(PROMPT_NAMES.STOCK_ANALYSIS);
    expect(prompt.name).toBe('stock-analysis');
    expect(prompt.isActive).toBe(true);
    expect(typeof prompt.template).toBe('function');
  });

  it('registers market-overview prompt', () => {
    initializePromptRegistry();
    const prompt = getActivePrompt(PROMPT_NAMES.MARKET_OVERVIEW);
    expect(prompt.name).toBe('market-overview');
  });

  it('registers discussion prompt', () => {
    initializePromptRegistry();
    const prompt = getActivePrompt(PROMPT_NAMES.DISCUSSION);
    expect(prompt.name).toBe('discussion');
  });

  it('registers chat prompt', () => {
    initializePromptRegistry();
    const prompt = getActivePrompt(PROMPT_NAMES.CHAT);
    expect(prompt.name).toBe('chat');
  });

  it('can record and retrieve metrics after registration', () => {
    initializePromptRegistry();
    recordPromptMetrics(PROMPT_NAMES.STOCK_ANALYSIS, 2500, 85, 12000, false);
    const metrics = getPromptMetrics(PROMPT_NAMES.STOCK_ANALYSIS);
    expect(metrics).toBeDefined();
    expect(metrics!.callCount).toBe(1);
    expect(metrics!.avgTokenUsage).toBe(2500);
  });

  it('is idempotent (double init does not throw)', () => {
    initializePromptRegistry();
    // Second init should not throw or duplicate
    expect(() => initializePromptRegistry()).not.toThrow();
  });
});
