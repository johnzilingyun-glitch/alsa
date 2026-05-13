import { create } from 'zustand';
import { Market, StockAnalysis } from '../types';

interface AnalysisState {
  symbol: string;
  market: Market;
  analysis: StockAnalysis | null;
  chatMessage: string;
  chatHistory: { id: string; role: 'user' | 'ai'; content: string }[];
  lastJobId: string | null;
  cachedReportHtml: string | null;
  cachedReportJobId: string | null;

  setSymbol: (symbol: string) => void;
  setMarket: (market: Market) => void;
  setAnalysis: (analysis: StockAnalysis | null | ((prev: StockAnalysis | null) => StockAnalysis | null)) => void;
  setChatMessage: (message: string) => void;
  setChatHistory: (history: { id: string; role: 'user' | 'ai'; content: string }[] | ((prev: { id: string; role: 'user' | 'ai'; content: string }[]) => { id: string; role: 'user' | 'ai'; content: string }[])) => void;
  setLastJobId: (jobId: string | null) => void;
  setCachedReport: (jobId: string, html: string) => void;
  resetAnalysis: () => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  symbol: '',
  market: 'A-Share',
  analysis: null,
  chatMessage: '',
  chatHistory: [],
  lastJobId: null,
  cachedReportHtml: null,
  cachedReportJobId: null,

  setSymbol: (symbol) => set({ symbol }),
  setMarket: (market) => set({ market }),
  setAnalysis: (updater) => set((state) => ({ analysis: typeof updater === 'function' ? updater(state.analysis) : updater })),
  setChatMessage: (chatMessage) => set({ chatMessage }),
  setChatHistory: (updater) => set((state) => ({ chatHistory: typeof updater === 'function' ? updater(state.chatHistory) : updater })),
  setLastJobId: (lastJobId) => set({ lastJobId }),
  setCachedReport: (jobId, html) => set({ cachedReportHtml: html, cachedReportJobId: jobId }),
  resetAnalysis: () => set({
    analysis: null,
    chatHistory: [],
    lastJobId: null,
    cachedReportHtml: null,
    cachedReportJobId: null,
  }),
}));
