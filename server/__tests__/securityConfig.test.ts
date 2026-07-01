import { describe, expect, it } from 'vitest';
import {
  buildSocketCorsOptions,
  getServerHost,
  isDiagnosticsEnabled,
  resolveApiToken,
  shouldBypassGatewayApiToken,
  shouldRequireApiToken,
  validateApiToken,
  validateSocketToken,
} from '../securityConfig';

describe('securityConfig', () => {
  it('defaults to loopback binding', () => {
    expect(getServerHost({})).toBe('127.0.0.1');
  });

  it('requires an API token outside development when configured', () => {
    expect(shouldRequireApiToken({ NODE_ENV: 'production', API_TOKEN: 'secret' })).toBe(true);
    expect(validateApiToken('Bearer secret', { NODE_ENV: 'production', API_TOKEN: 'secret' })).toBe(true);
    expect(validateApiToken('Bearer wrong', { NODE_ENV: 'production', API_TOKEN: 'secret' })).toBe(false);
  });

  it('fails fast when production API_TOKEN is missing', () => {
    expect(() => resolveApiToken({ NODE_ENV: 'production' })).toThrow(/API_TOKEN/);
  });

  it('returns configured API_TOKEN without generating a runtime secret', () => {
    expect(resolveApiToken({ NODE_ENV: 'production', API_TOKEN: 'configured-token' })).toBe('configured-token');
  });

  it('keeps diagnostics disabled unless explicitly enabled', () => {
    expect(isDiagnosticsEnabled({ NODE_ENV: 'production' })).toBe(false);
    expect(isDiagnosticsEnabled({ NODE_ENV: 'production', ENABLE_DIAGNOSTICS: 'true' })).toBe(true);
  });


  it('keeps gateway token bypass explicit for public and user-authenticated routes', () => {
    expect(shouldBypassGatewayApiToken('/health')).toBe(true);
    expect(shouldBypassGatewayApiToken('/auth/token')).toBe(true);
    expect(shouldBypassGatewayApiToken('/analysis/jobs')).toBe(true);
    expect(shouldBypassGatewayApiToken('/diagnostics/logs/debug')).toBe(false);
    expect(shouldBypassGatewayApiToken('/unknown')).toBe(false);
  });

  it('validates Socket.IO handshake tokens when gateway token auth is enabled', () => {
    const env = { NODE_ENV: 'production', API_TOKEN: 'socket-secret' };

    expect(validateSocketToken('socket-secret', env)).toBe(true);
    expect(validateSocketToken('Bearer socket-secret', env)).toBe(true);
    expect(validateSocketToken('wrong', env)).toBe(false);
    expect(validateSocketToken(undefined, env)).toBe(false);
  });

  it('allows Socket.IO without token only when gateway token auth is disabled', () => {
    expect(validateSocketToken(undefined, { NODE_ENV: 'test' })).toBe(true);
  });

  it('restricts Socket.IO origins to configured allowlist', () => {
    const options = buildSocketCorsOptions({ ALLOWED_ORIGINS: 'http://localhost:5173,https://alsa.example' });

    expect(options.origin).toEqual(['http://localhost:5173', 'https://alsa.example']);
  });
});
