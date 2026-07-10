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

    const response = await gatewayGenerate(prompt, model, (event, data) => console.log(`[Gateway] ${event}`, data), config);
    const generatedText = response.text;
    
    // Ensure we always have a fallback numeric structure, even if API returned empty
    const usage = response.usageMetadata || {
      promptTokenCount: 0,
      candidatesTokenCount: 0,
      totalTokenCount: 0
    };
    
    return res.json({
      success: true,
      via: 'server-llm-gateway',
      model: response.model,
      provider: response.provider,
      result: {
        text: generatedText,
        candidates: [{ content: { parts: [{ text: generatedText }] } }],
        usageMetadata: usage
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return res.status(502).json({ success: false, error: message });
  }
});

router.post('/llm/models', async (_req, res) => {
  const geminiDeepseekModels = [
    { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash', description: 'Server-managed Gemini model', status: 'available' },
    { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro', description: 'Server-managed Gemini model', status: 'available' },
    { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', description: 'Server-managed Gemini model', status: 'available' },
    { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', description: 'Server-managed Gemini model', status: 'available' },
    { id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro', description: 'Server-managed fallback model', status: 'available' },
    { id: 'deepseek-v4-flash', name: 'DeepSeek V4 Flash', description: 'Server-managed fallback model', status: 'available' },
  ];

  const CURATED_OPENROUTER_IDS = new Set([
    'tencent/hy3:free',
    'anthropic/claude-3.5-sonnet',
    'openai/gpt-4o',
    'google/gemini-2.0-flash-001',
    'meta-llama/llama-3.3-70b-instruct',
    'mistralai/mistral-7b-instruct',
  ]);

  let openrouterModels: Array<{ id: string; name: string; description: string; status: string }> = [];

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);

    const resp = await fetch('https://openrouter.ai/api/v1/models', {
      signal: controller.signal,
    });
    clearTimeout(timer);

    if (resp.ok) {
      const body = (await resp.json()) as { data?: Array<{ id: string; name?: string; description?: string }> };
      const rawModels = body?.data ?? [];

      const matched = rawModels.filter((m) => CURATED_OPENROUTER_IDS.has(m.id));
      const matchedIds = new Set(matched.map((m) => m.id));

      if (!matchedIds.has('tencent/hy3:free')) {
        openrouterModels.push({
          id: 'tencent/hy3:free',
          name: 'Tencent: Hy3',
          description: 'Tencent Hyperion 3 via OpenRouter',
          status: 'available',
        });
      }

      const curated = matched.map((m) => ({
        id: m.id,
        name: m.name || m.id,
        description: m.description || `${m.id} via OpenRouter`,
        status: 'available' as const,
      }));

      curated.sort((a, b) => {
        if (a.id === 'tencent/hy3:free') return -1;
        if (b.id === 'tencent/hy3:free') return 1;
        return 0;
      });

      openrouterModels = [...openrouterModels, ...curated.filter((m) => m.id !== 'tencent/hy3:free')];
    } else {
      throw new Error(`OpenRouter models API returned ${resp.status}`);
    }
  } catch {
    openrouterModels = [
      { id: 'tencent/hy3:free', name: 'Tencent: Hy3', description: 'Tencent Hyperion 3 model via OpenRouter', status: 'available' },
      { id: 'anthropic/claude-3.5-sonnet', name: 'Anthropic: Claude 3.5 Sonnet', description: 'Claude 3.5 Sonnet via OpenRouter', status: 'available' },
      { id: 'openai/gpt-4o', name: 'OpenAI: GPT-4o', description: 'GPT-4o via OpenRouter', status: 'available' },
      { id: 'google/gemini-2.0-flash-001', name: 'Google: Gemini 2.0 Flash', description: 'Gemini 2.0 Flash via OpenRouter', status: 'available' },
      { id: 'meta-llama/llama-3.3-70b-instruct', name: 'Meta: Llama 3.3 70B', description: 'Llama 3.3 70B Instruct via OpenRouter', status: 'available' },
      { id: 'mistralai/mistral-7b-instruct', name: 'Mistral: 7B Instruct', description: 'Mistral 7B Instruct via OpenRouter', status: 'available' },
    ];
  }

  return res.json({
    success: true,
    models: [...geminiDeepseekModels, ...openrouterModels],
  });
});

function extractPrompt(params: any): string {
  if (typeof params?.prompt === 'string') return params.prompt;
  if (typeof params?.contents === 'string') return params.contents;
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
    const config = req.body?.config ?? {};
    if (!prompt.trim()) {
      return res.status(400).json({ success: false, error: 'prompt is required' });
    }

    const result = await gatewayGenerate(prompt, model, () => {}, config);
    return res.json({ success: true, data: result });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return res.status(502).json({ success: false, error: message });
  }
});

export default router;
