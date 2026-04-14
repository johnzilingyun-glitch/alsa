import { describe, it, expect } from 'vitest';
import { detectWatchlistAlert } from '../watchlistService';
import type { WatchlistItem } from '../../types';

function makeWatchlistItem(scoreHistory: { score: number }[]): WatchlistItem {
  return {
    id: 'test-1',
    symbol: 'AAPL',
    name: 'Apple',
    market: 'US-Share',
    addedAt: '2026-03-20',
    notes: '',
    alertThreshold: 15,
    scoreHistory: scoreHistory.map((s, i) => ({
      date: `2026-03-${20 + i}`,
      score: s.score,
      price: 150,
      recommendation: 'Buy',
    })),
    alertHistory: [],
  };
}

describe('watchlistService', () => {
  describe('detectWatchlistAlert', () => {
    it('returns null when no previous score', () => {
      const item = makeWatchlistItem([]);
      expect(detectWatchlistAlert(item, 75)).toBeNull();
    });

    it('returns null when score change is below threshold', () => {
      const item = makeWatchlistItem([{ score: 70 }]);
      expect(detectWatchlistAlert(item, 75)).toBeNull(); // delta=5, threshold=15
    });

    it('detects score drop exceeding threshold', () => {
      const item = makeWatchlistItem([{ score: 80 }]);
      const alert = detectWatchlistAlert(item, 60); // delta=-20
      expect(alert).not.toBeNull();
      expect(alert!.type).toBe('score_drop');
      expect(alert!.message).toContain('20');
    });

    it('detects score rise exceeding threshold', () => {
      const item = makeWatchlistItem([{ score: 50 }]);
      const alert = detectWatchlistAlert(item, 70); // delta=+20
      expect(alert).not.toBeNull();
      expect(alert!.type).toBe('score_rise');
    });

    it('uses the most recent score for comparison', () => {
      const item = makeWatchlistItem([{ score: 30 }, { score: 70 }]);
      // Compared against latest (70), delta = -5
      expect(detectWatchlistAlert(item, 65)).toBeNull();
    });

    it('respects custom alert threshold', () => {
      const item = makeWatchlistItem([{ score: 70 }]);
      item.alertThreshold = 5;
      const alert = detectWatchlistAlert(item, 60); // delta=-10, threshold=5
      expect(alert).not.toBeNull();
    });

    it('alert has correct structure', () => {
      const item = makeWatchlistItem([{ score: 80 }]);
      const alert = detectWatchlistAlert(item, 50);
      expect(alert).toHaveProperty('id');
      expect(alert).toHaveProperty('type');
      expect(alert).toHaveProperty('message');
      expect(alert).toHaveProperty('triggeredAt');
      expect(alert!.acknowledged).toBe(false);
    });
  });
});
