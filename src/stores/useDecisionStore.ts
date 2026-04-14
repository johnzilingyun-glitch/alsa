import { create } from 'zustand';
import type { Market, DecisionEntry } from '../types';

interface DecisionState {
  entries: DecisionEntry[];
  stats: null; // Computed on demand

  addEntry: (entry: Omit<DecisionEntry, 'id' | 'createdAt' | 'reviewDate'>) => void;
  updateEntry: (id: string, updates: Partial<DecisionEntry>) => void;
  removeEntry: (id: string) => void;
  getPendingReviews: () => DecisionEntry[];
}

export const useDecisionStore = create<DecisionState>((set, get) => ({
  entries: [],
  stats: null,

  addEntry: (entry) => {
    const now = new Date();
    const reviewDate = new Date(now);
    reviewDate.setDate(reviewDate.getDate() + 30);

    const newEntry: DecisionEntry = {
      ...entry,
      id: `dec-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      createdAt: now.toISOString(),
      reviewDate: reviewDate.toISOString(),
    };

    set((state) => ({ entries: [...state.entries, newEntry] }));
  },

  updateEntry: (id, updates) => set((state) => ({
    entries: state.entries.map(e => e.id === id ? { ...e, ...updates } : e),
  })),

  removeEntry: (id) => set((state) => ({
    entries: state.entries.filter(e => e.id !== id),
  })),

  getPendingReviews: () => {
    const now = new Date();
    return get().entries.filter(e =>
      !e.outcome && new Date(e.reviewDate) <= now,
    );
  },
}));
