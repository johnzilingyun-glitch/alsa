import React, { useState, useEffect } from 'react';
import { X, Search, Clock, BarChart3, ChevronRight, Trash2, History as HistoryIcon } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { getHistoryContext, deleteHistoryItem } from '../services/aiService';
import { useUIStore } from '../stores/useUIStore';
import { generateHistoryItemKey } from '../services/dateUtils';

interface HistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (item: any) => void;
}

export function HistoryModal({ isOpen, onClose, onSelect }: HistoryModalProps) {
  const [history, setHistory] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const { showConfirm, showToast } = useUIStore();

  useEffect(() => {
    if (isOpen) {
      const controller = new AbortController();
      setLoading(true);
      getHistoryContext()
        .then(data => {
          if (!controller.signal.aborted) setHistory(data);
        })
        .catch(err => {
          if (!controller.signal.aborted) console.error('Failed to load history:', err);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
      return () => controller.abort();
    }
  }, [isOpen]);

  const filteredHistory = history.filter(item => 
    item.stockInfo?.symbol?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    item.stockInfo?.name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    showConfirm(
      '删除研判记录',
      '确定要永久删除这条研判记录吗？此操作无法撤销。',
      async () => {
        try {
          const success = await deleteHistoryItem(id);
          if (success) {
            setHistory(prev => prev.filter(item => item.id !== id));
            showToast('研判记录已永久删除');
          } else {
            showToast('删除失败，请重试', 'error');
          }
        } catch (err) {
          console.error('Delete error:', err);
          showToast('发生未知错误', 'error');
        }
      },
      'danger'
    );
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-zinc-900/10 backdrop-blur-md"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.98, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 10 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-full max-w-2xl overflow-hidden rounded-3xl border border-zinc-200 bg-white shadow-2xl shadow-zinc-900/10 flex flex-col max-h-[85vh]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="history-modal-title"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-zinc-100 p-8">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100/50">
                  <HistoryIcon size={24} strokeWidth={1.5} />
                </div>
                <div>
                  <h2 id="history-modal-title" className="text-xl font-bold text-zinc-950 tracking-tight">历史研判回顾</h2>
                  <p className="text-xs font-medium text-zinc-400 mt-0.5">Review your previous market analysis</p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="flex h-10 w-10 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-zinc-50 hover:text-zinc-900"
              >
                <X size={20} />
              </button>
            </div>
            
            {/* Search */}
            <div className="p-8 pb-4">
              <div className="relative group">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 group-focus-within:text-indigo-600 transition-colors" size={18} />
                <input
                  type="text"
                  placeholder="搜索历史股票代码或名称..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="input-premium h-12 pl-12 pr-6"
                />
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto px-8 pb-8 space-y-3 custom-scrollbar">
              {loading ? (
                <div className="flex flex-col items-center justify-center py-20 gap-4">
                  <div className="h-8 w-8 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                  <p className="text-xs font-bold text-zinc-400 uppercase tracking-widest">正在检索历史库...</p>
                </div>
              ) : filteredHistory.length === 0 ? (
                <div className="text-center py-20 text-zinc-400 space-y-4">
                  <BarChart3 size={40} className="mx-auto opacity-10" />
                  <div>
                    <p className="text-sm font-bold text-zinc-500 mb-1">
                      {searchTerm ? '未找到相关的研判记录' : '暂无分析记录'}
                    </p>
                    <p className="text-xs text-zinc-400">
                      {searchTerm ? '请尝试其他关键词' : '搜索并分析股票后，历史记录将保存在这里'}
                    </p>
                  </div>
                  {!searchTerm && (
                    <button
                      onClick={onClose}
                      className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
                    >
                      <Search size={12} />
                      返回搜索第一只股票 →
                    </button>
                  )}
                </div>
              ) : (
                filteredHistory.map((item, idx) => {
                  const itemKey = generateHistoryItemKey(item, idx);
                  return (
                    <button
                      key={itemKey}
                      onClick={() => { onSelect(item); onClose(); }}
                      className="w-full flex items-center justify-between p-5 bg-white hover:bg-zinc-50 rounded-2xl transition-all border border-zinc-100 hover:border-zinc-200 group"
                    >
                      <div className="flex items-center gap-5">
                        <div className="w-12 h-12 rounded-xl bg-zinc-50 border border-zinc-100 flex items-center justify-center text-zinc-400 group-hover:bg-white group-hover:text-indigo-600 transition-all">
                          <BarChart3 size={20} />
                        </div>
                        <div className="text-left">
                          <h4 className="font-bold text-zinc-900 group-hover:text-indigo-600 transition-colors">{item.stockInfo?.name}</h4>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="font-mono text-[10px] font-bold text-zinc-400 group-hover:text-zinc-500 transition-colors">{item.stockInfo?.symbol}</span>
                            {item.chatHistory && item.chatHistory.length > 0 && (
                              <span className="px-1.5 py-0.5 rounded-md bg-indigo-50 text-[8px] font-black uppercase text-indigo-600 tracking-tighter">
                                已沉淀对话
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-300">Analysis Date</p>
                          <p className="text-xs font-semibold text-zinc-500">
                            {item.stockInfo?.lastUpdated?.split(' ')[0] || '--'}
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={(e) => handleDelete(e, item.id)}
                            className="p-2 text-zinc-300 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                            title="删除记录"
                          >
                            <Trash2 size={16} />
                          </button>
                          <ChevronRight size={16} className="text-zinc-300 group-hover:text-indigo-600 transition-all group-hover:translate-x-1" />
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
            
            <div className="p-8 border-t border-zinc-100 bg-zinc-50/50 flex items-center justify-between">
              <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                共有 {filteredHistory.length} 条研判记录
              </p>
              <button onClick={onClose} className="text-[10px] font-bold text-indigo-600 uppercase tracking-widest hover:text-indigo-700">
                关闭视窗
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
