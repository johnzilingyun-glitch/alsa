import { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Search, Loader2, ChevronRight, ArrowLeft, X, ShieldAlert,
  CheckCircle2, AlertTriangle, Sparkles, ExternalLink, Download, FileText
} from 'lucide-react';
import { saveAnalysisToHistory } from '../../services/aiService';
import { useConfigStore } from '../../stores/useConfigStore';

type Phase = 'idle' | 'analyzing' | 'report';

export function SerenityAlphaAnalyst() {
  const { config } = useConfigStore();
  const model = config?.model || null;

  const [phase, setPhase] = useState<Phase>('idle');
  const [keyword, setKeyword] = useState<string>('');
  const [forceAnalyze, setForceAnalyze] = useState<boolean>(false);

  const [analyzeJobId, setAnalyzeJobId] = useState<string | null>(null);
  const [analyzeProgress, setAnalyzeProgress] = useState<any>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [reportHtml, setReportHtml] = useState<string>('');

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup polls on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const loadAnalysisReport = useCallback(async (jobId: string, sectorName: string) => {
    let fetchedHtml = '';
    try {
      const reportRes = await fetch(`/api/sector/report/${jobId}`);
      if (reportRes.ok) {
        fetchedHtml = await reportRes.text();
        setReportHtml(fetchedHtml);
      }
    } catch (e) {
      console.error('Failed to load report html', e);
    }
    void saveAnalysisToHistory('sector', {
      sectorName: sectorName,
      jobId: jobId,
      reportHtml: fetchedHtml ? true : false,
      stockInfo: {
        symbol: sectorName,
        name: `${sectorName} Serenity Alpha 深度研判`,
        market: 'sector',
        lastUpdated: new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
      },
    });
    setPhase('report');
  }, []);

  const startAnalysis = useCallback(async () => {
    if (pollRef.current) clearInterval(pollRef.current);

    const activeKeyword = keyword.trim() || 'A股市场';
    setPhase('analyzing');
    setAnalyzeError(null);
    setAnalyzeProgress(null);
    setReportHtml('');

    try {
      const res = await fetch('/api/sector/serenity-analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sector_name: activeKeyword,
          model,
          force: forceAnalyze,
          gemini_api_key: config.apiKey || undefined,
          deepseek_api_key: config.deepseekApiKey || undefined
        }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error?.message || '启动专属分析失败');

      const jobId = data.data.job_id;
      setAnalyzeJobId(jobId);

      if (data.data.status === 'completed') {
        await loadAnalysisReport(jobId, activeKeyword);
        return;
      }

      // Poll for analysis completion
      pollRef.current = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/sector/analyze/${jobId}`);
          const pollData = await pollRes.json();
          if (!pollData.success) {
            if (pollRef.current) clearInterval(pollRef.current);
            setAnalyzeError(pollData.error?.message || '分析任务不存在或已失效');
            setPhase('idle');
            return;
          }

          const job = pollData.data;
          setAnalyzeProgress(job.progress);

          if (job.status === 'completed') {
            if (pollRef.current) clearInterval(pollRef.current);
            const usageMetadata = job.result?.usageMetadata;
            if (usageMetadata) {
              import('../../stores/useConfigStore').then(({ useConfigStore }) => {
                useConfigStore.getState().addTokenUsage({
                  promptTokens: usageMetadata.promptTokens || 0,
                  candidatesTokens: usageMetadata.candidatesTokens || 0,
                  totalTokens: usageMetadata.totalTokens || 0
                });
              });
            }
            await loadAnalysisReport(jobId, activeKeyword);
          } else if (job.status === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
            setAnalyzeError(job.error || '分析失败');
            setPhase('idle');
          }
        } catch {
          // ignore poll network errors
        }
      }, 3000);
    } catch (err: any) {
      setAnalyzeError(err.message);
      setPhase('idle');
    }
  }, [model, keyword, forceAnalyze, loadAnalysisReport, config]);

  const reset = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (phase === 'analyzing' && analyzeJobId) {
      fetch(`/api/sector/analyze/${analyzeJobId}/cancel`, { method: 'POST' }).catch(() => {});
    }
    setPhase('idle');
    setAnalyzeJobId(null);
    setAnalyzeError(null);
    setAnalyzeProgress(null);
    setReportHtml('');
  }, [phase, analyzeJobId]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-t border-zinc-100 pt-6">
        <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-widest text-zinc-400">
          <Sparkles size={16} className="text-violet-500" />
          Serenity Alpha Analyst 专属研判
        </h3>
        {phase !== 'idle' && (
          <button
            onClick={reset}
            className="text-xs text-zinc-400 hover:text-zinc-600 flex items-center gap-1 transition-colors"
          >
            <X size={14} /> 重置
          </button>
        )}
      </div>

      <div className="bg-gradient-to-br from-violet-50/50 to-indigo-50/30 rounded-2xl border border-violet-100/60 p-6 shadow-sm">
        <AnimatePresence mode="wait">
          {/* IDLE */}
          {phase === 'idle' && (
            <motion.div
              key="idle"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-4"
            >
              <div className="text-left space-y-1">
                <p className="text-zinc-700 text-sm font-semibold">
                  调用 Serenity Alpha 深度研究员模型
                </p>
                <p className="text-zinc-400 text-xs leading-relaxed">
                  通过输入特定的新闻催化剂、概念或行业关键字，快速将市场催化现象映射到对应的小盘、高弹性标的财务预测中，获取极高纯度的阿尔法投资假设。
                </p>
              </div>

              {/* Controls */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 w-full">
                <div className="flex-1 flex items-center gap-2 bg-white px-3 py-2 rounded-xl border border-zinc-200 shadow-sm focus-within:border-violet-300 focus-within:shadow-md transition-all">
                  <Search size={16} className="text-zinc-400" />
                  <input
                    type="text"
                    placeholder="输入分析关键字（例如: 低空经济, 固态电池, 脑机接口），留空默认分析整体市场..."
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        startAnalysis();
                      }
                    }}
                    className="flex-1 text-sm bg-transparent border-0 outline-none text-zinc-700"
                  />
                </div>

                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-1.5 px-3 py-2 bg-white rounded-xl border border-zinc-200 shadow-sm cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={forceAnalyze}
                      onChange={(e) => setForceAnalyze(e.target.checked)}
                      className="rounded text-violet-600 focus:ring-violet-500 border-zinc-300 w-4 h-4"
                    />
                    <span className="text-xs font-medium text-zinc-600">强制重新生成</span>
                  </label>

                  <button
                    onClick={startAnalysis}
                    className="flex items-center justify-center gap-2 px-5 py-2 bg-violet-600 text-white font-medium text-sm rounded-xl hover:bg-violet-700 transition-colors shadow-sm"
                  >
                    <Sparkles size={14} />
                    开始研判
                  </button>
                </div>
              </div>

              {analyzeError && (
                <p className="text-rose-500 text-xs flex items-center gap-1">
                  <ShieldAlert size={12} className="shrink-0" /> {analyzeError}
                </p>
              )}
            </motion.div>
          )}

          {/* ANALYZING */}
          {phase === 'analyzing' && (
            <motion.div
              key="analyzing"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-4"
            >
              <div className="flex items-center gap-3 p-4 bg-violet-50/50 rounded-xl border border-violet-100/60">
                <Loader2 size={20} className="animate-spin text-violet-500 flex-shrink-0" />
                <div className="flex-1 min-w-0 text-left">
                  <p className="text-sm font-medium text-zinc-700">
                    Serenity Alpha 正在研判: <span className="text-violet-600 font-bold">{keyword.trim() || 'A股市场'}</span>
                  </p>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {analyzeProgress?.message || '静谧阿尔法分析师正在通过搜寻最新资讯与估算阿尔法弹性进行研报输出...'}
                  </p>
                </div>
                <div className="text-right flex-shrink-0">
                  <span className="text-lg font-bold text-violet-600">
                    {analyzeProgress?.progress || 0}%
                  </span>
                </div>
              </div>
              <div className="w-full h-2 bg-zinc-200 rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-violet-500 to-indigo-500 rounded-full"
                  animate={{ width: `${analyzeProgress?.progress || 5}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>
            </motion.div>
          )}

          {/* REPORT */}
          {phase === 'report' && (
            <motion.div
              key="report"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="space-y-4"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-emerald-500" />
                  <span className="text-sm font-semibold text-zinc-700">
                    {keyword.trim() || 'A股市场'} 专属研判完成
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={reset}
                    className="text-xs text-zinc-400 hover:text-zinc-600 flex items-center gap-1 transition-colors px-3 py-1.5 rounded-lg border border-zinc-200 hover:border-zinc-300 bg-white"
                  >
                    <ArrowLeft size={12} /> 分析其他主题
                  </button>
                  {reportHtml && analyzeJobId && (
                    <div className="flex items-center gap-2">
                      <a
                        href={`/api/sector/report/${analyzeJobId}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-violet-500 hover:text-violet-700 flex items-center gap-1 transition-colors px-3 py-1.5 rounded-lg border border-violet-200 hover:border-violet-300 bg-white"
                        title="在新窗口查看报告"
                      >
                        <ExternalLink size={12} /> 查看
                      </a>
                      <a
                        href={`/api/sector/report/${analyzeJobId}/html`}
                        download
                        className="text-xs text-emerald-600 hover:text-emerald-700 flex items-center gap-1 transition-colors px-3 py-1.5 rounded-lg border border-emerald-200 hover:border-emerald-300 bg-white"
                        title="下载为 HTML"
                      >
                        <FileText size={12} /> HTML
                      </a>
                      <a
                        href={`/api/sector/report/${analyzeJobId}/pdf`}
                        download
                        className="text-xs text-rose-600 hover:text-rose-700 flex items-center gap-1 transition-colors px-3 py-1.5 rounded-lg border border-rose-200 hover:border-rose-300 bg-white"
                        title="下载为 PDF"
                      >
                        <Download size={12} /> PDF
                      </a>
                    </div>
                  )}
                </div>
              </div>

              {reportHtml ? (
                <div className="bg-white rounded-xl border border-zinc-200/60 overflow-hidden shadow-sm">
                  <iframe
                    srcDoc={reportHtml}
                    className="w-full border-0"
                    style={{ height: '70vh' }}
                    title={`${keyword.trim() || 'A股市场'} Serenity Alpha 深度研判报告`}
                    sandbox="allow-same-origin"
                  />
                </div>
              ) : (
                <div className="p-6 bg-zinc-50 rounded-xl border border-zinc-200/60 text-center text-zinc-400 text-sm">
                  研报已完成，但读取报告失败。请尝试在新窗口中打开。
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
