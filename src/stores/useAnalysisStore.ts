import { create } from 'zustand';
import { Market, StockAnalysis } from '../types';

interface AnalysisState {
  symbol: string;
  market: Market;
  analysis: StockAnalysis | null;
  chatMessage: string;
  chatHistory: { id: string; role: 'user' | 'ai'; content: string }[];

  setSymbol: (symbol: string) => void;
  setMarket: (market: Market) => void;
  setAnalysis: (analysis: StockAnalysis | null | ((prev: StockAnalysis | null) => StockAnalysis | null)) => void;
  setChatMessage: (message: string) => void;
  setChatHistory: (history: { id: string; role: 'user' | 'ai'; content: string }[] | ((prev: { id: string; role: 'user' | 'ai'; content: string }[]) => { id: string; role: 'user' | 'ai'; content: string }[])) => void;
  resetAnalysis: () => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  symbol: '',
  market: 'A-Share',
  analysis: null,
  chatMessage: '',
  chatHistory: [],

  setSymbol: (symbol) => set({ symbol }),
  setMarket: (market) => set({ market }),
  setAnalysis: (updater) => set((state) => ({ analysis: typeof updater === 'function' ? updater(state.analysis) : updater })),
  setChatMessage: (chatMessage) => set({ chatMessage }),
  setChatHistory: (updater) => set((state) => ({ chatHistory: typeof updater === 'function' ? updater(state.chatHistory) : updater })),
  resetAnalysis: () => set({
    analysis: null,
    chatHistory: [],
  }),
}));
