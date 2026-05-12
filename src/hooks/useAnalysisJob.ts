import { useState, useCallback } from 'react';
import { StockAnalysis } from '../types';
import { useUIStore } from '../stores/useUIStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';

export function useAnalysisJob() {
  const [status, setStatus] = useState<'idle' | 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'>('idle');
  const [result, setResult] = useState<StockAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [insufficientBalance, setInsufficientBalance] = useState(false);

  const setAnalysisStatus = useUIStore(s => s.setAnalysisStatus);
  const setContentCount = useUIStore(s => s.setContentCount);
  const setRoundProgress = useDiscussionStore(s => s.setRoundProgress);

  const startAnalysis = useCallback(async (symbol: string, market: string, analysisLevel: string, model: string | null = null, config: any = null) => {
    setStatus('queued');
    setError(null);
    setResult(null);
    setInsufficientBalance(false);
    setAnalysisStatus('正在提交分析请求...');

    try {
      const res = await fetch('/api/analysis/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          symbol, 
          market, 
          analysis_level: analysisLevel,
          model: config?.model || model,
          config: config
        }),
      });

      const responseData = await res.json();
      if (!responseData.success) {
        throw new Error(responseData.error?.message || 'Failed to start analysis job');
      }

      const newJobId = responseData.data.job_id;
      setJobId(newJobId);
      setAnalysisStatus('分析任务已提交，正在排队...');

      // Start polling
      pollJob(newJobId);
    } catch (err: any) {
      setStatus('failed');
      setError(err.message);
    }
  }, []);

  const pollJob = async (id: string) => {
    const pollInterval = 2000;
    const maxAttempts = 300; // 10 minutes
    let attempts = 0;
    let lastMsg = '';

    const timer = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(timer);
        setStatus('failed');
        setError('Analysis timed out');
        return;
      }

      try {
        const res = await fetch(`/api/analysis/jobs/${id}`);
        const responseData = await res.json();
        
        if (!responseData.success) {
          throw new Error(responseData.error?.message || 'Polling failed');
        }

        const data = responseData.data;
        setStatus(data.status);

        if (data.progress) {
          const { stage, percent, round, total_rounds, message, count, error_type } = data.progress;
          
          if (count !== undefined) {
            setContentCount(count);
          }

          // Detect 402 insufficient balance
          if (error_type === 'insufficient_balance') {
            setInsufficientBalance(true);
          }
          
          // Map stage to a friendly message if no explicit message
          const statusMsg = message || {
            'queued': '正在排队等待，初始化数据管线...',
            'starting': '正在启动分析引擎...',
            'snapshot': '正在获取市场深度行情...',
            'quant': '正在执行量化指标计算...',
            'discussion': '正在召集专家进行深度研判...',
            'finalizing': '正在整理分析结论...',
            'completed': '分析完成',
            'failed': '分析失败',
          }[stage] || stage;

          if (statusMsg && statusMsg !== lastMsg) {
            setAnalysisStatus(statusMsg);
            lastMsg = statusMsg;
          }

          if (round !== undefined && total_rounds !== undefined) {
            setRoundProgress(round, total_rounds);
          }
        }

        if (data.status === 'completed') {
          clearInterval(timer);
          // Fetch final result
          const runRes = await fetch(`/api/analysis/runs/${data.analysis_id}`);
          const runData = await runRes.json();
          if (runData.success) {
            setResult(runData.data);
          } else {
            setError(runData.error?.message || 'Failed to fetch analysis result');
            setStatus('failed');
          }
        } else if (data.status === 'failed') {
          clearInterval(timer);
          setError(data.error_message || 'Job failed');
        } else if (data.status === 'cancelled') {
          clearInterval(timer);
          setStatus('cancelled');
        }
      } catch (err: any) {
        clearInterval(timer);
        setStatus('failed');
        setError(err.message);
      }
    }, pollInterval);
  };

  return { startAnalysis, status, result, error, jobId, insufficientBalance };
}
