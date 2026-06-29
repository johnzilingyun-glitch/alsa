import { Router } from 'express';
import axios from 'axios';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createAnalysisRepository } from '../repositories/analysisRepository.js';
import { gatewayGenerate } from '../llmGateway.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const axiosClient = axios.create({
  timeout: 5000,
});

const router = Router();
const repo = createAnalysisRepository();
const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || 'http://127.0.0.1:8001';
import { getPythonAuthHeaders } from '../securityConfig.js';


// ── Sector/Stock Report Download API ─────────────────────────────
// GET /reports/download?file=xxx_report.html  下载/alsa/reports下的HTML/PDF
router.get('/reports/download', async (req, res) => {
  const file = req.query.file as string;
  if (!file || !/^[\w.-]+\.(html|pdf)$/i.test(file)) {
    return res.status(400).json({ error: 'Invalid file name.' });
  }
  const reportsDir = path.resolve(__dirname, '../../reports');
  const filePath = path.join(reportsDir, file);
  if (!filePath.startsWith(reportsDir)) {
    return res.status(403).json({ error: 'Access denied.' });
  }
  if (!fs.existsSync(filePath)) {
    return res.status(404).json({ error: 'File not found.' });
  }
  res.download(filePath, file, err => {
    if (err) res.status(500).json({ error: 'Download failed.' });
  });
});

// ── Save Report to Local Disk ────────────────────────────────────
// POST /reports/save  保存研报HTML到本地reports目录做备份
router.post('/reports/save', async (req, res) => {
  const { filename, content } = req.body;
  if (!filename || !content) {
    return res.status(400).json({ error: 'Missing filename or content.' });
  }
  const safeName = filename.replace(/[^\w. -]/g, '_');
  const reportsDir = path.resolve(__dirname, '../../reports');
  if (!fs.existsSync(reportsDir)) {
    fs.mkdirSync(reportsDir, { recursive: true });
  }
  const filePath = path.join(reportsDir, safeName);
  if (!filePath.startsWith(reportsDir)) {
    return res.status(403).json({ error: 'Access denied.' });
  }
  try {
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`[Report] Saved to ${filePath}`);
    res.json({ success: true, path: filePath });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(500).json({ success: false, error: message });
  }
});

router.post('/analysis/jobs', async (req, res) => {
  const { symbol, market, analysis_level, model, promptVersion, config } = req.body;
  // SECURITY: Strip API keys from config — NEVER persisted to database
  const safeConfig = config ? { ...config } : {};
  delete safeConfig.apiKey;
  delete safeConfig.gemini_api_key;
  delete safeConfig.geminiApiKey;
  delete safeConfig.deepseekApiKey;
  delete safeConfig.deepseek_api_key;
  delete safeConfig.openaiApiKey;
  
  const analysisId = `ana_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
  console.log(`[AnalysisRoute] Received job request for ${symbol} (${market}) with model ${model}`);
  try {
    // 1. Create a record in SQLite (config sans API keys)
    await repo.save({
      analysisId,
      kind: 'stock',
      symbol,
      market,
      status: 'queued',
      promptVersion: promptVersion || 'v1',
      model: model || config?.model || 'gemini-3.1-pro-preview',
      config: safeConfig,
      outputPayload: {}
    });

    // 2. Trigger FastAPI job (without API keys — client sends key only when requested)
    const fastApiRes = await fetch(`${PYTHON_SERVICE_URL}/api/analysis/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getPythonAuthHeaders() },
      body: JSON.stringify({ symbol, market, analysis_level: analysis_level || 'standard', requested_model: config?.model || model || null, config: safeConfig })
    });

    const fastApiBody = await fastApiRes.text();
    let fastApiData: any;
    try {
      fastApiData = JSON.parse(fastApiBody);
    } catch {
      throw new Error(`FastAPI returned non-JSON response (${fastApiRes.status}): ${fastApiBody}`);
    }

    // Check Python API's own success field first
    if (!fastApiData.success) {
      const pyError = fastApiData.error?.message || fastApiData.error?.code || 'Unknown error';
      throw new Error(pyError);
    }

    // Handle nested success_response format: { success: true, data: { job_id: '...' } }
    const jobId = fastApiData.data?.job_id;

    if (!jobId) {
      throw new Error('No job_id returned from FastAPI');
    }

    res.status(202).json({
      success: true,
      data: {
        analysisId,
        job_id: jobId, // Aligning with frontend's expectation of snake_case 'job_id'
        status: 'queued'
      }
    });
  } catch (err: unknown) {
    console.error('Failed to create analysis job:', err);
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(500).json({ 
      success: false, 
      error: { message: `Failed to create analysis job: ${message}` } 
    });
  }
});

