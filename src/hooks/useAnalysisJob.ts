import { useState, useCallback } from 'react';
import { StockAnalysis } from '../types';

export function useAnalysisJob() {
  const [status, setStatus] = useState<'idle' | 'queued' | 'running' | 'completed' | 'failed'>('idle');
  const [result, setResult] = useState<StockAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startAnalysis = useCallback(async (symbol: string, market: string, model: string) => {
    setStatus('queued');
    setError(null);
    setResult(null);

    try {
      const res = await fetch('/api/analysis/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, market, model }),
      });

      if (!res.ok) throw new Error('Failed to start analysis job');

      const { analysisId, jobId } = await res.json();

      // Start polling
      pollJob(analysisId, jobId);
    } catch (err: any) {
      setStatus('failed');
      setError(err.message);
    }
  }, []);

  const pollJob = async (analysisId: string, jobId: string) => {
    const pollInterval = 2000;
    const maxAttempts = 60; // 2 minutes
    let attempts = 0;

    const timer = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(timer);
        setStatus('failed');
        setError('Analysis timed out');
        return;
      }

      try {
        const res = await fetch(`/api/analysis/jobs/${analysisId}/${jobId}`);
        if (!res.ok) throw new Error('Polling failed');

        const data = await res.json();
        setStatus(data.status);

        if (data.status === 'completed') {
          clearInterval(timer);
          setResult(data.result);
        } else if (data.status === 'failed') {
          clearInterval(timer);
          setError(data.error || 'Job failed');
        }
      } catch (err: any) {
        clearInterval(timer);
        setStatus('failed');
        setError(err.message);
      }
    }, pollInterval);
  };

  return { startAnalysis, status, result, error };
}
