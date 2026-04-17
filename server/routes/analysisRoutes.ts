import { Router } from 'express';
import { createAnalysisRepository } from '../repositories/analysisRepository.js';
import { gatewayGenerate } from '../llmGateway.js';
import axios from 'axios';

const router = Router();
const repo = createAnalysisRepository();
const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || 'http://127.0.0.1:8000';

router.post('/analysis/jobs', async (req, res) => {
  const { symbol, market, model, promptVersion } = req.body;
  const analysisId = `ana_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;

  try {
    // 1. Create a record in SQLite
    await repo.save({
      analysisId,
      kind: 'stock',
      symbol,
      market,
      status: 'queued',
      promptVersion: promptVersion || 'v1',
      model: model || 'gemini-1.5-flash',
      outputPayload: {}
    });

    // 2. Trigger FastAPI job
    const fastApiRes = await axios.post(`${PYTHON_SERVICE_URL}/api/analysis/jobs`, {
      symbol,
      market,
      analysisId // We pass our ID to link them
    });

    const jobId = fastApiRes.data.jobId;

    res.status(202).json({
      analysisId,
      jobId,
      status: 'queued'
    });
  } catch (err: any) {
    console.error('Failed to create analysis job:', err);
    res.status(500).json({ error: 'Failed to create analysis job', details: err.message });
  }
});

router.get('/analysis/jobs/:analysisId/:jobId', async (req, res) => {
  const { analysisId, jobId } = req.params;

  try {
    // 1. Poll FastAPI for status
    const fastApiRes = await axios.get(`${PYTHON_SERVICE_URL}/api/analysis/jobs/${jobId}`);
    const fastApiJob = fastApiRes.data;

    const record = await repo.getById(analysisId);
    if (!record) return res.status(404).json({ error: 'Analysis not found' });

    if (fastApiJob.status === 'completed' && record.status !== 'completed') {
      // Data is ready, now run LLM analysis
      const data = fastApiJob.result;
      
      // Simple prompt for now
      const prompt = `Analyze this stock snapshot: ${JSON.stringify(data.stockInfo)}. Technicals: ${JSON.stringify(data.technicals)}. Return a JSON summary.`;
      
      const llmRes = await gatewayGenerate(prompt, record.model);
      
      const finalPayload = {
        ...data,
        analysis: llmRes.text,
        provider: llmRes.provider
      };

      // Update SQLite
      await repo.save({
        ...record,
        status: 'completed',
        inputSnapshotPath: data.snapshot_path,
        outputPayload: finalPayload
      });

      return res.json({
        analysisId,
        status: 'completed',
        result: finalPayload
      });
    }

    if (fastApiJob.status === 'failed') {
       await repo.save({ ...record, status: 'failed' });
       return res.json({ analysisId, status: 'failed', error: fastApiJob.error });
    }

    res.json({
      analysisId,
      status: fastApiJob.status
    });
  } catch (err: any) {
    console.error('Failed to poll analysis job:', err);
    res.status(500).json({ error: 'Failed to poll analysis job' });
  }
});

router.get('/history/recent', async (req, res) => {
  const limit = parseInt(req.query.limit as string) || 20;
  const history = await repo.listRecent({ limit });
  res.json(history);
});

export default router;
