import { create } from 'zustand';
import type { Market, WatchlistItem, ScoreSnapshot, QuickScanResult, WatchlistAlert } from '../types';

interface WatchlistState {
  items: WatchlistItem[];
  isScanning: boolean;
  lastScanTime: string | null;

  addItem: (symbol: string, name: string, market: Market) => void;
  removeItem: (id: string) => void;
  updateNotes: (id: string, notes: string) => void;
  updateScore: (id: string, snapshot: ScoreSnapshot) => void;
  setLastQuickScan: (id: string, result: QuickScanResult) => void;
  addAlert: (id: string, alert: WatchlistAlert) => void;
  acknowledgeAlert: (id: string, alertId: string) => void;
  setIsScanning: (scanning: boolean) => void;
  setLastScanTime: (time: string) => void;
}

export const useWatchlistStore = create<WatchlistState>((set, get) => ({
  items: [],
  isScanning: false,
  lastScanTime: null,

  addItem: (symbol, name, market) => {
    const existing = get().items.find(i => i.symbol === symbol && i.market === market);
    if (existing) return;

    const item: WatchlistItem = {
      id: `wl-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      symbol,
      name,
      market,
      addedAt: new Date().toISOString(),
      notes: '',
      alertThreshold: 15,
      scoreHistory: [],
      alertHistory: [],
    };
    set((state) => ({ items: [...state.items, item] }));
  },

  removeItem: (id) => set((state) => ({
    items: state.items.filter(i => i.id !== id),
  })),

  updateNotes: (id, notes) => set((state) => ({
    items: state.items.map(i => i.id === id ? { ...i, notes } : i),
  })),

  updateScore: (id, snapshot) => set((state) => ({
    items: state.items.map(i =>
      i.id === id ? { ...i, scoreHistory: [...i.scoreHistory, snapshot] } : i,
    ),
  })),

  setLastQuickScan: (id, result) => set((state) => ({
    items: state.items.map(i =>
      i.id === id ? { ...i, lastQuickScan: result } : i,
    ),
  })),

  addAlert: (id, alert) => set((state) => ({
    items: state.items.map(i =>
      i.id === id ? { ...i, alertHistory: [...i.alertHistory, alert] } : i,
    ),
  })),

  acknowledgeAlert: (itemId, alertId) => set((state) => ({
    items: state.items.map(i =>
      i.id === itemId
        ? { ...i, alertHistory: i.alertHistory.map(a => a.id === alertId ? { ...a, acknowledged: true } : a) }
        : i,
    ),
  })),

  setIsScanning: (isScanning) => set({ isScanning }),
  setLastScanTime: (lastScanTime) => set({ lastScanTime }),
  setItems: (items: WatchlistItem[]) => set({ items }),
}));
