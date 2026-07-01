const REDACTED = '[REDACTED]';

const SENSITIVE_NAMES = new Set([
  'api_key',
  'apikey',
  'authorization',
  'cookie',
  'jwt',
  'key',
  'password',
  'refresh_token',
  'secret',
  'session',
  'token',
  'x-admin-token',
]);

export function isSensitiveName(name: string): boolean {
  const normalized = name.trim().toLowerCase().replace(/[-.]/g, '_');
  return SENSITIVE_NAMES.has(normalized) || normalized.endsWith('_token') || normalized.endsWith('_secret');
}

export function sanitizeUrlForLog(url: string): string {
  try {
    const parsed = new URL(url, 'http://alsa.local');
    for (const key of Array.from(parsed.searchParams.keys())) {
      if (isSensitiveName(key)) {
        parsed.searchParams.set(key, REDACTED);
      }
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return sanitizeLogValue(url);
  }
}

export function sanitizeLogValue(value: unknown): string {
  return String(value)
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]+/gi, `$1${REDACTED}`)
    .replace(/((?:api[_-]?key|authorization|cookie|jwt|password|secret|session|token)\s*[=:]\s*)[^&\s,;]+/gi, `$1${REDACTED}`);
}

export function formatHttpLog(method: string, url: string, requestId?: string, durationMs?: number): string {
  const parts = [method.toUpperCase(), sanitizeUrlForLog(url)];
  if (requestId) parts.push(`request_id=${sanitizeLogValue(requestId)}`);
  if (durationMs !== undefined) parts.push(`duration_ms=${durationMs}`);
  return parts.join(' ');
}
