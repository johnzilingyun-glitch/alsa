import { describe, it, expect, vi, beforeEach } from 'vitest';
import express from 'express';
import request from 'supertest';

process.env.API_TOKEN = 'test-token-for-analysis-routes';
process.env.NODE_ENV = 'test';

const { mockRun, mockQuery } = vi.hoisted(() => ({
  mockRun: vi.fn(),
  mockQuery: vi.fn(),
}));
vi.mock('../db/client.js', () => ({
  run: mockRun,
  query: mockQuery,
}));

const { mockGatewayGenerate } = vi.hoisted(() => ({
  mockGatewayGenerate: vi.fn(),
}));
vi.mock('../llmGateway.js', () => ({
  gatewayGenerate: mockGatewayGenerate,
}));

const { mockAxiosPost } = vi.hoisted(() => ({
  mockAxiosPost: vi.fn(),
}));
vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      post: mockAxiosPost,
      get: vi.fn().mockRejectedValue(new Error('Network Error')),
      request: vi.fn(),
    })),
  },
}));

import analysisRoutes from '../routes/analysisRoutes';

function setupApp() {
  const app = express();
  app.use(express.json());
  app.use('/api', analysisRoutes);
  app.set('io', { to: vi.fn().mockReturnValue({ emit: vi.fn() }) });
  return app;
}

function dbRow(overrides: Record<string, any> = {}) {
  return {
    analysis_id: 'ana_100_test',
    kind: 'stock',
    symbol: '00700',
    market: 'HK-Share',
    status: 'pending',
    prompt_version: 'v1',
    model: 'gemini-3.1-pro-preview',
    input_snapshot_path: null,
    output_payload: '{}',
    config: '{}',
    ...overrides,
  };
}

const completedResult = {
  stockInfo: { symbol: '00700', price: 400 },
  valuation: { pe: 25, pb: 5 },
  technicals: { rsi: 55, macd: 'bullish' },
  snapshot_path: '/data/snap/00700.json',
};

