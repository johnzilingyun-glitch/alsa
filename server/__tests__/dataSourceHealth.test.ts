import { describe, it, expect, beforeEach, vi } from 'vitest';
import { DataSourceMonitor, SourceName } from '../dataSourceHealth';

describe('DataSourceMonitor', () => {
  let monitor: DataSourceMonitor;
  const sources: SourceName[] = ['eastmoney_new', 'eastmoney_old', 'sina', 'yahoo'];

  beforeEach(() => {
    monitor = new DataSourceMonitor(sources);
  });

  describe('initial state', () => {
    it('should initialize all sources as healthy', () => {
      const report = monitor.getHealthReport();
      expect(report).toHaveLength(4);
      report.forEach(h => {
        expect(h.status).toBe('healthy');
        expect(h.successCount).toBe(0);
        expect(h.failureCount).toBe(0);
        expect(h.consecutiveFailures).toBe(0);
      });
    });

    it('should report all sources as available', () => {
      sources.forEach(s => {
        expect(monitor.isAvailable(s)).toBe(true);
      });
    });
  });

  describe('recordSuccess', () => {
    it('should increment success count and track latency', () => {
      monitor.recordSuccess('yahoo', 50);
      monitor.recordSuccess('yahoo', 100);
      const report = monitor.getHealthReport();
      const yahoo = report.find(h => h.source === 'yahoo')!;
      expect(yahoo.successCount).toBe(2);
      expect(yahoo.avgLatencyMs).toBe(75);
      expect(yahoo.lastSuccess).not.toBeNull();
    });

    it('should reset consecutive failures on success', () => {
      monitor.recordFailure('yahoo');
      monitor.recordFailure('yahoo');
      monitor.recordSuccess('yahoo', 50);
      const yahoo = monitor.getHealthReport().find(h => h.source === 'yahoo')!;
      expect(yahoo.consecutiveFailures).toBe(0);
    });

    it('should recover from down status on success', () => {
      // Force to down
      for (let i = 0; i < 3; i++) monitor.recordFailure('yahoo');
      expect(monitor.getHealthReport().find(h => h.source === 'yahoo')!.status).toBe('down');

      monitor.recordSuccess('yahoo', 50);
      const yahoo = monitor.getHealthReport().find(h => h.source === 'yahoo')!;
      expect(yahoo.status).toBe('healthy');
      expect(yahoo.downSince).toBeNull();
    });
  });

  describe('recordFailure', () => {
    it('should increment failure count', () => {
      monitor.recordFailure('sina');
      const sina = monitor.getHealthReport().find(h => h.source === 'sina')!;
      expect(sina.failureCount).toBe(1);
      expect(sina.consecutiveFailures).toBe(1);
      expect(sina.lastFailure).not.toBeNull();
    });

    it('should mark source as down after threshold consecutive failures', () => {
      monitor.recordFailure('sina');
      monitor.recordFailure('sina');
      expect(monitor.getHealthReport().find(h => h.source === 'sina')!.status).not.toBe('down');

      monitor.recordFailure('sina');
      const sina = monitor.getHealthReport().find(h => h.source === 'sina')!;
      expect(sina.status).toBe('down');
      expect(sina.downSince).not.toBeNull();
    });
  });

  describe('isAvailable', () => {
    it('should return false for down source within recovery window', () => {
      for (let i = 0; i < 3; i++) monitor.recordFailure('sina');
      expect(monitor.isAvailable('sina')).toBe(false);
    });

    it('should return true for down source after recovery timeout (half-open)', () => {
      for (let i = 0; i < 3; i++) monitor.recordFailure('sina');
      // Manually set downSince to past
      const report = monitor.getHealthReport();
      const sina = report.find(h => h.source === 'sina')!;
      // Simulate time passing by manipulating internal state
      sina.downSince = Date.now() - 6 * 60 * 1000; // 6 minutes ago
      expect(monitor.isAvailable('sina')).toBe(true);
    });
  });

  describe('degraded status', () => {
    it('should mark source as degraded when success rate drops below threshold', () => {
      // 2 successes, 8 failures = 20% success rate
      monitor.recordSuccess('eastmoney_new', 100);
      monitor.recordSuccess('eastmoney_new', 100);
      // Intersperse failures to keep below threshold without hitting consecutive limit
      for (let i = 0; i < 2; i++) {
        monitor.recordFailure('eastmoney_new');
        monitor.recordSuccess('eastmoney_new', 100); // reset consecutive
      }
      // Now add more failures without reaching consecutive threshold
      monitor.recordFailure('eastmoney_new');
      monitor.recordFailure('eastmoney_new');
      // Record another success to trigger evaluation
      monitor.recordSuccess('eastmoney_new', 100);

      const health = monitor.getHealthReport().find(h => h.source === 'eastmoney_new')!;
      // Success rate = 5/(5+4) = 55.5% < 70% → degraded
      expect(health.status).toBe('degraded');
    });
  });

  describe('getSortedAvailable', () => {
    it('should return sources sorted by latency, excluding down ones', () => {
      monitor.recordSuccess('yahoo', 200);
      monitor.recordSuccess('sina', 50);
      monitor.recordSuccess('eastmoney_new', 100);
      // Mark eastmoney_old as down
      for (let i = 0; i < 3; i++) monitor.recordFailure('eastmoney_old');

      const sorted = monitor.getSortedAvailable();
      expect(sorted).not.toContain('eastmoney_old');
      expect(sorted[0]).toBe('sina');
      expect(sorted[1]).toBe('eastmoney_new');
      expect(sorted[2]).toBe('yahoo');
    });

    it('should include sources with no recorded latency (0ms)', () => {
      const sorted = monitor.getSortedAvailable();
      expect(sorted).toHaveLength(4);
    });
  });
});
