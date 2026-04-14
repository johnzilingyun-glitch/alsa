import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getDataSourceHealth, formatHealthStatus } from '../healthService';

describe('healthService', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('getDataSourceHealth', () => {
    it('fetches health data from API', async () => {
      const mockData = [
        { source: 'yahoo', status: 'healthy', avgLatencyMs: 45, consecutiveFailures: 0 },
        { source: 'eastmoney_new', status: 'degraded', avgLatencyMs: 320, consecutiveFailures: 1 },
      ];
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockData),
      } as Response);

      const result = await getDataSourceHealth();
      expect(result).toEqual(mockData);
      expect(fetch).toHaveBeenCalledWith('/api/health/data-sources');
    });

    it('returns empty array on fetch error', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error'));
      const result = await getDataSourceHealth();
      expect(result).toEqual([]);
    });

    it('returns empty array on non-ok response', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({}),
      } as Response);
      const result = await getDataSourceHealth();
      expect(result).toEqual([]);
    });
  });

  describe('formatHealthStatus', () => {
    it('formats healthy source with green indicator', () => {
      const result = formatHealthStatus({ source: 'yahoo', status: 'healthy', avgLatencyMs: 45 });
      expect(result).toContain('🟢');
      expect(result).toContain('yahoo');
      expect(result).toContain('45ms');
    });

    it('formats degraded source with yellow indicator', () => {
      const result = formatHealthStatus({ source: 'eastmoney_new', status: 'degraded', avgLatencyMs: 320 });
      expect(result).toContain('🟡');
    });

    it('formats down source with red indicator', () => {
      const result = formatHealthStatus({ source: 'sina', status: 'down', avgLatencyMs: 0 });
      expect(result).toContain('🔴');
      expect(result).toContain('down');
    });
  });
});
