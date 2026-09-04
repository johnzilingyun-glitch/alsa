import React, { useState, useEffect, useRef } from 'react';
import { X, Target, TrendingUp, ShieldAlert, Activity, ExternalLink, ChevronRight, BarChart3, AlertCircle, Archive, CheckCircle2, Trash2, Plus, Search, Play } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { useMarketStore } from '../../stores/useMarketStore';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { alertsClient, type PostmortemPayload, type SearchAlert as AlertType } from '../../services/api/alertsClient';
import { alertIsShort, type SignalAction } from '../../utils/signalAction';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface SignalCenterProps {
  isOpen: boolean;
  onClose: () => void;
}

// Action badge metadata — buy uses emerald (project convention: gains/targets
// are emerald, losses/risks are rose, cf. SidebarSummary target/stop styling);
// sell is the inverse; hold/watch are neutral zinc.
const ACTION_META: Record<SignalAction, { label: string; className: string }> = {
  buy: { label: '买入', className: 'bg-emerald-100 text-emerald-700 border border-emerald-200' },
  sell: { label: '卖出', className: 'bg-rose-100 text-rose-700 border border-rose-200' },
  hold: { label: '持有', className: 'bg-zinc-100 text-zinc-600 border border-zinc-200' },
  watch: { label: '观望', className: 'bg-zinc-100 text-zinc-600 border border-zinc-200' },
};

