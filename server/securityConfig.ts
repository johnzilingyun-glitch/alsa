import crypto from 'crypto';
import fs from 'fs';
import path from 'path';

function _ensureApiToken() {
  let token = process.env.API_TOKEN;
  if (!token) {
    const runtimeEnvPath = path.resolve(process.cwd(), '.env.runtime');
    if (fs.existsSync(runtimeEnvPath)) {
      const content = fs.readFileSync(runtimeEnvPath, 'utf8');
      const match = content.match(/^API_TOKEN=(.*)$/m);
      if (match) {
        token = match[1].trim();
        process.env.API_TOKEN = token;
      }
    }

    if (!token) {
      token = crypto.randomBytes(32).toString('base64url');
      process.env.API_TOKEN = token;
      fs.appendFileSync(runtimeEnvPath, `\nAPI_TOKEN=${token}\n`);
      console.log('\n' + '='.repeat(50));
      console.log(`🔒 Generated secure API_TOKEN: ${token}`);
      console.log(`   (Saved to ${runtimeEnvPath})`);
      console.log('='.repeat(50) + '\n');
    }
  }
}
_ensureApiToken();

export type ServerEnv = Partial<Record<string, string | undefined>>;

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
