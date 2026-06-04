import { describe, it, expect, vi, beforeEach } from 'vitest';
import { generateContentWithUsage, fetchAvailableModelsList, generateAndParseJsonWithRetry, QuotaError, ModelNotFoundError } from './geminiService';
import { useConfigStore } from '../stores/useConfigStore';
import { GoogleGenAI } from '@google/genai';
import { requestScheduler } from './requestScheduler';

// Mock requestScheduler to execute tasks immediately without delays
vi.mock('./requestScheduler', () => ({
  requestScheduler: {
    schedule: vi.fn().mockImplementation(async (task: () => Promise<any>) => task()),
    reset: vi.fn(),
  },
}));

// Mock zustand store
vi.mock('../stores/useConfigStore', () => ({
  useConfigStore: {
    getState: vi.fn(),
  },
}));

// Mock GoogleGenAI
vi.mock('./llmProvider', async () => {
  const actual = await vi.importActual('./llmProvider');
  return {
    ...actual as any,
    getAvailableFallbackProviders: vi.fn(() => []),
    tryFallbackProviders: vi.fn(),
  };
});

vi.mock('@google/genai', () => {
  return {
    GoogleGenAI: vi.fn().mockImplementation(function() {
      const generateContent = vi.fn().mockImplementation(async ({ model }) => {
        if (model === 'gemini-3-flash-preview') {
          return { text: 'ok' }; // success
        }
        if (model === 'gemini-3.1-pro-preview') {
          throw new Error('429 RESOURCE_EXHAUSTED Quota exceeded'); // fake quota error
        }
        throw new Error('404 Not Found'); // other models fail
      });
      return {
        models: { generateContent }
      };
    })
  };
});

