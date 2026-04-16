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
    it('should return models with status based on REST API responses', async () => {
      // Mock global fetch for the models.get REST calls
      const originalFetch = globalThis.fetch;
      globalThis.fetch = vi.fn().mockImplementation(async (url: string) => {
        if (url.includes('gemini-3-flash-preview')) {
          return { ok: true, status: 200 };
        }
        if (url.includes('gemini-3.1-pro-preview')) {
          return { ok: false, status: 429 };
        }
        return { ok: false, status: 404 };
      }) as any;

      try {
        const availableModels = await fetchAvailableModelsList({ apiKey: 'test_key' });
        
        expect(availableModels.length).toBeGreaterThan(0);
        const available = availableModels.filter(m => m.status === 'available');
        expect(available.length).toBe(1);
        expect(available[0].id).toBe('gemini-3-flash-preview');
        
        const exhausted = availableModels.filter(m => m.status === 'quota_exhausted');
        expect(exhausted.length).toBe(1);
        expect(exhausted[0].id).toBe('gemini-3.1-pro-preview');
      } finally {
        globalThis.fetch = originalFetch;
      }
    });

    it('should throw an error if no models are available', async () => {
      const originalFetch = globalThis.fetch;
      globalThis.fetch = vi.fn().mockImplementation(async () => {
        return { ok: false, status: 404 };
      }) as any;

      try {
        await expect(fetchAvailableModelsList({ apiKey: 'test_key' })).rejects.toThrow('无可用模型');
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
