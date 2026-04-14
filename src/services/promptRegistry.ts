export interface PromptVersion {
  id: string;
  name: string;
  version: string;
  template: (...args: any[]) => string;
  changelog: string;
  createdAt: string;
  isActive: boolean;
}

export interface PromptMetrics {
  callCount: number;
  avgTokenUsage: number;
  avgResponseScore: number;
  avgLatencyMs: number;
  errorRate: number;
  lastUsed: string;
}

const registry = new Map<string, PromptVersion[]>();
const metrics = new Map<string, PromptMetrics>();

export function registerPrompt(version: PromptVersion): void {
  const versions = registry.get(version.name) ?? [];
  versions.push(version);
  registry.set(version.name, versions);
}

export function getActivePrompt(name: string): PromptVersion {
  const versions = registry.get(name) ?? [];
  const active = versions.find(v => v.isActive);
  if (!active) throw new Error(`No active prompt for ${name}`);
  return active;
}

export function recordPromptMetrics(
  name: string,
  tokenUsage: number,
  responseScore: number,
  latencyMs: number,
  isError: boolean,
): void {
  const m = metrics.get(name) ?? {
    callCount: 0,
    avgTokenUsage: 0,
    avgResponseScore: 0,
    avgLatencyMs: 0,
    errorRate: 0,
    lastUsed: '',
  };
  m.callCount++;
  m.avgTokenUsage = ((m.avgTokenUsage * (m.callCount - 1)) + tokenUsage) / m.callCount;
  m.avgResponseScore = ((m.avgResponseScore * (m.callCount - 1)) + responseScore) / m.callCount;
  m.avgLatencyMs = ((m.avgLatencyMs * (m.callCount - 1)) + latencyMs) / m.callCount;
  m.errorRate = ((m.errorRate * (m.callCount - 1)) + (isError ? 1 : 0)) / m.callCount;
  m.lastUsed = new Date().toISOString();
  metrics.set(name, m);
}

export function getPromptMetrics(name: string): PromptMetrics | undefined {
  return metrics.get(name);
}

export function getAllVersions(name: string): PromptVersion[] {
  return registry.get(name) ?? [];
}

export function clearRegistry(): void {
  registry.clear();
  metrics.clear();
}
