export type SourceName = 'eastmoney_new' | 'eastmoney_old' | 'sina' | 'yahoo' | 'python_market';
export type SourceStatus = 'healthy' | 'degraded' | 'down';
export type MarketName = 'A-Share' | 'HK-Share' | 'US-Share' | 'Unknown';
export type DataTypeName = 'quote' | 'history' | 'financial' | 'indices' | 'news' | 'unknown';

export interface SourceTags {
  market?: MarketName;
  dataType?: DataTypeName;
}

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

export interface DimensionalHealth {
  source: SourceName;
  market: MarketName;
  dataType: DataTypeName;
  successCount: number;
  failureCount: number;
  requestCount: number;
  avgLatencyMs: number;
  lastSuccess: number | null;
  lastFailure: number | null;
}

export class DataSourceMonitor {
  private health: Map<SourceName, SourceHealth>;
  private dimensionalHealth: Map<string, DimensionalHealth>;

  private static FAILURE_THRESHOLD = 3;
  private static RECOVERY_TIMEOUT_MS = 5 * 60 * 1000;
  private static DEGRADED_SUCCESS_RATE = 0.7;
  private static LATENCY_WINDOW = 20;

  private latencyBuffer = new Map<SourceName, number[]>();
  private dimensionalLatencyBuffer = new Map<string, number[]>();

  constructor(sources: SourceName[]) {
    this.health = new Map();
    this.dimensionalHealth = new Map();
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

  private dimensionKey(source: SourceName, market: MarketName, dataType: DataTypeName): string {
    return `${source}|${market}|${dataType}`;
  }

  private ensureDimensional(source: SourceName, market: MarketName, dataType: DataTypeName): DimensionalHealth {
    const key = this.dimensionKey(source, market, dataType);
    const existing = this.dimensionalHealth.get(key);
    if (existing) return existing;

    const created: DimensionalHealth = {
      source,
      market,
      dataType,
      successCount: 0,
      failureCount: 0,
      requestCount: 0,
      avgLatencyMs: 0,
      lastSuccess: null,
      lastFailure: null,
    };
    this.dimensionalHealth.set(key, created);
    this.dimensionalLatencyBuffer.set(key, []);
    return created;
  }

  recordSuccess(source: SourceName, latencyMs: number, tags?: SourceTags): void {
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

    const market = tags?.market ?? 'Unknown';
    const dataType = tags?.dataType ?? 'unknown';
    const d = this.ensureDimensional(source, market, dataType);
    d.successCount++;
    d.requestCount++;
    d.lastSuccess = Date.now();
    const dKey = this.dimensionKey(source, market, dataType);
    const dBuf = this.dimensionalLatencyBuffer.get(dKey)!;
    dBuf.push(latencyMs);
    if (dBuf.length > DataSourceMonitor.LATENCY_WINDOW) dBuf.shift();
    d.avgLatencyMs = dBuf.reduce((a, b) => a + b, 0) / dBuf.length;
  }

  recordFailure(source: SourceName, tags?: SourceTags): void {
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

    const market = tags?.market ?? 'Unknown';
    const dataType = tags?.dataType ?? 'unknown';
    const d = this.ensureDimensional(source, market, dataType);
    d.failureCount++;
    d.requestCount++;
    d.lastFailure = Date.now();
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

  getDimensionalHealthReport(): DimensionalHealth[] {
    return Array.from(this.dimensionalHealth.values()).map((d) => ({ ...d }));
  }

  getMarketSummary(): Array<{ market: MarketName; requestCount: number; successRate: number; avgLatencyMs: number }> {
    const summary = new Map<MarketName, { requestCount: number; successCount: number; totalLatency: number; latencyCount: number }>();
    for (const row of this.dimensionalHealth.values()) {
      const prev = summary.get(row.market) || { requestCount: 0, successCount: 0, totalLatency: 0, latencyCount: 0 };
      prev.requestCount += row.requestCount;
      prev.successCount += row.successCount;
      if (row.avgLatencyMs > 0) {
        prev.totalLatency += row.avgLatencyMs * row.requestCount;
        prev.latencyCount += row.requestCount;
      }
      summary.set(row.market, prev);
    }
    return Array.from(summary.entries()).map(([market, v]) => ({
      market,
      requestCount: v.requestCount,
      successRate: v.requestCount > 0 ? Number((v.successCount / v.requestCount).toFixed(4)) : 0,
      avgLatencyMs: v.latencyCount > 0 ? Number((v.totalLatency / v.latencyCount).toFixed(2)) : 0,
    }));
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
  'eastmoney_new', 'eastmoney_old', 'sina', 'yahoo', 'python_market'
]);