describe('analysisRoutes', () => {
  let app: express.Express;

  beforeEach(() => {
    vi.clearAllMocks();
    mockRun.mockResolvedValue(undefined);
    mockQuery.mockResolvedValue([]);
    mockGatewayGenerate.mockResolvedValue({ text: '{"summary":"test"}', provider: 'gemini' });
    mockAxiosPost.mockRejectedValue(new Error('Network Error'));
    app = setupApp();
  });

  describe('POST /api/analysis/jobs', () => {
    it('creates a job and returns 202 with analysisId and job_id', async () => {
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        text: vi.fn().mockResolvedValue(JSON.stringify({ success: true, data: { job_id: 'py_job_1' } })),
      });

      try {
        const res = await request(app)
          .post('/api/analysis/jobs')
          .send({ symbol: '00700', market: 'HK-Share', analysis_level: 'standard' });

        expect(res.status).toBe(202);
        expect(res.body.success).toBe(true);
        expect(res.body.data.job_id).toBe('py_job_1');
        expect(res.body.data.analysisId).toMatch(/^ana_/);
        expect(mockRun).toHaveBeenCalledOnce();
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('strips API keys from config before persisting', async () => {
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        text: vi.fn().mockResolvedValue(JSON.stringify({ success: true, data: { job_id: 'py_job_2' } })),
      });

      try {
        const res = await request(app)
          .post('/api/analysis/jobs')
          .send({
            symbol: 'AAPL',
            market: 'US-Share',
            config: { apiKey: 'sk-123', gemini_api_key: 'gi-456', deepseekApiKey: 'ds-789', model: 'deepseek-v4' }
          });

        expect(res.status).toBe(202);
        const savedConfig = mockRun.mock.calls[0][1][9];
        const parsed = JSON.parse(savedConfig);
        expect(parsed.apiKey).toBeUndefined();
        expect(parsed.gemini_api_key).toBeUndefined();
        expect(parsed.deepseekApiKey).toBeUndefined();
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('returns 500 when FastAPI returns non-JSON', async () => {
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        text: vi.fn().mockResolvedValue('Internal Server Error'),
      });

      try {
        const res = await request(app)
          .post('/api/analysis/jobs')
          .send({ symbol: '00700', market: 'HK-Share' });

        expect(res.status).toBe(500);
        expect(res.body.success).toBe(false);
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('returns 500 when FastAPI returns success=false', async () => {
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        text: vi.fn().mockResolvedValue(JSON.stringify({ success: false, error: { message: 'No API key' } })),
      });

      try {
        const res = await request(app)
          .post('/api/analysis/jobs')
          .send({ symbol: '00700', market: 'HK-Share' });

        expect(res.status).toBe(500);
        expect(res.body.success).toBe(false);
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('GET /api/analysis/jobs/:analysisId/:jobId', () => {
    it('returns completed analysis with LLM-generated content', async () => {
      mockQuery.mockResolvedValue([dbRow()]);

      const originalFetch = global.fetch;
      let fetchCallCount = 0;
      global.fetch = vi.fn().mockImplementation(async (url: string) => {
        fetchCallCount++;
        if (url.includes('/api/brain/context')) {
          return { ok: true, json: vi.fn().mockResolvedValue({ success: true, data: { facts: ['PE is above industry avg'], instructions: 'Focus on valuation' } }) };
        }
        return {
          ok: true,
          json: vi.fn().mockResolvedValue({
            data: { status: 'completed', result: completedResult }
          }),
        };
      });

      try {
        const res = await request(app).get('/api/analysis/jobs/ana_100_test/py_job_complete');

        expect(res.status).toBe(200);
        expect(res.body.success).toBe(true);
        expect(res.body.data.status).toBe('completed');
        expect(res.body.data.result.analysis).toBeDefined();
        expect(mockGatewayGenerate).toHaveBeenCalledOnce();
        expect(mockRun).toHaveBeenCalled();
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('returns pending status while job is running', async () => {
      mockQuery.mockResolvedValue([dbRow({ analysis_id: 'ana_101_test' })]);

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          data: { status: 'processing' }
        }),
      });

      try {
        const res = await request(app).get('/api/analysis/jobs/ana_101_test/py_job_processing');
        expect(res.status).toBe(200);
        expect(res.body.data.status).toBe('processing');
        expect(mockGatewayGenerate).not.toHaveBeenCalled();
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('returns failed status when job has failed', async () => {
      mockQuery.mockResolvedValue([dbRow()]);

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          data: { status: 'failed', error: { message: 'Rate limit exceeded' } }
        }),
      });

      try {
        const res = await request(app).get('/api/analysis/jobs/ana_100_test/py_job_failed');
        expect(res.status).toBe(200);
        expect(res.body.data.status).toBe('failed');
        expect(res.body.data.error).toBeDefined();
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('returns 404 when analysis not found in local DB', async () => {
      mockQuery.mockResolvedValue([]);

      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({
          data: { status: 'pending' }
        }),
      });

      try {
        const res = await request(app).get('/api/analysis/jobs/ana_nonexistent/job_1');
        expect(res.status).toBe(404);
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('POST /api/analysis/jobs/:jobId/apikey', () => {
    it('forwards API key to Python service', async () => {
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ success: true }),
      });

      try {
        const res = await request(app)
          .post('/api/analysis/jobs/job_1/apikey')
          .send({ provider: 'gemini', apiKey: 'test-key' });

        expect(res.status).toBe(200);
      } finally {
        global.fetch = originalFetch;
      }
    });

    it('returns 502 when Python service is unreachable', async () => {
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));

      try {
        const res = await request(app)
          .post('/api/analysis/jobs/job_1/apikey')
          .send({ provider: 'gemini', apiKey: 'test-key' });

        expect(res.status).toBe(502);
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('POST /api/analysis/apikey', () => {
    it('caches API key via Python service', async () => {
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: vi.fn().mockResolvedValue({ success: true }),
      });

      try {
        const res = await request(app)
          .post('/api/analysis/apikey')
          .send({ provider: 'deepseek', apiKey: 'ds-key' });

        expect(res.status).toBe(200);
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('POST /api/analysis/feedback', () => {
    it('records feedback and proxies to brain service', async () => {
      mockAxiosPost.mockResolvedValue({ data: { success: true } });
      mockQuery.mockResolvedValue([dbRow()]);

      const res = await request(app)
        .post('/api/analysis/feedback')
        .send({ analysisId: 'ana_100_test', feedback: 'Good analysis', userId: 'user1' });

      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
    });
  });

  describe('GET /api/history/recent', () => {
    it('returns recent analysis history', async () => {
      mockQuery.mockResolvedValue([{
        analysis_id: 'ana_100',
        kind: 'stock',
        symbol: '00700',
        market: 'HK-Share',
        status: 'completed',
        prompt_version: 'v1',
        model: 'gemini',
        input_snapshot_path: null,
        output_payload: '{}',
        config: '{}',
      }]);

      const res = await request(app).get('/api/history/recent?limit=10');
      expect(res.status).toBe(200);
      expect(res.body).toHaveLength(1);
      expect(res.body[0].analysisId).toBe('ana_100');
    });
  });

  describe('POST /api/analysis/cancel', () => {
    it('creates .stop file and returns success', async () => {
      const res = await request(app).post('/api/analysis/cancel');
      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
    });
  });

  describe('GET /api/analysis/settings/token-guard', () => {
    it('proxies to Python service', async () => {
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        json: vi.fn().mockResolvedValue({ enabled: true, max_tokens: 5000 }),
      });

      try {
        const res = await request(app).get('/api/analysis/settings/token-guard');
        expect(res.status).toBe(200);
        expect(res.body.enabled).toBe(true);
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('POST /api/analysis/settings/token-guard', () => {
    it('proxies update to Python service', async () => {
      const originalFetch = global.fetch;
      global.fetch = vi.fn().mockResolvedValue({
        json: vi.fn().mockResolvedValue({ success: true }),
      });

      try {
        const res = await request(app)
          .post('/api/analysis/settings/token-guard')
          .send({ enabled: false });
        expect(res.status).toBe(200);
      } finally {
        global.fetch = originalFetch;
      }
    });
  });

  describe('GET /api/reports/download', () => {
    it('rejects invalid filenames', async () => {
      const res = await request(app).get('/api/reports/download?file=../../../etc/passwd');
      expect(res.status).toBe(400);
    });

    it('rejects non-HTML/PDF extensions', async () => {
      const res = await request(app).get('/api/reports/download?file=report.exe');
      expect(res.status).toBe(400);
    });
  });

  describe('POST /api/reports/save', () => {
    it('rejects missing fields', async () => {
      const res = await request(app)
        .post('/api/reports/save')
        .send({ filename: 'test.html' });
      expect(res.status).toBe(400);
    });

    it('sanitizes filenames', async () => {
      const res = await request(app)
        .post('/api/reports/save')
        .send({ filename: 'my<report>.html', content: '<html/>' });
      expect(res.status).toBe(200);
    });
  });
});
