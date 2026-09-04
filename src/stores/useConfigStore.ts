import { create } from 'zustand';
import { LLMConfig } from '../types';

function getWeekIdentifier(d: Date) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return date.getUTCFullYear() + '-W' + Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
}

interface ConfigState {
  llmConfig: LLMConfig;
  setLLMConfig: (config: LLMConfig) => void;
  config: LLMConfig;
  setConfig: (config: LLMConfig) => void;
  tokenUsage: {
    promptTokens: number;
    candidatesTokens: number;
    totalTokens: number;
    dailyTotal: number;       // Tokens used today
    dailyResetDate: string;   // YYYY-MM-DD of current tracking day
    weeklyTotal: number;      // Tokens used this week
    weeklyResetDate: string;  // YYYY-Www of current tracking week
    monthlyTotal: number;     // Tokens used this month
    monthlyResetDate: string; // YYYY-MM of current tracking month
  };
  addTokenUsage: (usage: { promptTokens?: number, candidatesTokens?: number, totalTokens?: number }) => void;
  resetTokenUsage: () => void;
  /** Daily token budget (0 = unlimited). Free tier default: 900,000 (90% of 1M daily limit). */
  dailyTokenBudget: number;
  setDailyTokenBudget: (budget: number) => void;
  availableModels: { id: string, name: string, description: string, status?: string, statusMessage?: string }[];
  setAvailableModels: (models: { id: string, name: string, description: string, status?: string, statusMessage?: string }[]) => void;
  feishuWebhookUrl: string;
  setFeishuWebhookUrl: (webhook: string) => void;
  debugMode: boolean;
  setDebugMode: (enabled: boolean) => void;
  serviceStatus: 'available' | 'quota_exhausted' | 'error';
  setServiceStatus: (status: 'available' | 'quota_exhausted' | 'error') => void;
  lastErrorStatus: string | null;
  setLastErrorStatus: (status: string | null) => void;
  language: 'en' | 'zh-CN';
  setLanguage: (lang: 'en' | 'zh-CN') => void;
  cooldownUntil: number;
  setCooldownUntil: (until: number) => void;
}

