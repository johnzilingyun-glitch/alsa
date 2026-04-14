export interface SourceHealthInfo {
  source: string;
  status: 'healthy' | 'degraded' | 'down';
  avgLatencyMs: number;
  [key: string]: unknown;
}

export async function getDataSourceHealth(): Promise<SourceHealthInfo[]> {
  try {
    const res = await fetch('/api/health/data-sources');
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

const STATUS_ICONS: Record<string, string> = {
  healthy: '🟢',
  degraded: '🟡',
  down: '🔴',
};

export function formatHealthStatus(health: SourceHealthInfo): string {
  const icon = STATUS_ICONS[health.status] ?? '⚪';
  const latency = health.status === 'down' ? 'down' : `${Math.round(health.avgLatencyMs)}ms`;
  return `${icon} ${health.source} (${latency})`;
}
