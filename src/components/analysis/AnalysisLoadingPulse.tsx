import React, { useMemo, useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { Loader2, Database, Brain, Search, Sparkles, Activity, Maximize2, Minimize2, CheckCircle2 } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';
import { cn } from './utils';

const STEPS = [
  { icon: Database, match: ['行情', '大宗商品', 'Extracting', 'Syncing'] },
  { icon: Search, match: ['资讯', '舆情', 'Synthesizing'] },
  { icon: Brain, match: ['深度研判', '思考', '数据偏差', '定稿', 'Reasoning', 'Drift', 'Finalizing'] }
];

export function AnalysisLoadingPulse() {
  const { t } = useTranslation();
  const analysisStatus = useUIStore(s => s.analysisStatus);
  const analysisLogs = useUIStore(s => s.analysisLogs || []);
  const analysisActivity = useUIStore(s => s.analysisActivity);
  
  const [isExpanded, setIsExpanded] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (isExpanded) {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [analysisLogs.length, isExpanded]);

  // Determine active step based on status text keywords
  const activeStepIndex = useMemo(() => {
    if (!analysisStatus) return 0;
    const index = STEPS.findIndex(step => 
      step.match.some(keyword => analysisStatus.includes(keyword))
    );
    return index === -1 ? 0 : index;
  }, [analysisStatus]);
  
  if (analysisActivity !== 'analyzing') return null;

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
          isExpanded ? "rounded-3xl w-[380px]" : "rounded-full w-auto min-w-[200px]"
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
          <div className="p-8 pb-6 flex flex-col gap-6">
            <div className="flex items-center gap-4">
              <div className="relative w-12 h-12 rounded-2xl bg-indigo-600 flex flex-shrink-0 items-center justify-center shadow-lg shadow-indigo-600/30">
                <Sparkles className="text-white w-5 h-5 animate-pulse" />
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                  className="absolute inset-[-4px] rounded-[1.1rem] border border-transparent border-t-indigo-400/50"
                />
              </div>
              <div>
                <h3 className="font-bold text-zinc-900 leading-tight">
                  {t('loading.reasoning')}
                </h3>
                <p className="text-xs text-zinc-500 mt-0.5">ALSA Intelligence Engine</p>
              </div>
            </div>

            {/* Dynamic Step Indicators */}
            <div className="flex items-center justify-between px-2 pt-2 pb-4">
               {STEPS.map((step, i) => {
                 const Icon = step.icon;
                 const isActive = i === activeStepIndex;
                 const isPast = i < activeStepIndex;

                 return (
                   <div key={i} className="flex items-center relative">
                     <div className={cn(
                       "relative z-10 flex flex-col items-center gap-2 transition-all duration-500",
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
                     </div>
                     
                     {/* Connection Line */}
                     {i < STEPS.length - 1 && (
                       <div className={cn(
                         "absolute left-6 top-1/2 -translate-y-1/2 w-16 h-0.5 -z-0 transition-colors duration-500",
                         isPast ? "bg-indigo-200" : "bg-zinc-100"
                       )} />
                     )}
                   </div>
                 );
               })}
            </div>
            
            <div className="h-px w-full bg-gradient-to-r from-transparent via-zinc-200 to-transparent" />

            {/* Chain of Thought Logs */}
            <div className="space-y-3 max-h-[160px] overflow-y-auto pr-2 custom-scrollbar">
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
                      <div className="mt-1">
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
        ) : (
          /* Minimized Pill State */
          <div className="flex items-center gap-3 px-5 py-3 pr-12 cursor-pointer" onClick={() => setIsExpanded(true)}>
            <div className="relative flex items-center justify-center">
              <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
            </div>
            <div className="overflow-hidden relative h-[18px] flex-1">
              <AnimatePresence mode="popLayout">
                <motion.span
                  key={analysisStatus}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -15 }}
                  className="absolute text-[11px] font-bold text-indigo-600 uppercase tracking-widest whitespace-nowrap"
                >
                  {analysisStatus || t('common.loading')}
                </motion.span>
              </AnimatePresence>
            </div>
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
