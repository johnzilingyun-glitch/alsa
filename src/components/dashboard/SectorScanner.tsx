import { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Search, Loader2, ChevronRight, ArrowLeft, X, BarChart3,
  CheckCircle2, AlertTriangle, TrendingUp, ExternalLink, Download, FileText
} from 'lucide-react';
import { saveAnalysisToHistory } from '../../services/aiService';
import { useConfigStore } from '../../stores/useConfigStore';

interface SectorInfo {
  name: string;
  selected: boolean;
}

type Phase = 'idle' | 'scanning' | 'select' | 'analyzing' | 'report';

export function SectorScanner() {
  const { config } = useConfigStore();
  const model = config?.model || null;
  const [phase, setPhase] = useState<Phase>('idle');
  const [scanJobId, setScanJobId] = useState<string | null>(null);
  const [scanResult, setScanResult] = useState<string>('');
  const [sectors, setSectors] = useState<SectorInfo[]>([]);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanProgress, setScanProgress] = useState<string>('');

  const [analyzeJobId, setAnalyzeJobId] = useState<string | null>(null);
  const [analyzeProgress, setAnalyzeProgress] = useState<any>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [selectedSector, setSelectedSector] = useState<string>('');
  const [customSector, setCustomSector] = useState<string>('');

  const [reportHtml, setReportHtml] = useState<string>('');

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // New Date, Force Rescan & Calendar states
  const [selectedDate, setSelectedDate] = useState<string>(() => {
    return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' });
  });
  const [forceRescan, setForceRescan] = useState<boolean>(false);
  const [hasHistoryPrompt, setHasHistoryPrompt] = useState<boolean>(false);
  const [historyDates, setHistoryDates] = useState<string[]>([]);
  const [calendarYear, setCalendarYear] = useState<number>(new Date().getFullYear());
  const [calendarMonth, setCalendarMonth] = useState<number>(new Date().getMonth());

  // Cleanup polls on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const fetchHistoryDates = useCallback(async () => {
    try {
      const res = await fetch('/api/sector/history/dates');
      const data = await res.json();
      if (data.success && data.data?.dates) {
        setHistoryDates(data.data.dates);
      }
    } catch (e) {
      console.error('Failed to fetch history dates', e);
    }
  }, []);

  useEffect(() => {
    fetchHistoryDates();
  }, [fetchHistoryDates]);

  useEffect(() => {
    if (historyDates.includes(selectedDate)) {
      setHasHistoryPrompt(true);
    } else {
      setHasHistoryPrompt(false);
    }
  }, [selectedDate, historyDates]);

  const loadHistoryScan = useCallback(async (dateStr: string) => {
    setPhase('scanning');
    setScanProgress('正在载入历史扫描数据...');
    setScanError(null);
    setScanResult('');
    setSectors([]);
    try {
      const res = await fetch(`/api/sector/history?date=${dateStr}&type=scan`);
      const data = await res.json();
      if (data.success && data.data?.result) {
        const payload = data.data.result;
        setScanResult(payload.result || '');
        setSectors((payload.sectors || []).map((s: string) => ({ name: s, selected: false })));
        setScanJobId(data.data.job_id);
        setPhase('select');
        setHasHistoryPrompt(false);
      } else {
        throw new Error('加载历史扫描数据失败');
      }
    } catch (err: any) {
      setScanError(err.message);
      setPhase('idle');
    }
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
        name: `${sectorName}板块分析`,
        market: 'sector',
        lastUpdated: new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }),
      },
    });
    setPhase('report');
  }, []);

  const prevMonth = useCallback(() => {
    setCalendarMonth(m => {
      if (m === 0) {
        setCalendarYear(y => y - 1);
        return 11;
      }
      return m - 1;
    });
  }, []);

  const nextMonth = useCallback(() => {
    setCalendarMonth(m => {
      if (m === 11) {
        setCalendarYear(y => y + 1);
        return 0;
      }
      return m + 1;
    });
  }, []);

  const getCalendarDays = useCallback(() => {
    const daysInMonth = new Date(calendarYear, calendarMonth + 1, 0).getDate();
    const firstDayIndex = new Date(calendarYear, calendarMonth, 1).getDay();
    const days = [];
    for (let i = 0; i < firstDayIndex; i++) {
      days.push(null);
    }
    for (let d = 1; d <= daysInMonth; d++) {
      days.push(d);
    }
    return days;
  }, [calendarYear, calendarMonth]);

  // ---------- Scan ----------
  const startScan = useCallback(async (overrideForce?: boolean) => {
    if (pollRef.current) clearInterval(pollRef.current);
    const isForce = overrideForce !== undefined ? overrideForce : forceRescan;
    
    setPhase('scanning');
    setScanError(null);
    setScanResult('');
    setSectors([]);
    setScanProgress('正在启动市场扫描...');

    try {
      const res = await fetch('/api/sector/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          model, 
          date: selectedDate, 
          force: isForce,
          gemini_api_key: config.apiKey || undefined,
          deepseek_api_key: config.deepseekApiKey || undefined
        }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error?.message || '启动扫描失败');

      const jobId = data.data.job_id;
      setScanJobId(jobId);

      if (data.data.status === 'completed') {
        const payload = data.data.result;
        setScanResult(payload.result || '');
        setSectors((payload.sectors || []).map((s: string) => ({ name: s, selected: false })));
        setPhase('select');
        setHasHistoryPrompt(false);
        fetchHistoryDates();
        return;
      }

      // Start polling
      pollRef.current = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/sector/run/${jobId}`);
          const pollData = await pollRes.json();
          if (!pollData.success) {
            // Stop polling if the job is not found or other errors
            if (pollRef.current) clearInterval(pollRef.current);
            setScanError(pollData.error?.message || '扫描任务不存在或已失效');
            setPhase('idle');
            return;
          }

          const job = pollData.data;
          setScanProgress(job.progress || '扫描中...');

          if (job.status === 'completed') {
            if (pollRef.current) clearInterval(pollRef.current);
            setScanResult(job.result || '');
            setSectors((job.sectors || []).map((s: string) => ({ name: s, selected: false })));
            setPhase('select');
            setHasHistoryPrompt(false);
            fetchHistoryDates();
          } else if (job.status === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
            setScanError(job.error || '扫描失败');
            setPhase('idle');
          }
        } catch {
          // ignore poll network errors, keep trying
        }
      }, 3000);
    } catch (err: any) {
      setScanError(err.message);
      setPhase('idle');
    }
  }, [model, selectedDate, forceRescan, fetchHistoryDates]);

  // ---------- Analyze ----------
  const startAnalysis = useCallback(async (sectorName: string, overrideForce?: boolean) => {
    if (pollRef.current) clearInterval(pollRef.current);
    const isForce = overrideForce !== undefined ? overrideForce : forceRescan;

    setSelectedSector(sectorName);
    setPhase('analyzing');
    setAnalyzeError(null);
    setAnalyzeProgress(null);
    setReportHtml('');

    try {
      const res = await fetch('/api/sector/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          sector_name: sectorName, 
          model, 
          date: selectedDate, 
          force: isForce,
          gemini_api_key: config.apiKey || undefined,
          deepseek_api_key: config.deepseekApiKey || undefined
        }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error?.message || '启动分析失败');

      const jobId = data.data.job_id;
      setAnalyzeJobId(jobId);

      if (data.data.status === 'completed') {
        await loadAnalysisReport(jobId, sectorName);
        fetchHistoryDates();
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
            setPhase('select');
            return;
          }

          const job = pollData.data;
          setAnalyzeProgress(job.progress);

          if (job.status === 'completed') {
            if (pollRef.current) clearInterval(pollRef.current);
            await loadAnalysisReport(jobId, sectorName);
            fetchHistoryDates();
          } else if (job.status === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
            setAnalyzeError(job.error || '分析失败');
            setPhase('select');
          }
        } catch {
          // ignore poll network errors
        }
      }, 3000);
    } catch (err: any) {
      setAnalyzeError(err.message);
      setPhase('select');
    }
  }, [model, selectedDate, forceRescan, loadAnalysisReport, fetchHistoryDates]);

  const reset = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    
    // Attempt to cancel backend tasks
    if (phase === 'scanning' && scanJobId) {
      fetch(`/api/sector/run/${scanJobId}/cancel`, { method: 'POST' }).catch(() => {});
    } else if (phase === 'analyzing' && analyzeJobId) {
      fetch(`/api/sector/analyze/${analyzeJobId}/cancel`, { method: 'POST' }).catch(() => {});
    }

    setPhase('idle');
    setScanJobId(null);
    setScanResult('');
    setSectors([]);
    setScanError(null);
    setAnalyzeJobId(null);
    setAnalyzeError(null);
    setAnalyzeProgress(null);
    setReportHtml('');
    setHasHistoryPrompt(false);
  }, [phase, scanJobId, analyzeJobId]);

  const backToSelect = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (phase === 'analyzing' && analyzeJobId) {
      fetch(`/api/sector/analyze/${analyzeJobId}/cancel`, { method: 'POST' }).catch(() => {});
    }
    setPhase('select');
    setAnalyzeJobId(null);
    setAnalyzeProgress(null);
    setAnalyzeError(null);
    setReportHtml('');
  }, [phase, analyzeJobId]);

  // ---------- Render ----------
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-widest text-zinc-400">
          <BarChart3 size={16} className="text-indigo-500" />
          板块扫描与深度分析
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

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 items-start">
        <div className="lg:col-span-3 space-y-4">
          <AnimatePresence mode="wait">
        {/* IDLE — Start button */}
        {phase === 'idle' && (
          <motion.div
            key="idle"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex flex-col items-center gap-4 py-8 bg-gradient-to-br from-indigo-50/50 to-violet-50/30 rounded-2xl border border-indigo-100/60"
          >
            <div className="text-center space-y-2">
              <p className="text-zinc-600 text-sm">
                AI驱动的A股板块轮动扫描，发现最具投资价值的行业板块
              </p>
              <p className="text-zinc-400 text-xs">
                使用实时数据搜索 + 多专家分析，推荐5-8个热门板块并提供深度分析
              </p>
            </div>

            {/* Controls */}
            <div className="flex flex-wrap items-center justify-center gap-4 mt-2">
              {/* Date Selector */}
              <div className="flex items-center gap-2 p-2 bg-white rounded-xl border border-zinc-200/60 shadow-sm">
                <span className="text-xs font-medium text-zinc-500">选择日期</span>
                <input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="text-xs font-semibold text-zinc-700 bg-transparent border-0 outline-none focus:ring-0 cursor-pointer"
                />
              </div>

              {/* Force Rescan Switch */}
              <label className="flex items-center gap-2 p-2 bg-white rounded-xl border border-zinc-200/60 shadow-sm cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={forceRescan}
                  onChange={(e) => setForceRescan(e.target.checked)}
                  className="rounded text-indigo-600 focus:ring-indigo-500 border-zinc-300 w-4 h-4"
                />
                <span className="text-xs font-medium text-zinc-600">强制重新扫描</span>
              </label>
            </div>

            {/* History Prompt Alert */}
            {hasHistoryPrompt && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="w-full max-w-md p-4 bg-indigo-50 border border-indigo-100 rounded-2xl flex flex-col gap-3 shadow-sm text-center"
              >
                <p className="text-xs font-medium text-indigo-700 leading-relaxed">
                  💡 系统检测到该日期 <strong>({selectedDate})</strong> 已有保存的历史扫描数据。
                  您可以直接载入该日期的数据，也可以强制重新发起大模型扫描。
                </p>
                <div className="flex items-center justify-center gap-3">
                  <button
                    onClick={() => loadHistoryScan(selectedDate)}
                    className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-semibold text-xs transition-colors shadow-sm"
                  >
                    直接载入历史数据
                  </button>
                  <button
                    onClick={() => {
                      setForceRescan(true);
                      startScan(true);
                    }}
                    className="px-4 py-2 bg-white hover:bg-zinc-100 text-zinc-600 border border-zinc-200 rounded-xl font-semibold text-xs transition-colors"
                  >
                    重新扫描
                  </button>
                </div>
              </motion.div>
            )}

            {!hasHistoryPrompt && (
              <button
                onClick={() => startScan()}
                className="flex items-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-xl font-medium text-sm hover:bg-indigo-700 transition-colors shadow-sm mt-2"
              >
                <Search size={16} />
                开始板块扫描
              </button>
            )}

            {scanError && (
              <p className="text-rose-500 text-xs flex items-center gap-1">
                <AlertTriangle size={12} /> {scanError}
              </p>
            )}

            {/* Custom Sector Input for IDLE phase */}
            <div className="w-full max-w-md mt-6 pt-6 border-t border-indigo-100/60">
              <p className="text-xs text-zinc-500 text-center mb-3">或者，直接输入您关心的自定义主题：</p>
              <div className="flex items-center gap-2 bg-white p-2 rounded-xl border border-zinc-200/60 shadow-sm focus-within:border-indigo-300 focus-within:shadow-md transition-all">
                <Search size={16} className="text-zinc-400 ml-2" />
                <input
                  type="text"
                  placeholder="输入主题/板块名称 (如: 低空经济)..."
                  value={customSector}
                  onChange={e => setCustomSector(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && customSector.trim()) {
                      startAnalysis(customSector.trim());
                      setCustomSector('');
                    }
                  }}
                  className="flex-1 text-sm bg-transparent border-0 outline-none px-2 text-zinc-700 w-full"
                />
                <button
                  onClick={() => {
                    if (customSector.trim()) {
                      startAnalysis(customSector.trim());
                      setCustomSector('');
                    }
                  }}
                  disabled={!customSector.trim()}
                  className="px-4 py-1.5 bg-indigo-50 text-indigo-600 font-medium text-xs rounded-lg hover:bg-indigo-100 disabled:opacity-50 transition-colors flex-shrink-0"
                >
                  开始深度分析
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {/* SCANNING — Loading state */}
        {phase === 'scanning' && (
          <motion.div
            key="scanning"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center gap-4 py-12 bg-zinc-50 rounded-2xl border border-zinc-200/60"
          >
            <Loader2 size={32} className="animate-spin text-indigo-500" />
            <div className="text-center space-y-1">
              <p className="text-zinc-600 text-sm font-medium">{scanProgress}</p>
              <p className="text-zinc-400 text-xs">正在使用LLM + 实时搜索分析市场板块轮动，预计需要1-3分钟...</p>
            </div>
            <div className="w-48 h-1.5 bg-zinc-200 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-indigo-500 rounded-full"
                initial={{ width: '5%' }}
                animate={{ width: '80%' }}
                transition={{ duration: 120, ease: 'linear' }}
              />
            </div>
          </motion.div>
        )}

        {/* SELECT — Sector grid */}
        {phase === 'select' && (
          <motion.div
            key="select"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="space-y-4"
          >
            {/* Scan result preview */}
            {scanResult && (
              <details className="group">
                <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-600 transition-colors flex items-center gap-1">
                  <ChevronRight size={12} className="group-open:rotate-90 transition-transform" />
                  查看完整扫描报告
                </summary>
                <div className="mt-2 p-4 bg-zinc-50 rounded-xl border border-zinc-200/60 max-h-80 overflow-y-auto text-xs text-zinc-600 whitespace-pre-wrap font-mono leading-relaxed">
                  {scanResult}
                </div>
              </details>
            )}

            {analyzeError && (
              <div className="p-3 bg-rose-50 border border-rose-200/60 rounded-xl text-rose-600 text-xs flex items-center gap-2">
                <AlertTriangle size={14} /> {analyzeError}
              </div>
            )}

            {/* Sector grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {sectors.map((sector, idx) => (
                <motion.button
                  key={sector.name}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: idx * 0.05 }}
                  onClick={() => startAnalysis(sector.name)}
                  className="group relative flex flex-col items-start gap-2 p-4 bg-white rounded-xl border border-zinc-200/60 hover:border-indigo-300 hover:shadow-md transition-all text-left"
                >
                  <div className="flex items-center gap-2 w-full">
                    <span className="text-xs font-bold text-indigo-500 bg-indigo-50 w-6 h-6 rounded-lg flex items-center justify-center">
                      {idx + 1}
                    </span>
                    <span className="text-sm font-medium text-zinc-700 group-hover:text-indigo-600 transition-colors truncate flex-1">
                      {sector.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-zinc-400 group-hover:text-indigo-500 transition-colors">
                    深入分析 <ChevronRight size={12} />
                  </div>
                </motion.button>
              ))}
            </div>

            {sectors.length === 0 && (
              <p className="text-center text-zinc-400 text-sm py-4">未能提取到推荐板块，请重新扫描，或下方手动输入</p>
            )}

            {/* Custom Sector Input */}
            <div className="flex items-center gap-2 mt-4 bg-white p-2 rounded-xl border border-zinc-200/60 shadow-sm focus-within:border-indigo-300 focus-within:shadow-md transition-all">
              <Search size={16} className="text-zinc-400 ml-2" />
              <input
                type="text"
                placeholder="输入自定义主题/板块名称进行分析 (如: 低空经济, 固态电池)..."
                value={customSector}
                onChange={e => setCustomSector(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && customSector.trim()) {
                    startAnalysis(customSector.trim());
                    setCustomSector('');
                  }
                }}
                className="flex-1 text-sm bg-transparent border-0 outline-none px-2 text-zinc-700"
              />
              <button
                onClick={() => {
                  if (customSector.trim()) {
                    startAnalysis(customSector.trim());
                    setCustomSector('');
                  }
                }}
                disabled={!customSector.trim()}
                className="px-4 py-1.5 bg-indigo-50 text-indigo-600 font-medium text-xs rounded-lg hover:bg-indigo-100 disabled:opacity-50 transition-colors"
              >
                开始深度分析
              </button>
            </div>
          </motion.div>
        )}

        {/* ANALYZING — Progress */}
        {phase === 'analyzing' && (
          <motion.div
            key="analyzing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            <div className="flex items-center gap-3 p-4 bg-indigo-50/50 rounded-xl border border-indigo-100/60">
              <Loader2 size={20} className="animate-spin text-indigo-500 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-zinc-700">
                  正在深度分析: <span className="text-indigo-600">{selectedSector}</span>
                </p>
                <p className="text-xs text-zinc-400 mt-0.5">
                  {analyzeProgress?.message || analyzeProgress?.stage || '多位AI专家正在进行板块研讨...'}
                  {analyzeProgress?.round && analyzeProgress?.total_rounds && (
                    <span className="ml-2 text-indigo-500">
                      (第{analyzeProgress.round}/{analyzeProgress.total_rounds}轮)
                    </span>
                  )}
                </p>
              </div>
              <div className="text-right flex-shrink-0">
                <span className="text-lg font-bold text-indigo-600">
                  {analyzeProgress?.progress || 0}%
                </span>
              </div>
            </div>
            <div className="w-full h-2 bg-zinc-200 rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
                animate={{ width: `${analyzeProgress?.progress || 5}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
            <button
              onClick={backToSelect}
              className="text-xs text-zinc-400 hover:text-zinc-600 flex items-center gap-1 transition-colors"
            >
              <ArrowLeft size={12} /> 返回选择其他板块
            </button>
          </motion.div>
        )}

        {/* REPORT — Results */}
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
                <span className="text-sm font-medium text-zinc-700">
                  {selectedSector} 分析完成
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={backToSelect}
                  className="text-xs text-zinc-400 hover:text-zinc-600 flex items-center gap-1 transition-colors px-3 py-1.5 rounded-lg border border-zinc-200 hover:border-zinc-300"
                >
                  <ArrowLeft size={12} /> 分析其他板块
                </button>
                {reportHtml && analyzeJobId && (
                  <div className="flex items-center gap-2">
                    <a
                      href={`/api/sector/report/${analyzeJobId}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-indigo-500 hover:text-indigo-700 flex items-center gap-1 transition-colors px-3 py-1.5 rounded-lg border border-indigo-200 hover:border-indigo-300 bg-white"
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
                  title={`${selectedSector} 板块分析报告`}
                  sandbox="allow-same-origin"
                />
              </div>
            ) : (
              <div className="p-6 bg-zinc-50 rounded-xl border border-zinc-200/60 text-center text-zinc-400 text-sm">
                分析已完成，但报告生成失败。请尝试在新窗口查看。
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
        </div>

        {/* Sidebar Calendar Panel */}
        {(phase === 'idle' || phase === 'select') && (
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="bg-white/80 backdrop-blur-md rounded-2xl border border-zinc-200/60 p-4 shadow-sm space-y-4"
          >
            <div className="flex items-center justify-between border-b border-zinc-100 pb-2">
              <span className="text-xs font-bold text-zinc-500 flex items-center gap-1">
                <TrendingUp size={14} className="text-indigo-500" />
                历史扫描日历
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={prevMonth}
                  className="p-1 hover:bg-zinc-100 rounded text-zinc-400 hover:text-zinc-700 transition-colors text-xs font-bold"
                >
                  &lt;
                </button>
                <span className="text-xs font-bold text-zinc-700 min-w-16 text-center">
                  {calendarYear}年{calendarMonth + 1}月
                </span>
                <button
                  onClick={nextMonth}
                  className="p-1 hover:bg-zinc-100 rounded text-zinc-400 hover:text-zinc-700 transition-colors text-xs font-bold"
                >
                  &gt;
                </button>
              </div>
            </div>

            {/* Calendar Days grid */}
            <div className="grid grid-cols-7 gap-1 text-center text-xs">
              {['日', '一', '二', '三', '四', '五', '六'].map(w => (
                <div key={w} className="font-semibold text-zinc-400 py-1 text-[10px]">{w}</div>
              ))}
              {getCalendarDays().map((day, idx) => {
                if (day === null) return <div key={`empty-${idx}`} className="p-2" />;

                const dateStr = `${calendarYear}-${String(calendarMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                const hasData = historyDates.includes(dateStr);
                const isSelected = selectedDate === dateStr;
                const isToday = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Shanghai' }) === dateStr;

                return (
                  <button
                    key={dateStr}
                    onClick={() => {
                      setSelectedDate(dateStr);
                      if (hasData) {
                        loadHistoryScan(dateStr);
                      }
                    }}
                    className={`
                      relative p-1.5 rounded-lg transition-all flex flex-col items-center justify-center font-medium h-8 w-8 mx-auto text-[11px]
                      ${isSelected ? 'bg-indigo-600 text-white font-bold shadow-sm' : 'hover:bg-zinc-100 text-zinc-700'}
                      ${isToday && !isSelected ? 'border border-indigo-200 text-indigo-600' : ''}
                    `}
                  >
                    <span>{day}</span>
                    {hasData && (
                      <span className={`
                        absolute bottom-1 w-1 h-1 rounded-full
                        ${isSelected ? 'bg-white' : 'bg-indigo-500'}
                      `} />
                    )}
                  </button>
                );
              })}
            </div>
            
            <div className="text-[10px] text-zinc-400 bg-zinc-50 rounded-xl p-2.5 leading-relaxed">
              💡 <strong>日历说明</strong>：
              日历中带有<strong>蓝色圆点</strong>的日期代表有历史保存的扫描数据。点击对应的日期即可直接载入查看。
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
