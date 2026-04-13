import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useConfigStore } from '../../stores/useConfigStore';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    clear: vi.fn(() => { store = {}; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
  };
})();
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock });

describe('useConfigStore', () => {
  beforeEach(() => {
    localStorageMock.clear();
    useConfigStore.setState({
      tokenUsage: { 
        promptTokens: 0, 
        candidatesTokens: 0, 
        totalTokens: 0, 
        dailyTotal: 0, 
        dailyResetDate: new Date().toISOString().split('T')[0] 
      },
      availableModels: [],
      feishuWebhookUrl: '',
    });
  });

  it('should have initial token usage at zero', () => {
    const { tokenUsage } = useConfigStore.getState();
    expect(tokenUsage.promptTokens).toBe(0);
    expect(tokenUsage.candidatesTokens).toBe(0);
    expect(tokenUsage.totalTokens).toBe(0);
  });

  it('should accumulate token usage', () => {
    const { addTokenUsage } = useConfigStore.getState();
    addTokenUsage({ promptTokens: 100, candidatesTokens: 50, totalTokens: 150 });
    addTokenUsage({ promptTokens: 200, candidatesTokens: 100, totalTokens: 300 });

    const { tokenUsage } = useConfigStore.getState();
    expect(tokenUsage.promptTokens).toBe(300);
    expect(tokenUsage.candidatesTokens).toBe(150);
    expect(tokenUsage.totalTokens).toBe(450);
  });

  it('should handle partial token usage updates', () => {
    const { addTokenUsage } = useConfigStore.getState();
    addTokenUsage({ promptTokens: 50 });

    const { tokenUsage } = useConfigStore.getState();
    expect(tokenUsage.promptTokens).toBe(50);
    expect(tokenUsage.candidatesTokens).toBe(0);
    expect(tokenUsage.totalTokens).toBe(0);
  });

  it('should set and persist config', () => {
    const newConfig = { model: 'gemini-2.5-pro', apiKey: 'test-key' } as any;
    useConfigStore.getState().setConfig(newConfig);

    expect(useConfigStore.getState().config.model).toBe('gemini-2.5-pro');
    expect(useConfigStore.getState().geminiConfig.model).toBe('gemini-2.5-pro');
    expect(localStorageMock.setItem).toHaveBeenCalledWith('gemini_config', JSON.stringify(newConfig));
  });

  it('should set available models', () => {
    const models = [
      { id: 'gemini-3-flash', name: 'Gemini 3 Flash', description: 'Fast model' },
    ];
    useConfigStore.getState().setAvailableModels(models);
    expect(useConfigStore.getState().availableModels).toHaveLength(1);
    expect(useConfigStore.getState().availableModels[0].id).toBe('gemini-3-flash');
  });

  it('should set and persist feishu webhook', () => {
    useConfigStore.getState().setFeishuWebhookUrl('https://hook.example.com/v2/xxx');
    expect(useConfigStore.getState().feishuWebhookUrl).toBe('https://hook.example.com/v2/xxx');
    expect(localStorageMock.setItem).toHaveBeenCalledWith('feishu_webhook', 'https://hook.example.com/v2/xxx');
  });
});