export const useConfigStore = create<ConfigState>((set) => {
  const initialConfig = (() => {
    try {
      let saved = localStorage.getItem('llm_config');
      if (!saved) {
        // Fallback to legacy key to migrate users' configs
        saved = localStorage.getItem('gemini_config');
        if (saved) {
          localStorage.setItem('llm_config', saved); // Migrate to new key
        }
      }
      const parsed = saved ? JSON.parse(saved) : { model: 'minimax/minimax-m3:free' };
      // Migrate away from the removed free-tier model (tencent/hy3:free) for
      // users who previously saved it to localStorage.
      if (parsed?.model === 'tencent/hy3:free') {
        parsed.model = 'minimax/minimax-m3:free';
        try { localStorage.setItem('llm_config', JSON.stringify(parsed)); } catch { /* ignore */ }
      }
      return parsed;
    } catch (e) {
      console.error('Failed to parse config from localStorage:', e);
      return { model: 'minimax/minimax-m3:free' };
    }
  })();

  const initialTokenUsage = (() => {
    const now = new Date();
    const today = now.toISOString().split('T')[0];
    const thisMonth = now.toISOString().slice(0, 7);
    const thisWeek = getWeekIdentifier(now);

    const defaultUsage = {
      promptTokens: 0,
      candidatesTokens: 0,
      totalTokens: 0,
      dailyTotal: 0,
      dailyResetDate: today,
      weeklyTotal: 0,
      weeklyResetDate: thisWeek,
      monthlyTotal: 0,
      monthlyResetDate: thisMonth,
    };

    try {
      const saved = localStorage.getItem('token_usage');
      if (saved) {
        const parsed = JSON.parse(saved);
        // Ensure at least dailyResetDate exists
        if (parsed.dailyResetDate) {
          const isNewDay = parsed.dailyResetDate !== today;
          const isNewWeek = parsed.weeklyResetDate !== thisWeek;
          const isNewMonth = parsed.monthlyResetDate !== thisMonth;

          const updated = {
            promptTokens: Number(parsed.promptTokens) || 0,
            candidatesTokens: Number(parsed.candidatesTokens) || 0,
            totalTokens: Number(parsed.totalTokens) || 0,
            dailyTotal: isNewDay ? 0 : (Number(parsed.dailyTotal) || 0),
            dailyResetDate: today,
            weeklyTotal: isNewWeek ? 0 : (Number(parsed.weeklyTotal) || 0),
            weeklyResetDate: thisWeek,
            monthlyTotal: isNewMonth ? 0 : (Number(parsed.monthlyTotal) || 0),
            monthlyResetDate: thisMonth,
          };
          localStorage.setItem('token_usage', JSON.stringify(updated));
          return updated;
        }
      }
    } catch (e) {
      console.error('Failed to parse token_usage from localStorage:', e);
    }
    return defaultUsage;
  })();

  // Fetch initial config from backend
  try {
    if (typeof fetch !== 'undefined') {
      const fetchPromise = fetch('/api/analysis/settings');
      if (fetchPromise && typeof fetchPromise.then === 'function') {
        fetchPromise
          .then(res => {
            if (!res.ok) throw new Error('Settings API not available');
            return res.json();
          })
          .then(data => {
            if (data && data.config) {
              set((state) => ({
                config: data.config,
                ...(data.tokenUsage ? { tokenUsage: data.tokenUsage } : {}),
                ...(data.availableModels ? { availableModels: data.availableModels } : {}),
              }));
            }
          })
          .catch(e => console.warn('Using local settings only (backend settings API unavailable)'));
      }
    }
  } catch (e) {
    console.warn('Fetch failed or not supported in this environment');
  }

  return {
    llmConfig: initialConfig,
    config: initialConfig,
    tokenUsage: initialTokenUsage,
    availableModels: [],
    setAvailableModels: (models) => set({ availableModels: models }),
    dailyTokenBudget: (() => {
      try {
        const saved = localStorage.getItem('daily_token_budget');
        return saved ? Number(saved) : 900_000;
      } catch {
        console.warn('[useConfigStore] Failed to load daily token budget:');
        return 900_000;
      }
    })(),
    setDailyTokenBudget: (budget) => {
      localStorage.setItem('daily_token_budget', String(budget));
      set({ dailyTokenBudget: budget });
    },
    addTokenUsage: (usage) => set((state) => {
      const now = new Date();
      const today = now.toISOString().split('T')[0];
      const thisMonth = now.toISOString().slice(0, 7);
      const thisWeek = getWeekIdentifier(now);
      
      const currentUsage = state.tokenUsage || initialTokenUsage;
      const isNewDay = currentUsage.dailyResetDate !== today;
      const isNewMonth = currentUsage.monthlyResetDate !== thisMonth;
      // Force reset weekly total when a new month starts, so that weekly usage 
      // never exceeds monthly usage (e.g. when a calendar week spans two months)
      const isNewWeek = currentUsage.weeklyResetDate !== thisWeek || isNewMonth;
      
      const added = usage.totalTokens || 0;
      const newTokenUsage = {
        promptTokens: (currentUsage.promptTokens || 0) + (usage.promptTokens || 0),
        candidatesTokens: (currentUsage.candidatesTokens || 0) + (usage.candidatesTokens || 0),
        totalTokens: (currentUsage.totalTokens || 0) + (usage.totalTokens || 0),
        dailyTotal: isNewDay ? added : (currentUsage.dailyTotal || 0) + added,
        dailyResetDate: today,
        weeklyTotal: isNewWeek ? added : (currentUsage.weeklyTotal || 0) + added,
        weeklyResetDate: thisWeek,
        monthlyTotal: isNewMonth ? added : (currentUsage.monthlyTotal || 0) + added,
        monthlyResetDate: thisMonth,
      };
      // Persist to localStorage so usage survives page refresh
      try {
        localStorage.setItem('token_usage', JSON.stringify(newTokenUsage));
      } catch {
        console.warn('[useConfigStore] Failed to persist token usage (quota exceeded):');
        /* quota exceeded — ignore */
      }
      return { tokenUsage: newTokenUsage };
    }),
    resetTokenUsage: () => {
      const now = new Date();
      const freshUsage = {
        promptTokens: 0,
        candidatesTokens: 0,
        totalTokens: 0,
        dailyTotal: 0,
        dailyResetDate: now.toISOString().split('T')[0],
        weeklyTotal: 0,
        weeklyResetDate: getWeekIdentifier(now),
        monthlyTotal: 0,
        monthlyResetDate: now.toISOString().slice(0, 7),
      };
      try {
        localStorage.setItem('token_usage', JSON.stringify(freshUsage));
      } catch {
        console.warn('[useConfigStore] Failed to reset token usage:');
        /* ignore */
      }
      set({ tokenUsage: freshUsage });
    },
    setLLMConfig: (config) => {
      localStorage.setItem('llm_config', JSON.stringify(config));
      set({ llmConfig: config, config: config });
    },
    setConfig: (config) => {
      localStorage.setItem('llm_config', JSON.stringify(config));
      set({ llmConfig: config, config: config });
    },
    feishuWebhookUrl: localStorage.getItem('feishu_webhook') || '',
    setFeishuWebhookUrl: (webhook: string) => {
      localStorage.setItem('feishu_webhook', webhook);
      set({ feishuWebhookUrl: webhook });
    },
    debugMode: localStorage.getItem('debug_mode') === 'true',
    setDebugMode: (enabled: boolean) => {
      localStorage.setItem('debug_mode', String(enabled));
      set({ debugMode: enabled });
    },
    serviceStatus: 'available',
    setServiceStatus: (status) => set({ serviceStatus: status }),
    lastErrorStatus: null,
    setLastErrorStatus: (status) => set({ lastErrorStatus: status }),
    language: (localStorage.getItem('app_language') as 'en' | 'zh-CN') || 'zh-CN',
    setLanguage: (lang: 'en' | 'zh-CN') => {
      localStorage.setItem('app_language', lang);
      set({ language: lang });
    },
    cooldownUntil: 0,
    setCooldownUntil: (until: number) => set({ cooldownUntil: until }),
  };
});
