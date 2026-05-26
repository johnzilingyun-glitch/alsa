import { Router } from 'express';
import { logDebug, logError } from './stockLogger.js';
import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import { gatewayGenerate, gatewayStatus } from './llmGateway.js';

const router = Router();
const LOG_FILE = path.join(process.cwd(), 'logs', 'debug_records.log');


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



// ── Debug log routes ───────────────────────────────────────────────────────

router.post('/logs/debug', (req, res) => {
    const { type, data } = req.body;
    logDebug(type || 'client_debug', data);
    res.json({ success: true });
});

router.post('/bridge/generate', async (req, res) => {
    const { params, model, config } = req.body || {};
    const startTime = Date.now();

    logDebug('gateway_bridge_start', { model, paramSize: JSON.stringify(params).length });
    console.log('[LLMGateway] POST /copilot/generate - model:', model);

    const prompt = extractPromptText(params);
    if (!prompt) {
        logDebug('gateway_bridge_error', { error: 'no_prompt' });
        res.status(400).json({ success: false, error: '请求缺少可解析的 prompt 内容。' });
        return;
    }

    const targetModel = model || 'gemini-3.1-flash-lite-preview';

    try {
        const result = await gatewayGenerate(
            prompt,
            targetModel,
            (event, data) => logDebug(event, data as any),
            config
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
        logError(err, 'llm_bridge_generate');
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

router.get('/debug/config', (req, res) => {
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

// ── Update .env keys ───────────────────────────────────────────────────────
const ALLOWED_ENV_KEYS = new Set(['DEEPSEEK_API_KEY', 'GEMINI_API_KEY', 'DEEPSEEK_MODEL', 'GEMINI_MODEL', 'DEFAULT_LLM_PROVIDER']);

router.post('/env/update', (req, res) => {
    const { updates } = req.body;
    if (!updates || typeof updates !== 'object') {
        return res.status(400).json({ error: 'Missing updates object' });
    }

    // Only allow whitelisted keys
    const safeUpdates: Record<string, string> = {};
    for (const [key, value] of Object.entries(updates)) {
        if (!ALLOWED_ENV_KEYS.has(key)) continue;
        if (typeof value !== 'string') continue;
        safeUpdates[key] = value;
    }

    if (Object.keys(safeUpdates).length === 0) {
        return res.json({ success: true, message: 'No valid keys to update' });
    }

    try {
        const envPath = path.join(process.cwd(), '.env.runtime');
        let envContent = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf8') : '';

        for (const [key, value] of Object.entries(safeUpdates)) {
            const regex = new RegExp(`^${key}=.*$`, 'm');
            if (regex.test(envContent)) {
                envContent = envContent.replace(regex, `${key}=${value}`);
            } else {
                envContent = envContent.trimEnd() + `\n${key}=${value}`;
            }
            // Also update process.env in-memory
            process.env[key] = value;
        }

        fs.writeFileSync(envPath, envContent, 'utf8');
        logDebug('env_update', { keys: Object.keys(safeUpdates) });
        res.json({ success: true, updated: Object.keys(safeUpdates) });
    } catch (error) {
        logError(error, 'env_update');
        res.status(500).json({ error: 'Failed to update .env.runtime' });
    }
});

export default router;
