/**
 * useStatsStore – persisted visit & usage statistics
 *
 * Tracks:
 *  - Page/session open counts (daily, weekly, monthly, cumulative)
 *  - First-visit date
 *  - Last-visit timestamp
 *
 * All data is stored in localStorage under 'alsa_stats_v1'.
 */

import { create } from 'zustand';

const STATS_KEY = 'alsa_stats_v1';

function getWeekId(d: Date) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return date.getUTCFullYear() + '-W' + Math.ceil((((date.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
}

export interface VisitStats {
  /** Total number of page opens since first install */
  totalSessions: number;
  /** Sessions in the current week (resets weekly) */
  weeklySessions: number;
  weeklyResetId: string;
  /** Sessions in the current month (resets monthly) */
  monthlySessions: number;
  monthlyResetId: string;
  /** Sessions today */
  dailySessions: number;
  dailyResetDate: string;
  /** ISO timestamp of very first open */
  firstVisit: string;
  /** ISO timestamp of last open */
  lastVisit: string;
}

interface StatsState {
  stats: VisitStats;
  /** Call once on app mount to record a new session */
  recordSession: () => void;
  /** Reset all stats */
  resetStats: () => void;
}

function loadStats(): VisitStats {
  try {
    const raw = localStorage.getItem(STATS_KEY);
    if (raw) return JSON.parse(raw) as VisitStats;
  } catch {
    console.warn('[useStatsStore] Failed to load stats from localStorage:');
    /* ignore */
  }
  return makeEmptyStats();
}

function makeEmptyStats(): VisitStats {
  const now = new Date();
  return {
    totalSessions: 0,
    weeklySessions: 0,
    weeklyResetId: getWeekId(now),
    monthlySessions: 0,
    monthlyResetId: now.toISOString().slice(0, 7),
    dailySessions: 0,
    dailyResetDate: now.toISOString().split('T')[0],
    firstVisit: now.toISOString(),
    lastVisit: now.toISOString(),
  };
}

function saveStats(s: VisitStats) {
  try {
    localStorage.setItem(STATS_KEY, JSON.stringify(s));
  } catch {
    console.warn('[useStatsStore] Failed to save stats to localStorage:');
    /* ignore */
  }
}

export const useStatsStore = create<StatsState>((set) => {
  const initialStats = loadStats();

  return {
    stats: initialStats,

    recordSession: () => set((state) => {
      const now = new Date();
      const today = now.toISOString().split('T')[0];
      const thisWeek = getWeekId(now);
      const thisMonth = now.toISOString().slice(0, 7);
      const s = state.stats;

      const newStats: VisitStats = {
        totalSessions: (s.totalSessions || 0) + 1,
        weeklySessions: s.weeklyResetId === thisWeek ? (s.weeklySessions || 0) + 1 : 1,
        weeklyResetId: thisWeek,
        monthlySessions: s.monthlyResetId === thisMonth ? (s.monthlySessions || 0) + 1 : 1,
        monthlyResetId: thisMonth,
        dailySessions: s.dailyResetDate === today ? (s.dailySessions || 0) + 1 : 1,
        dailyResetDate: today,
        firstVisit: s.firstVisit || now.toISOString(),
        lastVisit: now.toISOString(),
      };
      saveStats(newStats);
      return { stats: newStats };
    }),

    resetStats: () => {
      const fresh = makeEmptyStats();
      saveStats(fresh);
      set({ stats: fresh });
    },
  };
});
