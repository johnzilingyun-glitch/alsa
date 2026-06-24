import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useStatsStore } from '../useStatsStore';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: () => { store = {}; },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

describe('useStatsStore', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
    // Reset store to fresh state
    useStatsStore.setState({
      stats: {
        totalSessions: 0,
        weeklySessions: 0,
        weeklyResetId: '',
        monthlySessions: 0,
        monthlyResetId: '',
        dailySessions: 0,
        dailyResetDate: '',
        firstVisit: new Date().toISOString(),
        lastVisit: new Date().toISOString(),
      },
    });
  });

  describe('initial state', () => {
    it('should have zero sessions initially', () => {
      const { stats } = useStatsStore.getState();
      expect(stats.totalSessions).toBe(0);
    });
  });

  describe('recordSession', () => {
    it('should increment totalSessions', () => {
      useStatsStore.getState().recordSession();
      expect(useStatsStore.getState().stats.totalSessions).toBe(1);

      useStatsStore.getState().recordSession();
      expect(useStatsStore.getState().stats.totalSessions).toBe(2);
    });

    it('should increment dailySessions for same day', () => {
      useStatsStore.getState().recordSession();
      useStatsStore.getState().recordSession();
      expect(useStatsStore.getState().stats.dailySessions).toBe(2);
    });

    it('should update lastVisit', () => {
      const before = new Date().toISOString();
      useStatsStore.getState().recordSession();
      const { lastVisit } = useStatsStore.getState().stats;
      expect(lastVisit >= before).toBe(true);
    });

    it('should persist to localStorage', () => {
      useStatsStore.getState().recordSession();
      expect(localStorageMock.setItem).toHaveBeenCalled();
    });

    it('should reset dailySessions on new day', () => {
      // Set state to yesterday
      useStatsStore.setState({
        stats: {
          ...useStatsStore.getState().stats,
          dailySessions: 5,
          dailyResetDate: '2020-01-01', // Old date
          totalSessions: 5,
        },
      });

      useStatsStore.getState().recordSession();
      // Daily should reset to 1 (new day)
      expect(useStatsStore.getState().stats.dailySessions).toBe(1);
      // But total should still accumulate
      expect(useStatsStore.getState().stats.totalSessions).toBe(6);
    });

    it('should reset weeklySessions on new week', () => {
      useStatsStore.setState({
        stats: {
          ...useStatsStore.getState().stats,
          weeklySessions: 10,
          weeklyResetId: '2020-W1', // Old week
          totalSessions: 10,
        },
      });

      useStatsStore.getState().recordSession();
      expect(useStatsStore.getState().stats.weeklySessions).toBe(1);
    });

    it('should reset monthlySessions on new month', () => {
      useStatsStore.setState({
        stats: {
          ...useStatsStore.getState().stats,
          monthlySessions: 20,
          monthlyResetId: '2020-01', // Old month
          totalSessions: 20,
        },
      });

      useStatsStore.getState().recordSession();
      expect(useStatsStore.getState().stats.monthlySessions).toBe(1);
    });

    it('should preserve firstVisit across sessions', () => {
      const firstVisit = '2024-01-01T00:00:00.000Z';
      useStatsStore.setState({
        stats: {
          ...useStatsStore.getState().stats,
          firstVisit,
        },
      });

      useStatsStore.getState().recordSession();
      expect(useStatsStore.getState().stats.firstVisit).toBe(firstVisit);
    });
  });

  describe('resetStats', () => {
    it('should clear all session counts', () => {
      useStatsStore.getState().recordSession();
      useStatsStore.getState().recordSession();
      expect(useStatsStore.getState().stats.totalSessions).toBe(2);

      useStatsStore.getState().resetStats();
      const { stats } = useStatsStore.getState();
      expect(stats.totalSessions).toBe(0);
      expect(stats.dailySessions).toBe(0);
      expect(stats.weeklySessions).toBe(0);
      expect(stats.monthlySessions).toBe(0);
    });

    it('should persist reset to localStorage', () => {
      useStatsStore.getState().resetStats();
      expect(localStorageMock.setItem).toHaveBeenCalled();
    });
  });
});
