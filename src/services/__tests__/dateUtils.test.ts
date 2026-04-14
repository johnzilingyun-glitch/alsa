import { describe, it, expect, vi } from 'vitest';
import { getBeijingDate, generateHistoryItemKey } from '../dateUtils';

describe('dateUtils', () => {
  describe('getBeijingDate', () => {
    it('should format date correctly', () => {
      const date = new Date('2026-03-30T08:00:00Z');
      const formatted = getBeijingDate(date);
      expect(formatted).toBeDefined();
      expect(typeof formatted).toBe('string');
    });

    it('should fall back to ISO date if Intl.DateTimeFormat fails', () => {
      const date = new Date('2026-03-30T08:00:00Z');
      const origDTF = Intl.DateTimeFormat;
      vi.stubGlobal('Intl', {
        ...Intl,
        DateTimeFormat: vi.fn().mockImplementation(() => {
          throw new Error('Invalid timezone');
        }),
      });

      const formatted = getBeijingDate(date);
      expect(formatted).toBe('2026-03-30');

      vi.stubGlobal('Intl', { ...Intl, DateTimeFormat: origDTF });
    });
  });

  describe('generateHistoryItemKey', () => {
    it('should use item.id if available', () => {
      const item = { id: 'test-id' };
      expect(generateHistoryItemKey(item, 0)).toBe('test-id');
    });

    it('should generate a composite key if id is missing', () => {
      const item = {
        stockInfo: {
          symbol: 'AAPL',
          lastUpdated: '2026-03-30 10:00:00'
        }
      };
      expect(generateHistoryItemKey(item, 5)).toBe('history-AAPL-2026-03-30 10:00:00-5');
    });

    it('should handle missing stockInfo gracefully', () => {
      const item = {};
      expect(generateHistoryItemKey(item, 10)).toBe('history-unknown-no-time-10');
    });
  });
});
