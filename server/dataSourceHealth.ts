export type SourceName = 'eastmoney_new' | 'eastmoney_old' | 'sina' | 'yahoo';
export type SourceStatus = 'healthy' | 'degraded' | 'down';

export interface SourceHealth {
  source: SourceName;
  status: SourceStatus;
  successCount: number;
  failureCount: number;
  consecutiveFailures: number;
  avgLatencyMs: number;
  lastSuccess: number | null;
  lastFailure: number | null;
  downSince: number | null;
}

export class DataSourceMonitor {
  private health: Map<SourceName, SourceHealth>;

  private static FAILURE_THRESHOLD = 3;
  private static RECOVERY_TIMEOUT_MS = 5 * 60 * 1000;
  private static DEGRADED_SUCCESS_RATE = 0.7;
  private static LATENCY_WINDOW = 20;

  private latencyBuffer = new Map<SourceName, number[]>();

  constructor(sources: SourceName[]) {
    this.health = new Map();
    for (const s of sources) {
      this.health.set(s, {
        source: s,
        status: 'healthy',
        successCount: 0,
        failureCount: 0,
        consecutiveFailures: 0,
        avgLatencyMs: 0,
        lastSuccess: null,
        lastFailure: null,
        downSince: null,
      });
      this.latencyBuffer.set(s, []);
    }
  }

  recordSuccess(source: SourceName, latencyMs: number): void {
    const h = this.health.get(source);
    if (!h) return;

    h.successCount++;
    h.consecutiveFailures = 0;
    h.lastSuccess = Date.now();

    // Track latency with sliding window
    const buf = this.latencyBuffer.get(source)!;
    buf.push(latencyMs);
    if (buf.length > DataSourceMonitor.LATENCY_WINDOW) buf.shift();
    h.avgLatencyMs = buf.reduce((a, b) => a + b, 0) / buf.length;

    // Recover from down — reset counters for a fresh start
    if (h.status === 'down') {
      h.downSince = null;
      h.status = 'healthy';
      h.failureCount = 0;
      h.successCount = 1;
      h.consecutiveFailures = 0;
      return;
    }

    // Update status based on success rate
    this.updateStatus(h);
  }

  recordFailure(source: SourceName): void {
    const h = this.health.get(source);
    if (!h) return;

    h.failureCount++;
    h.consecutiveFailures++;
    h.lastFailure = Date.now();

    if (h.consecutiveFailures >= DataSourceMonitor.FAILURE_THRESHOLD) {
      h.status = 'down';
      if (!h.downSince) h.downSince = Date.now();
    } else {
      this.updateStatus(h);
    }
  }

  isAvailable(source: SourceName): boolean {
    const h = this.health.get(source);
    if (!h) return false;
    if (h.status !== 'down') return true;
    // Half-open: allow probe after recovery timeout
    return Date.now() - (h.downSince ?? 0) > DataSourceMonitor.RECOVERY_TIMEOUT_MS;
  }

  getHealthReport(): SourceHealth[] {
    return Array.from(this.health.values());
  }

  getSortedAvailable(): SourceName[] {
    return Array.from(this.health.entries())
      .filter(([name]) => this.isAvailable(name))
      .sort((a, b) => a[1].avgLatencyMs - b[1].avgLatencyMs)
      .map(([name]) => name);
  }

  private updateStatus(h: SourceHealth): void {
    if (h.status === 'down') return; // Don't override down status here
    const total = h.successCount + h.failureCount;
    if (total < 3) {
      h.status = 'healthy';
      return;
    }
    const successRate = h.successCount / total;
    h.status = successRate < DataSourceMonitor.DEGRADED_SUCCESS_RATE ? 'degraded' : 'healthy';
  }
}

export const monitor = new DataSourceMonitor([
  'eastmoney_new', 'eastmoney_old', 'sina', 'yahoo',
]);
