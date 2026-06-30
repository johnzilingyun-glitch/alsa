import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Search, Loader2, X, CheckCircle2, AlertTriangle, Sparkles, Bot, Users,
  BookOpen, BrainCircuit, BarChart3, TrendingUp, Shield,
  Zap, Target, Eye, Activity, Hash, Scale, History, ChevronRight,
} from 'lucide-react';
import { useConfigStore } from '../../stores/useConfigStore';
import { StockSearchInput } from '../shared/StockSearchInput';
import { saveAnalysisToHistory } from '../../services/aiService';

interface ExpertDef {
  role: string;
  icon: typeof Bot;
  color: string;
  bg: string;
}

const ALL_EXPERTS: ExpertDef[] = [
  { role: 'Technical Analyst', icon: BarChart3, color: 'text-blue-600', bg: 'bg-blue-50 border-blue-200 hover:bg-blue-100' },
  { role: 'Fundamental Analyst', icon: BookOpen, color: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-200 hover:bg-emerald-100' },
  { role: 'Sentiment Analyst', icon: Activity, color: 'text-purple-600', bg: 'bg-purple-50 border-purple-200 hover:bg-purple-100' },
  { role: 'Risk Manager', icon: Shield, color: 'text-amber-600', bg: 'bg-amber-50 border-amber-200 hover:bg-amber-100' },
  { role: 'Aggressive Risk Analyst', icon: Zap, color: 'text-rose-600', bg: 'bg-rose-50 border-rose-200 hover:bg-rose-100' },
  { role: 'Conservative Risk Analyst', icon: Shield, color: 'text-teal-600', bg: 'bg-teal-50 border-teal-200 hover:bg-teal-100' },
  { role: 'Neutral Risk Analyst', icon: Scale, color: 'text-zinc-600', bg: 'bg-zinc-50 border-zinc-200 hover:bg-zinc-100' },
  { role: 'Bull Researcher', icon: TrendingUp, color: 'text-green-600', bg: 'bg-green-50 border-green-200 hover:bg-green-100' },
  { role: 'Bear Researcher', icon: TrendingUp, color: 'text-red-600', bg: 'bg-red-50 border-red-200 hover:bg-red-100' },
  { role: 'Contrarian Strategist', icon: BrainCircuit, color: 'text-violet-600', bg: 'bg-violet-50 border-violet-200 hover:bg-violet-100' },
  { role: 'Deep Research Specialist', icon: Search, color: 'text-indigo-600', bg: 'bg-indigo-50 border-indigo-200 hover:bg-indigo-100' },
  { role: 'Professional Reviewer', icon: Eye, color: 'text-cyan-600', bg: 'bg-cyan-50 border-cyan-200 hover:bg-cyan-100' },
  { role: 'Chief Strategist', icon: BrainCircuit, color: 'text-orange-600', bg: 'bg-orange-50 border-orange-200 hover:bg-orange-100' },
  { role: 'Value Investing Sage', icon: Target, color: 'text-lime-600', bg: 'bg-lime-50 border-lime-200 hover:bg-lime-100' },
  { role: 'Growth Visionary', icon: Sparkles, color: 'text-sky-600', bg: 'bg-sky-50 border-sky-200 hover:bg-sky-100' },
  { role: 'Macro Hedge Titan', icon: Activity, color: 'text-fuchsia-600', bg: 'bg-fuchsia-50 border-fuchsia-200 hover:bg-fuchsia-100' },
];

type InputMode = 'stock' | 'topic';
type Phase = 'idle' | 'analyzing' | 'report';

interface HistoryItem {
  jobId: string;
  sectorName?: string;
  experts?: string;
  stockInfo?: { name?: string; lastUpdated?: string };
}

interface JobProgress {
  progress?: number;
  message?: string;
}

export function UserExpertAnalysis() {
  const { config } = useConfigStore();
  const model = config?.model || null;

  const [selectedExperts, setSelectedExperts] = useState<Set<string>>(new Set());
  const [inputMode, setInputMode] = useState<InputMode>('stock');
  const [stockSymbol, setStockSymbol] = useState('');
  const [stockMarket, setStockMarket] = useState('A-Share');
  const [topicText, setTopicText] = useState('');
  const [forceAnalyze, setForceAnalyze] = useState(false);
  const [phase, setPhase] = useState<Phase>('idle');
  const [analyzeJobId, setAnalyzeJobId] = useState<string | null>(null);
  const [analyzeProgress, setAnalyzeProgress] = useState<JobProgress | null>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [reportHtml, setReportHtml] = useState<string>('');
  const [showHistory, setShowHistory] = useState(false);
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedHistory, setSelectedHistory] = useState<HistoryItem | null>(null);
  const [historyReportHtml, setHistoryReportHtml] = useState<string | null>(null);
  const [historyReportLoading, setHistoryReportLoading] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const toggleExpert = useCallback((role: string) => {
    setSelectedExperts(prev => {
      const next = new Set(prev);
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedExperts(new Set(ALL_EXPERTS.map(e => e.role)));
  }, []);

  const deselectAll = useCallback(() => {
    setSelectedExperts(new Set());
  }, []);

  const handleStockSelect = useCallback((symbol: string, market?: string) => {
    setStockSymbol(symbol);
    if (market) setStockMarket(market);
  }, []);

  const loadAnalysisReport = useCallback(async (jobId: string, sectorName: string) => {
    let html = '';
    try {
      const res = await fetch(`/api/sector/report/${jobId}`);
      if (res.ok) {
        html = await res.text();
      }
    } catch {
      // report fetch failed silently
    }
    if (!html || html.trim().length < 50) {
      setAnalyzeError('报告内容异常或为空，请使用「强制重新生成」选项重试');
      setPhase('idle');
      return;
    }
    setReportHtml(html);
    void saveAnalysisToHistory('sector', {
      sectorName,
      jobId,
      experts: Array.from(selectedExperts).join(', '),
      reportHtml: true,
    });
    setPhase('report');
  }, [selectedExperts]);

  const startAnalysis = useCallback(async () => {
    const experts = Array.from(selectedExperts);
    if (experts.length === 0) {
      setAnalyzeError('请至少选择一个专家');
      return;
    }
    const query = inputMode === 'stock' ? stockSymbol : topicText.trim();
    if (!query) {
      setAnalyzeError(inputMode === 'stock' ? '请输入股票代码' : '请输入分析主题');
      return;
    }

    setPhase('analyzing');
    setAnalyzeError(null);
    setAnalyzeProgress(null);
    setReportHtml('');

    try {
      const body: Record<string, unknown> = {
        sector_name: query,
        model: model ?? undefined,
        force: forceAnalyze,
        gemini_api_key: config.apiKey ?? undefined,
        deepseek_api_key: config.deepseekApiKey ?? undefined,
        experts,
      };
      if (inputMode === 'stock') {
        body.market = stockMarket;
        body.symbol = stockSymbol;
      }

      const res = await fetch('/api/sector/serenity-analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json() as Record<string, unknown>;
      if (!data.success) throw new Error((data.error as Record<string, string>)?.message || '启动分析失败');

      const jobData = data.data as Record<string, unknown> | undefined;
      const jobId = (jobData?.job_id as string) || 'unknown';
      setAnalyzeJobId(jobId);

      if (jobData?.status === 'completed') {
        await loadAnalysisReport(jobId, query);
        return;
      }

      pollRef.current = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/sector/analyze/${jobId}`);
          const pollData = await pollRes.json() as Record<string, unknown>;
          if (!pollData.success) {
            clearInterval(pollRef.current!);
            setAnalyzeError((pollData.error as Record<string, string>)?.message || '分析任务不存在或已失效');
            setPhase('idle');
            return;
          }

          const job = pollData.data as Record<string, unknown>;
          setAnalyzeProgress(job.progress as JobProgress);

          if (job.status === 'completed') {
            clearInterval(pollRef.current!);
            const usageMetadata = job.result as Record<string, unknown> | undefined;
            const meta = usageMetadata?.usageMetadata as Record<string, number> | undefined;
            if (meta) {
              useConfigStore.getState().addTokenUsage({
                promptTokens: meta.promptTokenCount || 0,
                candidatesTokens: meta.candidatesTokenCount || 0,
                totalTokens: meta.totalTokenCount || 0,
              });
            }
            await loadAnalysisReport(jobId, query);
          } else if (job.status === 'failed') {
            clearInterval(pollRef.current!);
            setAnalyzeError((job.error as string) || '分析失败');
            setPhase('idle');
          }
        } catch {
          // ignore poll network errors
        }
      }, 3000);
    } catch (err: unknown) {
      setAnalyzeError(err instanceof Error ? err.message : '启动分析失败');
      setPhase('idle');
    }
  }, [selectedExperts, inputMode, stockSymbol, stockMarket, topicText, model, config, forceAnalyze, loadAnalysisReport]);

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

  const fetchHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch('/api/history/context');
      const data = await res.json() as Record<string, unknown>;
      const list = ((data?.data || data) as unknown[]) || [];
      const items = list.filter((item: unknown) => (item as Record<string, unknown>).type === 'sector') as HistoryItem[];
      setHistoryItems(items.reverse());
      setShowHistory(true);
    } catch {
      setAnalyzeError('获取历史记录失败');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const loadHistoryReport = useCallback(async (item: HistoryItem) => {
    setSelectedHistory(item);
    setHistoryReportHtml(null);
    setHistoryReportLoading(true);
    try {
      const res = await fetch(`/api/sector/report/${item.jobId}`);
      if (res.ok) {
        setHistoryReportHtml(await res.text());
      } else {
        setHistoryReportHtml('无法加载报告内容');
      }
    } catch {
      setHistoryReportHtml('加载报告失败');
    } finally {
      setHistoryReportLoading(false);
    }
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between border-t border-zinc-100 pt-6">
        <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-widest text-zinc-400">
          <Users size={16} className="text-indigo-500" />
          用户自选专家分析
        </h3>
        <button
          onClick={() => { if (showHistory) setShowHistory(false); else fetchHistory(); }}
          className="flex items-center gap-1 text-xs font-medium text-zinc-500 hover:text-indigo-600 px-2.5 py-1.5 rounded-lg border border-zinc-200 hover:border-indigo-300 bg-white transition-colors"
        >
          <History size={13} />
          {showHistory ? '收起历史' : '历史记录'}
        </button>
      </div>

      <div className="bg-gradient-to-br from-indigo-50/50 to-blue-50/30 rounded-2xl border border-indigo-100/60 p-6 shadow-sm">
        <div className="space-y-5">
          {phase === 'idle' && (
            <>
              <div>
                <div className="flex items-center justify-between mb-3">
                  <p className="text-sm font-semibold text-zinc-700 flex items-center gap-1.5">
                    <Bot size={14} className="text-indigo-500" />
                    选择分析专家 ({selectedExperts.size}/{ALL_EXPERTS.length})
                  </p>
                  <div className="flex items-center gap-2">
                    <button onClick={selectAll} className="text-[11px] font-medium text-indigo-600 hover:text-indigo-700 px-2 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 transition-colors">全选</button>
                    <button onClick={deselectAll} className="text-[11px] font-medium text-zinc-500 hover:text-zinc-600 px-2 py-1 rounded-lg bg-zinc-50 hover:bg-zinc-100 transition-colors">清空</button>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {ALL_EXPERTS.map(({ role, icon: Icon, color, bg }) => {
                    const isSelected = selectedExperts.has(role);
                    return (
                      <button key={role} onClick={() => toggleExpert(role)}
                        className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition-all ${
                          isSelected ? `${color} ${bg} shadow-sm` : 'text-zinc-400 border-zinc-200 bg-white hover:bg-zinc-50 hover:text-zinc-600'
                        }`}>
                        <Icon size={12} /> {role}
                        {isSelected && <CheckCircle2 size={10} className="opacity-60" />}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex items-center gap-1 p-1 bg-zinc-100/80 rounded-xl w-fit">
                <button onClick={() => setInputMode('stock')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${inputMode === 'stock' ? 'bg-white text-indigo-600 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'}`}>股票搜索</button>
                <button onClick={() => setInputMode('topic')}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${inputMode === 'topic' ? 'bg-white text-indigo-600 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'}`}>自定义主题</button>
              </div>

              {inputMode === 'stock' ? (
                <StockSearchInput value={stockSymbol} market={stockMarket} placeholder="输入股票代码 / 名称 / 拼音..." onSelect={handleStockSelect} className="w-full" />
              ) : (
                <div className="flex items-center gap-2 bg-white px-3 py-2 rounded-xl border border-zinc-200 shadow-sm focus-within:border-indigo-300 focus-within:shadow-md transition-all">
                  <Hash size={16} className="text-zinc-400 shrink-0" />
                  <input type="text" placeholder="输入分析主题（例如: 低空经济, 固态电池, 半导体行业）..." value={topicText}
                    onChange={(e) => setTopicText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') startAnalysis(); }}
                    className="flex-1 text-sm bg-transparent border-0 outline-none text-zinc-700" />
                </div>
              )}

              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1.5 px-3 py-2 bg-white rounded-xl border border-zinc-200 shadow-sm cursor-pointer select-none">
                  <input type="checkbox" checked={forceAnalyze}
                    onChange={(e) => setForceAnalyze(e.target.checked)}
                    className="rounded text-indigo-600 focus:ring-indigo-500 border-zinc-300 w-4 h-4" />
                  <span className="text-xs font-medium text-zinc-600">强制重新生成</span>
                </label>
                <button onClick={startAnalysis}
                  className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 bg-indigo-600 text-white font-medium text-sm rounded-xl hover:bg-indigo-700 transition-colors shadow-sm">
                  <Sparkles size={14} /> 启动 {selectedExperts.size} 位专家分析
                </button>
              </div>

              {analyzeError && (
                <div className="flex items-start gap-2 p-3 bg-rose-50 border border-rose-200 rounded-xl">
                  <AlertTriangle size={14} className="text-rose-500 shrink-0 mt-0.5" />
                  <p className="text-xs text-rose-600">{analyzeError}</p>
                </div>
              )}
            </>
          )}

          {phase === 'analyzing' && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 p-4 bg-indigo-50/50 rounded-xl border border-indigo-100/60">
                <Loader2 size={20} className="animate-spin text-indigo-500 flex-shrink-0" />
                <div className="flex-1 min-w-0 text-left">
                  <p className="text-sm font-medium text-zinc-700">
                    专家正在研判: <span className="text-indigo-600 font-bold">{inputMode === 'stock' ? stockSymbol : (topicText.trim() || 'A股市场')}</span>
                  </p>
                  <p className="text-xs text-zinc-400 mt-0.5">{analyzeProgress?.message || '正在调用所选专家进行分析...'}</p>
                </div>
                <div className="text-right flex-shrink-0">
                  <span className="text-lg font-bold text-indigo-600">{analyzeProgress?.progress || 0}%</span>
                </div>
              </div>
              <div className="w-full h-2 bg-zinc-200 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-indigo-500 to-blue-500 rounded-full transition-all duration-500"
                  style={{ width: `${analyzeProgress?.progress || 5}%` }} />
              </div>
              <button onClick={reset} className="text-xs text-zinc-400 hover:text-zinc-600 transition-colors">取消分析</button>
              {analyzeError && (
                <div className="flex items-start gap-2 p-3 bg-rose-50 border border-rose-200 rounded-xl">
                  <AlertTriangle size={14} className="text-rose-500 shrink-0 mt-0.5" />
                  <p className="text-xs text-rose-600">{analyzeError}</p>
                </div>
              )}
            </div>
          )}

          {phase === 'report' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 size={16} className="text-emerald-500" />
                  <span className="text-sm font-semibold text-zinc-700">
                    {inputMode === 'stock' ? stockSymbol : (topicText.trim() || 'A股市场')} 专家分析完成
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={reset} className="text-xs text-zinc-400 hover:text-zinc-600 flex items-center gap-1 transition-colors px-3 py-1.5 rounded-lg border border-zinc-200 hover:border-zinc-300 bg-white">
                    <ChevronRight size={12} className="rotate-180" /> 分析其他主题
                  </button>
                  {reportHtml && analyzeJobId && (
                    <a href={`/api/sector/report/${analyzeJobId}`} target="_blank" rel="noopener noreferrer"
                      className="text-xs text-indigo-600 hover:text-indigo-700 flex items-center gap-1 transition-colors px-3 py-1.5 rounded-lg border border-indigo-200 hover:border-indigo-300 bg-white">
                      查看 <ChevronRight size={12} />
                    </a>
                  )}
                </div>
              </div>
              {reportHtml ? (
                <div className="bg-white rounded-xl border border-zinc-200/60 overflow-hidden shadow-sm">
                  <iframe srcDoc={reportHtml} className="w-full border-0" style={{ height: '70vh' }}
                    title={`${inputMode === 'stock' ? stockSymbol : (topicText.trim() || 'A股市场')} 专家分析报告`} sandbox="allow-same-origin" />
                </div>
              ) : (
                <div className="p-6 bg-zinc-50 rounded-xl border border-zinc-200/60 text-center text-zinc-400 text-sm">
                  报告已完成，但读取失败。请在新窗口中查看。
                </div>
              )}
            </div>
          )}

          {showHistory && (
            <div className="border-t border-indigo-100/60 pt-4 space-y-3">
              <p className="text-xs font-semibold text-zinc-500 flex items-center gap-1.5">
                <History size={12} /> 历史记录
              </p>
              {historyLoading ? (
                <div className="flex items-center justify-center py-6 text-zinc-400">
                  <Loader2 size={16} className="animate-spin mr-2" />
                  <span className="text-xs">加载中...</span>
                </div>
              ) : historyItems.length === 0 ? (
                <div className="text-center py-6 text-zinc-400 text-xs">暂无历史记录</div>
              ) : selectedHistory ? (
                <div className="space-y-3">
                  <button onClick={() => { setSelectedHistory(null); setHistoryReportHtml(null); }}
                    className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-700 font-medium">
                    <ChevronRight size={12} className="rotate-180" /> 返回列表
                  </button>
                  <div className="bg-white rounded-xl border border-zinc-200/60 overflow-hidden">
                    <div className="px-4 py-3 border-b border-zinc-100 bg-zinc-50/50">
                      <p className="text-sm font-semibold text-zinc-800">{selectedHistory.sectorName || '板块分析'}</p>
                      <p className="text-xs text-zinc-400 mt-0.5">
                        {selectedHistory.stockInfo?.lastUpdated && new Date(selectedHistory.stockInfo.lastUpdated).toLocaleString('zh-CN')}
                        {selectedHistory.experts && ` | ${selectedHistory.experts}`}
                      </p>
                    </div>
                    <div className="p-4">
                      {historyReportLoading ? (
                        <div className="flex items-center justify-center py-8 text-zinc-400">
                          <Loader2 size={20} className="animate-spin mr-2" />
                          <span className="text-sm">加载报告中...</span>
                        </div>
                      ) : historyReportHtml ? (
                        <iframe srcDoc={historyReportHtml} className="w-full border-0 rounded-lg" style={{ height: '60vh' }} title="历史报告" sandbox="allow-same-origin" />
                      ) : (
                        <div className="text-center py-8 text-zinc-400 text-sm">
                          报告内容暂不可用。
                          {selectedHistory.jobId && (
                            <a href={`/api/sector/report/${selectedHistory.jobId}`} target="_blank" rel="noopener noreferrer"
                              className="block mt-2 text-indigo-600 hover:text-indigo-700 underline">在新窗口打开</a>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {historyItems.map((item, i) => (
                    <button key={item.jobId || i} onClick={() => loadHistoryReport(item)}
                      className="w-full flex items-center justify-between p-3 bg-white rounded-xl border border-zinc-200/60 hover:border-indigo-200 hover:bg-indigo-50/30 transition-all text-left">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-zinc-700 truncate">{item.sectorName || '板块分析'}</p>
                        <p className="text-[11px] text-zinc-400 mt-0.5">
                          {item.stockInfo?.lastUpdated && new Date(item.stockInfo.lastUpdated).toLocaleString('zh-CN')}
                          {item.experts && ` · ${item.experts}`}
                        </p>
                      </div>
                      <ChevronRight size={14} className="text-zinc-300 shrink-0 ml-2" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
