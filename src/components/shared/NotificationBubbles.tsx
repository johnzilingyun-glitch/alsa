import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { CheckCircle2, XCircle, Loader2, ChevronDown, ChevronUp, X, ArrowRight } from 'lucide-react';
import { useJobQueueStore, type BackgroundJob } from '../../stores/useJobQueueStore';

function JobBubble({ job, onView }: { job: BackgroundJob; onView: (job: BackgroundJob) => void }) {
  const { dismissNotification, toggleExpand } = useJobQueueStore();

  const isComplete = job.status === 'completed';
  const isFailed = job.status === 'failed';
  const isRunning = job.status === 'running' || job.status === 'queued';

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 60, scale: 0.9 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 60, scale: 0.9, transition: { duration: 0.2 } }}
      className={`rounded-2xl border shadow-2xl backdrop-blur-xl overflow-hidden ${
        isComplete ? 'border-emerald-200 bg-white/95' :
        isFailed ? 'border-rose-200 bg-white/95' :
        'border-indigo-200 bg-white/95'
      }`}
      style={{ minWidth: 280, maxWidth: 360 }}
    >
      {/* Header - always visible */}
      <div className="flex items-center gap-3 px-4 py-3 cursor-pointer" onClick={() => toggleExpand(job.id)}>
        <div className={`flex h-8 w-8 items-center justify-center rounded-full flex-shrink-0 ${
          isComplete ? 'bg-emerald-50' : isFailed ? 'bg-rose-50' : 'bg-indigo-50'
        }`}>
          {isComplete && <CheckCircle2 className="text-emerald-500" size={16} />}
          {isFailed && <XCircle className="text-rose-500" size={16} />}
          {isRunning && <Loader2 className="text-indigo-500 animate-spin" size={16} />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-zinc-900 truncate">{job.symbol}</span>
            <span className="text-[10px] font-medium text-zinc-400 uppercase">{job.market}</span>
          </div>
          <p className={`text-xs truncate ${
            isComplete ? 'text-emerald-600' : isFailed ? 'text-rose-500' : 'text-indigo-500'
          }`}>
            {isComplete ? '分析完成' : isFailed ? (job.error || '分析失败') : (job.progress?.message || '分析中...')}
          </p>
        </div>

        <div className="flex items-center gap-1 flex-shrink-0">
          {job.expanded ? <ChevronUp size={14} className="text-zinc-400" /> : <ChevronDown size={14} className="text-zinc-400" />}
          <button
            onClick={(e) => { e.stopPropagation(); dismissNotification(job.id); }}
            className="p-1 rounded-lg hover:bg-zinc-100 transition-colors text-zinc-400 hover:text-zinc-600"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Expanded content */}
      <AnimatePresence>
        {job.expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 border-t border-zinc-100 pt-3">
              {isRunning && job.progress && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs text-zinc-500">
                    <span>{job.progress.stage}</span>
                    <span>{job.progress.percent ?? 0}%</span>
                  </div>
                  <div className="h-1.5 bg-zinc-100 rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-indigo-500 rounded-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${job.progress.percent ?? 0}%` }}
                      transition={{ duration: 0.5, ease: 'easeOut' }}
                    />
                  </div>
                  {job.progress.round !== undefined && job.progress.total_rounds !== undefined && (
                    <p className="text-[11px] text-zinc-400">
                      专家研判 {job.progress.round}/{job.progress.total_rounds}
                    </p>
                  )}
                </div>
              )}

              {isComplete && (
                <button
                  onClick={() => onView(job)}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 transition-colors"
                >
                  <span>查看报告</span>
                  <ArrowRight size={14} />
                </button>
              )}

              {isFailed && (
                <p className="text-xs text-rose-500 leading-relaxed">
                  {job.error || '未知错误，请稍后重试'}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function NotificationBubbles({ onViewResult }: { onViewResult: (job: BackgroundJob) => void }) {
  const jobs = useJobQueueStore(s => s.jobs);
  const visibleJobs = jobs.filter(j => j.notificationVisible || j.status === 'running' || j.status === 'queued');

  if (visibleJobs.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-[200] flex flex-col gap-3 items-end">
      <AnimatePresence mode="popLayout">
        {visibleJobs.map((job) => (
          <JobBubble key={job.id} job={job} onView={onViewResult} />
        ))}
      </AnimatePresence>
    </div>
  );
}
