import { describe, expect, it } from 'vitest';
import {
  buildSocketCorsOptions,
  getServerHost,
  isDiagnosticsEnabled,
  shouldRequireApiToken,
  validateApiToken,
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

  it('keeps diagnostics disabled unless explicitly enabled', () => {
    expect(isDiagnosticsEnabled({ NODE_ENV: 'production' })).toBe(false);
    expect(isDiagnosticsEnabled({ NODE_ENV: 'production', ENABLE_DIAGNOSTICS: 'true' })).toBe(true);
  });

  it('restricts Socket.IO origins to configured allowlist', () => {
    const options = buildSocketCorsOptions({ ALLOWED_ORIGINS: 'http://localhost:5173,https://alsa.example' });

    expect(options.origin).toEqual(['http://localhost:5173', 'https://alsa.example']);
  });
});
