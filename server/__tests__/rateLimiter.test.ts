import { describe, expect, it, vi, beforeEach } from 'vitest';
import { checkRateLimit, createRateLimiter, getRateLimitKey, getRateLimitPolicy, resetRateLimitBuckets } from '../rateLimiter';

describe('rateLimiter', () => {
  beforeEach(() => {
    resetRateLimitBuckets();
  });

  it('builds policy from environment with safe defaults', () => {
    expect(getRateLimitPolicy({})).toEqual({ windowMs: 60_000, maxRequests: 300 });
    expect(getRateLimitPolicy({ API_RATE_LIMIT_WINDOW_MS: '1000', API_RATE_LIMIT_MAX: '2' })).toEqual({
      windowMs: 1000,
      maxRequests: 2,
    });
  });

  it('prefers first forwarded IP for keying behind proxies', () => {
    const key = getRateLimitKey({ ip: '127.0.0.1', headers: { 'x-forwarded-for': '203.0.113.10, 10.0.0.1' } } as any);

    expect(key).toBe('203.0.113.10');
  });

  it('blocks requests after the configured bucket is exhausted', () => {
    const policy = { windowMs: 1000, maxRequests: 2 };

    expect(checkRateLimit('client', policy, 100).allowed).toBe(true);
    expect(checkRateLimit('client', policy, 200).allowed).toBe(true);
    expect(checkRateLimit('client', policy, 300).allowed).toBe(false);
    expect(checkRateLimit('client', policy, 1200).allowed).toBe(true);
  });

  it('returns 429 with retry metadata when middleware limit is exceeded', () => {
    const middleware = createRateLimiter({ windowMs: 1000, maxRequests: 1 });
    const req = { ip: '127.0.0.1', headers: {} };
    const headers = new Map<string, string>();
    const res = {
      setHeader: vi.fn((name: string, value: string) => headers.set(name, value)),
      status: vi.fn().mockReturnThis(),
      json: vi.fn(),
    };
    const next = vi.fn();

    middleware(req as any, res as any, next);
    middleware(req as any, res as any, next);

    expect(next).toHaveBeenCalledOnce();
    expect(res.status).toHaveBeenCalledWith(429);
    expect(res.json).toHaveBeenCalledWith(expect.objectContaining({ error: 'RATE_LIMITED' }));
    expect(headers.get('Retry-After')).toBeDefined();
  });
});
