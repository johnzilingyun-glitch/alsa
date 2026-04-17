import { useCallback } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore } from '../stores/useUIStore';
import { useMarketStore } from '../stores/useMarketStore';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';
import { useScenarioStore } from '../stores/useScenarioStore';
import { analyzeStock, sendChatMessage, startAgentDiscussion, startMultiRoundDiscussion, saveAnalysisToHistory, getHistoryContext } from '../services/aiService';
import { StockAnalysis, AgentMessage, Market } from '../types';

export function useStockAnalysis() {
  const geminiConfig = useConfigStore(s => s.config);
  const { setLoading, setAnalysisError, setIsDiscussing, setShowDiscussion, resetErrors, analysisLevel } = useUIStore();
  const { setAnalysis, setSymbol, setMarket, symbol, market, analysis, resetAnalysis } = useAnalysisStore();
  const { setDiscussionResults: setDiscussionStoreResults, resetDiscussion, setRoundProgress, setAbortController, setDiscussionMessages } = useDiscussionStore();
  const { setScenarioResults, resetScenario } = useScenarioStore();
  const { setHistoryItems, setOptimizationLogs, addRecentSearch } = useMarketStore();

  const withTimeout = useCallback(async <T,>(promise: Promise<T>, ms: number, message: string): Promise<T> => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    try {
      return await Promise.race<T>([
        promise,
        new Promise<T>((_, reject) => {
          timer = setTimeout(() => reject(new Error(message)), ms);
        }),
      ]);
    } finally {
      if (timer) clearTimeout(timer);
    }
  }, []);

  const fetchAdminData = useCallback(async () => {
    try {
      const [history, logsRes] = await Promise.all([
        getHistoryContext(),
        fetch('/api/logs/optimization')
      ]);
      setHistoryItems(history);
      
      if (!logsRes.ok) {
        console.error(`Failed to fetch optimization logs: ${logsRes.status} ${logsRes.statusText}`);
      } else {
        const text = await logsRes.text();
        try {
          const logs = JSON.parse(text);
          setOptimizationLogs(logs);
        } catch (e) {
          console.error('Failed to parse optimization logs JSON. Response text:', text.substring(0, 500), e);
        }
      }
    } catch (err) {
      console.error('Failed to fetch admin data:', err);
    }
  }, [setHistoryItems, setOptimizationLogs]);

  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol || !symbol.trim()) return;

    setLoading(true);
    resetAnalysis();
    resetDiscussion();
    resetScenario();
    resetErrors();

    try {
      const isCopilotMode = geminiConfig?.serviceMode === 'copilot_local';
      const analysisTimeoutMs = isCopilotMode ? 160_000 : 35_000;
      const timeoutMsg = isCopilotMode
        ? '分析请求超时：Copilot CLI 推理超时（已等待 160 秒）。请检查 copilot login 状态，或切换到 Gemini (BYOK) 模式。'
        : '分析请求超时：当前数据源可能不稳定。建议稍后重试，或切换到热门标的（如 600519/000001）验证链路是否恢复。';

      const result = await withTimeout(
        analyzeStock(symbol, market, geminiConfig),
        analysisTimeoutMs,
        timeoutMsg
      );
      
      // Update global market state if backend resolved to a different market
      if ((result as any).resolvedMarket && (result as any).resolvedMarket !== market) {
        setMarket((result as any).resolvedMarket);
      }
      
      setAnalysis(result);

      // Add to recent searches
      if (result.stockInfo) {
        addRecentSearch({
          symbol: result.stockInfo.symbol,
          name: result.stockInfo.name,
          market: result.stockInfo.market as Market
        });
      }

      setShowDiscussion(false);

      // Quick mode: skip expert discussion entirely
      if (analysisLevel === 'quick') {
        await saveAnalysisToHistory('stock', result);
        void fetchAdminData();
      } else {
        // Pre-populate scenario store from initial analysis so cards show during discussion
        if (result as any) {
          setScenarioResults(result as any);
        }

        setIsDiscussing(true);
        // Auto-show discussion panel for standard and deep modes
        if (analysisLevel === 'deep' || analysisLevel === 'standard') {
          setShowDiscussion(true);
        }

        try {
          let discussion;

          if (analysisLevel === 'deep' || analysisLevel === 'standard') {
            // Multi-round iterative discussion for standard and deep modes
            const controller = new AbortController();
            setAbortController(controller);

            discussion = await startMultiRoundDiscussion(
              result,
              analysisLevel,
              geminiConfig,
              (progress) => {
                setRoundProgress(progress.currentRound, progress.totalRounds);
                setDiscussionMessages(progress.messages);
                if (progress.partialDiscussion) {
                  // [PHASE 3 OPTIMIZATION]: Incremental UI update
                  setDiscussionStoreResults(progress.partialDiscussion as any);
                  setScenarioResults(progress.partialDiscussion as any);
                }
              },
              controller.signal,
            );

            setAbortController(null);
          } else {
            // Fallback (though currently quick mode skips this block)
            discussion = await startAgentDiscussion(result, geminiConfig);
          }

          setDiscussionStoreResults(discussion);
          setScenarioResults(discussion);

          // Merge discussion into analysis, but only non-undefined fields
          // to avoid overwriting initial analysis data with undefined
          const definedDiscussion = Object.fromEntries(
            Object.entries(discussion).filter(([, v]) => v !== undefined)
          );

          const finalAnalysis: StockAnalysis = {
            ...result,
            ...definedDiscussion,
            discussion: discussion.messages,
            tradingPlan: discussion.tradingPlan || result.tradingPlan,
            verificationMetrics: discussion.verificationMetrics || result.verificationMetrics,
            capitalFlow: discussion.capitalFlow || result.capitalFlow,
            expectedValueOutcome: discussion.expectedValueOutcome || result.expectedValueOutcome,
            sensitivityMatrix: discussion.sensitivityMatrix || result.sensitivityMatrix,
            dataVerification: discussion.dataVerification || result.dataVerification
          };
          setAnalysis(finalAnalysis);

          await saveAnalysisToHistory('stock', finalAnalysis);
          void fetchAdminData();
        } catch (err) {
          console.error('Agent discussion failed:', err);
          setAnalysisError(err instanceof Error ? err.message : '专家讨论失败，请稍后重试。');
        } finally {
          setIsDiscussing(false);
          setRoundProgress(0, 0);
        }
      }
    } catch (err) {
      console.error(err);
      setAnalysisError(err instanceof Error ? err.message : '分析股票失败，请稍后重试。');
    } finally {
      setLoading(false);
    }
  }, [symbol, market, geminiConfig, analysisLevel, setLoading, resetAnalysis, resetDiscussion, resetScenario, resetErrors, setAnalysis, setShowDiscussion, setIsDiscussing, setDiscussionStoreResults, setScenarioResults, setAnalysisError, setRoundProgress, setAbortController, setDiscussionMessages, fetchAdminData, withTimeout]);

  const resetToHome = useCallback(() => {
    resetAnalysis();
    resetDiscussion();
    resetScenario();
  }, [resetAnalysis, resetDiscussion, resetScenario]);

  return { handleSearch, resetToHome, fetchAdminData };
}
