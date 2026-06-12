import React, { useMemo, useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { Loader2, Database, Brain, Search, Sparkles, Activity, Maximize2, Minimize2, CheckCircle2, XCircle, Clock, Target, Zap, AlertTriangle, Radio } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';
import { useDiscussionStore } from '../../stores/useDiscussionStore';
import { useConfigStore } from '../../stores/useConfigStore';
import { cn } from './utils';

const STEPS = [
  { icon: Database, label: '数据采集', match: ['行情', '大宗商品', 'Extracting', 'Syncing', '排队', '提交', '启动', '初始化'] },
  { icon: Search, label: '量化计算', match: ['资讯', '舆情', 'Synthesizing', '量化', '指标'] },
  { icon: Brain, label: '专家研判', match: ['深度研判', '思考', '数据偏差', '定稿', 'Reasoning', 'Drift', 'Finalizing', '专家', '召集'] }
];

const STAGE_DESCRIPTIONS: Record<string, string> = {
  'queued': '正在连接数据管线，准备获取实时行情与基本面数据',
  'starting': '正在初始化分析引擎，加载量化模型与专家模块',
  'snapshot': '正在从多个数据源聚合行情、财务、资金流等全维度数据',
  'quant': '正在通过 Polars 引擎计算 MA/RSI/MACD/布林带等量化指标',
  'discussion': '多位 AI 分析师正在进行多轮辩论式深度研判',
  'finalizing': '正在整合各专家意见，生成最终投资建议与风险评估',
};

function formatElapsedTime(startedAt: number | null): string {
  if (!startedAt) return '0s';
  const elapsed = Math.floor((Date.now() - startedAt) / 1000);
  if (elapsed < 60) return `${elapsed}s`;
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  return `${mins}m ${secs}s`;
}

export function AnalysisLoadingPulse() {
  const { t } = useTranslation();
  const analysisStatus = useUIStore(s => s.analysisStatus);
  const analysisLogs = useUIStore(s => s.analysisLogs || []);
  const analysisActivity = useUIStore(s => s.analysisActivity);
  const contentCount = useUIStore(s => s.contentCount);
  const analysisTarget = useUIStore(s => s.analysisTarget);
  const analysisStartedAt = useUIStore(s => s.analysisStartedAt);
  const analysisError = useUIStore(s => s.analysisError);
  const modelName = useConfigStore(s => s.config?.model) || 'default';
  
  // Track content count changes for "AI is streaming" indicator
  const prevCountRef = useRef(0);
  const [isStreaming, setIsStreaming] = useState(false);
  const streamTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  
  useEffect(() => {
    if (contentCount > prevCountRef.current) {
      prevCountRef.current = contentCount;
      setIsStreaming(true);
      // Clear previous timeout
      if (streamTimeoutRef.current) clearTimeout(streamTimeoutRef.current);
      // Mark as not streaming after 5s of no count change
      streamTimeoutRef.current = setTimeout(() => setIsStreaming(false), 5000);
    }
    return () => { if (streamTimeoutRef.current) clearTimeout(streamTimeoutRef.current); };
  }, [contentCount]);
  
  const currentRound = useDiscussionStore(s => s.currentRound);
  const totalRounds = useDiscussionStore(s => s.totalRounds);
  const currentStep = useDiscussionStore(s => s.currentStep);
  const lastReasoning = useDiscussionStore(s => s.lastReasoning);
  
  const [isExpanded, setIsExpanded] = useState(true);
  const [isCancelling, setIsCancelling] = useState(false);
  const [elapsed, setElapsed] = useState('0s');
  const logsEndRef = useRef<HTMLDivElement>(null);
  const abortDiscussion = useDiscussionStore(s => s.abortDiscussion);

  // Elapsed time ticker
  useEffect(() => {
    if (!analysisStartedAt) return;
    const interval = setInterval(() => {
      setElapsed(formatElapsedTime(analysisStartedAt));
    }, 1000);
    return () => clearInterval(interval);
  }, [analysisStartedAt]);

  const handleCancel = async () => {
    setIsCancelling(true);
    try {
      // 1. Signal backend to stop via .stop file
      await fetch('/api/analysis/cancel', { method: 'POST' });
      // 2. Abort frontend discussion AbortController
      abortDiscussion();
    } catch (e) {
      console.error('Failed to cancel analysis:', e);
    }
  };

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (isExpanded) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [analysisLogs.length, isExpanded]);

  // Determine active step based on status text keywords
  const activeStepIndex = useMemo(() => {
    if (currentRound > 0) {
      if (currentRound === 1) return 0; // Grounding
      if (currentRound === totalRounds) return 2; // Finalizing
      return 1; // Reasoning
    }
    if (!analysisStatus) return 0;
    const index = STEPS.findIndex(step => 
      step.match.some(keyword => String(analysisStatus).includes(keyword))
    );
    return index === -1 ? 0 : index;
  }, [analysisStatus, currentRound, totalRounds]);

  // Current stage description
  const stageDescription = useMemo(() => {
    if (currentRound > 0) {
      if (currentRound === 1) return STAGE_DESCRIPTIONS['snapshot'];
      if (currentRound === totalRounds) return STAGE_DESCRIPTIONS['finalizing'];
      return STAGE_DESCRIPTIONS['discussion'];
    }
    // Try to match from status text
    const statusStr = String(analysisStatus || '');
    if (statusStr.includes('排队') || statusStr.includes('提交')) return STAGE_DESCRIPTIONS['queued'];
    if (statusStr.includes('启动') || statusStr.includes('初始化')) return STAGE_DESCRIPTIONS['starting'];
    if (statusStr.includes('行情') || statusStr.includes('获取')) return STAGE_DESCRIPTIONS['snapshot'];
    if (statusStr.includes('量化') || statusStr.includes('指标')) return STAGE_DESCRIPTIONS['quant'];
    if (statusStr.includes('专家') || statusStr.includes('研判') || statusStr.includes('召集')) return STAGE_DESCRIPTIONS['discussion'];
    if (statusStr.includes('整理') || statusStr.includes('结论')) return STAGE_DESCRIPTIONS['finalizing'];
    return STAGE_DESCRIPTIONS['queued'];
  }, [analysisStatus, currentRound, totalRounds]);

  const phaseName = useMemo(() => {
    if (currentRound === 0) return t('loading.reasoning');
    if (currentRound === 1) return 'Evidence Grounding & Synthesis';
    if (currentRound === totalRounds) return 'Final Logic Audit & Signing';
    return `Expert Deliberation Round ${currentRound}`;
  }, [currentRound, totalRounds, t]);
  
  if (analysisActivity !== 'analyzing' && analysisActivity !== 'discussing') return null;

  return (
    <AnimatePresence>
      <motion.div
        layout
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.95 }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className={cn(
          "fixed bottom-6 right-6 z-[60] overflow-hidden",
          "bg-white/90 backdrop-blur-xl border border-indigo-100/50 shadow-2xl shadow-indigo-600/10",
          isExpanded ? "rounded-3xl w-[400px]" : "rounded-full w-auto min-w-[200px]"
        )}
      >
        {/* Toggle Button */}
        <button 
          onClick={() => setIsExpanded(!isExpanded)}
          className="absolute top-4 right-4 z-10 p-1.5 rounded-full hover:bg-zinc-100 text-zinc-400 hover:text-zinc-600 transition-colors"
        >
          {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>

        {isExpanded ? (
          <div className="p-7 pb-5 flex flex-col gap-5">
            {/* Header with Target Info */}
            <div className="flex items-center gap-4">
              <div className="relative w-12 h-12 rounded-2xl bg-indigo-600 flex flex-shrink-0 items-center justify-center shadow-lg shadow-indigo-600/30">
                <Sparkles className="text-white w-5 h-5 animate-pulse" />
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                  className="absolute inset-[-4px] rounded-[1.1rem] border border-transparent border-t-indigo-400/50"
                />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-bold text-zinc-900 leading-tight truncate">
                  {phaseName}
                </h3>
                <p className="text-xs text-zinc-500 mt-0.5 flex items-center gap-2 flex-wrap">
                  <span>{currentRound > 0 ? `Stage ${currentRound} of ${totalRounds}` : 'ALSA Intelligence Engine'}</span>
                  <span className="w-1 h-1 rounded-full bg-zinc-300" />
                  <span className="text-[10px] text-zinc-400 font-mono">{modelName}</span>
                </p>
              </div>
            </div>

            {/* Analysis Target Badge + Elapsed Timer */}
            <div className="flex items-center gap-2 flex-wrap">
              {analysisTarget && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-50 border border-indigo-100/60 text-[11px] font-semibold text-indigo-700">
                  <Target size={12} className="text-indigo-400" />
                  <span className="font-mono tracking-wide">{analysisTarget.symbol}</span>
                  <span className="text-indigo-400">·</span>
                  <span className="text-indigo-500">{analysisTarget.market}</span>
                </div>
              )}
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-50 border border-amber-100/60 text-[11px] font-semibold text-amber-700">
                <Clock size={12} className="text-amber-400" />
                <span className="font-mono">{elapsed}</span>
              </div>
              {contentCount > 0 ? (
                <motion.div 
                  key={contentCount}
                  initial={{ scale: 1.15, opacity: 0.7 }}
                  animate={{ scale: 1, opacity: 1 }}
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-bold font-mono border",
                    isStreaming 
                      ? "bg-emerald-50 border-emerald-200/60 text-emerald-700" 
                      : "bg-zinc-50 border-zinc-200/60 text-zinc-500"
                  )}
                >
                  {isStreaming && <Radio size={11} className="text-emerald-500 animate-pulse" />}
                  <span>{contentCount.toLocaleString()}</span>
                  <span className="text-[9px] font-normal opacity-60">chars</span>
                </motion.div>
              ) : (
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-emerald-50 border border-emerald-100/60 text-[10px] font-medium text-emerald-600">
                  <Zap size={11} className="text-emerald-400" />
                  AI 工作中不会超时
                </div>
              )}
            </div>

            {/* Stage Description */}
            <motion.div 
              key={stageDescription}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="px-3 py-2.5 rounded-xl bg-zinc-50/80 border border-zinc-100/60"
            >
              <p className="text-[11px] text-zinc-500 leading-relaxed">
                <span className="text-zinc-400 mr-1">▸</span>
                {stageDescription}
              </p>
            </motion.div>

            {/* Progress Bar */}
            {totalRounds > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                  <span>Engine Progress</span>
                  <span>{Math.round((currentRound / totalRounds) * 100)}%</span>
                </div>
                <div className="h-1.5 w-full bg-zinc-100 rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${(currentRound / totalRounds) * 100}%` }}
                    className="h-full bg-indigo-600 rounded-full"
                  />
                </div>
              </div>
            )}

            {/* Dynamic Step Indicators */}
            <div className="flex items-center justify-between px-2 pt-1 pb-3">
               {STEPS.map((step, i) => {
                 const Icon = step.icon;
                 const isActive = i === activeStepIndex;
                 const isPast = i < activeStepIndex;

                 return (
                   <div key={i} className="flex items-center relative">
                     <div className={cn(
                       "relative z-10 flex flex-col items-center gap-1.5 transition-all duration-500",
                       isActive ? "scale-110 opacity-100" : 
                       isPast ? "scale-100 opacity-60" : "scale-90 opacity-30"
                     )}>
                       <div className={cn(
                         "p-2.5 rounded-xl transition-colors duration-500",
                         isActive ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/20" : 
                         isPast ? "bg-indigo-50 text-indigo-600 border border-indigo-100" : 
                         "bg-zinc-100 text-zinc-400"
                       )}>
                         <Icon size={16} className={cn(isActive && "animate-pulse")} />
                       </div>
                       <span className={cn(
                         "text-[9px] font-semibold tracking-wider",
                         isActive ? "text-indigo-600" : isPast ? "text-indigo-400" : "text-zinc-300"
                       )}>
                         {step.label}
                       </span>
                     </div>
                     
                     {/* Connection Line */}
                     {i < STEPS.length - 1 && (
                       <div className={cn(
                         "absolute left-6 top-5 w-16 h-0.5 -z-0 transition-colors duration-500",
                         isPast ? "bg-indigo-200" : "bg-zinc-100"
                       )} />
                     )}
                   </div>
                 );
               })}
            </div>
            
            <div className="h-px w-full bg-gradient-to-r from-transparent via-zinc-200 to-transparent" />

            {/* Chain of Thought Logs */}
            <div className="space-y-3">
              {lastReasoning && (
                <motion.div 
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="p-3.5 rounded-2xl bg-indigo-50/50 border border-indigo-100/50 shadow-inner"
                >
                  <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                    <Brain size={12} className="animate-pulse" />
                    {t('analysis.conference.reasoning_snippet')}
                  </p>
                  <p className="text-xs text-indigo-900/80 leading-relaxed font-medium italic">
                    "{lastReasoning}"
                  </p>
                </motion.div>
              )}

              <div className="space-y-2.5 max-h-[120px] overflow-y-auto pr-2 custom-scrollbar">
                <AnimatePresence initial={false}>
                  {analysisLogs.map((log, index) => {
                    const isLatest = index === analysisLogs.length - 1;
                    return (
                      <motion.div 
                        key={log.timestamp + index}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="flex items-start gap-3"
                      >
                        <div className="mt-0.5">
                          {isLatest ? (
                            <Loader2 className="w-3.5 h-3.5 text-indigo-500 animate-spin" />
                          ) : (
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
                          )}
                        </div>
                        <span className={cn(
                          "text-xs font-medium leading-relaxed font-mono",
                          isLatest ? "text-indigo-600" : "text-zinc-500"
                        )}>
                          {log.message}
                        </span>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
                <div ref={logsEndRef} />
              </div>
            </div>

            {/* Insufficient Balance Warning */}
            {analysisError && analysisError.includes('余额不足') && (
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-3 rounded-xl bg-amber-50 border border-amber-200/60"
              >
                <p className="text-[11px] text-amber-800 font-semibold flex items-center gap-1.5">
                  <AlertTriangle size={13} className="text-amber-500 flex-shrink-0" />
                  API 余额不足，部分分析师内容缺失
                </p>
                <p className="text-[10px] text-amber-600 mt-1 ml-5">
                  点击「中断并生成报告」将使用已获取的内容生成报告，或前往设置更换 API Key。
                </p>
              </motion.div>
            )}

            {/* Cancel Button */}
            <button
              onClick={handleCancel}
              disabled={isCancelling}
              className={cn(
                "w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-semibold transition-all",
                isCancelling
                  ? "bg-zinc-100 text-zinc-400 cursor-not-allowed"
                  : "bg-red-50 text-red-600 hover:bg-red-100 border border-red-100 hover:border-red-200"
              )}
            >
              <XCircle size={14} />
              {isCancelling ? '正在中断...' : (analysisError && analysisError.includes('余额不足') ? '中断并生成报告' : '中断分析')}
            </button>
          </div>
        ) : (
          /* Minimized Pill State */
          <div className="flex items-center gap-3 px-5 py-3 pr-2">
            <div className="relative flex items-center justify-center cursor-pointer" onClick={() => setIsExpanded(true)}>
              <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
            </div>
            <div className="overflow-hidden relative h-[18px] flex-1 cursor-pointer" onClick={() => setIsExpanded(true)}>
              <AnimatePresence mode="popLayout">
                <motion.span
                  key={analysisStatus}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  className="absolute text-[11px] font-bold text-indigo-600 uppercase tracking-widest whitespace-nowrap"
                >
                  {analysisTarget ? `${analysisTarget.symbol} · ` : ''}{analysisStatus || t('common.loading')}
                </motion.span>
              </AnimatePresence>
            </div>
            {/* Elapsed badge in minimized mode */}
            <span className="text-[10px] font-mono text-amber-600 bg-amber-50 px-2 py-0.5 rounded-lg border border-amber-100/60 whitespace-nowrap">
              {elapsed}
            </span>
            <button
              onClick={handleCancel}
              disabled={isCancelling}
              className="p-1.5 rounded-full text-zinc-400 hover:text-red-500 hover:bg-red-50 transition-colors"
              title="中断分析"
            >
              <XCircle size={14} />
            </button>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
