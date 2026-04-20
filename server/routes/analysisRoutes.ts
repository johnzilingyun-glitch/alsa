import { Router } from 'express';
import { createAnalysisRepository } from '../repositories/analysisRepository.js';
import { gatewayGenerate } from '../llmGateway.js';
import axios from 'axios';

const router = Router();
const repo = createAnalysisRepository();
const PYTHON_SERVICE_URL = process.env.PYTHON_SERVICE_URL || 'http://127.0.0.1:8001';

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
      // 2. Fetch Brain Context (Facts and Evolved Instructions)
      let brainFacts = [];
      let evolvedInstructions = '';
      try {
        const brainRes = await axios.get(`${PYTHON_SERVICE_URL}/api/brain/context?user_id=default&query=${record.symbol}`);
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

      const llmRes = await gatewayGenerate(prompt, record.model);
      
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

router.post('/analysis/feedback', async (req, res) => {
  const { analysisId, feedback, userId } = req.body;
  try {
    const record = await repo.getById(analysisId);
    
    // Proxy to Python Brain Service
    await axios.post(`${PYTHON_SERVICE_URL}/api/brain/feedback`, {
      user_id: userId || 'default',
      feedback,
      context: record ? `${record.symbol} (${record.market}) Analysis` : 'General'
    });

    res.json({ success: true, message: 'Feedback recorded and brain evolution triggered.' });
  } catch (err: any) {
    console.error('Failed to process feedback:', err);
    res.status(500).json({ error: 'Failed to process feedback' });
  }
});

router.get('/history/recent', async (req, res) => {
  const limit = parseInt(req.query.limit as string) || 20;
  const history = await repo.listRecent({ limit });
  res.json(history);
});

export default router;
