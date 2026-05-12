import { useCallback, useEffect, useState } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore } from '../stores/useUIStore';
import { useMarketStore } from '../stores/useMarketStore';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';
import { useScenarioStore } from '../stores/useScenarioStore';
import { StockAnalysis, Market } from '../types';
import { useAnalysisJob } from './useAnalysisJob';

export function useStockAnalysis() {
  const geminiConfig = useConfigStore(s => s.config);
  const setLoading = useUIStore(s => s.setLoading);
  const setAnalysisError = useUIStore(s => s.setAnalysisError);
  const setIsDiscussing = useUIStore(s => s.setIsDiscussing);
  const setShowDiscussion = useUIStore(s => s.setShowDiscussion);
  const resetErrors = useUIStore(s => s.resetErrors);
  const analysisLevel = useUIStore(s => s.analysisLevel);
  const setAnalysisTarget = useUIStore(s => s.setAnalysisTarget);

  const setAnalysis = useAnalysisStore(s => s.setAnalysis);
  const symbol = useAnalysisStore(s => s.symbol);
  const market = useAnalysisStore(s => s.market);
  const resetAnalysis = useAnalysisStore(s => s.resetAnalysis);

  const setDiscussionStoreResults = useDiscussionStore(s => s.setDiscussionResults);
  const resetDiscussion = useDiscussionStore(s => s.resetDiscussion);
  const setDiscussionMessages = useDiscussionStore(s => s.setDiscussionMessages);

  const setScenarioResults = useScenarioStore(s => s.setScenarioResults);
  const resetScenario = useScenarioStore(s => s.resetScenario);

  const setHistoryItems = useMarketStore(s => s.setHistoryItems);
  const setOptimizationLogs = useMarketStore(s => s.setOptimizationLogs);
  const addRecentSearch = useMarketStore(s => s.addRecentSearch);
  const watchlist = useMarketStore(s => s.watchlist);
  const setWatchlist = useMarketStore(s => s.setWatchlist);

  const { startAnalysis, status, result, error, jobId, insufficientBalance } = useAnalysisJob();
  const setLastJobId = useAnalysisStore(s => s.setLastJobId);
  
  // History selection state
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false);
  const [historyDialogItems, setHistoryDialogItems] = useState<any[]>([]);
  const [pendingSearchSymbol, setPendingSearchSymbol] = useState<string>('');

  // Watch for job completion
  useEffect(() => {
    if (status === 'completed' && result) {
      setLoading(false);
      setIsDiscussing(false);
      setAnalysis(result);
      setScenarioResults(result as any);
      setDiscussionStoreResults(result as any);
      if (jobId) setLastJobId(jobId);
      if (result.discussion) {
        setDiscussionMessages(result.discussion);
      }
      
      // Add to recent searches
      if (result.stockInfo) {
        addRecentSearch({
          symbol: result.stockInfo.symbol,
          name: result.stockInfo.name,
          market: result.stockInfo.market as Market
        });
      }
    } else if (status === 'failed' && error) {
      setLoading(false);
      setIsDiscussing(false);
      if (insufficientBalance) {
        setAnalysisError('API 余额不足 (Insufficient Balance)。请前往设置更换 API Key 或充值后重试。');
      } else {
        setAnalysisError(error);
      }
    } else if (status === 'running') {
      setIsDiscussing(true);
      setShowDiscussion(true);
      // Show balance warning in status if detected
      if (insufficientBalance) {
        setAnalysisError('⚠️ API 余额不足，部分分析师生成中断。分析将以已获取的内容完成。请尽快更换 API Key。');
      }
    }
  }, [status, result, error, insufficientBalance, setAnalysis, setLoading, setIsDiscussing, setShowDiscussion, setScenarioResults, setDiscussionStoreResults, setDiscussionMessages, addRecentSearch, setAnalysisError]);

  const fetchAdminData = useCallback(async () => {
    try {
      const historyRes = await fetch('/api/history/context');
      const logsRes = await fetch('/api/logs/optimization');
      
      if (historyRes.ok) {
        const history = await historyRes.json();
        setHistoryItems(history);
      }
      
      if (logsRes.ok) {
        const logs = await logsRes.json();
        setOptimizationLogs(logs);
      }
    } catch (err) {
      console.error('Failed to fetch admin data:', err);
    }
  }, [setHistoryItems, setOptimizationLogs]);

  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol || !symbol.trim()) return;

    // Check for existing analysis history
    try {
      const histRes = await fetch(`/api/analysis/history/${encodeURIComponent(symbol)}`);
      if (histRes.ok) {
        const histData = await histRes.json();
        if (histData.success && histData.data?.length > 0) {
          setPendingSearchSymbol(symbol);
          setHistoryDialogItems(histData.data);
          setHistoryDialogOpen(true);
          return; // Wait for user choice
        }
      }
    } catch { /* ignore, proceed with new analysis */ }

    // No history — start fresh analysis
    doStartAnalysis();
  }, [symbol, market, analysisLevel, geminiConfig, startAnalysis, setLoading, resetAnalysis, resetDiscussion, resetScenario, resetErrors, setAnalysisTarget]);

  const doStartAnalysis = useCallback(() => {
    setHistoryDialogOpen(false);
    setLoading(true);
    resetAnalysis();
    resetDiscussion();
    resetScenario();
    resetErrors();
    setAnalysisTarget({ symbol, market });
    startAnalysis(symbol, market, analysisLevel, geminiConfig?.model || null, geminiConfig);
  }, [symbol, market, analysisLevel, geminiConfig, startAnalysis, setLoading, resetAnalysis, resetDiscussion, resetScenario, resetErrors, setAnalysisTarget]);

  const loadHistoryResult = useCallback(async (analysisId: string) => {
    setHistoryDialogOpen(false);
    setLoading(true);
    resetErrors();
    try {
      const res = await fetch(`/api/analysis/runs/${analysisId}`);
      const data = await res.json();
      if (data.success && data.data) {
        setAnalysis(data.data);
        setScenarioResults(data.data as any);
        setDiscussionStoreResults(data.data as any);
        if (data.data.discussion) {
          setDiscussionMessages(data.data.discussion);
        }
        if (data.data.stockInfo) {
          addRecentSearch({
            symbol: data.data.stockInfo.symbol,
            name: data.data.stockInfo.name,
            market: data.data.stockInfo.market as Market
          });
        }
      } else {
        setAnalysisError('加载历史记录失败');
      }
    } catch (err: any) {
      setAnalysisError(err.message || '加载历史记录失败');
    } finally {
      setLoading(false);
    }
  }, [setAnalysis, setLoading, resetErrors, setScenarioResults, setDiscussionStoreResults, setDiscussionMessages, addRecentSearch, setAnalysisError]);

  const toggleWatchlist = useCallback(async (stock: { symbol: string; name: string; market: Market }) => {
    const isStarred = watchlist.some(w => w.symbol === stock.symbol);
    try {
      if (isStarred) {
        const res = await fetch(`/api/watchlist/${stock.symbol}?market=${stock.market}`, { method: 'DELETE' });
        if (res.ok) setWatchlist(watchlist.filter(w => w.symbol !== stock.symbol));
      } else {
        const res = await fetch('/api/watchlist/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(stock)
        });
        if (res.ok) {
          const newItem = await res.json();
          setWatchlist([...watchlist, newItem]);
        }
      }
    } catch (err) {
      console.error('Failed to toggle watchlist:', err);
    }
  }, [watchlist, setWatchlist]);

  const resetToHome = useCallback(() => {
    resetAnalysis();
    resetDiscussion();
    resetScenario();
  }, [resetAnalysis, resetDiscussion, resetScenario]);

  return { handleSearch, resetToHome, fetchAdminData, toggleWatchlist, historyDialogOpen, historyDialogItems, pendingSearchSymbol, setHistoryDialogOpen, doStartAnalysis, loadHistoryResult };
}
