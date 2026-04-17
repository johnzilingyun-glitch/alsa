/**
 * GitHub Copilot Authentication & API
 *
 * Two independent concerns:
 *  1. OAuth Device Flow  — lets web users authenticate via browser, stores token on server
 *  2. Copilot Chat API   — uses a GitHub OAuth token to call the Copilot completions endpoint
 *
 * Token priority when making API calls:
 *   env COPILOT_GITHUB_TOKEN → env GH_TOKEN → env GITHUB_TOKEN
 *   → data/.github_token (written by device flow)
 *   → `gh auth token` (if gh CLI is installed)
 */

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';

// GitHub OAuth App used for device flow.
// Override with your own app via GITHUB_OAUTH_CLIENT_ID in .env
const CLIENT_ID = process.env.GITHUB_OAUTH_CLIENT_ID || '178c6fc778ccc68e1d6a';

const TOKEN_FILE = path.join(process.cwd(), 'data', '.github_token');

// ── Token storage ──────────────────────────────────────────────────────────

export function saveGithubToken(token: string): void {
  const dir = path.dirname(TOKEN_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(TOKEN_FILE, token.trim(), 'utf8');
}

export function loadGithubToken(): string | null {
  // 1. Explicit Copilot-specific env var (highest priority)
  if (process.env.COPILOT_GITHUB_TOKEN?.trim()) return process.env.COPILOT_GITHUB_TOKEN.trim();

  // 2. OAuth token saved by device flow (preferred over generic PAT — PATs are blocked by Copilot API)
  if (fs.existsSync(TOKEN_FILE)) {
    const tok = fs.readFileSync(TOKEN_FILE, 'utf8').trim();
    if (tok) return tok;
  }

  // 3. GitHub CLI OAuth token (if installed)
  try {
    const tok = execSync('gh auth token', {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
    if (tok) return tok;
  } catch {
    // gh CLI not installed or not authenticated
  }

  // 4. Generic PAT as last resort (likely blocked by Copilot API, but try anyway)
  if (process.env.GH_TOKEN?.trim()) return process.env.GH_TOKEN.trim();
  if (process.env.GITHUB_TOKEN?.trim()) return process.env.GITHUB_TOKEN.trim();

  return null;
}

export function clearGithubToken(): void {
  if (fs.existsSync(TOKEN_FILE)) fs.unlinkSync(TOKEN_FILE);
}

// ── Device Flow ────────────────────────────────────────────────────────────

export interface DeviceFlowStart {
  device_code: string;
  user_code: string;
  verification_uri: string;
  expires_in: number;
  interval: number;
}

export async function startDeviceFlow(): Promise<DeviceFlowStart> {
  const res = await fetch('https://github.com/login/device/code', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: CLIENT_ID, scope: 'read:user' }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub device flow init failed (${res.status}): ${body.slice(0, 200)}`);
  }

  return res.json() as Promise<DeviceFlowStart>;
}

export type PollResult =
  | { status: 'pending' }
  | { status: 'slow_down'; interval: number }
  | { status: 'expired' }
  | { status: 'error'; message: string }
  | { status: 'success'; token: string };

export async function pollDeviceFlow(deviceCode: string): Promise<PollResult> {
  const res = await fetch('https://github.com/login/oauth/access_token', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: CLIENT_ID,
      device_code: deviceCode,
      grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
    }),
  });

  const data = (await res.json()) as any;

  if (data.access_token) return { status: 'success', token: data.access_token };
  if (data.error === 'authorization_pending') return { status: 'pending' };
  if (data.error === 'slow_down') return { status: 'slow_down', interval: data.interval ?? 10 };
  if (data.error === 'expired_token') return { status: 'expired' };

  return { status: 'error', message: data.error_description || JSON.stringify(data) };
}

// ── Copilot API token exchange ─────────────────────────────────────────────

interface CopilotTokenCache {
  token: string;
  expiresAt: number; // ms since epoch
}

let _tokenCache: CopilotTokenCache | null = null;

export async function getCopilotApiToken(githubToken: string): Promise<string> {
  const now = Date.now();
  if (_tokenCache && _tokenCache.expiresAt > now + 30_000) {
    return _tokenCache.token; // still valid with 30s buffer
  }

  const res = await fetch('https://api.github.com/copilot_internal/v2/token', {
    headers: {
      Authorization: `token ${githubToken}`,
      Accept: 'application/json',
      'User-Agent': 'GitHubCopilotCLI/1.0',
      'X-Github-Api-Version': '2023-07-07',
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Copilot token exchange failed (${res.status}): ${body.slice(0, 300)}`);
  }

  const data = (await res.json()) as { token: string; expires_at: string };
  _tokenCache = {
    token: data.token,
    expiresAt: new Date(data.expires_at).getTime(),
  };
  return data.token;
}

// ── Copilot Chat completions ───────────────────────────────────────────────

const COPILOT_MODEL_MAP: Record<string, string> = {
  // Default: use best available Standard model
  copilot_auto:        'gpt-5.4',
  // UI alias → real CLI/API name (from `copilot models`)
  'gpt-5':             'gpt-5.4',
  'gpt-5.4':           'gpt-5.4',
  'gpt-5.2':           'gpt-5.2',
  'gpt-5-mini':        'gpt-5-mini',
  'gpt-5.4-mini':      'gpt-5.4-mini',
  'gpt-4.1':           'gpt-4.1',
  'claude-opus-4-1':   'claude-opus-4.6',   // old UI alias → latest Opus
  'claude-opus-4.5':   'claude-opus-4.5',
  'claude-opus-4.6':   'claude-opus-4.6',
  'claude-opus-4.7':   'claude-opus-4.7',
  'claude-sonnet-4':   'claude-sonnet-4.6', // prefer latest sonnet
  'claude-sonnet-4.6': 'claude-sonnet-4.6',
  'claude-sonnet-4.5': 'claude-sonnet-4.5',
  'claude-haiku-4.5':  'claude-haiku-4.5',
};

export function resolveCopilotModel(requested: string): string {
  return COPILOT_MODEL_MAP[requested] ?? requested;
}

export async function callCopilotChatApi(
  githubToken: string,
  prompt: string,
  requestedModel: string,
): Promise<string> {
  const copilotToken = await getCopilotApiToken(githubToken);
  const model = resolveCopilotModel(requestedModel);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60_000); // 60s REST timeout

  try {
    const res = await fetch('https://api.githubcopilot.com/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${copilotToken}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'Editor-Version': 'vscode/1.85.0',
        'Editor-Plugin-Version': 'copilot-chat/0.12.0',
        'Copilot-Integration-Id': 'vscode-chat',
        'User-Agent': 'GitHubCopilotChat/0.12.0',
      },
      body: JSON.stringify({
        model,
        messages: [
          {
            role: 'system',
            content:
              'You are a professional financial analyst. When the user requests structured output, respond ONLY with valid JSON.',
          },
          { role: 'user', content: prompt },
        ],
        temperature: 0.3,
        max_tokens: 16384,
        stream: false,
      }),
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Copilot API ${res.status}: ${body.slice(0, 300)}`);
    }

    const data = (await res.json()) as any;
    return data?.choices?.[0]?.message?.content ?? '';
  } catch (err) {
    clearTimeout(timer);
    throw err;
  }
}

// ── Auth status ────────────────────────────────────────────────────────────

export interface CopilotAuthStatus {
  authenticated: boolean;
  username?: string;
  hasSubscription?: boolean;
  tokenSource?: 'env' | 'file' | 'gh_cli';
}

export async function getCopilotAuthStatus(): Promise<CopilotAuthStatus> {
  const token = loadGithubToken();
  if (!token) return { authenticated: false };

  // Detect source for display (matches new loadGithubToken priority)
  const tokenSource: CopilotAuthStatus['tokenSource'] = process.env.COPILOT_GITHUB_TOKEN?.trim()
    ? 'env'
    : (fs.existsSync(TOKEN_FILE) && fs.readFileSync(TOKEN_FILE, 'utf8').trim())
    ? 'file'
    : 'gh_cli';

  try {
    const userRes = await fetch('https://api.github.com/user', {
      headers: { Authorization: `token ${token}`, Accept: 'application/json' },
    });
    if (!userRes.ok) return { authenticated: false };
    const user = (await userRes.json()) as any;

    try {
      await getCopilotApiToken(token);
      return { authenticated: true, username: user.login, hasSubscription: true, tokenSource };
    } catch {
      return { authenticated: true, username: user.login, hasSubscription: false, tokenSource };
    }
  } catch {
    return { authenticated: false };
  }
}
