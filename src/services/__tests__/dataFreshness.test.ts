import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getDataFreshness, getMarketFreshness } from '../dataFreshness';

describe('dataFreshness', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-27T10:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('getDataFreshness', () => {
    it('returns fresh (🟢) for data less than 5 minutes old', () => {
      const result = getDataFreshness('2026-03-27T09:57:00Z');
      expect(result.status).toBe('fresh');
      expect(result.label).toContain('🟢');
      expect(result.ageMinutes).toBe(3);
    });

    it('returns delayed (🟡) for data 5-30 minutes old', () => {
      const result = getDataFreshness('2026-03-27T09:45:00Z');
      expect(result.status).toBe('delayed');
      expect(result.label).toContain('🟡');
      expect(result.ageMinutes).toBe(15);
    });

    it('returns stale (🔴) for data over 30 minutes old', () => {
      const result = getDataFreshness('2026-03-27T09:00:00Z');
      expect(result.status).toBe('stale');
      expect(result.label).toContain('🔴');
      expect(result.ageMinutes).toBe(60);
    });

    it('returns stale for empty/undefined timestamp', () => {
      const result = getDataFreshness('');
      expect(result.status).toBe('stale');
      expect(result.label).toContain('🔴');
    });

    it('returns stale for invalid timestamp', () => {
      const result = getDataFreshness('not-a-date');
      expect(result.status).toBe('stale');
      expect(result.label).toContain('🔴');
    });

    it('returns fresh at exactly 0 minutes', () => {
      const result = getDataFreshness('2026-03-27T10:00:00Z');
      expect(result.status).toBe('fresh');
      expect(result.ageMinutes).toBe(0);
    });

    it('returns fresh at exactly 4 minutes 59 seconds', () => {
      const result = getDataFreshness('2026-03-27T09:55:01Z');
      expect(result.status).toBe('fresh');
    });

    it('returns delayed at exactly 5 minutes', () => {
      const result = getDataFreshness('2026-03-27T09:55:00Z');
      expect(result.status).toBe('delayed');
    });

    it('returns stale at exactly 30 minutes', () => {
      const result = getDataFreshness('2026-03-27T09:30:00Z');
      expect(result.status).toBe('stale');
    });
  });

  describe('getMarketFreshness', () => {
    it('returns freshness for a map of market update times', () => {
      const times: Record<string, string> = {
        'A-Share': '2026-03-27T09:58:00Z',
        'HK-Share': '2026-03-27T09:40:00Z',
        'US-Share': '2026-03-27T09:10:00Z',
      };
      const result = getMarketFreshness(times);
      expect(result['A-Share'].status).toBe('fresh');
      expect(result['HK-Share'].status).toBe('delayed');
      expect(result['US-Share'].status).toBe('stale');
    });

    it('handles empty map', () => {
      const result = getMarketFreshness({});
      expect(Object.keys(result)).toHaveLength(0);
    });
  });
});