export function SignalCenter({ isOpen, onClose }: SignalCenterProps) {
  const { t } = useTranslation();
  const setLastJobId = useAnalysisStore(s => s.setLastJobId);
  // Persisted (stale) localStorage can merge these back as null, which would
  // crash the initial render before alerts are re-fetched. Guard with defaults.
  const searchAlerts = useMarketStore(s => s.searchAlerts) ?? [];
  const alertPrices = useMarketStore(s => s.alertPrices) ?? {};
  const historyItems = useMarketStore(s => s.historyItems) ?? [];
  const setAlerts = useMarketStore(s => s.setAlerts);
  const { setSymbol, setMarket, setAnalysis } = useAnalysisStore();
  const [tab, setTab] = useState<'active' | 'closed'>('active');
  const [closedAlerts, setClosedAlerts] = useState<AlertType[]>([]);
  const [postmortemTarget, setPostmortemTarget] = useState<any>(null);
  const [pmForm, setPmForm] = useState<PostmortemPayload>({
    exit_price: 0,
    outcome_category: 'TRUE_POSITIVE',
    notes: '',
    decision_quality: 5,
  });
  const [pmSubmitting, setPmSubmitting] = useState(false);
  
  const [isManualAdding, setIsManualAdding] = useState(false);
  const [manualForm, setManualForm] = useState<Partial<AlertType>>({
    symbol: '',
    name: '',
    market: 'A-Share' as any,
    entry_price: 0,
    target_price: 0,
    stop_loss: 0,
    currency: 'CNY',
  });
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [isResuming, setIsResuming] = useState<string | null>(null);

  const handleResumeAlert = async (alertId: string) => {
    try {
      setIsResuming(alertId);
      await alertsClient.resumeAlert(alertId);
      const res = await alertsClient.getMonitoringStatus();
      setAlerts(res.items || []);
    } catch (e) {
      console.error('Failed to resume alert:', e);
    } finally {
      setIsResuming(null);
    }
  };

  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    const fetchSuggestions = async () => {
      const sym = manualForm.symbol || '';
      const mkt = manualForm.market || 'A-Share';
      if (!sym || sym.trim().length < 1 || isComposing) {
        setSuggestions([]);
        setShowSuggestions(false);
        return;
      }
      try {
        const params = new URLSearchParams();
        params.set('input', sym);
        params.set('market', mkt);
        const res = await fetch(`/api/stock/suggest?${params.toString()}`, { signal: controller.signal });
        if (res.ok) {
          const data = await res.json();
          setSuggestions(data);
          setShowSuggestions(data.length > 0);
          setSelectedIndex(-1);
        }
      } catch (e: any) {
        if (e.name !== 'AbortError') console.error('Failed to fetch suggestions:', e);
      }
    };
    const timeout = setTimeout(fetchSuggestions, 300);
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [manualForm.symbol, manualForm.market, isComposing]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectSuggestion = (s: any) => {
    const finalSym = s.symbol || s.fullSymbol;
    setManualForm(f => ({ ...f, symbol: finalSym, name: s.name || f.name }));
    setShowSuggestions(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => (prev + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => (prev - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      handleSelectSuggestion(suggestions[selectedIndex]);
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  const handleDeleteAlert = async (alertId: string, isClosed: boolean) => {
    if (!confirm('确定要删除这条监控记录吗？')) return;
    setIsDeleting(alertId);
    try {
      await alertsClient.delete(alertId);
      if (isClosed) {
        setClosedAlerts(prev => prev.filter(a => a.alert_id !== alertId));
      } else {
        setAlerts(searchAlerts.filter(a => a.alert_id !== alertId));
      }
    } catch (e) {
      console.error('Delete failed:', e);
    } finally {
      setIsDeleting(null);
    }
  };

  const handleManualSubmit = async () => {
    if (!manualForm.symbol || !manualForm.entry_price || !manualForm.target_price || !manualForm.stop_loss) {
      alert('请填写完整信息');
      return;
    }
    try {
      await alertsClient.create(manualForm as AlertType);
      setIsManualAdding(false);
      // refresh active
      const res = await alertsClient.list();
      setAlerts(res.items || []);
    } catch (e) {
      console.error('Create failed:', e);
    }
  };

  useEffect(() => {
    if (isOpen && tab === 'closed') {
      alertsClient.listClosed().then(res => setClosedAlerts(res.items || [])).catch(() => {});
    }
  }, [isOpen, tab]);

  // Refresh active signals from backend whenever the panel opens, so alerts created
  // elsewhere (e.g. "执行监控" in the report view) appear without a full page reload.
  useEffect(() => {
    if (isOpen) {
      alertsClient.list().then(res => setAlerts(res.items || [])).catch(() => {});
    }
  }, [isOpen, setAlerts]);

  const handlePostmortemSubmit = async () => {
    if (!postmortemTarget) return;
    setPmSubmitting(true);
    try {
      await alertsClient.recordPostmortem(postmortemTarget.alert_id, pmForm);
      setPostmortemTarget(null);
      // Refresh closed list
      const res = await alertsClient.listClosed();
      setClosedAlerts(res.items || []);
      setTab('closed');
    } catch (e) {
      console.error('Postmortem submit failed:', e);
    } finally {
      setPmSubmitting(false);
    }
  };

  const getStatus = (alert: AlertType) => {
    if (alert.monitoring_enabled === false) return 'inactive';
    const price = alertPrices[alert.symbol];
    if (!price) return 'neutral';
    // hold/watch are non-directional tracking signals: never surface the
    // bullish "目标达成/止损" verdicts, only a neutral near-anchor hint.
    if (alert.action === 'hold' || alert.action === 'watch') {
      if (alert.entry_price > 0 && Math.abs(price - alert.entry_price) / alert.entry_price <= 0.02) return 'indigo';
      return 'neutral';
    }
    // sell → short semantics (price <= target hits profit, >= stop hits loss);
    // buy/legacy → long semantics, legacy rows infer direction from geometry
    // (target < entry ⇒ short) exactly like the backend monitor service.
    const isShort = alertIsShort(alert);
    if (isShort ? price <= alert.target_price : price >= alert.target_price) return 'gold';
    if (isShort ? price >= alert.stop_loss : price <= alert.stop_loss) return 'red';
    if (alert.entry_price > 0 && Math.abs(price - alert.entry_price) / alert.entry_price <= 0.02) return 'indigo';
    return 'neutral';
  };

  const getVerdictHint = (alert: AlertType, status: string) => {
    if (alert.action === 'hold' || alert.action === 'watch') {
      switch (status) {
        case 'inactive': return '已停止监控 (触发或确认)';
        case 'indigo': return '接近关注价位 🔍';
        default: return alert.action === 'hold' ? '持有观察中 · 价格运行中' : '观望跟踪中 · 价格运行中';
      }
    }
    const isShort = alertIsShort(alert);
    switch (status) {
      case 'inactive': return '已停止监控 (触发或确认)';
      case 'gold': return isShort ? '空头目标达成！🚀 建议考虑止盈' : '目标达成！🚀 建议考虑止盈';
      case 'red': return isShort ? '涨破止损位！⚠️ 建议按计划回补离场' : '跌破止损！⚠️ 建议按计划离场';
      case 'indigo': return isShort ? '进入做空入场区 ✨ 关注择机介入' : '进入买入区 ✨ 关注择机介入';
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
              <div className="flex items-center gap-3">
                <div className="flex bg-zinc-100 rounded-xl p-1">
                  <button onClick={() => setTab('active')} className={cn("px-4 py-1.5 rounded-lg text-xs font-bold transition-all", tab === 'active' ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-400 hover:text-zinc-600")}>
                    活跃信号 ({searchAlerts.length})
                  </button>
                  <button onClick={() => setTab('closed')} className={cn("px-4 py-1.5 rounded-lg text-xs font-bold transition-all", tab === 'closed' ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-400 hover:text-zinc-600")}>
                    <Archive size={12} className="inline mr-1" />复盘记录
                  </button>
                </div>
                <button
                  onClick={() => setIsManualAdding(true)}
                  className="flex items-center gap-1 bg-indigo-600 hover:bg-indigo-700 text-white px-3 py-2 rounded-xl text-xs font-bold transition-colors"
                >
                  <Plus size={14} /> 手动添加
                </button>
                <button
                onClick={onClose}
                className="flex h-10 w-10 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-900"
              >
                <X size={20} />
              </button>
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto p-8 space-y-4 custom-scrollbar">
              {tab === 'active' ? (
              <>
              {!searchAlerts.length ? (
                <div className="text-center py-24 text-zinc-400 space-y-4">
                  <Activity size={48} className="mx-auto opacity-10" />
                  <p className="text-sm font-bold text-zinc-500">暂无活动中的交易信号</p>
                  <p className="text-xs">当您进行股票深度研判并生成交易计划后，信号将在此实时监控</p>
                </div>
              ) : (
                <div className="space-y-4">
                   {searchAlerts.map((alert) => {
                     if (!alert) return null;
                     const price = alertPrices[alert.symbol];
                    const status = getStatus(alert);
                    // searchAlerts is any[] in the store — narrow the action
                    // explicitly before indexing ACTION_META.
                    const alertAction: SignalAction | undefined = alert.action;
                    const actionMeta = alertAction ? ACTION_META[alertAction] : undefined;
                    const isShort = alertIsShort(alert);
                    
                    // Find corresponding history item to show full trading plan text if available.
                    // NOTE: the backend writes `tradingPlan.strategy` (see
                    // analysis_job_service._extract_structured_fields); the
                    // previously referenced actionPlan/summary fields never existed.
                    const histItem = historyItems.find(h => h.stockInfo?.symbol === alert.symbol);
                    const tradingPlanText = histItem?.tradingPlan?.strategy || "查看完整研判报告以获取详细计划";

                    return (
                      <motion.div
                        key={alert.id}
                        layout
                        className={cn(
                          "group relative overflow-hidden rounded-2xl border transition-all duration-500 p-6",
                          status === 'inactive' ? "bg-zinc-50 border-zinc-200 opacity-80" :
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
                              <h4 className="font-bold text-zinc-950 group-hover:text-indigo-600 transition-colors flex items-center gap-2">
                                {alert.name}
                                {actionMeta && (
                                  <span className={cn("px-1.5 py-0.5 rounded-md text-[10px] font-bold tracking-wide", actionMeta.className)}>
                                    {actionMeta.label}
                                  </span>
                                )}
                              </h4>
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
                              <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Target {isShort ? '↓' : '↑'}</span>
                              <span className={cn("text-xs font-bold", status === 'gold' ? "text-yellow-600" : "text-zinc-600")}>{alert.target_price}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Stop Loss {isShort ? '↑' : '↓'}</span>
                              <span className={cn("text-xs font-bold", status === 'red' ? "text-rose-600" : "text-zinc-600")}>{alert.stop_loss}</span>
                            </div>
                            <div className={cn(
                              "mt-2 px-2.5 py-1.5 rounded-lg text-center text-[10px] font-bold uppercase tracking-wider",
                              status === 'gold' ? "bg-yellow-500 text-white" :
                              status === 'red' ? "bg-rose-500 text-white" :
                              status === 'indigo' ? "bg-indigo-600 text-white" :
                              "bg-zinc-100 text-zinc-500"
                            )}>
                              {getVerdictHint(alert, status)}
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
                            
                            {histItem && (
                              <button
                                onClick={() => {
                                  setAnalysis(histItem);
                                  setLastJobId((histItem as any).job_id || (histItem as any).jobId || (histItem as any)._jobId || (histItem as any).analysis_id || (histItem as any).analysisId || histItem.id || null);
                                  setSymbol(alert.symbol);
                                  setMarket(alert.market);
                                  onClose();
                                }}
                                className="absolute bottom-4 right-4 text-xs font-bold text-indigo-600 hover:text-indigo-700 flex items-center gap-1 group/btn"
                              >
                                查看研判全文 <ChevronRight size={14} className="group-hover/btn:translate-x-0.5 transition-transform" />
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Postmortem Button */}
                        <div className="flex justify-end mt-3 pt-3 border-t border-zinc-100/50 gap-4">
                          {(status === 'inactive' || alert.acknowledged === true) && (
                            <button
                              onClick={() => handleResumeAlert(alert.alert_id!)}
                              disabled={isResuming === alert.alert_id}
                              className="text-[10px] font-bold text-zinc-400 hover:text-emerald-600 uppercase tracking-widest flex items-center gap-1 transition-colors disabled:opacity-50"
                            >
                              <Play size={12} /> {isResuming === alert.alert_id ? '恢复中' : '恢复监控'}
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteAlert(alert.alert_id!, false)}
                            disabled={isDeleting === alert.alert_id}
                            className="text-[10px] font-bold text-zinc-400 hover:text-rose-600 uppercase tracking-widest flex items-center gap-1 transition-colors disabled:opacity-50"
                          >
                            <Trash2 size={12} /> {isDeleting === alert.alert_id ? '删除中' : '删除'}
                          </button>
                          <button
                            onClick={() => {
                              setPostmortemTarget(alert);
                              const price = alertPrices[alert.symbol];
                              setPmForm({
                                exit_price: price || alert.entry_price,
                                outcome_category: status === 'gold' ? 'TRUE_POSITIVE' : status === 'red' ? 'FALSE_POSITIVE' : 'TRUE_POSITIVE',
                                notes: '',
                                decision_quality: 5,
                              });
                            }}
                            className="text-[10px] font-bold text-zinc-400 hover:text-indigo-600 uppercase tracking-widest flex items-center gap-1 transition-colors"
                          >
                            <CheckCircle2 size={12} /> 结束并复盘
                          </button>
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
              </>
              ) : (
                /* Closed / Postmortem Tab */
                !closedAlerts.length ? (
                  <div className="text-center py-24 text-zinc-400 space-y-4">
                    <Archive size={48} className="mx-auto opacity-10" />
                    <p className="text-sm font-bold text-zinc-500">暂无复盘记录</p>
                    <p className="text-xs">当您关闭信号并记录复盘时，历史交易将在此展示</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {closedAlerts.map((a) => {
                      const isWin = a.realized_return_pct != null && a.realized_return_pct > 0;
                      const catLabel: Record<string, string> = {
                        TRUE_POSITIVE: '✅ 正确信号',
                        FALSE_POSITIVE: '❌ 错误信号',
                        MISSED: '😐 错过机会',
                        REGIME_MISMATCH: '🔄 市场环境错配',
                      };
                      return (
                        <div key={a.alert_id} className={cn(
                          "rounded-xl border p-5",
                          isWin ? "border-emerald-200 bg-emerald-50/30" : "border-rose-200 bg-rose-50/30"
                        )}>
                          <div className="flex items-center justify-between mb-3">
                            <div>
                              <span className="font-bold text-zinc-900">{a.name}</span>
                              <span className="text-[10px] text-zinc-400 ml-2 font-mono">{a.symbol}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-white border">
                                {catLabel[a.outcome_category || ''] || a.outcome_category}
                              </span>
                              <button
                                onClick={() => handleDeleteAlert(a.alert_id!, true)}
                                disabled={isDeleting === a.alert_id}
                                className="text-zinc-400 hover:text-rose-600 transition-colors disabled:opacity-50"
                              >
                                <Trash2 size={14} />
                              </button>
                            </div>
                          </div>
                          <div className="grid grid-cols-5 gap-4 text-center">
                            <div>
                              <p className="text-[9px] text-zinc-400 font-bold uppercase">入场</p>
                              <p className="text-sm font-bold text-zinc-700">{a.entry_price}</p>
                            </div>
                            <div>
                              <p className="text-[9px] text-zinc-400 font-bold uppercase">离场</p>
                              <p className="text-sm font-bold text-zinc-700">{a.exit_price}</p>
                            </div>
                            <div>
                              <p className="text-[9px] text-zinc-400 font-bold uppercase">收益</p>
                              <p className={cn("text-sm font-bold", isWin ? "text-emerald-600" : "text-rose-600")}>
                                {a.realized_return_pct != null ? `${a.realized_return_pct > 0 ? '+' : ''}${a.realized_return_pct}%` : '--'}
                              </p>
                            </div>
                            <div>
                              <p className="text-[9px] text-zinc-400 font-bold uppercase">MAE</p>
                              <p className="text-sm font-bold text-rose-500">{a.mae_pct != null ? `-${a.mae_pct}%` : '--'}</p>
                            </div>
                            <div>
                              <p className="text-[9px] text-zinc-400 font-bold uppercase">MFE</p>
                              <p className="text-sm font-bold text-emerald-500">{a.mfe_pct != null ? `+${a.mfe_pct}%` : '--'}</p>
                            </div>
                          </div>
                          {a.postmortem_notes && (
                            <p className="mt-3 text-xs text-zinc-500 italic border-t border-zinc-100 pt-2">"{a.postmortem_notes}"</p>
                          )}
                          {a.decision_quality_score != null && (
                            <div className="mt-2 flex items-center gap-1">
                              <span className="text-[9px] text-zinc-400 font-bold">决策质量:</span>
                              <div className="flex gap-0.5">
                                {Array.from({ length: 10 }, (_, i) => (
                                  <div key={i} className={cn("w-2 h-2 rounded-sm", i < a.decision_quality_score! ? "bg-indigo-500" : "bg-zinc-200")} />
                                ))}
                              </div>
                              <span className="text-[10px] font-bold text-zinc-500">{a.decision_quality_score}/10</span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )
              )}
            </div>

            {/* Postmortem Modal */}
            <AnimatePresence>
              {postmortemTarget && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 bg-white/95 backdrop-blur-sm z-10 flex items-center justify-center p-8"
                >
                  <div className="w-full max-w-md space-y-5">
                    <div className="text-center">
                      <h3 className="text-lg font-bold text-zinc-900">信号复盘</h3>
                      <p className="text-xs text-zinc-400 mt-1">{postmortemTarget.name} · {postmortemTarget.symbol}</p>
                    </div>

                    <div className="space-y-4">
                      <div>
                        <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">离场价格</label>
                        <input
                          type="number"
                          step="0.01"
                          value={pmForm.exit_price}
                          onChange={e => setPmForm(f => ({ ...f, exit_price: parseFloat(e.target.value) || 0 }))}
                          className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">结果分类</label>
                        <div className="grid grid-cols-2 gap-2">
                          {([
                            ['TRUE_POSITIVE', '✅ 正确信号'],
                            ['FALSE_POSITIVE', '❌ 错误信号'],
                            ['MISSED', '😐 错过机会'],
                            ['REGIME_MISMATCH', '🔄 环境错配'],
                          ] as const).map(([val, label]) => (
                            <button
                              key={val}
                              onClick={() => setPmForm(f => ({ ...f, outcome_category: val }))}
                              className={cn(
                                "px-3 py-2 rounded-lg text-xs font-bold border transition-all",
                                pmForm.outcome_category === val
                                  ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                                  : "border-zinc-200 text-zinc-500 hover:border-zinc-300"
                              )}
                            >{label}</button>
                          ))}
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">MAE% (最大回撤)</label>
                          <input
                            type="number"
                            step="0.1"
                            value={pmForm.mae_pct ?? ''}
                            onChange={e => setPmForm(f => ({ ...f, mae_pct: e.target.value ? parseFloat(e.target.value) : undefined }))}
                            className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
                            placeholder="e.g. 5.2"
                          />
                        </div>
                        <div>
                          <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">MFE% (最大浮盈)</label>
                          <input
                            type="number"
                            step="0.1"
                            value={pmForm.mfe_pct ?? ''}
                            onChange={e => setPmForm(f => ({ ...f, mfe_pct: e.target.value ? parseFloat(e.target.value) : undefined }))}
                            className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
                            placeholder="e.g. 12.8"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">决策质量 ({pmForm.decision_quality}/10)</label>
                        <input
                          type="range"
                          min={1}
                          max={10}
                          value={pmForm.decision_quality ?? 5}
                          onChange={e => setPmForm(f => ({ ...f, decision_quality: parseInt(e.target.value) }))}
                          className="w-full accent-indigo-600"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">复盘笔记</label>
                        <textarea
                          value={pmForm.notes ?? ''}
                          onChange={e => setPmForm(f => ({ ...f, notes: e.target.value }))}
                          rows={3}
                          className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400 resize-none"
                          placeholder="记录你的反思和经验教训..."
                        />
                      </div>
                    </div>

                    <div className="flex gap-3">
                      <button
                        onClick={() => setPostmortemTarget(null)}
                        className="flex-1 py-2.5 rounded-xl border border-zinc-200 text-xs font-bold text-zinc-500 hover:bg-zinc-50 transition-colors"
                      >取消</button>
                      <button
                        onClick={handlePostmortemSubmit}
                        disabled={pmSubmitting}
                        className="flex-1 py-2.5 rounded-xl bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 transition-colors disabled:opacity-50"
                      >{pmSubmitting ? '保存中...' : '保存复盘'}</button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Manual Add Modal */}
            <AnimatePresence>
              {isManualAdding && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 bg-white/95 backdrop-blur-sm z-10 flex items-center justify-center p-8"
                >
                  <div className="w-full max-w-md space-y-5">
                    <div className="text-center">
                      <h3 className="text-lg font-bold text-zinc-900">手动添加监控信号</h3>
                      <p className="text-xs text-zinc-400 mt-1">输入您自定义的交易计划</p>
                    </div>

                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-3">
                        <div className="relative" ref={searchContainerRef}>
                          <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">代码 (Symbol)</label>
                          <input
                            value={manualForm.symbol}
                            onCompositionStart={() => setIsComposing(true)}
                            onCompositionEnd={(e) => {
                              setIsComposing(false);
                              setManualForm(f => ({ ...f, symbol: e.currentTarget.value }));
                            }}
                            onChange={e => setManualForm(f => ({ ...f, symbol: e.target.value }))}
                            onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
                            onKeyDown={handleKeyDown}
                            className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
                            placeholder="e.g. AAPL / 腾讯"
                            autoComplete="off"
                          />
                          {showSuggestions && suggestions.length > 0 && (
                            <div className="absolute top-[100%] left-0 right-0 mt-1 z-[60] overflow-hidden rounded-xl border border-zinc-100 bg-white shadow-xl shadow-indigo-600/10">
                              <div className="p-1 max-h-40 overflow-y-auto custom-scrollbar">
                                {suggestions.map((s, idx) => (
                                  <button
                                    key={`sugg-${s.symbol}-${idx}`}
                                    type="button"
                                    onClick={() => handleSelectSuggestion(s)}
                                    onMouseEnter={() => setSelectedIndex(idx)}
                                    className={`flex w-full items-center justify-between px-2 py-1.5 rounded-lg transition-all ${
                                      idx === selectedIndex ? 'bg-indigo-50 text-indigo-700' : 'text-zinc-700 hover:bg-zinc-50'
                                    }`}
                                  >
                                    <div className="flex items-center gap-2">
                                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${idx === selectedIndex ? 'bg-indigo-100 text-indigo-600' : 'bg-zinc-100 text-zinc-500'}`}>
                                        {s.symbol}
                                      </span>
                                      <span className="font-bold text-xs truncate max-w-[100px] text-left">{s.name}</span>
                                    </div>
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                        <div>
                          <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">名称 (Name)</label>
                          <input
                            value={manualForm.name}
                            onChange={e => setManualForm(f => ({ ...f, name: e.target.value }))}
                            className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
                            placeholder="e.g. 苹果"
                          />
                        </div>
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        <div>
                          <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">入场 (Entry)</label>
                          <input
                            type="number"
                            step="0.01"
                            value={manualForm.entry_price || ''}
                            onChange={e => setManualForm(f => ({ ...f, entry_price: parseFloat(e.target.value) || 0 }))}
                            className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
                          />
                        </div>
                        <div>
                          <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">目标 (Target)</label>
                          <input
                            type="number"
                            step="0.01"
                            value={manualForm.target_price || ''}
                            onChange={e => setManualForm(f => ({ ...f, target_price: parseFloat(e.target.value) || 0 }))}
                            className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
                          />
                        </div>
                        <div>
                          <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">止损 (Stop)</label>
                          <input
                            type="number"
                            step="0.01"
                            value={manualForm.stop_loss || ''}
                            onChange={e => setManualForm(f => ({ ...f, stop_loss: parseFloat(e.target.value) || 0 }))}
                            className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
                          />
                        </div>
                      </div>
                      <div>
                        <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">市场类别</label>
                        <select
                          value={manualForm.market}
                          onChange={e => setManualForm(f => ({ ...f, market: e.target.value as any, currency: e.target.value === 'A-Share' ? 'CNY' : e.target.value === 'HK-Share' ? 'HKD' : 'USD' }))}
                          className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400 bg-white"
                        >
                          <option value="A-Share">A股 (A-Share)</option>
                          <option value="HK-Share">港股 (HK-Share)</option>
                          <option value="US-Share">美股 (US-Share)</option>
                        </select>
                      </div>
                    </div>

                    <div className="flex gap-3">
                      <button
                        onClick={() => setIsManualAdding(false)}
                        className="flex-1 py-2.5 rounded-xl border border-zinc-200 text-xs font-bold text-zinc-500 hover:bg-zinc-50 transition-colors"
                      >取消</button>
                      <button
                        onClick={handleManualSubmit}
                        className="flex-1 py-2.5 rounded-xl bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 transition-colors"
                      >确认添加</button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

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
