import { Router } from 'express';
import { gatewayGenerate } from '../llmGateway.js';

const router = Router();


router.post('/llm/generate', async (req, res) => {
  try {
    const params = req.body?.params ?? {};
    const prompt = extractPrompt(params);
    const model = typeof req.body?.model === 'string' ? req.body.model : String(params?.model || '');
    const config = req.body?.config ?? {};
    if (!prompt.trim()) {
      return res.status(400).json({ success: false, error: 'prompt is required' });
    }

    const text = await gatewayGenerate(prompt, model, () => {}, config);
    return res.json({
      success: true,
      via: 'server-llm-gateway',
      model,
      result: {
        text,
        candidates: [{ content: { parts: [{ text }] } }],
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return res.status(502).json({ success: false, error: message });
  }
});

router.post('/llm/models', async (_req, res) => {
  return res.json({
    success: true,
    models: [
      { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash', description: 'Server-managed Gemini model', status: 'available' },
      { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro', description: 'Server-managed Gemini model', status: 'available' },
      { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', description: 'Server-managed Gemini model', status: 'available' },
      { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', description: 'Server-managed Gemini model', status: 'available' },
      { id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro', description: 'Server-managed fallback model', status: 'available' },
      { id: 'deepseek-v4-flash', name: 'DeepSeek V4 Flash', description: 'Server-managed fallback model', status: 'available' },
    ],
  });
});

function extractPrompt(params: any): string {
  if (typeof params?.prompt === 'string') return params.prompt;
  const contents = Array.isArray(params?.contents) ? params.contents : [];
  return contents
    .flatMap((content: any) => Array.isArray(content?.parts) ? content.parts : [])
    .map((part: any) => typeof part?.text === 'string' ? part.text : '')
    .filter(Boolean)
    .join('\n');
}

router.post('/llm/fallback', async (req, res) => {
  try {
    const prompt = typeof req.body?.prompt === 'string' ? req.body.prompt : '';
    const model = typeof req.body?.model === 'string' ? req.body.model : '';
    if (!prompt.trim()) {
      return res.status(400).json({ success: false, error: 'prompt is required' });
    }

    const result = await gatewayGenerate(prompt, model, () => {});
    return res.json({ success: true, data: result });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return res.status(502).json({ success: false, error: message });
  }
});

export default router;