// POST /analysis/jobs/:jobId/apikey — forward API key to Python service (in-memory only)
router.post('/analysis/jobs/:jobId/apikey', async (req, res) => {
  const { jobId } = req.params;
  const { provider, apiKey } = req.body;
  try {
    const fastApiRes = await fetch(`${PYTHON_SERVICE_URL}/api/analysis/jobs/${jobId}/apikey`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getPythonAuthHeaders() },
      body: JSON.stringify({ provider, apiKey })
    });
    const data = await fastApiRes.json();
    res.status(fastApiRes.ok ? 200 : 400).json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(502).json({ success: false, error: { message: `Key submission failed: ${message}` } });
  }
});

// POST /analysis/apikey — proactively cache/update API key in memory (no job_id needed)
router.post('/analysis/apikey', async (req, res) => {
  const { provider, apiKey } = req.body;
  try {
    const fastApiRes = await fetch(`${PYTHON_SERVICE_URL}/api/analysis/apikey`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getPythonAuthHeaders() },
      body: JSON.stringify({ provider, apiKey })
    });
    const data = await fastApiRes.json();
    res.status(fastApiRes.ok ? 200 : 400).json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(502).json({ success: false, error: { message: `Key caching failed: ${message}` } });
  }
});

router.get('/analysis/jobs/:analysisId/:jobId', async (req, res) => {
  const { analysisId, jobId } = req.params;

  try {
    // 1. Poll FastAPI for status
    const fastApiRes = await fetch(`${PYTHON_SERVICE_URL}/api/analysis/jobs/${jobId}`, {
      headers: getPythonAuthHeaders()
    });
    if (!fastApiRes.ok) {
        throw new Error(`FastAPI status check failed: ${fastApiRes.status}`);
    }
    const fastApiData = await fastApiRes.json();
    const fastApiJob = fastApiData.data; // Access nested data field

    if (!fastApiJob) {
      return res.status(404).json({ error: 'Job data not found in backend response' });
    }

    const record = await repo.getById(analysisId);
    if (!record) return res.status(404).json({ error: 'Analysis not found' });

    if (fastApiJob.status === 'completed' && record.status !== 'completed') {
      // 2. Fetch Brain Context (Facts and Evolved Instructions)
      let brainFacts: string[] = [];
      let evolvedInstructions = '';
      try {
        const brainRes = await axiosClient.get(`${PYTHON_SERVICE_URL}/api/brain/context?user_id=default&query=${record.symbol}`, {
          headers: getPythonAuthHeaders()
        });
        if (brainRes.data.success) {
          brainFacts = brainRes.data.data.facts || [];
          evolvedInstructions = brainRes.data.data.instructions || '';
        }
      } catch (brainErr) {
        console.warn('Failed to fetch brain context, proceeding with defaults:', brainErr);
      }

      // 3. Data is ready, now run LLM analysis
      const data = fastApiJob.result;
      
      const prompt = `
# SYSTEM INSTRUCTIONS
${evolvedInstructions || 'Analyze the following stock data with institutional-grade rigor. Focus on quantitative discrepancies and risk-adjusted returns.'}

# USER CONTEXT / MEMORY
${brainFacts.length > 0 ? brainFacts.map(f => `- ${f}`).join('\n') : 'No specific user memory for this symbol.'}

# DATA SNAPSHOT
Symbol: ${record.symbol} (${record.market})
Quote: ${JSON.stringify(data.stockInfo)}
Valuation: ${JSON.stringify(data.valuation)}
Technicals: ${JSON.stringify(data.technicals)}

# TASK
Perform a deep-dive analysis. Return a JSON object with the following fields:
- "summary": A 2-sentence institutional summary.
- "quantitative_check": Analysis of PE/PB vs historical/industry norms.
- "technical_outlook": Strategy alignment based on technical indicators.
- "risk_rating": Low/Medium/High with 1-sentence justification.
- "actionable_insight": A specific trading or holding recommendation.
`;

      const llmRes = await gatewayGenerate(prompt, record.model, () => {}, record.config as any);
      
      const finalPayload = {
        ...data,
        analysis: llmRes.text,
        provider: llmRes.provider,
        brain_context: { facts: brainFacts, instructions_applied: !!evolvedInstructions }
      };

      // 4. Update SQLite
      await repo.save({
        ...record,
        status: 'completed',
        inputSnapshotPath: data.snapshot_path,
        outputPayload: finalPayload
      });

      req.app.get('io').to(analysisId).emit('statusUpdate', { status: 'completed', result: finalPayload });

      return res.json({
        success: true,
        data: {
          analysisId,
          status: 'completed',
          result: finalPayload
        }
      });
    }

    if (fastApiJob.status === 'failed') {
       await repo.save({ ...record, status: 'failed' });
       req.app.get('io').to(analysisId).emit('statusUpdate', { status: 'failed', error: fastApiJob.error });
       return res.json({ 
         success: true, 
         data: { analysisId, status: 'failed', error: fastApiJob.error } 
       });
    }

    if (fastApiJob.status !== record.status) {
      await repo.save({ ...record, status: fastApiJob.status });
      req.app.get('io').to(analysisId).emit('statusUpdate', { status: fastApiJob.status });
    }

    res.json({
      success: true,
      data: {
        analysisId,
        status: fastApiJob.status
      }
    });
  } catch (err: unknown) {
    console.error('Failed to poll analysis job:', err);
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(500).json({ 
      success: false, 
      error: { message: `Failed to poll analysis job: ${message}` } 
    });
  }
});

