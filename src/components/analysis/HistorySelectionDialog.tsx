import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Clock, RefreshCw, FileText, X } from 'lucide-react';

interface HistoryItem {
  job_id: string;
  analysis_id: string;
  symbol: string;
  market: string;
  model: string | null;
  finished_at: string | null;
  created_at: string | null;
}

interface HistorySelectionDialogProps {
  isOpen: boolean;
  symbol: string;
  items: HistoryItem[];
  onSelect: (analysisId: string) => void;
  onForceNew: () => void;
  onClose: () => void;
}

function formatTime(isoStr: string | null): string {
  if (!isoStr) return '未知时间';
  const d = new Date(isoStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return '刚刚';
  if (diffMins < 60) return `${diffMins} 分钟前`;
  if (diffHours < 24) return `${diffHours} 小时前`;
  if (diffDays < 7) return `${diffDays} 天前`;
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function HistorySelectionDialog({ isOpen, symbol, items, onSelect, onForceNew, onClose }: HistorySelectionDialogProps) {
  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[110] flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="absolute inset-0 bg-zinc-900/20 backdrop-blur-sm"
        />
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          className="relative w-full max-w-md rounded-2xl border border-zinc-200 bg-white shadow-2xl overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 pt-5 pb-3">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
                <FileText size={18} />
              </div>
              <div>
                <h3 className="text-sm font-bold text-zinc-900">发现历史分析记录</h3>
                <p className="text-[11px] text-zinc-400 mt-0.5">
                  <span className="font-mono font-semibold text-indigo-600">{symbol}</span> 有 {items.length} 条历史记录
                </p>
              </div>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-zinc-100 text-zinc-400 transition-colors">
              <X size={16} />
            </button>
          </div>

          {/* History Items */}
          <div className="px-4 py-2 max-h-[300px] overflow-y-auto">
            {items.map((item, i) => (
              <button
                key={item.job_id}
                onClick={() => onSelect(item.analysis_id)}
                className="w-full flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-indigo-50 transition-colors text-left group"
              >
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-100 text-zinc-500 group-hover:bg-indigo-100 group-hover:text-indigo-600 transition-colors text-xs font-bold">
                  {i + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Clock size={12} className="text-zinc-400 flex-shrink-0" />
                    <span className="text-xs font-semibold text-zinc-700">{formatTime(item.finished_at)}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[10px] text-zinc-400">{item.model || 'unknown'}</span>
                    <span className="text-[10px] text-zinc-300">·</span>
                    <span className="text-[10px] text-zinc-400 font-mono">{item.job_id}</span>
                  </div>
                </div>
                <span className="text-[10px] text-indigo-500 font-semibold opacity-0 group-hover:opacity-100 transition-opacity">
                  查看 →
                </span>
              </button>
            ))}
          </div>

          {/* Force New Analysis Button */}
          <div className="px-4 pb-4 pt-2">
            <button
              onClick={onForceNew}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-600/20"
            >
              <RefreshCw size={14} />
              强制重新分析
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
