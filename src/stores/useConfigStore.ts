import { create } from 'zustand';
import { GeminiConfig } from '../types';

function getWeekIdentifier(d: Date) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return date.getUTCFullYear() + '-W' + Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
}

interface ConfigState {
  geminiConfig: GeminiConfig;
  setGeminiConfig: (config: GeminiConfig) => void;
  config: GeminiConfig;
  setConfig: (config: GeminiConfig) => void;
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
      const saved = localStorage.getItem('gemini_config');
      const parsed = saved ? JSON.parse(saved) : { model: 'gemini-3.1-pro-preview' };
      return parsed;
    } catch (e) {
      console.error('Failed to parse gemini_config from localStorage:', e);
      return { model: 'gemini-3.1-pro-preview' };
    }
  })();

  return {
    geminiConfig: initialConfig,
    config: initialConfig,
    tokenUsage: { 
      promptTokens: 0, 
      candidatesTokens: 0, 
      totalTokens: 0, 
      dailyTotal: 0, 
      dailyResetDate: new Date().toISOString().split('T')[0],
      weeklyTotal: 0,
      weeklyResetDate: getWeekIdentifier(new Date()),
      monthlyTotal: 0,
      monthlyResetDate: new Date().toISOString().slice(0, 7) // YYYY-MM
    },
    availableModels: [],
    setAvailableModels: (models) => set({ availableModels: models }),
    dailyTokenBudget: 900_000, // 90% of free-tier 1M daily limit
    setDailyTokenBudget: (budget) => set({ dailyTokenBudget: budget }),
    addTokenUsage: (usage) => set((state) => {
      const now = new Date();
      const today = now.toISOString().split('T')[0];
      const thisMonth = now.toISOString().slice(0, 7);
      const thisWeek = getWeekIdentifier(now);
      
      const isNewDay = state.tokenUsage.dailyResetDate !== today;
      const isNewWeek = state.tokenUsage.weeklyResetDate !== thisWeek;
      const isNewMonth = state.tokenUsage.monthlyResetDate !== thisMonth;
      
      const added = usage.totalTokens || 0;
      return {
        tokenUsage: {
          promptTokens: state.tokenUsage.promptTokens + (usage.promptTokens || 0),
          candidatesTokens: state.tokenUsage.candidatesTokens + (usage.candidatesTokens || 0),
          totalTokens: state.tokenUsage.totalTokens + (usage.totalTokens || 0),
          dailyTotal: isNewDay ? added : (state.tokenUsage.dailyTotal || 0) + added,
          dailyResetDate: today,
          weeklyTotal: isNewWeek ? added : (state.tokenUsage.weeklyTotal || 0) + added,
          weeklyResetDate: thisWeek,
          monthlyTotal: isNewMonth ? added : (state.tokenUsage.monthlyTotal || 0) + added,
          monthlyResetDate: thisMonth,
        },
      };
    }),
    setGeminiConfig: (config) => {
      localStorage.setItem('gemini_config', JSON.stringify(config));
      set({ geminiConfig: config, config: config });
    },
    setConfig: (config) => {
      localStorage.setItem('gemini_config', JSON.stringify(config));
      set({ geminiConfig: config, config: config });
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
