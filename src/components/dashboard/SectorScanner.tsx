import { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Search, Loader2, ChevronRight, ArrowLeft, X, BarChart3,
  CheckCircle2, AlertTriangle, TrendingUp, ExternalLink
} from 'lucide-react';
import { saveAnalysisToHistory } from '../../services/aiService';

interface SectorInfo {
  name: string;
  selected: boolean;
}

type Phase = 'idle' | 'scanning' | 'select' | 'analyzing' | 'report';

export function SectorScanner() {
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

  const [reportHtml, setReportHtml] = useState<string>('');

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup polls on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ---------- Scan ----------
  const startScan = useCallback(async () => {
    setPhase('scanning');
    setScanError(null);
    setScanResult('');
    setSectors([]);
    setScanProgress('正在启动市场扫描...');

    try {
      const res = await fetch('/api/sector/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error?.message || '启动扫描失败');

      const jobId = data.data.job_id;
      setScanJobId(jobId);

      // Start polling
      pollRef.current = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/sector/scan/${jobId}`);
          const pollData = await pollRes.json();
          if (!pollData.success) return;

          const job = pollData.data;
          setScanProgress(job.progress || '扫描中...');

          if (job.status === 'completed') {
            if (pollRef.current) clearInterval(pollRef.current);
            setScanResult(job.result || '');
            setSectors((job.sectors || []).map((s: string) => ({ name: s, selected: false })));
            setPhase('select');
          } else if (job.status === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
            setScanError(job.error || '扫描失败');
            setPhase('idle');
          }
        } catch {
          // ignore poll errors
        }
      }, 3000);
    } catch (err: any) {
      setScanError(err.message);
      setPhase('idle');
    }
  }, []);

  // ---------- Analyze ----------
  const startAnalysis = useCallback(async (sectorName: string) => {
    setSelectedSector(sectorName);
    setPhase('analyzing');
    setAnalyzeError(null);
    setAnalyzeProgress(null);
    setReportHtml('');

    try {
      const res = await fetch('/api/sector/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sector_name: sectorName }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error?.message || '启动分析失败');

      const jobId = data.data.job_id;
      setAnalyzeJobId(jobId);

      // Poll for analysis completion
      pollRef.current = setInterval(async () => {
        try {
          const pollRes = await fetch(`/api/sector/analyze/${jobId}`);
          const pollData = await pollRes.json();
          if (!pollData.success) return;

          const job = pollData.data;
          setAnalyzeProgress(job.progress);

          if (job.status === 'completed') {
            if (pollRef.current) clearInterval(pollRef.current);
            // Fetch HTML report
            let fetchedHtml = '';
            try {
              const reportRes = await fetch(`/api/sector/report/${jobId}`);
              if (reportRes.ok) {
                fetchedHtml = await reportRes.text();
                setReportHtml(fetchedHtml);
              }
            } catch {
              // report generation optional
            }
            // Save to history
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
          } else if (job.status === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
            setAnalyzeError(job.error || '分析失败');
            setPhase('select');
          }
        } catch {
          // ignore poll errors
        }
      }, 3000);
    } catch (err: any) {
      setAnalyzeError(err.message);
      setPhase('select');
    }
  }, []);

  const reset = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    setPhase('idle');
    setScanJobId(null);
    setScanResult('');
    setSectors([]);
    setScanError(null);
    setAnalyzeJobId(null);
    setAnalyzeProgress(null);
    setAnalyzeError(null);
    setReportHtml('');
  }, []);

  const backToSelect = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    setPhase('select');
    setAnalyzeJobId(null);
    setAnalyzeProgress(null);
    setAnalyzeError(null);
    setReportHtml('');
  }, []);

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
            <button
              onClick={startScan}
              className="flex items-center gap-2 px-6 py-3 bg-indigo-600 text-white rounded-xl font-medium text-sm hover:bg-indigo-700 transition-colors shadow-sm"
            >
              <Search size={16} />
              开始板块扫描
            </button>
            {scanError && (
              <p className="text-rose-500 text-xs flex items-center gap-1">
                <AlertTriangle size={12} /> {scanError}
              </p>
            )}
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
              <p className="text-center text-zinc-400 text-sm py-4">未能提取到推荐板块，请重新扫描</p>
            )}
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
                  <a
                    href={`/api/sector/report/${analyzeJobId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-indigo-500 hover:text-indigo-700 flex items-center gap-1 transition-colors px-3 py-1.5 rounded-lg border border-indigo-200 hover:border-indigo-300"
                  >
                    <ExternalLink size={12} /> 在新窗口查看报告
                  </a>
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
  );
}
