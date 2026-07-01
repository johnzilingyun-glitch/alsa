import type { Request, Response, NextFunction } from 'express';

export type RateLimitEnv = Partial<Record<string, string | undefined>>;

export interface RateLimitPolicy {
  windowMs: number;
  maxRequests: number;
}

interface Bucket {
  resetAt: number;
  count: number;
}

const buckets = new Map<string, Bucket>();

function parsePositiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export function getRateLimitPolicy(env: RateLimitEnv = process.env): RateLimitPolicy {
  return {
    windowMs: parsePositiveInt(env.API_RATE_LIMIT_WINDOW_MS, 60_000),
    maxRequests: parsePositiveInt(env.API_RATE_LIMIT_MAX, 300),
  };
}

export function getRateLimitKey(req: Pick<Request, 'ip' | 'headers'>): string {
  const forwardedFor = req.headers['x-forwarded-for'];
  const forwardedIp = Array.isArray(forwardedFor) ? forwardedFor[0] : forwardedFor?.split(',')[0];
  return (forwardedIp || req.ip || 'unknown').trim();
}

export function checkRateLimit(key: string, policy: RateLimitPolicy, now: number = Date.now()): { allowed: boolean; remaining: number; resetAt: number } {
  const existing = buckets.get(key);
  const bucket = !existing || existing.resetAt <= now
    ? { count: 0, resetAt: now + policy.windowMs }
    : existing;

  bucket.count += 1;
  buckets.set(key, bucket);

  const remaining = Math.max(policy.maxRequests - bucket.count, 0);
  return {
    allowed: bucket.count <= policy.maxRequests,
    remaining,
    resetAt: bucket.resetAt,
  };
}

export function resetRateLimitBuckets(): void {
  buckets.clear();
}

export function createRateLimiter(policy: RateLimitPolicy = getRateLimitPolicy()) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const result = checkRateLimit(getRateLimitKey(req), policy);
    const retryAfterSeconds = Math.max(Math.ceil((result.resetAt - Date.now()) / 1000), 1);

    res.setHeader('X-RateLimit-Limit', String(policy.maxRequests));
    res.setHeader('X-RateLimit-Remaining', String(result.remaining));
    res.setHeader('X-RateLimit-Reset', String(Math.ceil(result.resetAt / 1000)));

    if (!result.allowed) {
      res.setHeader('Retry-After', String(retryAfterSeconds));
      res.status(429).json({ success: false, error: 'RATE_LIMITED', retryAfter: retryAfterSeconds });
      return;
    }

    next();
  };
}
