import React, { useState, useEffect } from 'react';
import { X, Play, RefreshCw, BarChart2, TrendingUp, AlertCircle, ShieldAlert, CheckCircle2, ChevronRight, Activity, Calendar, List, DollarSign } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface BacktestPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export function BacktestPanel({ isOpen, onClose }: BacktestPanelProps) {
  const { t } = useTranslation();
  const [model, setModel] = useState('MockAgent');
  const [market, setMarket] = useState('A-Share');
  const [startDate, setStartDate] = useState('2020-01-01');
  const [endDate, setEndDate] = useState('2021-12-31');
  
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'trades'>('overview');

  useEffect(() => {
    let interval: any;
    if (isRunning) {
      interval = setInterval(async () => {
        try {
          const res = await fetch('/api/backtest/results');
          const data = await res.json();
          if (data.status === 'completed' && data.data) {
            setResults(data.data);
            setIsRunning(false);
            clearInterval(interval);
          } else if (data.status === 'error') {
            setError(data.message || 'Backtest engine error');
            setIsRunning(false);
            clearInterval(interval);
          }
        } catch (e) {
          console.error(e);
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [isRunning]);

  const handleRunBacktest = async () => {
    setIsRunning(true);
    setResults(null);
    setError(null);
    try {
      const res = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate,
          model,
          market: market === 'A-Share' ? 'CN' : 'US'
        })
      });
      if (!res.ok) {
        throw new Error('Failed to start backtest');
      }
    } catch (e: any) {
      setError(e.message);
      setIsRunning(false);
    }
  };

  const formatPct = (val: number | undefined) => {
    if (val === undefined) return '--';
    return (val * 100).toFixed(2) + '%';
  };

  const formatNum = (val: number | undefined) => {
    if (val === undefined) return '--';
    return val.toFixed(4);
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
            className="absolute inset-0 bg-zinc-900/40 backdrop-blur-md"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.98, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 10 }}
            className="relative w-full max-w-5xl overflow-hidden rounded-3xl border border-zinc-200 bg-white shadow-2xl flex flex-col max-h-[90vh]"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-zinc-100 p-6 lg:p-8 bg-zinc-50/50">
              <div className="flex items-center gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/20">
                  <BarChart2 size={28} />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-zinc-950 tracking-tight">AI 量化回测控制台</h2>
                  <p className="text-sm font-medium text-zinc-400 mt-1 flex items-center gap-2">
                    <Activity size={14} /> Powered by Microsoft Qlib Engine
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="flex h-12 w-12 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-900"
              >
                <X size={24} />
              </button>
            </div>

            <div className="flex flex-col lg:flex-row flex-1 overflow-hidden">
              {/* Left Side: Configuration */}
              <div className="w-full lg:w-1/3 bg-white border-r border-zinc-100 p-8 overflow-y-auto">
                <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest mb-6">配置参数</h3>
                
                <div className="space-y-6">
                  {/* Model Selection */}
                  <div className="space-y-3">
                    <label className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider block">决策代理模型 (AI Agent)</label>
                    <div className="grid gap-2">
                      {[
                        { id: 'MockAgent', name: 'Mock Agent', desc: '用于测试底层连通性的沙盒代理' },
                        { id: 'portfolio_cross_sectional', name: '多股截面调仓 (真实基本面)', desc: '按PE和市值周期性轮动' },
                        { id: 'GPT-4o', name: 'GPT-4o (即将开放)', desc: '深度语言模型基本面分析' },
                        { id: 'DeepSeek-V3', name: 'DeepSeek-V3 (即将开放)', desc: '金融定制强化学习模型' }
                      ].map(m => (
                        <button
                          key={m.id}
                          onClick={() => setModel(m.id)}
                          disabled={m.id !== 'MockAgent' && m.id !== 'portfolio_cross_sectional'}
                          className={cn(
                            "text-left p-3 rounded-xl border-2 transition-all flex flex-col items-start w-full",
                            model === m.id ? "border-indigo-600 bg-indigo-50/50" : "border-zinc-100 hover:border-zinc-200",
                            (m.id !== 'MockAgent' && m.id !== 'portfolio_cross_sectional') && "opacity-50 cursor-not-allowed"
                          )}
                        >
                          <span className={cn("text-sm font-bold", model === m.id ? "text-indigo-700" : "text-zinc-700")}>{m.name}</span>
                          <span className="text-[10px] text-zinc-400 mt-0.5">{m.desc}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Market Selection */}
                  <div className="space-y-3">
                    <label className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider block">回测市场 (Market)</label>
                    <div className="grid grid-cols-2 gap-2">
                      {['A-Share', 'US-Share'].map(m => (
                        <button
                          key={m}
                          onClick={() => setMarket(m)}
                          className={cn(
                            "p-3 rounded-xl border-2 text-center transition-all",
                            market === m ? "border-indigo-600 bg-indigo-50/50 text-indigo-700" : "border-zinc-100 hover:border-zinc-200 text-zinc-500",
                            m === 'US-Share' && "opacity-50 cursor-not-allowed"
                          )}
                          disabled={m === 'US-Share'}
                        >
                          <span className="text-sm font-bold">{m}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Date Range */}
                  <div className="space-y-3">
                    <label className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider block">回测区间 (Time Range)</label>
                    <div className="grid gap-3">
                      <div className="relative">
                        <Calendar size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
                        <input
                          type="date"
                          value={startDate}
                          onChange={(e) => setStartDate(e.target.value)}
                          className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-zinc-200 text-sm font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                        />
                      </div>
                      <div className="relative">
                        <Calendar size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
                        <input
                          type="date"
                          value={endDate}
                          onChange={(e) => setEndDate(e.target.value)}
                          className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-zinc-200 text-sm font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-8 pt-8 border-t border-zinc-100">
                  <button
                    onClick={handleRunBacktest}
                    disabled={isRunning}
                    className="w-full relative overflow-hidden group bg-zinc-950 text-white rounded-2xl p-4 font-bold transition-all hover:bg-zinc-900 active:scale-95 disabled:opacity-70 disabled:active:scale-100"
                  >
                    <div className="flex items-center justify-center gap-2 relative z-10">
                      {isRunning ? (
                        <>
                          <RefreshCw size={18} className="animate-spin text-zinc-400" />
                          <span className="text-zinc-300">引擎运行中...</span>
                        </>
                      ) : (
                        <>
                          <Play size={18} />
                          <span>启动回测</span>
                        </>
                      )}
                    </div>
                    {!isRunning && (
                      <div className="absolute inset-0 bg-gradient-to-r from-indigo-500/0 via-white/10 to-indigo-500/0 translate-x-[-100%] group-hover:animate-[shimmer_1.5s_infinite]" />
                    )}
                  </button>
                  {error && (
                    <div className="mt-4 flex items-start gap-2 p-3 bg-rose-50 text-rose-600 rounded-xl text-xs font-medium">
                      <AlertCircle size={14} className="mt-0.5 shrink-0" />
                      <p>{error}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Right Side: Results */}
              <div className="w-full lg:w-2/3 bg-zinc-50/50 p-8 overflow-y-auto">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-xs font-bold text-zinc-400 uppercase tracking-widest">执行报告 (Execution Report)</h3>
                  {results && (
                    <div className="flex bg-zinc-200/50 p-1 rounded-lg">
                      <button 
                        onClick={() => setActiveTab('overview')}
                        className={cn("px-3 py-1.5 text-xs font-bold rounded-md transition-colors", activeTab === 'overview' ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-500 hover:text-zinc-700")}
                      >
                        <BarChart2 size={14} className="inline mr-1" />概览图表
                      </button>
                      <button 
                        onClick={() => setActiveTab('trades')}
                        className={cn("px-3 py-1.5 text-xs font-bold rounded-md transition-colors", activeTab === 'trades' ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-500 hover:text-zinc-700")}
                      >
                        <List size={14} className="inline mr-1" />交易明细
                      </button>
                    </div>
                  )}
                </div>
                
                {isRunning ? (
                  <div className="h-full min-h-[400px] flex flex-col items-center justify-center text-zinc-400 space-y-6">
                    <div className="relative">
                      <div className="w-16 h-16 rounded-full border-4 border-indigo-100" />
                      <div className="w-16 h-16 rounded-full border-4 border-indigo-600 border-t-transparent animate-spin absolute inset-0" />
                    </div>
                    <div className="text-center space-y-2">
                      <h4 className="text-lg font-bold text-zinc-900">正在分配 Qlib 算力节点</h4>
                      <p className="text-sm">正在加载 {market} {startDate} 至 {endDate} 的因子与行情数据...</p>
                    </div>
                  </div>
                ) : !results ? (
                  <div className="h-full min-h-[400px] flex flex-col items-center justify-center text-zinc-300 space-y-4">
                    <TrendingUp size={64} className="opacity-20" />
                    <p className="text-sm font-medium">请在左侧配置参数并点击「启动回测」以获取分析报告</p>
                  </div>
                ) : (
                  <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                    {/* Hero Stats */}
                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                      <div className="bg-white p-5 rounded-2xl border border-zinc-100 shadow-sm">
                        <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-1">期末总资产</p>
                        <p className="text-xl font-bold text-zinc-900">¥{(results.final_account / 10000).toFixed(2)}万</p>
                      </div>
                      <div className="bg-white p-5 rounded-2xl border border-zinc-100 shadow-sm">
                        <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-1">年化收益 (Ann. Return)</p>
                        <p className={cn("text-xl font-bold", (results.metrics?.annualized_return?.risk || 0) > 0 ? "text-emerald-600" : "text-rose-600")}>
                          {formatPct(results.metrics?.annualized_return?.risk)}
                        </p>
                      </div>
                      <div className="bg-white p-5 rounded-2xl border border-zinc-100 shadow-sm">
                        <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-1">最大回撤 (Max Drawdown)</p>
                        <p className="text-xl font-bold text-rose-600">
                          {formatPct(results.metrics?.max_drawdown?.risk)}
                        </p>
                      </div>
                      <div className="bg-white p-5 rounded-2xl border border-zinc-100 shadow-sm">
                        <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-1">夏普比率 (Sharpe)</p>
                        <p className="text-xl font-bold text-indigo-600">
                          {formatNum(results.metrics?.sharpe_ratio)}
                        </p>
                      </div>
                      <div className="bg-white p-5 rounded-2xl border border-zinc-100 shadow-sm">
                        <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-1">胜率 (Win Rate)</p>
                        <p className="text-xl font-bold text-indigo-600">
                          {formatPct(results.metrics?.win_rate)}
                        </p>
                      </div>
                    </div>

                    {activeTab === 'overview' && (
                      <>
                        {/* Equity Curve */}
                        {results.snapshots && results.snapshots.length > 0 && (
                          <div className="bg-white rounded-2xl border border-zinc-100 shadow-sm p-6">
                            <h4 className="text-sm font-bold text-zinc-900 mb-4 flex items-center gap-2">
                              <TrendingUp size={16} className="text-indigo-600" /> 
                              资金曲线 (Equity Curve)
                            </h4>
                            <div className="h-[250px] w-full">
                              <ResponsiveContainer width="100%" height="100%">
                                <LineChart data={results.snapshots}>
                                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f4f4f5" />
                                  <XAxis 
                                    dataKey="date" 
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{fontSize: 10, fill: '#a1a1aa'}}
                                    tickFormatter={(val) => val.substring(5)}
                                    minTickGap={30}
                                  />
                                  <YAxis 
                                    domain={['dataMin', 'dataMax']} 
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{fontSize: 10, fill: '#a1a1aa'}}
                                    tickFormatter={(val) => `${(val/10000).toFixed(0)}w`}
                                    width={40}
                                  />
                                  <Tooltip 
                                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                                    formatter={(value: any) => [`¥${Number(value).toFixed(2)}`, '资产总值']}
                                    labelStyle={{ fontWeight: 'bold', color: '#18181b', marginBottom: '4px' }}
                                  />
                                  <Line 
                                    type="monotone" 
                                    dataKey="total_equity" 
                                    stroke="#4f46e5" 
                                    strokeWidth={2}
                                    dot={false}
                                    activeDot={{ r: 4, strokeWidth: 0 }}
                                  />
                                </LineChart>
                              </ResponsiveContainer>
                            </div>
                          </div>
                        )}
                        
                        {/* Detailed Metrics */}
                        <div className="bg-white rounded-2xl border border-zinc-100 shadow-sm overflow-hidden">
                          <div className="px-6 py-4 border-b border-zinc-100 bg-zinc-50/50">
                            <h4 className="text-sm font-bold text-zinc-900 flex items-center gap-2">
                              <ShieldAlert size={16} className="text-indigo-600" /> 
                              策略风险指标矩阵
                            </h4>
                          </div>
                          <div className="p-6">
                            <table className="w-full text-left">
                              <thead>
                                <tr className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest border-b border-zinc-100">
                                  <th className="pb-3">Indicator</th>
                                  <th className="pb-3 text-right">Value</th>
                                </tr>
                              </thead>
                              <tbody className="text-sm font-medium">
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">Mean Daily Return</td>
                                  <td className="py-3 text-right text-zinc-900">{formatPct(results.metrics?.mean?.risk)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">Daily Return Volatility (Std)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatPct(results.metrics?.std?.risk)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">Annualized Return</td>
                                  <td className="py-3 text-right text-emerald-600">{formatPct(results.metrics?.annualized_return?.risk)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">Sharpe Ratio</td>
                                  <td className="py-3 text-right text-zinc-900">{formatNum(results.metrics?.sharpe_ratio)}</td>
                                </tr>
                                <tr>
                                  <td className="py-3 text-zinc-600">Max Drawdown</td>
                                  <td className="py-3 text-right text-rose-600">{formatPct(results.metrics?.max_drawdown?.risk)}</td>
                                </tr>
                              </tbody>
                            </table>
                          </div>
                        </div>
                      </>
                    )}

                    {activeTab === 'trades' && (
                      <div className="bg-white rounded-2xl border border-zinc-100 shadow-sm overflow-hidden">
                        <div className="px-6 py-4 border-b border-zinc-100 bg-zinc-50/50 flex justify-between items-center">
                          <h4 className="text-sm font-bold text-zinc-900 flex items-center gap-2">
                            <List size={16} className="text-indigo-600" /> 
                            交易流水明细
                          </h4>
                          <span className="text-xs font-medium text-zinc-500">
                            总计 {results.trades?.length || 0} 笔交易
                          </span>
                        </div>
                        <div className="p-0 overflow-x-auto max-h-[500px] overflow-y-auto">
                          <table className="w-full text-left text-sm">
                            <thead className="bg-white sticky top-0 z-10 shadow-sm">
                              <tr className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest border-b border-zinc-100">
                                <th className="py-3 px-6">日期</th>
                                <th className="py-3 px-6">股票代码</th>
                                <th className="py-3 px-6 text-center">方向</th>
                                <th className="py-3 px-6 text-right">成交价</th>
                                <th className="py-3 px-6 text-right">数量</th>
                                <th className="py-3 px-6 text-right">手续费</th>
                                <th className="py-3 px-6 text-right">平仓盈亏</th>
                              </tr>
                            </thead>
                            <tbody className="text-sm font-medium">
                              {results.trades && results.trades.length > 0 ? (
                                results.trades.map((t: any, i: number) => (
                                  <tr key={i} className="border-b border-zinc-50 hover:bg-zinc-50/50 transition-colors">
                                    <td className="py-3 px-6 text-zinc-500 font-mono text-xs">{t.date}</td>
                                    <td className="py-3 px-6 text-zinc-900 font-bold">{t.symbol}</td>
                                    <td className="py-3 px-6 text-center">
                                      <span className={cn(
                                        "px-2 py-0.5 rounded-full text-[10px] uppercase font-bold",
                                        t.action === 'BUY' ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                                      )}>
                                        {t.action}
                                      </span>
                                    </td>
                                    <td className="py-3 px-6 text-right text-zinc-700">¥{t.price.toFixed(2)}</td>
                                    <td className="py-3 px-6 text-right text-zinc-700">{t.shares}</td>
                                    <td className="py-3 px-6 text-right text-zinc-400">¥{t.fee.toFixed(2)}</td>
                                    <td className={cn(
                                      "py-3 px-6 text-right font-bold",
                                      t.action === 'BUY' ? "text-zinc-300" : (t.realized_pnl > 0 ? "text-emerald-600" : "text-rose-600")
                                    )}>
                                      {t.action === 'BUY' ? '--' : `¥${t.realized_pnl.toFixed(2)}`}
                                    </td>
                                  </tr>
                                ))
                              ) : (
                                <tr>
                                  <td colSpan={7} className="py-12 text-center text-zinc-400">暂无交易记录</td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    <div className="flex items-center justify-between p-4 rounded-xl bg-indigo-50 border border-indigo-100">
                      <div className="flex items-center gap-3">
                        <CheckCircle2 size={20} className="text-indigo-600" />
                        <div>
                          <p className="text-sm font-bold text-indigo-900">回测执行完毕</p>
                          <p className="text-xs text-indigo-700/70 mt-0.5">模型 {results.model} 在 {results.start_date} 至 {results.end_date} 期间的推理已经完成</p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
