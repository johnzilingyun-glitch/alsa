import { useState, useEffect, useCallback, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { StockAnalysis } from '../types';

export function useAnalysisStatus() {
  const [status, setStatus] = useState<'idle' | 'queued' | 'running' | 'completed' | 'failed'>('idle');
  const [result, setResult] = useState<StockAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    socketRef.current = io(); // Connect to server
    return () => {
      socketRef.current?.disconnect();
    };
  }, []);

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

      const { analysisId } = await res.json();

      // Join WebSocket room
      socketRef.current?.emit('joinRoom', analysisId);

      // Listen for status updates
      socketRef.current?.on('statusUpdate', (data: any) => {
        setStatus(data.status);
        if (data.status === 'completed') {
          setResult(data.result);
        } else if (data.status === 'failed') {
          setError(data.error || 'Job failed');
        }
      });

    } catch (err: any) {
      setStatus('failed');
      setError(err.message);
    }
  }, []);

  return { startAnalysis, status, result, error };
}
