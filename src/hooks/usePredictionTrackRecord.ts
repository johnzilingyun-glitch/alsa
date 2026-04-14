import { useState, useEffect } from 'react';
import type { StockAnalysis, BacktestTimeSeries, SystematicBias } from '../types';
import { buildBacktestTimeSeries, detectSystematicBias } from '../services/backtestTimeSeries';
import { getHistoryContext } from '../services/adminService';

export interface PredictionTrackRecord {
  timeSeries: BacktestTimeSeries | null;
  bias: SystematicBias | null;
  previousAnalysis: StockAnalysis | null;
  loading: boolean;
}

export function usePredictionTrackRecord(analysis: StockAnalysis | null): PredictionTrackRecord {
  const [timeSeries, setTimeSeries] = useState<BacktestTimeSeries | null>(null);
  const [bias, setBias] = useState<SystematicBias | null>(null);
  const [previousAnalysis, setPreviousAnalysis] = useState<StockAnalysis | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!analysis?.stockInfo?.symbol) {
      setTimeSeries(null);
      setBias(null);
      setPreviousAnalysis(null);
      return;
    }

    let cancelled = false;
    const symbol = analysis.stockInfo.symbol;

    async function loadTrackRecord() {
      setLoading(true);
      try {
        const history = await getHistoryContext();
        if (cancelled) return;

        // Filter history to same symbol, extract .data field as StockAnalysis
        const symbolHistory: StockAnalysis[] = history
          .filter((item: any) => {
            const isStock = item.type === 'stock' || (item.stockInfo && !item.indices);
            if (!isStock) return false;
            const sym = item.data?.stockInfo?.symbol ?? item.stockInfo?.symbol;
            return sym === symbol;
          })
          .map((item: any) => item.data ?? item)
          .filter((a: any) => a?.stockInfo?.price != null)
          .sort((a: any, b: any) => {
            const timeA = new Date(a.generatedAt || a.stockInfo?.lastUpdated || 0).getTime();
            const timeB = new Date(b.generatedAt || b.stockInfo?.lastUpdated || 0).getTime();
            return timeB - timeA;
          });

        if (cancelled) return;

        if (symbolHistory.length > 0) {
          setPreviousAnalysis(symbolHistory[0]);
        }

        if (symbolHistory.length >= 1 && analysis) {
          const ts = buildBacktestTimeSeries(symbol, analysis, symbolHistory);
          setTimeSeries(ts);
          setBias(detectSystematicBias(ts));
        }
      } catch (err) {
        console.error('Failed to load prediction track record:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadTrackRecord();
    return () => { cancelled = true; };
  }, [analysis?.stockInfo?.symbol, analysis?.stockInfo?.price]);

  return { timeSeries, bias, previousAnalysis, loading };
}
