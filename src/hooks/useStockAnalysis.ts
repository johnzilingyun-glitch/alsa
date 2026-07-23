import { useCallback, useEffect, useRef, useState } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore, selectLoading } from '../stores/useUIStore';
import { useMarketStore } from '../stores/useMarketStore';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';
import { useScenarioStore } from '../stores/useScenarioStore';
import { useJobQueueStore } from '../stores/useJobQueueStore';
import { StockAnalysis, Market } from '../types';
import { useAnalysisJob } from './useAnalysisJob';
import { saveAnalysisToHistory } from '../services/aiService';
import { alertsClient } from '../services/api/alertsClient';

export function useStockAnalysis() {
  const llmConfig = useConfigStore(s => s.config);
  const isAnalyzing = useUIStore(selectLoading);
  const setLoading = useUIStore(s => s.setLoading);
  const setAnalysisError = useUIStore(s => s.setAnalysisError);
  const setIsDiscussing = useUIStore(s => s.setIsDiscussing);
  const setShowDiscussion = useUIStore(s => s.setShowDiscussion);
  const resetErrors = useUIStore(s => s.resetErrors);
  const analysisLevel = useUIStore(s => s.analysisLevel);
  const setAnalysisTarget = useUIStore(s => s.setAnalysisTarget);
  const showToast = useUIStore(s => s.showToast);
  const verificationMode = useUIStore(s => s.verificationMode);

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

  const addJob = useJobQueueStore(s => s.addJob);
  const updateJob = useJobQueueStore(s => s.updateJob);

  const { startAnalysis, status, result, error, jobId, insufficientBalance } = useAnalysisJob();
  const setLastJobId = useAnalysisStore(s => s.setLastJobId);
  const bgPollTimers = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());
  
  // History selection state
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false);
  const [historyDialogItems, setHistoryDialogItems] = useState<any[]>([]);
  const [pendingSearchSymbol, setPendingSearchSymbol] = useState<string>('');

  // Cleanup background poll timers on unmount
  useEffect(() => {
    return () => {
      bgPollTimers.current.forEach((timer) => clearInterval(timer));
      bgPollTimers.current.clear();
    };
  }, []);

  // Background job polling
  const startBackgroundJob = useCallback(async (bgSymbol: string, bgMarket: string) => {
    // Check if API Key is configured
    const model = llmConfig?.model || '';
    const isDeepSeek = model.toLowerCase().startsWith('deepseek');
    const isOpenRouter = !isDeepSeek && !model.toLowerCase().startsWith('gemini');
    const apiKey = isDeepSeek ? (llmConfig?.deepseekApiKey || '') : isOpenRouter ? (llmConfig?.openrouterApiKey || '') : (llmConfig?.apiKey || '');

    // All known providers fall back to the server's runtime key
    // (DEEPSEEK_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY in .env.runtime),
    // so a missing local key is never fatal for them — let the request through
    // and let the backend surface a clear error if it also lacks a key.
    const relaxLocalKey = isOpenRouter || isDeepSeek || model.toLowerCase().startsWith('gemini');
    if (!relaxLocalKey && (!apiKey || !apiKey.trim())) {
      showToast(
        isDeepSeek
          ? '请先前往设置配置 DeepSeek API Key (Please configure DeepSeek API Key in settings)'
          : '请先前往设置配置 Gemini API Key (Please configure Gemini API Key in settings)',
        'error'
      );
      return;
    }

    const bgId = `bg_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
    // Record search immediately
    addRecentSearch({ symbol: bgSymbol, name: bgSymbol, market: bgMarket as Market });
    
    try {
      // Submit job to backend
      const res = await fetch('/api/analysis/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          symbol: bgSymbol, 
          market: bgMarket, 
          analysis_level: analysisLevel,
          model: llmConfig?.model || null,
          config: llmConfig,
          verification_mode: verificationMode
        }),
      });
      const responseData = await res.json();
      if (!responseData.success) {
        showToast(`${bgSymbol} 分析提交失败`, 'error');
        return;
      }

      const bgJobId = responseData.data.job_id;
      addJob({
        id: bgId,
        jobId: bgJobId,
        symbol: bgSymbol,
        market: bgMarket,
        status: 'queued',
      });
      showToast(`${bgSymbol} 已加入分析队列`, 'info');

      // Start polling
      const timer = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/analysis/jobs/${bgJobId}`);
          const pollData = await pollRes.json();
          if (!pollData.success) return;
          const data = pollData.data;

          updateJob(bgId, {
            status: data.status,
            progress: data.progress,
            analysisId: data.analysis_id,
          });

          if (data.status === 'completed') {
            clearInterval(timer);
            bgPollTimers.current.delete(bgId);
            // Fetch full result
            const runRes = await fetch(`/api/analysis/runs/${data.analysis_id}`);
            const runData = await runRes.json();
            if (runData.success) {
              updateJob(bgId, { status: 'completed', result: runData.data });
              // Save completed background job to history context
              void saveAnalysisToHistory('stock', { ...runData.data, _jobId: bgJobId });
            } else {
              updateJob(bgId, { status: 'failed', error: '获取结果失败' });
            }
          } else if (data.status === 'failed') {
            clearInterval(timer);
            bgPollTimers.current.delete(bgId);
            updateJob(bgId, { status: 'failed', error: data.error_message || '分析失败' });
          }
        } catch {
          console.warn('[useStockAnalysis] Transient polling error, continuing:');
          // Ignore transient errors, keep polling
        }
      }, 2000);

      bgPollTimers.current.set(bgId, timer);
    } catch (err: any) {
      showToast(`${bgSymbol} 提交失败: ${err.message}`, 'error');
      return false;
    }
  }, [analysisLevel, llmConfig, verificationMode, addJob, updateJob, showToast, addRecentSearch]);

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
      
      // Save to history for the HistoryModal — include jobId for deep report reload
      void saveAnalysisToHistory('stock', { ...result, _jobId: jobId });
      
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
        setAnalysisError(`API 余额不足 (Insufficient Balance)。请前往设置更换 API Key 或充值后重试。\n\n${error}`);
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

  const doStartAnalysis = useCallback((explicitSymbol?: string, explicitMarket?: string) => {
    const s = explicitSymbol || symbol;
    const m = explicitMarket || market;
    
    // Check if API Key is configured
    const model = llmConfig?.model || '';
    const isDeepSeek = model.toLowerCase().startsWith('deepseek');
    const isOpenRouter = !isDeepSeek && !model.toLowerCase().startsWith('gemini');
    const apiKey = isDeepSeek ? (llmConfig?.deepseekApiKey || '') : isOpenRouter ? (llmConfig?.openrouterApiKey || '') : (llmConfig?.apiKey || '');

    const relaxLocalKey = isOpenRouter || isDeepSeek || model.toLowerCase().startsWith('gemini');
    if (!relaxLocalKey && (!apiKey || !apiKey.trim())) {
      setLoading(false);
      setAnalysisError(
        isDeepSeek
          ? '请先前往设置配置 DeepSeek API Key (Please configure DeepSeek API Key in settings)'
          : '请先前往设置配置 Gemini API Key (Please configure Gemini API Key in settings)'
      );
      showToast('API Key 未配置 (API Key not configured)', 'error');
      return;
    }

    setHistoryDialogOpen(false);
    setLoading(true);
    resetAnalysis();
    resetDiscussion();
    resetScenario();
    resetErrors();
    setAnalysisTarget({ symbol: s, market: m });
    // Record search immediately so it appears in recent searches even if analysis fails
    addRecentSearch({ symbol: s, name: s, market: m as Market });
    startAnalysis(s, m, analysisLevel, llmConfig?.model || null, llmConfig, verificationMode);
  }, [symbol, market, analysisLevel, llmConfig, verificationMode, startAnalysis, setLoading, resetAnalysis, resetDiscussion, resetScenario, resetErrors, setAnalysisTarget, addRecentSearch, setAnalysisError, showToast]);

  const handleSearch = useCallback(async (e?: React.FormEvent, targetSymbol?: string, targetMarket?: string) => {
    if (e) e.preventDefault();
    const searchSymbol = targetSymbol || symbol;
    const searchMarket = targetMarket || market;
    if (!searchSymbol || !searchSymbol.trim()) return;

    // If currently analyzing, submit to background queue
    if (isAnalyzing) {
      startBackgroundJob(searchSymbol, searchMarket);
      return;
    }

    // Check for existing analysis history
    try {
      const histRes = await fetch(`/api/analysis/history/${encodeURIComponent(searchSymbol)}`);
      if (histRes.ok) {
        const histData = await histRes.json();
        if (histData.success && histData.data?.length > 0) {
          setPendingSearchSymbol(searchSymbol);
          setHistoryDialogItems(histData.data);
          setHistoryDialogOpen(true);
          return; // Wait for user choice
        }
      }
    } catch {
      console.warn('[useStockAnalysis] History fetch failed, proceeding with new analysis:');
      /* ignore, proceed with new analysis */
    }

    // No history — start fresh analysis
    doStartAnalysis(searchSymbol, searchMarket);
  }, [symbol, market, analysisLevel, llmConfig, startAnalysis, setLoading, resetAnalysis, resetDiscussion, resetScenario, resetErrors, setAnalysisTarget, isAnalyzing, startBackgroundJob, doStartAnalysis]);

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
        setLastJobId(data.data.job_id || data.data.jobId || data.data.analysis_id || null);
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

  /** Load a completed background job result into the main analysis view */
  const loadBackgroundResult = useCallback((job: { result: any; jobId: string; symbol: string; market: string; id: string }) => {
    if (!job.result) return;
    const { dismissNotification } = useJobQueueStore.getState();
    dismissNotification(job.id);
    setAnalysis(job.result);
    setScenarioResults(job.result as any);
    setDiscussionStoreResults(job.result as any);
    setLastJobId(job.jobId);
    if (job.result.discussion) {
      setDiscussionMessages(job.result.discussion);
    }
    // Save to history when loading completed background job
    void saveAnalysisToHistory('stock', { ...job.result, _jobId: job.jobId });
    if (job.result.stockInfo) {
      addRecentSearch({
        symbol: job.result.stockInfo.symbol,
        name: job.result.stockInfo.name,
        market: job.result.stockInfo.market as Market
      });
    }
  }, [setAnalysis, setScenarioResults, setDiscussionStoreResults, setLastJobId, setDiscussionMessages, addRecentSearch]);

  return { handleSearch, resetToHome, fetchAdminData, toggleWatchlist, historyDialogOpen, historyDialogItems, pendingSearchSymbol, setHistoryDialogOpen, doStartAnalysis, loadHistoryResult, loadBackgroundResult };
}
