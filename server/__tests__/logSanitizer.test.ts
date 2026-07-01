import { describe, expect, it } from 'vitest';
import { formatHttpLog, isSensitiveName, sanitizeLogValue, sanitizeUrlForLog } from '../logSanitizer';

describe('logSanitizer', () => {
  it('detects sensitive parameter names', () => {
    expect(isSensitiveName('token')).toBe(true);
    expect(isSensitiveName('api-key')).toBe(true);
    expect(isSensitiveName('refresh_token')).toBe(true);
    expect(isSensitiveName('symbol')).toBe(false);
  });

  it('redacts sensitive URL query parameters while preserving safe values', () => {
    const sanitized = sanitizeUrlForLog('/api/analysis?symbol=AAPL&token=abc123&api_key=secret&market=US-Share');

    expect(sanitized).toContain('symbol=AAPL');
    expect(sanitized).toContain('market=US-Share');
    expect(sanitized).toContain('token=%5BREDACTED%5D');
    expect(sanitized).toContain('api_key=%5BREDACTED%5D');
    expect(sanitized).not.toContain('abc123');
    expect(sanitized).not.toContain('secret');
  });

  it('redacts bearer tokens and key-value secrets in free-form logs', () => {
    const sanitized = sanitizeLogValue('Authorization: Bearer abc.def token=secret password=hunter2');

    expect(sanitized).toContain('[REDACTED]');
    expect(sanitized).not.toContain('abc.def');
    expect(sanitized).not.toContain('secret');
    expect(sanitized).not.toContain('hunter2');
  });

  it('formats request logs with request id and duration', () => {
    const log = formatHttpLog('get', '/api/foo?token=secret&symbol=MSFT', 'req_1', 512);

    expect(log).toContain('GET /api/foo?token=%5BREDACTED%5D&symbol=MSFT');
    expect(log).toContain('request_id=req_1');
    expect(log).toContain('duration_ms=512');
    expect(log).not.toContain('secret');
  });
});