router.post('/analysis/feedback', async (req, res) => {
  const { analysisId, feedback, userId } = req.body;
  try {
    const record = await repo.getById(analysisId);

    // Proxy to Python Brain Service
    await axiosClient.post(`${PYTHON_SERVICE_URL}/api/brain/feedback`, {
      user_id: userId || 'default',
      feedback,
      context: record ? `${record.symbol} (${record.market}) Analysis` : 'General'
    }, {
      headers: getPythonAuthHeaders()
    });

    res.json({ success: true, message: 'Feedback recorded and brain evolution triggered.' });
  } catch (err: unknown) {
    console.error('Failed to process feedback:', err);
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(500).json({ error: 'Failed to process feedback', details: message });
  }
});

router.get('/history/recent', async (req, res) => {
  const limit = parseInt(req.query.limit as string) || 20;
  const history = await repo.listRecent({ limit });
  res.json(history);
});

router.delete('/analysis/history/:jobId', async (req, res) => {
  try {
    const resp = await fetch(`${PYTHON_SERVICE_URL}/api/analysis/history/${req.params.jobId}`, {
      method: 'DELETE',
      headers: getPythonAuthHeaders()
    });
    const data = await resp.json();
    res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(500).json({ success: false, error: { message } });
  }
});

// Cancel / stop analysis — creates a .stop file that LLM gateway checks
router.post('/analysis/cancel', async (req, res) => {
  try {
    // The Python service checks for .stop in its cwd (alsa/alsa root)
    const projectRoot = path.resolve(__dirname, '..', '..');
    const stopFilePath = path.join(projectRoot, '.stop');
    fs.writeFileSync(stopFilePath, `cancelled at ${new Date().toISOString()}`);
    console.log(`Analysis cancel signal created: ${stopFilePath}`);
    
    // Auto-clean the .stop file after 30 seconds so it doesn't persist
    setTimeout(() => {
      try {
        if (fs.existsSync(stopFilePath)) {
          fs.unlinkSync(stopFilePath);
          console.log('Auto-cleaned .stop file after 30s');
        }
      } catch { /* ignore */ }
    }, 30_000);

    res.json({ success: true, message: 'Cancel signal sent' });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(500).json({ error: 'Failed to send cancel signal', details: message });
  }
});

// ── Token Guard Settings (proxy to Python service) ─────────────────────────

router.get('/analysis/settings/token-guard', async (req, res) => {
  try {
    const resp = await fetch(`${PYTHON_SERVICE_URL}/api/analysis/settings/token-guard`, {
      headers: getPythonAuthHeaders()
    });
    const data = await resp.json();
    res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(500).json({ success: false, error: { message } });
  }
});

router.post('/analysis/settings/token-guard', async (req, res) => {
  try {
    const resp = await fetch(`${PYTHON_SERVICE_URL}/api/analysis/settings/token-guard`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getPythonAuthHeaders() },
      body: JSON.stringify(req.body),
    });
    const data = await resp.json();
    res.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    res.status(500).json({ success: false, error: { message } });
  }
});

export default router;
