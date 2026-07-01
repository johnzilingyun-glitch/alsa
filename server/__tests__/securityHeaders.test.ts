import { describe, expect, it, vi } from 'vitest';
import { applySecurityHeaders, createRequestId } from '../securityHeaders';

describe('securityHeaders', () => {
  it('keeps a safe inbound request id', () => {
    expect(createRequestId('req_123-abc')).toBe('req_123-abc');
  });

  it('replaces unsafe inbound request ids', () => {
    const requestId = createRequestId('bad id with spaces');

    expect(requestId).not.toBe('bad id with spaces');
    expect(requestId).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('sets hardened security headers', () => {
    const headers = new Map<string, string>();
    const req = { header: vi.fn().mockReturnValue('req-safe') };
    const res = {
      locals: {},
      setHeader: vi.fn((name: string, value: string) => headers.set(name, value)),
    };
    const next = vi.fn();

    applySecurityHeaders(req as any, res as any, next);

    expect(headers.get('X-Request-Id')).toBe('req-safe');
    expect(headers.get('X-Content-Type-Options')).toBe('nosniff');
    expect(headers.get('X-Frame-Options')).toBe('DENY');
    expect(headers.get('Permissions-Policy')).toContain('camera=()');
    expect(headers.get('Content-Security-Policy')).toContain("frame-ancestors 'none'");
    expect(next).toHaveBeenCalledOnce();
  });
});
