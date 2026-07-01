import crypto from 'crypto';
import type { Request, Response, NextFunction } from 'express';

const REQUEST_ID_HEADER = 'X-Request-Id';

export function createRequestId(existingId?: string): string {
  const normalized = existingId?.trim();
  if (normalized && /^[a-zA-Z0-9._:-]{1,128}$/.test(normalized)) {
    return normalized;
  }
  return crypto.randomUUID();
}

export function applySecurityHeaders(req: Request, res: Response, next: NextFunction): void {
  const requestId = createRequestId(req.header(REQUEST_ID_HEADER));
  res.locals.requestId = requestId;
  res.setHeader(REQUEST_ID_HEADER, requestId);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
  res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  res.setHeader(
    'Content-Security-Policy',
    "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'",
  );
  next();
}
