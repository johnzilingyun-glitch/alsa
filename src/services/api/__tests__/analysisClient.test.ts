import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createAnalysisJob, pollAnalysisJob } from '../analysisClient';

describe('analysisClient', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  it('createAnalysisJob should return job_id', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ job_id: 'job_test_123' }),
    });

    const jobId = await createAnalysisJob('600519', 'A-Share');
    expect(jobId).toBe('job_test_123');
    expect(global.fetch).toHaveBeenCalledWith('/api/analysis/jobs', expect.any(Object));
  });

  it('pollAnalysisJob should complete when status is completed', async () => {
    const mockResult = { indicators: { ma_5: 1650 } };
    
    // First call: running, Second call: completed
    (global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'running' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'completed', result: JSON.stringify(mockResult) }),
      });

    const result = await pollAnalysisJob('job_123');
    expect(result).toEqual(mockResult);
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('pollAnalysisJob should throw when status is failed', async () => {
    (global.fetch as any).mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'failed', error: 'Database error' }),
    });

    await expect(pollAnalysisJob('job_123')).rejects.toThrow('Database error');
  });
});
