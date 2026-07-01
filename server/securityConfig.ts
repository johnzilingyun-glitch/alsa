import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

export type ServerEnv = Partial<Record<string, string | undefined>>;

function isProductionEnv(env: ServerEnv = process.env): boolean {
  return env.NODE_ENV === 'production';
}

export function resolveApiToken(env: ServerEnv = process.env): string | undefined {
  if (env.API_TOKEN) return env.API_TOKEN;

  if (isProductionEnv(env)) {
    throw new Error('API_TOKEN must be explicitly configured in production');
  }

  const runtimeEnvPath = path.resolve(process.cwd(), '.env.runtime');
  if (fs.existsSync(runtimeEnvPath)) {
    const content = fs.readFileSync(runtimeEnvPath, 'utf8');
    const match = content.match(/^API_TOKEN=(.*)$/m);
    if (match?.[1]?.trim()) {
      return match[1].trim();
    }
  }

  const token = crypto.randomBytes(32).toString('base64url');
  fs.appendFileSync(runtimeEnvPath, `\nAPI_TOKEN=${token}\n`);
  return token;
}

function _ensureApiToken() {
  process.env.API_TOKEN = resolveApiToken();
}
_ensureApiToken();

function parseBoolean(value: string | undefined): boolean {
  return value === 'true' || value === '1' || value === 'yes';
}

export function getServerPort(env: ServerEnv = process.env): number {
  const parsed = Number(env.PORT);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 3000;
}

export function getServerHost(env: ServerEnv = process.env): string {
  return env.HOST || env.SERVER_HOST || '127.0.0.1';
}

export function getAllowedOrigins(env: ServerEnv = process.env): string[] {
  const configured = env.ALLOWED_ORIGINS || env.CORS_ORIGIN || 'http://localhost:5173,http://127.0.0.1:5173';
  return configured
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
}

export function buildSocketCorsOptions(env: ServerEnv = process.env): { origin: string[]; credentials: boolean } {
  return { origin: getAllowedOrigins(env), credentials: true };
}

export function isDiagnosticsEnabled(env: ServerEnv = process.env): boolean {
  return parseBoolean(env.ENABLE_DIAGNOSTICS);
}


const PUBLIC_API_PATHS = new Set(['/health', '/ping-early']);
const JWT_OR_PROXY_API_PREFIXES = [
  '/auth',
  '/admin',
  '/alerts',
  '/analysis',
  '/backtest',
  '/brain',
  '/diagnostics',
  '/feishu',
  '/history',
  '/journal',
  '/llm',
  '/market',
  '/mock-trading',
  '/predictions',
  '/sector',
  '/stock',
  '/ths',
  '/watchlist',
];

export function isPublicApiPath(pathname: string): boolean {
  return PUBLIC_API_PATHS.has(pathname);
}

export function isUserOrProxyAuthenticatedApiPath(pathname: string): boolean {
  return JWT_OR_PROXY_API_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export function shouldBypassGatewayApiToken(pathname: string): boolean {
  return isPublicApiPath(pathname) || isUserOrProxyAuthenticatedApiPath(pathname);
}

export function shouldRequireApiToken(env: ServerEnv = process.env): boolean {
  return Boolean(env.API_TOKEN) && env.NODE_ENV !== 'test';
}

export function validateApiToken(authHeader: string | undefined, env: ServerEnv = process.env): boolean {
  const expected = env.API_TOKEN;
  if (!expected) return false;
  if (!authHeader) return false;

  const token = authHeader.startsWith('Bearer ')
    ? authHeader.slice('Bearer '.length)
    : authHeader;
  if (!token || !expected) return false;
  const a = Buffer.from(token);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

export function getPythonAuthHeaders(env: ServerEnv = process.env): Record<string, string> {
  const token = env.API_TOKEN;
  if (!token) return {};
  return { 'Authorization': `Bearer ${token}` };
}