describe('geminiService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (useConfigStore.getState as any).mockReturnValue({
      serviceStatus: 'available',
      setServiceStatus: vi.fn(),
      cooldownUntil: 0,
      setCooldownUntil: vi.fn(),
      debugMode: false,
    });
  });

  describe('generateContentWithUsage', () => {
    it('should add token usage to the store when available', async () => {
      const mockAddTokenUsage = vi.fn();
      (useConfigStore.getState as any).mockReturnValue({
        addTokenUsage: mockAddTokenUsage,
        serviceStatus: 'available',
        setServiceStatus: vi.fn(),
        cooldownUntil: 0,
        setCooldownUntil: vi.fn(),
        debugMode: false,
      });

      const mockAi = {
        models: {
          generateContent: vi.fn().mockResolvedValue({
            text: 'response',
            usageMetadata: {
              promptTokenCount: 10,
              candidatesTokenCount: 20,
              totalTokenCount: 30
            }
          })
        }
      };

      const result = await generateContentWithUsage(mockAi, { model: 'test', contents: 'hello' });
      
      expect(result.text).toBe('response');
      expect(mockAddTokenUsage).toHaveBeenCalledWith({
        promptTokens: 10,
        candidatesTokens: 20,
        totalTokens: 30
      });
    });

    it('should not break if usageMetadata is missing', async () => {
      const mockAddTokenUsage = vi.fn();
      (useConfigStore.getState as any).mockReturnValue({
        addTokenUsage: mockAddTokenUsage,
        serviceStatus: 'available',
        setServiceStatus: vi.fn(),
        cooldownUntil: 0,
        setCooldownUntil: vi.fn(),
        debugMode: false,
      });

      const mockAi = {
        models: {
          generateContent: vi.fn().mockResolvedValue({
            text: 'response no metadata'
          })
        }
      };

      const result = await generateContentWithUsage(mockAi, { model: 'test', contents: 'hello' });
      
      expect(result.text).toBe('response no metadata');
      expect(mockAddTokenUsage).not.toHaveBeenCalled();
    });
  });

  describe('fetchAvailableModelsList', () => {
    it('should return models from the backend model registry', async () => {
      const originalFetch = globalThis.fetch;
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          models: [
            { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash', description: 'Server-managed Gemini model', status: 'available' },
            { id: 'deepseek-v4-flash', name: 'DeepSeek V4 Flash', description: 'Server-managed fallback model', status: 'available' },
          ],
        }),
      }) as any;

      try {
        const availableModels = await fetchAvailableModelsList({ model: 'gemini-3.5-flash' });

        expect(globalThis.fetch).toHaveBeenCalledWith('/api/llm/models', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }));
        expect(availableModels).toHaveLength(2);
        expect(availableModels.every(m => m.status === 'available')).toBe(true);
      } finally {
        globalThis.fetch = originalFetch;
      }
    });

    it('should throw an error if the backend model registry is unavailable', async () => {
      const originalFetch = globalThis.fetch;
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => ({ success: false, error: 'model registry unavailable' }),
      }) as any;

      try {
        await expect(fetchAvailableModelsList({ model: 'gemini-3.5-flash' })).rejects.toThrow('model registry unavailable');
      } finally {
        globalThis.fetch = originalFetch;
      }
    });
  });

  describe('generateAndParseJsonWithRetry', () => {
    it('should strip responseMimeType when tools are present in params.config', async () => {
      const capturedParams: any[] = [];
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async (p: any) => {
            capturedParams.push(JSON.parse(JSON.stringify(p)));
            return { text: '{"result": "ok"}' };
          })
        }
      };

      await generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-3.1-flash-lite-preview',
        contents: 'test prompt',
        config: {
          responseMimeType: 'application/json',
          tools: [{ googleSearch: {} }]
        }
      });

      expect(capturedParams.length).toBe(1);
      const sentConfig = capturedParams[0].config;
      // responseMimeType must be stripped when tools are present
      expect(sentConfig.responseMimeType).toBeUndefined();
      expect(sentConfig.responseSchema).toBeUndefined();
      // tools must still be present
      expect(sentConfig.tools).toEqual([{ googleSearch: {} }]);
    });

    it('should keep responseMimeType when no tools are present', async () => {
      const capturedParams: any[] = [];
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async (p: any) => {
            capturedParams.push(JSON.parse(JSON.stringify(p)));
            return { text: '{"result": "ok"}' };
          })
        }
      };

      await generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-3.1-flash-lite-preview',
        contents: 'test prompt',
        config: {
          responseMimeType: 'application/json',
        }
      });

      expect(capturedParams.length).toBe(1);
      const sentConfig = capturedParams[0].config;
      expect(sentConfig.responseMimeType).toBe('application/json');
    });

    it('should strip responseMimeType when tools come via options', async () => {
      const capturedParams: any[] = [];
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async (p: any) => {
            capturedParams.push(JSON.parse(JSON.stringify(p)));
            return { text: '{"result": "ok"}' };
          })
        }
      };

      await generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-3.1-flash-lite-preview',
        contents: 'test prompt',
      }, {
        responseMimeType: 'application/json',
        tools: [{ googleSearch: {} }],
      });

      expect(capturedParams.length).toBe(1);
      const sentConfig = capturedParams[0].config;
      expect(sentConfig.responseMimeType).toBeUndefined();
      expect(sentConfig.tools).toEqual([{ googleSearch: {} }]);
    });

    it('should retry same model on transient 429 (RPM limit) and succeed', async () => {
      let callCount = 0;
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async (p: any) => {
            callCount++;
            // First call hits 429 (RPM limit), second call succeeds
            if (callCount === 1) {
              throw { message: '429 RESOURCE_EXHAUSTED', status: 429 };
            }
            return { text: '{"result": "retry_ok"}' };
          })
        }
      };

      (useConfigStore.getState as any).mockReturnValue({
        serviceStatus: 'available',
        setServiceStatus: vi.fn(),
        cooldownUntil: 0,
        setCooldownUntil: vi.fn(),
        debugMode: false,
        config: { tier: 'free' },
      });

      const result = await generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-3.1-flash-lite-preview',
        contents: 'test',
      }, { transportRetries: 2 });

      expect(result).toEqual({ result: 'retry_ok' });
      // Same model retried after brief wait
      expect(callCount).toBe(2);
    }, 15000);

    it('should throw QuotaError after persistent 429 (RPD exhaustion)', async () => {
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async () => {
            throw { message: '429 RESOURCE_EXHAUSTED', status: 429 };
          })
        }
      };

      (useConfigStore.getState as any).mockReturnValue({
        serviceStatus: 'available',
        setServiceStatus: vi.fn(),
        cooldownUntil: 0,
        setCooldownUntil: vi.fn(),
        debugMode: false,
        config: { tier: 'free' },
      });

      await expect(generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-3.1-flash-lite-preview',
        contents: 'test',
      }, { transportRetries: 2 })).rejects.toThrow(/API 服务暂时不可用|配额已耗尽/);
    }, 60000);

    it('should skip retries immediately when model has zero quota (limit: 0)', async () => {
      let callCount = 0;
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async ({ model }: any) => {
            callCount++;
            if (model === 'gemini-2.5-pro') {
              // Real Gemini error for a model with zero free-tier quota
              throw {
                message: '{"error":{"code":429,"message":"Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-2.5-pro","status":"RESOURCE_EXHAUSTED","details":[{"@type":"type.googleapis.com/google.rpc.QuotaFailure","violations":[{"quotaMetric":"generativelanguage.googleapis.com/generate_content_free_tier_requests","quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}',
                status: 429,
                name: 'ApiError',
              };
            }
            // Fallback model succeeds
            return { text: '{"result": "fallback_ok"}' };
          }),
        },
      };

      (useConfigStore.getState as any).mockReturnValue({
        serviceStatus: 'available',
        setServiceStatus: vi.fn(),
        cooldownUntil: 0,
        setCooldownUntil: vi.fn(),
        debugMode: false,
        config: { tier: 'free' },
      });

      const result = await generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-2.5-pro',
        contents: 'test',
      }, { transportRetries: 2 });

      expect(result).toEqual({ result: 'fallback_ok' });
      // gemini-2.5-pro should be called only ONCE (no retry for limit:0),
      // then fallback model called once
      expect(callCount).toBe(2);
    }, 20000);

    it('should throw model-not-found error (NOT quota) for 404 responses', async () => {
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async () => {
            throw { message: '{"error":{"code":404,"message":"Model not found","status":"NOT_FOUND"}}', status: 404, name: 'ApiError' };
          })
        }
      };

      (useConfigStore.getState as any).mockReturnValue({
        serviceStatus: 'available',
        setServiceStatus: vi.fn(),
        cooldownUntil: 0,
        setCooldownUntil: vi.fn(),
        debugMode: false,
        config: { tier: 'free' },
      });

      await expect(generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-3.1-flash-lite-preview',
        contents: 'test',
      }, { transportRetries: 2 })).rejects.toThrow(/不可用.*404/);
    });

    it('should throw original error for 400 bad request (NOT quota)', async () => {
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async () => {
            throw { message: '{"error":{"code":400,"message":"Invalid argument","status":"INVALID_ARGUMENT"}}', status: 400, name: 'ApiError' };
          })
        }
      };

      (useConfigStore.getState as any).mockReturnValue({
        serviceStatus: 'available',
        setServiceStatus: vi.fn(),
        cooldownUntil: 0,
        setCooldownUntil: vi.fn(),
        debugMode: false,
        config: { tier: 'free' },
      });

      await expect(generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-3.1-flash-lite-preview',
        contents: 'test',
      }, { transportRetries: 1 })).rejects.toThrow(/Invalid argument|INVALID_ARGUMENT/);
    });

    it('should throw API key error for 403 responses (NOT quota)', async () => {
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async () => {
            throw { message: '{"error":{"code":403,"message":"API key not valid","status":"PERMISSION_DENIED"}}', status: 403, name: 'ApiError' };
          })
        }
      };

      (useConfigStore.getState as any).mockReturnValue({
        serviceStatus: 'available',
        setServiceStatus: vi.fn(),
        cooldownUntil: 0,
        setCooldownUntil: vi.fn(),
        debugMode: false,
        config: { tier: 'free' },
      });

      await expect(generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-3.1-flash-lite-preview',
        contents: 'test',
      }, { transportRetries: 1 })).rejects.toThrow(/API key|PERMISSION_DENIED/);
    });

    it('should retry and fail gracefully for 503 server errors', async () => {
      const mockAi = {
        models: {
          generateContent: vi.fn().mockImplementation(async () => {
            throw { message: '503 Service Unavailable', status: 503 };
          })
        }
      };

      (useConfigStore.getState as any).mockReturnValue({
        serviceStatus: 'available',
        setServiceStatus: vi.fn(),
        cooldownUntil: 0,
        setCooldownUntil: vi.fn(),
        debugMode: false,
        config: { tier: 'free' },
      });

      await expect(generateAndParseJsonWithRetry(mockAi, {
        model: 'gemini-3.1-flash-lite-preview',
        contents: 'test',
      }, { transportRetries: 2, baseDelayMs: 100 })).rejects.toThrow(/暂时不可用|负载过高/);
    }, 10000);
  });
});
