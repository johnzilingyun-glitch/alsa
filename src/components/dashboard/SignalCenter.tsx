import React, { useState, useEffect } from 'react';
import { X, Target, TrendingUp, ShieldAlert, Activity, ExternalLink, ChevronRight, BarChart3, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { useMarketStore } from '../../stores/useMarketStore';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface SignalCenterProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SignalCenter({ isOpen, onClose }: SignalCenterProps) {
  const { t } = useTranslation();
  const { searchAlerts, alertPrices, historyItems } = useMarketStore();
  const { setSymbol, setMarket, setAnalysis } = useAnalysisStore();

  const getStatus = (alert: any) => {
    const price = alertPrices[alert.symbol];
    if (!price) return 'neutral';
    if (price >= alert.target_price) return 'gold';
    if (price <= alert.stop_loss) return 'red';
    const entryDiff = Math.abs(price - alert.entry_price) / alert.entry_price;
    if (entryDiff <= 0.02) return 'indigo';
    return 'neutral';
  };

  const getVerdictHint = (status: string) => {
    switch (status) {
      case 'gold': return '目标达成！🚀 建议考虑止盈';
      case 'red': return '跌破止损！⚠️ 建议按计划离场';
      case 'indigo': return '进入买入区 ✨ 关注择机介入';
      default: return '持仓待机 · 价格运行中';
    }
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
            className="absolute inset-0 bg-zinc-900/20 backdrop-blur-md"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.98, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 10 }}
            className="relative w-full max-w-4xl overflow-hidden rounded-3xl border border-zinc-200 bg-white shadow-2xl flex flex-col max-h-[90vh]"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-zinc-100 p-8 bg-zinc-50/50">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/20">
                  <Target size={24} />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-zinc-950 tracking-tight">智能交易信号中心</h2>
                  <p className="text-xs font-medium text-zinc-400 mt-0.5">Real-time Trading Signal & Plan Monitor</p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="flex h-10 w-10 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-900"
              >
                <X size={20} />
              </button>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto p-8 space-y-4 custom-scrollbar">
              {!searchAlerts.length ? (
                <div className="text-center py-24 text-zinc-400 space-y-4">
                  <Activity size={48} className="mx-auto opacity-10" />
                  <p className="text-sm font-bold text-zinc-500">暂无活动中的交易信号</p>
                  <p className="text-xs">当您进行股票深度研判并生成交易计划后，信号将在此实时监控</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {searchAlerts.map((alert) => {
                    const price = alertPrices[alert.symbol];
                    const status = getStatus(alert);
                    
                    // Find corresponding history item to show full trading plan text if available
                    const histItem = historyItems.find(h => h.stockInfo?.symbol === alert.symbol);
                    const tradingPlanText = histItem?.tradingPlan?.actionPlan || histItem?.tradingPlan?.summary || "查看完整研判报告以获取详细计划";

                    return (
                      <motion.div
                        key={alert.id}
                        layout
                        className={cn(
                          "group relative overflow-hidden rounded-2xl border transition-all duration-500 p-6",
                          status === 'gold' ? "bg-yellow-50/30 border-yellow-200 shadow-lg shadow-yellow-500/5" :
                          status === 'red' ? "bg-rose-50/30 border-rose-200 shadow-lg shadow-rose-500/5" :
                          status === 'indigo' ? "bg-indigo-50/30 border-indigo-200 shadow-lg shadow-indigo-500/5" :
                          "bg-white border-zinc-100 hover:border-zinc-200"
                        )}
                      >
                        <div className="flex flex-col lg:flex-row gap-6">
                          {/* Stock & Price Info */}
                          <div className="lg:w-1/4 space-y-3">
                            <div>
                              <h4 className="font-bold text-zinc-950 group-hover:text-indigo-600 transition-colors">{alert.name}</h4>
                              <p className="text-[10px] font-mono text-zinc-400 uppercase tracking-widest">{alert.symbol} · {alert.market}</p>
                            </div>
                            <div className="pt-2 border-t border-zinc-100/50">
                              <p className="text-[8px] font-bold text-zinc-400 uppercase tracking-widest mb-1">Current Price</p>
                              <div className="flex items-baseline gap-1">
                                <span className={cn(
                                  "text-2xl font-bold tracking-tighter",
                                  status === 'gold' ? "text-yellow-600" : status === 'red' ? "text-rose-600" : "text-zinc-950"
                                )}>
                                  {price ? price.toFixed(2) : '---'}
                                </span>
                                <span className="text-[10px] text-zinc-400 font-bold uppercase">{alert.currency}</span>
                              </div>
                            </div>
                          </div>

                          {/* Plan Levels */}
                          <div className="lg:w-1/4 grid grid-cols-1 gap-3 border-l border-zinc-100/50 pl-6">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Entry</span>
                              <span className={cn("text-xs font-bold", status === 'indigo' ? "text-indigo-600" : "text-zinc-600")}>{alert.entry_price}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Target</span>
                              <span className={cn("text-xs font-bold", status === 'gold' ? "text-yellow-600" : "text-zinc-600")}>{alert.target_price}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Stop Loss</span>
                              <span className={cn("text-xs font-bold", status === 'red' ? "text-rose-600" : "text-zinc-600")}>{alert.stop_loss}</span>
                            </div>
                            <div className={cn(
                              "mt-2 px-2.5 py-1.5 rounded-lg text-center text-[10px] font-bold uppercase tracking-wider",
                              status === 'gold' ? "bg-yellow-500 text-white" :
                              status === 'red' ? "bg-rose-500 text-white" :
                              status === 'indigo' ? "bg-indigo-600 text-white" :
                              "bg-zinc-100 text-zinc-500"
                            )}>
                              {getVerdictHint(status)}
                            </div>
                          </div>

                          {/* Full Plan Text */}
                          <div className="flex-1 bg-zinc-50/50 rounded-xl p-4 border border-zinc-100/50 relative">
                            <h5 className="text-[8px] font-bold text-zinc-400 uppercase tracking-[0.2em] mb-2 flex items-center gap-1">
                              <BarChart3 size={10} /> AI Trading Plan Detail
                            </h5>
                            <p className="text-xs text-zinc-600 leading-relaxed italic">
                              "{tradingPlanText}"
                            </p>
                            
                            <button
                              onClick={() => {
                                if (histItem) {
                                  setAnalysis(histItem);
                                  setSymbol(alert.symbol);
                                  setMarket(alert.market);
                                  onClose();
                                }
                              }}
                              className="absolute bottom-4 right-4 text-xs font-bold text-indigo-600 hover:text-indigo-700 flex items-center gap-1 group/btn"
                            >
                              查看研判全文 <ChevronRight size={14} className="group-hover/btn:translate-x-0.5 transition-transform" />
                            </button>
                          </div>
                        </div>
                        
                        {/* Interactive glow border for status */}
                        <div className={cn(
                          "absolute bottom-0 left-0 h-1 transition-all duration-700",
                          status === 'gold' ? "bg-yellow-500 w-full" :
                          status === 'red' ? "bg-rose-500 w-full" :
                          status === 'indigo' ? "bg-indigo-600 w-full" : "bg-transparent w-0"
                        )} />
                      </motion.div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="p-8 border-t border-zinc-100 bg-zinc-50/50 flex items-center justify-between">
              <div className="flex items-center gap-6">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
                  <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">止盈达成</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                  <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">跌破止损</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse" />
                  <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">买入区间</span>
                </div>
              </div>
              <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                实时监控中 · 数据每 30 秒同步
              </p>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
