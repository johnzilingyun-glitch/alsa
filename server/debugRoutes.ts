import { Router } from 'express';
import { logDebug, logError } from './stockLogger.js';
import fs from 'fs';
import path from 'path';

const router = Router();
const LOG_FILE = path.join(process.cwd(), 'logs', 'debug_records.log');

router.post('/logs/debug', (req, res) => {
    const { type, data } = req.body;
    logDebug(type || 'client_debug', data);
    res.json({ success: true });
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
