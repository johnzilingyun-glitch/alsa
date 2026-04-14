import { FreshnessInfo, FreshnessStatus } from '../types';

const FRESH_THRESHOLD_MS = 5 * 60 * 1000;   // 5 minutes
const DELAYED_THRESHOLD_MS = 30 * 60 * 1000; // 30 minutes

export function getDataFreshness(timestamp: string): FreshnessInfo {
  if (!timestamp) {
    return { status: 'stale', label: '🔴 过时', ageMinutes: Infinity };
  }

  const parsed = new Date(timestamp).getTime();
  if (isNaN(parsed)) {
    return { status: 'stale', label: '🔴 过时', ageMinutes: Infinity };
  }

  const ageMs = Date.now() - parsed;
  const ageMinutes = Math.floor(ageMs / 60000);

  let status: FreshnessStatus;
  let label: string;

  if (ageMs < FRESH_THRESHOLD_MS) {
    status = 'fresh';
    label = '🟢 实时';
  } else if (ageMs < DELAYED_THRESHOLD_MS) {
    status = 'delayed';
    label = '🟡 延迟';
  } else {
    status = 'stale';
    label = '🔴 过时';
  }

  return { status, label, ageMinutes };
}

export function getMarketFreshness(
  times: Record<string, string>,
): Record<string, FreshnessInfo> {
  const result: Record<string, FreshnessInfo> = {};
  for (const [market, timestamp] of Object.entries(times)) {
    result[market] = getDataFreshness(timestamp);
  }
  return result;
}
