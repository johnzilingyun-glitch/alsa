import { Router } from 'express';
import { logDebug, logError } from './stockLogger.js';
import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { gatewayGenerate, gatewayStatus } from './llmGateway.js';
import {
  startDeviceFlow,
  pollDeviceFlow,
  saveGithubToken,
  clearGithubToken,
  getCopilotAuthStatus,
} from './copilotAuth.js';

const router = Router();
const LOG_FILE = path.join(process.cwd(), 'logs', 'debug_records.log');

// Kept for backward compatibility — still exported and tested
function getGhCliToken(): string | null {
    try {
        const token = execSync('gh auth token', { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
        if (token) return token;
    } catch {
        // ignore
    }
    return null;
}

export function buildGithubTokenCandidates(env: NodeJS.ProcessEnv = process.env, ghToken?: string | null): string[] {
    const tokenList = [
        env.COPILOT_GITHUB_TOKEN,
        env.GH_TOKEN,
        env.GITHUB_TOKEN,
        ghToken,
    ]
        .map(v => (typeof v === 'string' ? v.trim() : ''))
        .filter(Boolean);

    return Array.from(new Set(tokenList));
}

export function isBadCredentialsError(status: number, message: string): boolean {
    const text = (message || '').toLowerCase();
    return status === 401 || text.includes('bad credentials') || text.includes('invalid token') || text.includes('authentication failed');
}

export function getCliModelCandidates(targetModel: string): string[] {
    if (targetModel === 'copilot_auto') {
        return ['claude-opus-4.6', 'claude-sonnet-4.6', 'gpt-5.4'];
    }
    return [targetModel];
}

function extractPromptText(params: any): string {
    const contents = params?.contents;
    if (typeof contents === 'string') return contents;
    if (Array.isArray(contents)) {
        return contents
            .map((c: any) => {
                if (typeof c === 'string') return c;
                const parts = c?.parts;
                if (Array.isArray(parts)) {
                    return parts.map((p: any) => (typeof p?.text === 'string' ? p.text : '')).join('\n');
                }
                return '';
            })
            .filter(Boolean)
            .join('\n\n');
    }
    return '';
}

export function normalizeCopilotModel(model: string): string {
    const key = (model || '').trim().toLowerCase();
    const aliasMap: Record<string, string> = {
        'auto': 'copilot_auto',
        'copilot_auto': 'copilot_auto',
        'gpt-5': 'gpt-5.4',
        'gpt5': 'gpt-5.4',
        'gpt-5.4': 'gpt-5.4',
        'gpt5.4': 'gpt-5.4',
        'gpt-5.2': 'gpt-5.2',
        'gpt-5-mini': 'gpt-5-mini',
        'gpt5-mini': 'gpt-5-mini',
        'gpt-5.4-mini': 'gpt-5.4-mini',
        'gpt5.4-mini': 'gpt-5.4-mini',
        'gpt-4.1': 'gpt-4.1',
        'gpt-4.1-mini': 'gpt-4.1-mini',
        'gpt-4o-mini': 'gpt-4o-mini',
        'o4-mini': 'o4-mini',
        'claude ops 4.6': 'claude-opus-4.6',
        'claude-ops-4.6': 'claude-opus-4.6',
        'claude_opus_4_6': 'claude-opus-4.6',
        'claude-opus-4.1': 'claude-opus-4.6',
        'claude-opus-4-1': 'claude-opus-4.6',
        'claude-opus-4.5': 'claude-opus-4.5',
        'claude-opus-4.6': 'claude-opus-4.6',
        'claude-opus-4.7': 'claude-opus-4.7',
        'claude-sonnet-4': 'claude-sonnet-4.6',
        'claude-sonnet-4.5': 'claude-sonnet-4.5',
        'claude-sonnet-4.6': 'claude-sonnet-4.6',
        'claude-haiku-4.5': 'claude-haiku-4.5',
    };
    return aliasMap[key] || model;
}

// ── Copilot OAuth device flow ──────────────────────────────────────────────

// Step 1: Start device flow — returns user_code + verification_uri to show in UI
router.post('/copilot/auth/start', async (_req, res) => {
    try {
        const flow = await startDeviceFlow();
        logDebug('copilot_auth_start', { user_code: flow.user_code });
        res.json({ success: true, ...flow });
    } catch (err: any) {
        logError(err, 'copilot_auth_start');
        res.status(500).json({ success: false, error: err?.message || 'Device flow failed' });
    }
});

// Step 2: Poll — called repeatedly by frontend until success/expired
router.get('/copilot/auth/poll', async (req, res) => {
    const { device_code } = req.query as { device_code?: string };
    if (!device_code) {
        res.status(400).json({ success: false, error: 'Missing device_code' });
        return;
    }
    try {
        const result = await pollDeviceFlow(device_code);
        if (result.status === 'success') {
            saveGithubToken(result.token);
            logDebug('copilot_auth_success', {});
        }
        res.json({ success: true, ...result });
    } catch (err: any) {
        logError(err, 'copilot_auth_poll');
        res.status(500).json({ success: false, error: err?.message });
    }
});

// Current auth status
router.get('/copilot/auth/status', async (_req, res) => {
    try {
        const status = await getCopilotAuthStatus();
        res.json({ success: true, ...status });
    } catch (err: any) {
        res.json({ success: true, authenticated: false, error: err?.message });
    }
});

// Logout: remove stored token
router.delete('/copilot/auth/token', (_req, res) => {
    clearGithubToken();
    logDebug('copilot_auth_logout', {});
    res.json({ success: true });
});

// ── Debug log routes ───────────────────────────────────────────────────────

router.post('/logs/debug', (req, res) => {
    const { type, data } = req.body;
    logDebug(type || 'client_debug', data);
    res.json({ success: true });
});

router.post('/copilot/generate', async (req, res) => {
    const { params, model } = req.body || {};
    const startTime = Date.now();

    logDebug('copilot_generate_start', { model, paramSize: JSON.stringify(params).length });
    console.log('[LLMGateway] POST /copilot/generate - model:', model);

    const prompt = extractPromptText(params);
    if (!prompt) {
        logDebug('copilot_generate_error', { error: 'no_prompt' });
        res.status(400).json({ success: false, error: '请求缺少可解析的 prompt 内容。' });
        return;
    }

    const targetModel = normalizeCopilotModel(model || 'copilot_auto');

    try {
        const result = await gatewayGenerate(
            prompt,
            targetModel,
            (event, data) => logDebug(event, data as any),
        );

        const elapsed = Date.now() - startTime;
        console.log(`[LLMGateway] ✅ ${result.provider}/${result.model} in ${elapsed}ms (${result.text.length} chars)`);

        res.json({
            success: true,
            model: result.model,
            via: result.provider,
            result: {
                text: result.text,
                candidates: [
                    {
                        index: 0,
                        finishReason: 'STOP',
                        content: { parts: [{ text: result.text }] },
                    },
                ],
                usageMetadata: { promptTokenCount: 0, candidatesTokenCount: 0, totalTokenCount: 0 },
            },
        });
    } catch (err: any) {
        const elapsed = Date.now() - startTime;
        logDebug('gateway_all_failed', { targetModel, elapsed, error: err?.message });
        logError(err, 'copilot_bridge_generate');
        res.status(502).json({ success: false, error: err?.message || 'LLM gateway failed' });
    }
});

// Gateway status: shows which providers are currently available
router.get('/gateway/status', (_req, res) => {
    res.json({ success: true, providers: gatewayStatus() });
});

// Diagnostic endpoint: test Gemini API key directly (bypasses all app retry/scheduler logic)
router.post('/test-gemini', async (req, res) => {
    const { apiKey, model = 'gemini-3.1-flash-lite-preview' } = req.body;
    if (!apiKey) {
        res.status(400).json({ error: 'Missing apiKey in request body' });
        return;
    }

    const maskedKey = `${apiKey.substring(0, 8)}...${apiKey.substring(apiKey.length - 4)}`;
    logDebug('test_gemini_start', { model, apiKey: maskedKey });

    try {
        // Step 1: Test model metadata (no quota cost)
        const metaRes = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}?key=${apiKey}`);
        const metaBody = await metaRes.text();
        logDebug('test_gemini_model_meta', { status: metaRes.status, ok: metaRes.ok, body: metaBody.substring(0, 500) });

        if (!metaRes.ok) {
            res.json({
                success: false,
                step: 'model_meta',
                status: metaRes.status,
                detail: metaBody.substring(0, 500),
                diagnosis: metaRes.status === 404 ? `Model "${model}" does not exist. Change model in settings.`
                         : metaRes.status === 403 ? 'API key not authorized. Enable Generative Language API.'
                         : metaRes.status === 400 ? 'Invalid API key format.'
                         : `Unexpected error: HTTP ${metaRes.status}`,
            });
            return;
        }

        // Step 2: Test generateContent (costs 1 RPM + 1 RPD)
        const genRes = await fetch(
            `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    contents: [{ parts: [{ text: 'Say "ok" in one word.' }] }],
                }),
            }
        );
        const genBody = await genRes.text();
        logDebug('test_gemini_generate', { status: genRes.status, ok: genRes.ok, body: genBody.substring(0, 500) });

        if (!genRes.ok) {
            let diagnosis = `HTTP ${genRes.status}`;
            if (genRes.status === 429) {
                try {
                    const parsed = JSON.parse(genBody);
                    const errStatus = parsed?.error?.status;
                    diagnosis = errStatus === 'RESOURCE_EXHAUSTED'
                        ? 'RPD (daily quota) exhausted. Wait until tomorrow or use a different API key.'
                        : 'RPM (per-minute) rate limit hit. Wait 60 seconds and retry.';
                } catch { diagnosis = '429 - quota or rate limit'; }
            }
            res.json({ success: false, step: 'generate', status: genRes.status, detail: genBody.substring(0, 500), diagnosis });
            return;
        }

        res.json({ success: true, step: 'generate', status: genRes.status, detail: 'API key and model are working correctly.' });
    } catch (err: any) {
        logError(err, 'test_gemini');
        res.json({ success: false, step: 'network', detail: err?.message || String(err), diagnosis: 'Network error reaching Gemini API.' });
    }
});

router.get('/logs/debug', (req, res) => {
    try {
        if (fs.existsSync(LOG_FILE)) {
            const content = fs.readFileSync(LOG_FILE, 'utf8');
            res.send(content);
        } else {
            res.send('No debug logs found.');
        }
    } catch (error) {
        logError(error, 'read_debug_logs');
        res.status(500).send('Error reading logs');
    }
});

router.delete('/logs/debug', (req, res) => {
    try {
        if (fs.existsSync(LOG_FILE)) {
            fs.writeFileSync(LOG_FILE, '');
            res.json({ success: true, message: 'Logs cleared' });
        } else {
            res.json({ success: true, message: 'No file to clear' });
        }
    } catch (error) {
        logError(error, 'clear_debug_logs');
        res.status(500).json({ error: 'Failed to clear logs' });
    }
});

export default router;
