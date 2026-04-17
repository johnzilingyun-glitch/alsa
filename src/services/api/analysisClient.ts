export interface AnalysisJobResponse {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  result?: string; // JSON string
  error?: string;
}

export async function createAnalysisJob(symbol: string, market: string): Promise<string> {
  const res = await fetch('/api/analysis/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, market, level: 'standard' }),
  });
  if (!res.ok) throw new Error('Failed to start analysis job');
  const data = await res.json();
  return data.job_id;
}

export async function pollAnalysisJob(jobId: string): Promise<any> {
  let attempts = 0;
  const maxAttempts = 50;
  const pollInterval = 1500;

  while (attempts < maxAttempts) {
    const res = await fetch(`/api/analysis/jobs/${jobId}`);
    if (!res.ok) throw new Error('Polling failed');
    
    const data: AnalysisJobResponse = await res.json();
    if (data.status === 'completed' && data.result) {
      return JSON.parse(data.result);
    }
    if (data.status === 'failed') {
      throw new Error(data.error || 'Job failed');
    }

    await new Promise(resolve => setTimeout(resolve, pollInterval));
    attempts++;
  }
  throw new Error('Analysis timed out');
}
