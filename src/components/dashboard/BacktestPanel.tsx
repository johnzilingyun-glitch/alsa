import React, { useState, useEffect, useMemo, useRef } from 'react';
import { X, Play, RefreshCw, BarChart2, TrendingUp, AlertCircle, ShieldAlert, CheckCircle2, ChevronRight, Activity, Calendar, List, DollarSign } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Brush } from 'recharts';

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
  const [targetSymbol, setTargetSymbol] = useState('600519');
  const [customSymbolsList, setCustomSymbolsList] = useState('600519.SS, 601398.SS, 600036.SS, 601318.SS, 000858.SZ, 000333.SZ, 600900.SS, 601012.SS');

  const [preset, setPreset] = useState<'conservative' | 'balanced' | 'aggressive' | 'custom'>('balanced');
  const [initialCapital, setInitialCapital] = useState(1000000);
  const [commissionRate, setCommissionRate] = useState(0.03); // %
  const [fastWindow, setFastWindow] = useState(5);
  const [slowWindow, setSlowWindow] = useState(20);
  const [rebalanceInterval, setRebalanceInterval] = useState(63);
  
  const [isRunning, setIsRunning] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'trades'>('overview');

  // ── Custom Rule Strategy State ──
  const [crPreset, setCrPreset] = useState<'value_dip' | 'trend_follow' | 'mean_reversion' | 'custom'>('value_dip');
  // Buy rules toggles
  const [crBuyRsi, setCrBuyRsi] = useState(true);
  const [crBuyMacd, setCrBuyMacd] = useState(false);
  const [crBuyMa, setCrBuyMa] = useState(false);
  const [crBuyBoll, setCrBuyBoll] = useState(false);
  const [crBuyPe, setCrBuyPe] = useState(true);
  const [crBuyPb, setCrBuyPb] = useState(false);
  const [crBuyMcap, setCrBuyMcap] = useState(false);
  const [crBuyMom, setCrBuyMom] = useState(false);
  const [crBuyVol, setCrBuyVol] = useState(false);
  const [crBuyBeta, setCrBuyBeta] = useState(false);
  // Sell rules toggles
  const [crSellRsi, setCrSellRsi] = useState(true);
  const [crSellMacd, setCrSellMacd] = useState(false);
  const [crSellMa, setCrSellMa] = useState(false);
  const [crSellBoll, setCrSellBoll] = useState(false);
  const [crSellMom, setCrSellMom] = useState(false);
  const [crSellVol, setCrSellVol] = useState(false);
  const [crSellBeta, setCrSellBeta] = useState(false);
  // Indicator params
  const [crRsiPeriod, setCrRsiPeriod] = useState(14);
  const [crRsiBuyThreshold, setCrRsiBuyThreshold] = useState(30);
  const [crRsiSellThreshold, setCrRsiSellThreshold] = useState(70);
  const [crMacdFast, setCrMacdFast] = useState(12);
  const [crMacdSlow, setCrMacdSlow] = useState(26);
  const [crMacdSignal, setCrMacdSignal] = useState(9);
  const [crMaPeriod, setCrMaPeriod] = useState(20);
  const [crMaType, setCrMaType] = useState<'sma' | 'ema'>('sma');
  const [crBollPeriod, setCrBollPeriod] = useState(20);
  const [crBollDev, setCrBollDev] = useState(2.0);
  // Quantitative Factor params (Buy Side)
  const [crMomPeriod, setCrMomPeriod] = useState(10);
  const [crMomThreshold, setCrMomThreshold] = useState(0.0);
  const [crVolPeriod, setCrVolPeriod] = useState(10);
  const [crVolThreshold, setCrVolThreshold] = useState(1.0);
  const [crBetaPeriod, setCrBetaPeriod] = useState(10);
  const [crBetaThreshold, setCrBetaThreshold] = useState(0.0);

  // Quantitative Factor params (Sell Side)
  const [crSellMomPeriod, setCrSellMomPeriod] = useState(10);
  const [crSellMomThreshold, setCrSellMomThreshold] = useState(0.0);
  const [crSellVolPeriod, setCrSellVolPeriod] = useState(10);
  const [crSellVolThreshold, setCrSellVolThreshold] = useState(1.0);
  const [crSellBetaPeriod, setCrSellBetaPeriod] = useState(10);
  const [crSellBetaThreshold, setCrSellBetaThreshold] = useState(0.0);
  // Fundamental params
  const [crPeMax, setCrPeMax] = useState(15);
  const [crPbMax, setCrPbMax] = useState(2.0);
  const [crMcapMin, setCrMcapMin] = useState(100);
  // Risk controls
  const [crStopLoss, setCrStopLoss] = useState(5.0);
  const [crTakeProfit, setCrTakeProfit] = useState(20.0);
  const [crTrailingStop, setCrTrailingStop] = useState(0.0);
  // Position sizing
  const [crPosMode, setCrPosMode] = useState<'fixed_shares' | 'fixed_pct' | 'kelly'>('fixed_pct');
  const [crPosValue, setCrPosValue] = useState(30);

  const chartData = useMemo(() => {
    if (!results || !results.snapshots) return [];
    const tradesMap: Record<string, any[]> = {};
    if (results.trades) {
      results.trades.forEach((t: any) => {
        if (!t.date) return;
        const dateStr = t.date.substring(0, 10);
        if (!tradesMap[dateStr]) {
          tradesMap[dateStr] = [];
        }
        tradesMap[dateStr].push(t);
      });
    }
    return results.snapshots.map((s: any) => ({
      ...s,
      trades: tradesMap[s.date] || [],
    }));
  }, [results]);

  // Autocomplete Suggestions for Target Symbol
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const symbolInputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchSuggestions = async () => {
      if (!targetSymbol || targetSymbol.trim().length < 1) {
        setSuggestions([]);
        setShowSuggestions(false);
        return;
      }

      try {
        const params = new URLSearchParams();
        params.set('input', targetSymbol);
        params.set('market', market === 'A-Share' ? 'CN' : 'US');
        
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
  }, [targetSymbol, market]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (symbolInputRef.current && !symbolInputRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectSuggestion = (s: any) => {
    const finalSym = s.symbol || s.fullSymbol;
    setTargetSymbol(finalSym);
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


  const applyCrPreset = (key: string) => {
    setCrPreset(key as any);
    // Reset all new factors by default
    setCrBuyMom(false); setCrBuyVol(false); setCrBuyBeta(false);
    setCrSellMom(false); setCrSellVol(false); setCrSellBeta(false);
    setCrMomPeriod(10); setCrMomThreshold(0.0);
    setCrVolPeriod(10); setCrVolThreshold(1.0);
    setCrBetaPeriod(10); setCrBetaThreshold(0.0);
    setCrSellMomPeriod(10); setCrSellMomThreshold(0.0);
    setCrSellVolPeriod(10); setCrSellVolThreshold(1.0);
    setCrSellBetaPeriod(10); setCrSellBetaThreshold(0.0);

    if (key === 'value_dip') {
      setCrBuyRsi(true); setCrBuyMacd(false); setCrBuyMa(false); setCrBuyBoll(false);
      setCrBuyPe(true); setCrBuyPb(false); setCrBuyMcap(false);
      setCrSellRsi(true); setCrSellMacd(false); setCrSellMa(false); setCrSellBoll(false);
      setCrRsiPeriod(14); setCrRsiBuyThreshold(30); setCrRsiSellThreshold(70);
      setCrPeMax(15); setCrStopLoss(5); setCrTakeProfit(20); setCrTrailingStop(0);
      setCrPosMode('fixed_pct'); setCrPosValue(30);
    } else if (key === 'trend_follow') {
      setCrBuyRsi(false); setCrBuyMacd(true); setCrBuyMa(true); setCrBuyBoll(false);
      setCrBuyPe(false); setCrBuyPb(false); setCrBuyMcap(false);
      setCrSellRsi(false); setCrSellMacd(true); setCrSellMa(true); setCrSellBoll(false);
      setCrMacdFast(12); setCrMacdSlow(26); setCrMacdSignal(9);
      setCrMaPeriod(20); setCrMaType('sma');
      setCrStopLoss(8); setCrTakeProfit(0); setCrTrailingStop(12);
      setCrPosMode('fixed_pct'); setCrPosValue(20);
    } else if (key === 'mean_reversion') {
      setCrBuyRsi(false); setCrBuyMacd(false); setCrBuyMa(false); setCrBuyBoll(true);
      setCrBuyPe(false); setCrBuyPb(false); setCrBuyMcap(false);
      setCrSellRsi(false); setCrSellMacd(false); setCrSellMa(false); setCrSellBoll(true);
      setCrBollPeriod(20); setCrBollDev(2.0);
      setCrStopLoss(5); setCrTakeProfit(15); setCrTrailingStop(0);
      setCrPosMode('fixed_shares'); setCrPosValue(100);
    }
  };

  const buildCustomRuleParams = () => {
    const buyRules: any[] = [];
    if (crBuyRsi) buyRules.push({ type: 'rsi_oversold', rsi_period: crRsiPeriod, rsi_threshold: crRsiBuyThreshold });
    if (crBuyMacd) buyRules.push({ type: 'macd_golden_cross', fast: crMacdFast, slow: crMacdSlow, signal: crMacdSignal });
    if (crBuyMa) buyRules.push({ type: 'price_above_ma', ma_period: crMaPeriod, ma_type: crMaType });
    if (crBuyBoll) buyRules.push({ type: 'boll_lower_break', boll_period: crBollPeriod, boll_dev: crBollDev });
    if (crBuyPe) buyRules.push({ type: 'pe_below', pe_max: crPeMax });
    if (crBuyPb) buyRules.push({ type: 'pb_below', pb_max: crPbMax });
    if (crBuyMcap) buyRules.push({ type: 'market_cap_above', mc_min: crMcapMin });
    if (crBuyMom) buyRules.push({ type: 'momentum_above', momentum_period: crMomPeriod, momentum_threshold: crMomThreshold });
    if (crBuyVol) buyRules.push({ type: 'volatility_above', volatility_period: crVolPeriod, volatility_threshold: crVolThreshold });
    if (crBuyBeta) buyRules.push({ type: 'beta_above', beta_period: crBetaPeriod, beta_threshold: crBetaThreshold });

    const sellRules: any[] = [];
    if (crSellRsi) sellRules.push({ type: 'rsi_overbought', rsi_period: crRsiPeriod, rsi_threshold: crRsiSellThreshold });
    if (crSellMacd) sellRules.push({ type: 'macd_dead_cross', fast: crMacdFast, slow: crMacdSlow, signal: crMacdSignal });
    if (crSellMa) sellRules.push({ type: 'price_below_ma', ma_period: crMaPeriod, ma_type: crMaType });
    if (crSellBoll) sellRules.push({ type: 'boll_upper_break', boll_period: crBollPeriod, boll_dev: crBollDev });
    if (crSellMom) sellRules.push({ type: 'momentum_below', momentum_period: crSellMomPeriod, momentum_threshold: crSellMomThreshold });
    if (crSellVol) sellRules.push({ type: 'volatility_below', volatility_period: crSellVolPeriod, volatility_threshold: crSellVolThreshold });
    if (crSellBeta) sellRules.push({ type: 'beta_below', beta_period: crSellBetaPeriod, beta_threshold: crSellBetaThreshold });

    return {
      buy_rules: buyRules,
      sell_rules: sellRules,
      stop_loss_pct: crStopLoss,
      take_profit_pct: crTakeProfit,
      trailing_stop_pct: crTrailingStop,
      position_mode: crPosMode,
      position_value: crPosValue,
      target_symbol: targetSymbol,
    };
  };

  const applyPreset = (p: string, currentModel = model) => {
    setPreset(p as any);
    if (p === 'custom') return;
    
    if (currentModel === 'portfolio_cross_sectional') {
      setInitialCapital(1000000);
      setCommissionRate(0.03);
      if (p === 'conservative') {
        setRebalanceInterval(126);
      } else if (p === 'balanced') {
        setRebalanceInterval(63);
      } else {
        setRebalanceInterval(21);
      }
    } else {
      setInitialCapital(1000000);
      setCommissionRate(0.03);
      if (p === 'conservative') {
        setFastWindow(10);
        setSlowWindow(30);
      } else if (p === 'balanced') {
        setFastWindow(5);
        setSlowWindow(20);
      } else {
        setFastWindow(3);
        setSlowWindow(10);
      }
    }
  };

  useEffect(() => {
    if (preset !== 'custom') {
      applyPreset(preset, model);
    } else {
      setInitialCapital(1000000);
    }
  }, [model]);

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
      const strategyParams: Record<string, any> = model === 'MockAgent'
        ? { fast_window: fastWindow, slow_window: slowWindow }
        : model === 'custom_rule'
        ? buildCustomRuleParams()
        : { rebalance_interval: rebalanceInterval };

      // Pass custom stock pool for portfolio mode
      if (model === 'portfolio_cross_sectional' && customSymbolsList.trim()) {
        strategyParams.custom_symbols = customSymbolsList.split(',').map(s => s.trim()).filter(Boolean);
      }

      const res = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate,
          model,
          market: market === 'A-Share' ? 'CN' : 'US',
          config: {
            initial_capital: initialCapital,
            commission: commissionRate / 100,
            target_symbol: (model === 'MockAgent' || model === 'custom_rule') ? targetSymbol : undefined,
            strategy_params: strategyParams
          }
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

  const [isConverting, setIsConverting] = useState(false);
  const [convertMsg, setConvertMsg] = useState<string | null>(null);

  const handleConvertToMock = async () => {
    if (!results) return;
    setIsConverting(true);
    setConvertMsg(null);
    try {
      const res = await fetch('/api/backtest/convert-to-mock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          market: market,
          initial_capital: initialCapital,
          strategy_name: model,
        })
      });
      const data = await res.json();
      if (data.success) {
        setConvertMsg(`✅ 模拟盘已创建：${data.data.account_name}（账户 ${data.data.account_id}），含 ${data.data.positions_count} 只持仓`);
      } else {
        setConvertMsg(`❌ 转换失败：${data.message || '未知错误'}`);
      }
    } catch (e: any) {
      setConvertMsg(`❌ 网络错误：${e.message}`);
    } finally {
      setIsConverting(false);
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
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-0">
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
            className="relative w-screen h-screen overflow-hidden bg-white flex flex-col"
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
                        { id: 'custom_rule', name: '自定义规则策略', desc: '可视化配置指标/估值/风控规则' },
                        { id: 'GPT-4o', name: 'GPT-4o (即将开放)', desc: '深度语言模型基本面分析' },
                        { id: 'DeepSeek-V3', name: 'DeepSeek-V3 (即将开放)', desc: '金融定制强化学习模型' }
                      ].map(m => (
                        <button
                          key={m.id}
                          onClick={() => setModel(m.id)}
                          disabled={m.id !== 'MockAgent' && m.id !== 'portfolio_cross_sectional' && m.id !== 'custom_rule'}
                          className={cn(
                            "text-left p-3 rounded-xl border-2 transition-all flex flex-col items-start w-full",
                            model === m.id ? "border-indigo-600 bg-indigo-50/50" : "border-zinc-100 hover:border-zinc-200",
                            (m.id !== 'MockAgent' && m.id !== 'portfolio_cross_sectional' && m.id !== 'custom_rule') && "opacity-50 cursor-not-allowed"
                          )}
                        >
                          <span className={cn("text-sm font-bold", model === m.id ? "text-indigo-700" : "text-zinc-700")}>{m.name}</span>
                          <span className="text-[10px] text-zinc-400 mt-0.5">{m.desc}</span>
                        </button>
                      ))}
                    </div>
                    {/* Model Info Banner */}
                    <div className="mt-2.5 p-3 bg-indigo-50/40 border border-indigo-100/30 rounded-xl text-[10px] text-indigo-700 leading-normal">
                      {model === 'MockAgent' ? (
                        <span><strong>Mock Agent 介绍：</strong>使用经典的趋势跟踪（双均线交叉）算法。当快线向上穿越（金叉）慢线时发出买入信号，向下穿越（死叉）时发出卖出信号。主要用于测试回测系统各功能的底层连通。</span>
                      ) : model === 'portfolio_cross_sectional' ? (
                        <span><strong>多股截面调仓介绍：</strong>基于价值和市值轮动的多因子量化策略。从白马股池中挑选估值偏低（PE &lt; 20）且市值大于10亿的股票，并等权重分配资金进行周期持仓与调仓。</span>
                      ) : (
                        <span><strong>自定义规则策略介绍：</strong>支持可视化配置多重买入条件（RSI、MACD、布林带、均线、PE/PB 估值及市值）和卖出条件，可设定固定止损、固定止盈和移动止损等出场风控。</span>
                      )}
                    </div>
                  </div>

                  {/* Market Selection */}
                  <div className="space-y-3">
                    <label className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider block">回测市场 (Market)</label>
                    <div className="grid grid-cols-2 gap-2">
                      {['A-Share', 'US-Share'].map(m => (
                        <button
                          key={m}
                          onClick={() => {
                            setMarket(m);
                            setTargetSymbol(m === 'A-Share' ? '600519' : 'AAPL');
                            setCustomSymbolsList(m === 'A-Share' 
                              ? '600519.SS, 601398.SS, 600036.SS, 601318.SS, 000858.SZ, 000333.SZ, 600900.SS, 601012.SS'
                              : 'AAPL, MSFT, TSLA, AMZN, GOOGL, NVDA, META, NFLX'
                            );
                          }}
                          className={cn(
                            "p-3 rounded-xl border-2 text-center transition-all",
                            market === m ? "border-indigo-600 bg-indigo-50/50 text-indigo-700" : "border-zinc-100 hover:border-zinc-200 text-zinc-500"
                          )}
                        >
                          <span className="text-sm font-bold">{m}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Stock Pool Input */}
                  {model === 'portfolio_cross_sectional' && (
                    <div className="space-y-3">
                      <label className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider block">自建股票池 (Custom Stock Pool)</label>
                      <textarea
                        value={customSymbolsList}
                        onChange={(e) => setCustomSymbolsList(e.target.value)}
                        placeholder="例如 600519.SS, 601398.SS, 600036.SS"
                        rows={3}
                        className="w-full px-4 py-2.5 rounded-xl border border-zinc-200 text-sm font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 font-mono text-zinc-800 leading-relaxed"
                      />
                      <span className="text-[9px] text-zinc-400 leading-normal block">请输入逗号分隔的股票代码列表（A股以 .SS/.SZ 结尾，美股直接写代码）。</span>
                    </div>
                  )}

                  {/* Target Symbol Input */}
                  {(model === 'MockAgent' || model === 'custom_rule') && (
                    <div className="space-y-3 relative" ref={symbolInputRef}>
                      <label className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider block">股票代码 (Stock Symbol)</label>
                      <input
                        type="text"
                        value={targetSymbol}
                        onChange={(e) => setTargetSymbol(e.target.value)}
                        onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
                        onKeyDown={handleKeyDown}
                        placeholder={market === 'A-Share' ? '例如 600519' : '例如 AAPL'}
                        className="w-full px-4 py-2.5 rounded-xl border border-zinc-200 text-sm font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 font-mono"
                      />
                      
                      {/* Suggestions Dropdown */}
                      {showSuggestions && suggestions.length > 0 && (
                        <div className="absolute top-full left-0 right-0 mt-1 z-[60] overflow-hidden rounded-2xl border border-zinc-100 bg-white/95 backdrop-blur-xl shadow-2xl shadow-indigo-600/10 max-h-60 overflow-y-auto">
                          <div className="p-1.5" role="listbox" aria-label="Search suggestions">
                            {suggestions.map((s, idx) => (
                              <button
                                key={`suggestion-${s.symbol}-${idx}`}
                                type="button"
                                role="option"
                                aria-selected={idx === selectedIndex}
                                onClick={() => handleSelectSuggestion(s)}
                                onMouseEnter={() => setSelectedIndex(idx)}
                                className={`flex w-full items-center justify-between px-4 py-2 rounded-xl transition-all ${
                                  idx === selectedIndex ? 'bg-indigo-50 text-indigo-700' : 'text-zinc-700 hover:bg-zinc-50'
                                }`}
                              >
                                <div className="flex items-center gap-3">
                                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${idx === selectedIndex ? 'bg-indigo-100 text-indigo-600' : 'bg-zinc-100 text-zinc-500'}`}>
                                    {s.symbol}
                                  </span>
                                  <span className="font-bold text-xs text-left">{s.name}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                   {s.exchange && <span className="text-[9px] font-bold uppercase tracking-widest text-zinc-400">{s.exchange}</span>}
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

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

                  {/* Backtest Config Parameters */}
                  <div className="space-y-4 pt-4 border-t border-zinc-100">
                    <label className="text-[11px] font-bold text-zinc-500 uppercase tracking-wider block">回测控制参数</label>
                    
                    {/* Presets */}
                    {model !== 'custom_rule' && (
                      <div className="space-y-2">
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">参数预设</span>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { id: 'conservative', name: '稳健型' },
                            { id: 'balanced', name: '平衡型' },
                            { id: 'aggressive', name: '激进型' }
                          ].map(p => (
                            <button
                              key={p.id}
                              type="button"
                              onClick={() => applyPreset(p.id)}
                              className={cn(
                                "py-1.5 px-2 rounded-lg border text-xs font-bold text-center transition-all",
                                preset === p.id ? "border-indigo-600 bg-indigo-50/50 text-indigo-700" : "border-zinc-200 hover:border-zinc-300 text-zinc-500"
                              )}
                            >
                              {p.name}
                            </button>
                          ))}
                        </div>
                        
                        {/* Preset Description */}
                        <div className="mt-2.5 p-3 bg-zinc-50 border border-zinc-100 rounded-xl text-[10px] text-zinc-500 leading-normal">
                          {model === 'MockAgent' ? (
                            preset === 'conservative' ? (
                              <span><strong>稳健型参数：</strong>快均线 10 天 / 慢均线 30 天。交易频率较低，过滤小周期短期扰动，追求稳健趋势。</span>
                            ) : preset === 'balanced' ? (
                              <span><strong>平衡型参数：</strong>快均线 5 天 / 慢均线 20 天。标准经典参数配置，能够捕捉中短期核心主干趋势。</span>
                            ) : preset === 'aggressive' ? (
                              <span><strong>激进型参数：</strong>快均线 3 天 / 慢均线 10 天。对价格异常敏感，调仓信号高度灵敏，伴随较高的交易摩擦。</span>
                            ) : (
                              <span><strong>自定义参数：</strong>快均线 {fastWindow} 天 / 慢均线 {slowWindow} 天。您可以自由调整均线周期进行策略测试。</span>
                            )
                          ) : (
                            preset === 'conservative' ? (
                              <span><strong>稳健型参数：</strong>调仓周期 126 天（约半年）。极低换仓频率，减少频繁交易带来的摩擦成本，倾向价值定力。</span>
                            ) : preset === 'balanced' ? (
                              <span><strong>平衡型参数：</strong>调仓周期 63 天（约一个季度）。季度调整，紧密跟随企业定期财报更新节奏进行再平衡。</span>
                            ) : preset === 'aggressive' ? (
                              <span><strong>激进型参数：</strong>调仓周期 21 天（约一个交易月）。月度高频轮动，淘汰劣势及高估值标的，追求Alpha。</span>
                            ) : (
                              <span><strong>自定义参数：</strong>调仓周期 {rebalanceInterval} 天。手动探索不同的截面调仓轮动频率。</span>
                            )
                          )}
                        </div>
                      </div>
                    )}

                    {/* Initial Capital & Commission */}
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">初始资金 (¥)</span>
                        <input
                          type="number"
                          value={initialCapital}
                          onChange={(e) => {
                            setInitialCapital(Number(e.target.value));
                            setPreset('custom');
                          }}
                          className="w-full px-3 py-2 rounded-xl border border-zinc-200 text-xs font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                        />
                      </div>
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">手续费率 (%)</span>
                        <input
                          type="number"
                          step="0.001"
                          value={commissionRate}
                          onChange={(e) => {
                            setCommissionRate(Number(e.target.value));
                            setPreset('custom');
                          }}
                          className="w-full px-3 py-2 rounded-xl border border-zinc-200 text-xs font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                        />
                      </div>
                    </div>

                    {/* Strategy Specific */}
                    {model === 'custom_rule' ? (
                      <div className="space-y-4 pt-2">
                        {/* Custom Rule Preset Templates */}
                        <div className="space-y-2">
                          <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block">规则预设模板</span>
                          <div className="grid grid-cols-3 gap-1.5">
                            {[
                              { id: 'value_dip', name: '价值低估' },
                              { id: 'trend_follow', name: '趋势追踪' },
                              { id: 'mean_reversion', name: '均值回归' }
                            ].map(p => (
                              <button
                                key={p.id}
                                type="button"
                                onClick={() => applyCrPreset(p.id)}
                                className={cn(
                                  "py-1 px-1.5 rounded-lg border text-[10px] font-bold text-center transition-all",
                                  crPreset === p.id ? "border-indigo-600 bg-indigo-50/50 text-indigo-700" : "border-zinc-200 hover:border-zinc-300 text-zinc-500"
                                )}
                              >
                                {p.name}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Buy Rules Section */}
                        <div className="space-y-2.5 p-3 rounded-2xl bg-zinc-50 border border-zinc-100">
                          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block text-indigo-600">买入条件 (AND 组合)</span>
                          
                          {/* RSI Oversold */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyRsi}
                                onChange={(e) => { setCrBuyRsi(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">RSI 超卖买入</span>
                            </label>
                            {crBuyRsi && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">RSI 周期</span>
                                  <input
                                    type="number"
                                    value={crRsiPeriod}
                                    onChange={(e) => { setCrRsiPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">买入阈值</span>
                                  <input
                                    type="number"
                                    value={crRsiBuyThreshold}
                                    onChange={(e) => { setCrRsiBuyThreshold(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* MACD Golden Cross */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyMacd}
                                onChange={(e) => { setCrBuyMacd(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">MACD 金叉买入</span>
                            </label>
                            {crBuyMacd && (
                              <div className="grid grid-cols-3 gap-1.5 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">快线</span>
                                  <input
                                    type="number"
                                    value={crMacdFast}
                                    onChange={(e) => { setCrMacdFast(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">慢线</span>
                                  <input
                                    type="number"
                                    value={crMacdSlow}
                                    onChange={(e) => { setCrMacdSlow(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">信号</span>
                                  <input
                                    type="number"
                                    value={crMacdSignal}
                                    onChange={(e) => { setCrMacdSignal(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Price Above MA */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyMa}
                                onChange={(e) => { setCrBuyMa(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">站上均线买入</span>
                            </label>
                            {crBuyMa && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">均线周期</span>
                                  <input
                                    type="number"
                                    value={crMaPeriod}
                                    onChange={(e) => { setCrMaPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">均线类型</span>
                                  <select
                                    value={crMaType}
                                    onChange={(e) => { setCrMaType(e.target.value as any); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none bg-white font-medium text-zinc-800"
                                  >
                                    <option value="sma">SMA</option>
                                    <option value="ema">EMA</option>
                                  </select>
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Bollinger Lower Break */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyBoll}
                                onChange={(e) => { setCrBuyBoll(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">触碰布林下轨买入</span>
                            </label>
                            {crBuyBoll && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">布林周期</span>
                                  <input
                                    type="number"
                                    value={crBollPeriod}
                                    onChange={(e) => { setCrBollPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">标准差倍数</span>
                                  <input
                                    type="number"
                                    step="0.1"
                                    value={crBollDev}
                                    onChange={(e) => { setCrBollDev(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* PE Below */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyPe}
                                onChange={(e) => { setCrBuyPe(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">估值 PE (TTM) 低于</span>
                            </label>
                            {crBuyPe && (
                              <div className="pl-5">
                                <input
                                  type="number"
                                  value={crPeMax}
                                  onChange={(e) => { setCrPeMax(Number(e.target.value)); setCrPreset('custom'); }}
                                  className="w-24 px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                />
                              </div>
                            )}
                          </div>

                          {/* PB Below */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyPb}
                                onChange={(e) => { setCrBuyPb(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">估值 PB 低于</span>
                            </label>
                            {crBuyPb && (
                              <div className="pl-5">
                                <input
                                  type="number"
                                  step="0.1"
                                  value={crPbMax}
                                  onChange={(e) => { setCrPbMax(Number(e.target.value)); setCrPreset('custom'); }}
                                  className="w-24 px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                />
                              </div>
                            )}
                          </div>

                          {/* Market Cap Above */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyMcap}
                                onChange={(e) => { setCrBuyMcap(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">市值高于 (亿元)</span>
                            </label>
                            {crBuyMcap && (
                              <div className="pl-5">
                                <input
                                  type="number"
                                  value={crMcapMin}
                                  onChange={(e) => { setCrMcapMin(Number(e.target.value)); setCrPreset('custom'); }}
                                  className="w-24 px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                />
                              </div>
                            )}
                          </div>

                          {/* Momentum Above */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyMom}
                                onChange={(e) => { setCrBuyMom(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">价格动量 (ROC%) 高于</span>
                            </label>
                            {crBuyMom && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">动量周期</span>
                                  <input
                                    type="number"
                                    value={crMomPeriod}
                                    onChange={(e) => { setCrMomPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">阈值 (%)</span>
                                  <input
                                    type="number"
                                    step="0.1"
                                    value={crMomThreshold}
                                    onChange={(e) => { setCrMomThreshold(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Volatility Above */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyVol}
                                onChange={(e) => { setCrBuyVol(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">历史波动率 (STD) 高于</span>
                            </label>
                            {crBuyVol && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">波动周期</span>
                                  <input
                                    type="number"
                                    value={crVolPeriod}
                                    onChange={(e) => { setCrVolPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">波动阈值</span>
                                  <input
                                    type="number"
                                    step="0.1"
                                    value={crVolThreshold}
                                    onChange={(e) => { setCrVolThreshold(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Beta Above */}
                          <div className="space-y-1.5">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crBuyBeta}
                                onChange={(e) => { setCrBuyBeta(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">自身弹性系数 (BETA) 高于</span>
                            </label>
                            {crBuyBeta && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">弹性周期</span>
                                  <input
                                    type="number"
                                    value={crBetaPeriod}
                                    onChange={(e) => { setCrBetaPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">弹性阈值</span>
                                  <input
                                    type="number"
                                    step="0.01"
                                    value={crBetaThreshold}
                                    onChange={(e) => { setCrBetaThreshold(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Sell Rules Section */}
                        <div className="space-y-2.5 p-3 rounded-2xl bg-zinc-50 border border-zinc-100">
                          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block text-rose-600">卖出条件 (OR 组合)</span>
                          
                          {/* RSI Overbought */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crSellRsi}
                                onChange={(e) => { setCrSellRsi(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">RSI 超买卖出</span>
                            </label>
                            {crSellRsi && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">RSI 周期</span>
                                  <input
                                    type="number"
                                    value={crRsiPeriod}
                                    onChange={(e) => { setCrRsiPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">卖出阈值</span>
                                  <input
                                    type="number"
                                    value={crRsiSellThreshold}
                                    onChange={(e) => { setCrRsiSellThreshold(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* MACD Dead Cross */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crSellMacd}
                                onChange={(e) => { setCrSellMacd(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">MACD 死叉卖出</span>
                            </label>
                            {crSellMacd && (
                              <div className="grid grid-cols-3 gap-1.5 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">快线</span>
                                  <input
                                    type="number"
                                    value={crMacdFast}
                                    onChange={(e) => { setCrMacdFast(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">慢线</span>
                                  <input
                                    type="number"
                                    value={crMacdSlow}
                                    onChange={(e) => { setCrMacdSlow(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">信号</span>
                                  <input
                                    type="number"
                                    value={crMacdSignal}
                                    onChange={(e) => { setCrMacdSignal(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Price Below MA */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crSellMa}
                                onChange={(e) => { setCrSellMa(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">跌破均线卖出</span>
                            </label>
                            {crSellMa && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">均线周期</span>
                                  <input
                                    type="number"
                                    value={crMaPeriod}
                                    onChange={(e) => { setCrMaPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">均线类型</span>
                                  <select
                                    value={crMaType}
                                    onChange={(e) => { setCrMaType(e.target.value as any); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none bg-white font-medium text-zinc-800"
                                  >
                                    <option value="sma">SMA</option>
                                    <option value="ema">EMA</option>
                                  </select>
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Bollinger Upper Break */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crSellBoll}
                                onChange={(e) => { setCrSellBoll(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">触碰布林上轨卖出</span>
                            </label>
                            {crSellBoll && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">布林周期</span>
                                  <input
                                    type="number"
                                    value={crBollPeriod}
                                    onChange={(e) => { setCrBollPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">标准差倍数</span>
                                  <input
                                    type="number"
                                    step="0.1"
                                    value={crBollDev}
                                    onChange={(e) => { setCrBollDev(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Momentum Below */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crSellMom}
                                onChange={(e) => { setCrSellMom(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">价格动量跌破阈值卖出</span>
                            </label>
                            {crSellMom && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">动量周期</span>
                                  <input
                                    type="number"
                                    value={crSellMomPeriod}
                                    onChange={(e) => { setCrSellMomPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">阈值 (%)</span>
                                  <input
                                    type="number"
                                    step="0.1"
                                    value={crSellMomThreshold}
                                    onChange={(e) => { setCrSellMomThreshold(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Volatility Below */}
                          <div className="space-y-1.5 pb-2 border-b border-zinc-200/50">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crSellVol}
                                onChange={(e) => { setCrSellVol(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">历史波动率低于阈值卖出</span>
                            </label>
                            {crSellVol && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">波动周期</span>
                                  <input
                                    type="number"
                                    value={crSellVolPeriod}
                                    onChange={(e) => { setCrSellVolPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">波动阈值</span>
                                  <input
                                    type="number"
                                    step="0.1"
                                    value={crSellVolThreshold}
                                    onChange={(e) => { setCrSellVolThreshold(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>

                          {/* Beta Below */}
                          <div className="space-y-1.5">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={crSellBeta}
                                onChange={(e) => { setCrSellBeta(e.target.checked); setCrPreset('custom'); }}
                                className="rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5"
                              />
                              <span className="text-xs font-bold text-zinc-700">弹性系数低于阈值卖出</span>
                            </label>
                            {crSellBeta && (
                              <div className="grid grid-cols-2 gap-2 pl-5">
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">弹性周期</span>
                                  <input
                                    type="number"
                                    value={crSellBetaPeriod}
                                    onChange={(e) => { setCrSellBetaPeriod(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                                <div className="space-y-0.5">
                                  <span className="text-[9px] text-zinc-400">弹性阈值</span>
                                  <input
                                    type="number"
                                    step="0.01"
                                    value={crSellBetaThreshold}
                                    onChange={(e) => { setCrSellBetaThreshold(Number(e.target.value)); setCrPreset('custom'); }}
                                    className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                                  />
                                </div>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Risk Controls Section */}
                        <div className="space-y-2.5 p-3 rounded-2xl bg-zinc-50 border border-zinc-100">
                          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block text-indigo-600">出场风控设置</span>
                          <div className="grid grid-cols-3 gap-2">
                            <div className="space-y-0.5">
                              <span className="text-[9px] text-zinc-400 block font-semibold">固定止损(%)</span>
                              <input
                                type="number"
                                step="0.5"
                                value={crStopLoss}
                                onChange={(e) => { setCrStopLoss(Number(e.target.value)); setCrPreset('custom'); }}
                                className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                              />
                            </div>
                            <div className="space-y-0.5">
                              <span className="text-[9px] text-zinc-400 block font-semibold">固定止盈(%)</span>
                              <input
                                type="number"
                                step="0.5"
                                value={crTakeProfit}
                                onChange={(e) => { setCrTakeProfit(Number(e.target.value)); setCrPreset('custom'); }}
                                className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                              />
                            </div>
                            <div className="space-y-0.5">
                              <span className="text-[9px] text-zinc-400 block font-semibold">移动止损(%)</span>
                              <input
                                type="number"
                                step="0.5"
                                value={crTrailingStop}
                                onChange={(e) => { setCrTrailingStop(Number(e.target.value)); setCrPreset('custom'); }}
                                className="w-full px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                              />
                            </div>
                          </div>
                          <span className="text-[8px] text-zinc-400 block leading-tight mt-0.5">设为 0 表示不启用。移动止损自买入后最高价起算。</span>
                        </div>

                        {/* Position Sizing Section */}
                        <div className="space-y-2.5 p-3 rounded-2xl bg-zinc-50 border border-zinc-100">
                          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider block text-indigo-600">仓位管理模式</span>
                          <div className="flex flex-col gap-1.5">
                            {[
                              { id: 'fixed_shares', label: '固定手数' },
                              { id: 'fixed_pct', label: '固定比例 (%)' },
                              { id: 'kelly', label: '凯利公式 (10%预设)' }
                            ].map(mode => (
                              <label key={mode.id} className="flex items-center gap-2 text-xs font-semibold text-zinc-700 cursor-pointer">
                                <input
                                  type="radio"
                                  name="pos_mode"
                                  value={mode.id}
                                  checked={crPosMode === mode.id}
                                  onChange={(e) => { setCrPosMode(e.target.value as any); setCrPreset('custom'); }}
                                  className="border-zinc-300 text-indigo-600 focus:ring-indigo-500 h-3.5 w-3.5 animate-none"
                                />
                                <span>{mode.label}</span>
                              </label>
                            ))}
                          </div>
                          {crPosMode !== 'kelly' && (
                            <div className="space-y-0.5 pt-1.5 border-t border-zinc-200/50">
                              <span className="text-[9px] text-zinc-400">
                                {crPosMode === 'fixed_shares' ? '手数 (股数，例如 100)' : '比例值 (百分比，例如 20)'}
                              </span>
                              <input
                                type="number"
                                value={crPosValue}
                                onChange={(e) => { setCrPosValue(Number(e.target.value)); setCrPreset('custom'); }}
                                className="w-24 px-2 py-1 rounded-lg border border-zinc-200 text-xs focus:outline-none"
                              />
                            </div>
                          )}
                        </div>

                        {/* Natural Language Rule Description */}
                        <div className="p-3 bg-indigo-50/50 border border-indigo-100 rounded-xl text-[10px] text-indigo-700 leading-normal space-y-1">
                          <strong>💡 当前策略描述：</strong>
                          <div>
                            买入条件：满足全部【
                            {[
                              crBuyRsi && `RSI超卖(Period:${crRsiPeriod}, Thresh:${crRsiBuyThreshold})`,
                              crBuyMacd && `MACD金叉(Fast:${crMacdFast}, Slow:${crMacdSlow}, Sig:${crMacdSignal})`,
                              crBuyMa && `站上${crMaPeriod}日${crMaType.toUpperCase()}`,
                              crBuyBoll && `突破布林下轨(Period:${crBollPeriod}, Dev:${crBollDev})`,
                              crBuyPe && `PE TTM < ${crPeMax}`,
                              crBuyPb && `PB < ${crPbMax}`,
                              crBuyMcap && `总市值 > ${crMcapMin}亿`,
                              crBuyMom && `价格动量ROC向上突破(Period:${crMomPeriod}, Thresh:${crMomThreshold}%)`,
                              crBuyVol && `历史波动率高于(Period:${crVolPeriod}, Thresh:${crVolThreshold})`,
                              crBuyBeta && `弹性系数BETA高于(Period:${crBetaPeriod}, Thresh:${crBetaThreshold})`
                            ].filter(Boolean).join(' 且 ') || '无限制条件（默认不买入）'}
                            】时买入；
                          </div>
                          <div>
                            卖出条件：满足任一【
                            {[
                              crSellRsi && `RSI超买(Period:${crRsiPeriod}, Thresh:${crRsiSellThreshold})`,
                              crSellMacd && `MACD死叉(Fast:${crMacdFast}, Slow:${crMacdSlow}, Sig:${crMacdSignal})`,
                              crSellMa && `跌破${crMaPeriod}日${crMaType.toUpperCase()}`,
                              crSellBoll && `突破布林上轨(Period:${crBollPeriod}, Dev:${crBollDev})`,
                              crSellMom && `价格动量ROC向下突破(Period:${crSellMomPeriod}, Thresh:${crSellMomThreshold}%)`,
                              crSellVol && `历史波动率低于(Period:${crSellVolPeriod}, Thresh:${crSellVolThreshold})`,
                              crSellBeta && `弹性系数BETA低于(Period:${crSellBetaPeriod}, Thresh:${crSellBetaThreshold})`,
                              crStopLoss > 0 && `固定止损 ${crStopLoss}%`,
                              crTakeProfit > 0 && `固定止盈 ${crTakeProfit}%`,
                              crTrailingStop > 0 && `移动止损 ${crTrailingStop}%`
                            ].filter(Boolean).join(' 或 ') || '无限制条件（仅可通过风控或手动卖出）'}
                            】时卖出。
                          </div>
                          <div>
                            仓位管理：使用【{crPosMode === 'fixed_shares' ? `固定股数 ${crPosValue} 股` : crPosMode === 'fixed_pct' ? `单次交易使用总资金 ${crPosValue}%` : '凯利公式等比调仓'}】。
                          </div>
                        </div>
                      </div>
                    ) : model === 'MockAgent' ? (
                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1">
                          <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">快均线 (天)</span>
                          <input
                            type="number"
                            min="2"
                            max="50"
                            value={fastWindow}
                            onChange={(e) => {
                              setFastWindow(Number(e.target.value));
                              setPreset('custom');
                            }}
                            className="w-full px-3 py-2 rounded-xl border border-zinc-200 text-xs font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                          />
                        </div>
                        <div className="space-y-1">
                          <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">慢均线 (天)</span>
                          <input
                            type="number"
                            min="10"
                            max="200"
                            value={slowWindow}
                            onChange={(e) => {
                              setSlowWindow(Number(e.target.value));
                              setPreset('custom');
                            }}
                            className="w-full px-3 py-2 rounded-xl border border-zinc-200 text-xs font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">调仓间隔 (天)</span>
                        <input
                          type="number"
                          min="5"
                          max="250"
                          value={rebalanceInterval}
                          onChange={(e) => {
                            setRebalanceInterval(Number(e.target.value));
                            setPreset('custom');
                          }}
                          className="w-full px-3 py-2 rounded-xl border border-zinc-200 text-xs font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
                        />
                      </div>
                    )}
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
                                <LineChart data={chartData}>
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
                                    yAxisId="left"
                                    domain={['dataMin', 'dataMax']} 
                                    axisLine={false}
                                    tickLine={false}
                                    tick={{fontSize: 10, fill: '#a1a1aa'}}
                                    tickFormatter={(val) => `${(val/10000).toFixed(0)}w`}
                                    width={45}
                                  />
                                  {results.snapshots && results.snapshots.some((s: any) => s.close_price > 0) && (
                                    <YAxis 
                                      yAxisId="right"
                                      orientation="right"
                                      domain={['dataMin', 'dataMax']} 
                                      axisLine={false}
                                      tickLine={false}
                                      tick={{fontSize: 10, fill: '#a1a1aa'}}
                                      tickFormatter={(val) => `¥${val.toFixed(1)}`}
                                      width={40}
                                    />
                                  )}
                                  <Tooltip 
                                    contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)' }}
                                    formatter={(value: any, name: any) => {
                                      if (name === '资产总值') return [`¥${Number(value).toFixed(2)}`, name];
                                      if (name === '标的价格') return [`¥${Number(value).toFixed(2)}`, name];
                                      return [value, name];
                                    }}
                                    labelStyle={{ fontWeight: 'bold', color: '#18181b', marginBottom: '4px' }}
                                  />
                                  <Line 
                                    yAxisId="left"
                                    type="monotone" 
                                    dataKey="total_equity" 
                                    stroke="#4f46e5" 
                                    strokeWidth={2}
                                    dot={false}
                                    activeDot={{ r: 4, strokeWidth: 0 }}
                                    name="资产总值"
                                  />
                                  {results.snapshots && results.snapshots.some((s: any) => s.close_price > 0) && (
                                    <Line 
                                      yAxisId="right"
                                      type="monotone" 
                                      dataKey="close_price" 
                                      stroke="#e11d48"
                                      strokeWidth={1.5}
                                      strokeDasharray="3 3"
                                      activeDot={{ r: 4, strokeWidth: 0 }}
                                      name="标的价格"
                                      dot={(props: any) => {
                                        const { cx, cy, payload } = props;
                                        if (!payload || !payload.trades || payload.trades.length === 0) return <React.Fragment key={props.key || payload?.date}></React.Fragment>;
                                        const hasBuy = payload.trades.some((t: any) => t.action === 'BUY');
                                        const hasSell = payload.trades.some((t: any) => t.action === 'SELL');
                                        
                                        if (hasBuy && hasSell) {
                                          return (
                                            <g key={payload.date + '-bs'}>
                                              <circle cx={cx} cy={cy} r={6} fill="#fbbf24" stroke="#fff" strokeWidth={1.5} />
                                              <text x={cx} y={cy - 10} textAnchor="middle" fontSize={8} fontWeight="bold" fill="#d97706">B/S</text>
                                            </g>
                                          );
                                        } else if (hasBuy) {
                                          return (
                                            <g key={payload.date + '-b'}>
                                              <circle cx={cx} cy={cy} r={6} fill="#10b981" stroke="#fff" strokeWidth={1.5} />
                                              <text x={cx} y={cy - 10} textAnchor="middle" fontSize={8} fontWeight="bold" fill="#059669">买</text>
                                            </g>
                                          );
                                        } else if (hasSell) {
                                          return (
                                            <g key={payload.date + '-s'}>
                                              <circle cx={cx} cy={cy} r={6} fill="#ef4444" stroke="#fff" strokeWidth={1.5} />
                                              <text x={cx} y={cy - 10} textAnchor="middle" fontSize={8} fontWeight="bold" fill="#dc2626">卖</text>
                                            </g>
                                          );
                                        }
                                        return <React.Fragment key={props.key || payload?.date}></React.Fragment>;
                                      }}
                                    />
                                  )}
                                  <Brush 
                                    dataKey="date" 
                                    height={20} 
                                    stroke="#e4e4e7"
                                    fill="#ffffff"
                                    tickFormatter={(val) => val.substring(5)}
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
                                  <th className="pb-3">指标名称 (Indicator)</th>
                                  <th className="pb-3 text-right">指标数值 (Value)</th>
                                </tr>
                              </thead>
                              <tbody className="text-sm font-medium">
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">日均收益率 (Mean Daily Return)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatPct(results.metrics?.mean?.risk)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">日收益波动率 (Daily Volatility Std)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatPct(results.metrics?.std?.risk)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">年化收益率 (Annualized Return)</td>
                                  <td className="py-3 text-right text-emerald-600">{formatPct(results.metrics?.annualized_return?.risk)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">夏普比率 (Sharpe Ratio)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatNum(results.metrics?.sharpe_ratio)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">最大回撤 (Max Drawdown)</td>
                                  <td className="py-3 text-right text-rose-600">{formatPct(results.metrics?.max_drawdown?.risk)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">阿尔法超额收益 (Jensen's Alpha)</td>
                                  <td className="py-3 text-right text-emerald-600">{formatPct(results.metrics?.alpha)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">贝塔系数 (Beta Coefficient)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatNum(results.metrics?.beta)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">特雷诺比率 (Treynor Ratio)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatNum(results.metrics?.treynor_ratio)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">信息比率 (Information Ratio)</td>
                                  <td className="py-3 text-right text-indigo-600">{formatNum(results.metrics?.information_ratio)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">卡玛比率 (Calmar Ratio)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatNum(results.metrics?.calmar_ratio)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">索提诺比率 (Sortino Ratio)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatNum(results.metrics?.sortino_ratio)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">获利因子 (Profit Factor)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatNum(results.metrics?.profit_factor)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">盈亏比 (Profit-Loss Ratio)</td>
                                  <td className="py-3 text-right text-zinc-900">{formatNum(results.metrics?.profit_loss_ratio)}</td>
                                </tr>
                                <tr className="border-b border-zinc-50">
                                  <td className="py-3 text-zinc-600">最大连续亏损次数 (Max Consecutive Loss)</td>
                                  <td className="py-3 text-right text-zinc-900">{results.metrics?.max_consecutive_loss !== undefined ? results.metrics.max_consecutive_loss : '--'}</td>
                                </tr>
                                <tr>
                                  <td className="py-3 text-zinc-600">平均持仓天数 (Average Holding Days)</td>
                                  <td className="py-3 text-right text-zinc-900">
                                    {results.metrics?.avg_holding_days !== undefined ? `${results.metrics.avg_holding_days.toFixed(1)} 天` : '--'}
                                  </td>
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
                      <button
                        onClick={handleConvertToMock}
                        disabled={isConverting}
                        className="shrink-0 px-4 py-2 bg-indigo-600 text-white text-xs font-bold rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-60"
                      >
                        {isConverting ? '转换中...' : '一键转模拟盘'}
                      </button>
                    </div>
                    {convertMsg && (
                      <div className={cn(
                        "p-3 rounded-xl text-xs font-medium",
                        convertMsg.startsWith('✅') ? "bg-emerald-50 text-emerald-700 border border-emerald-100" : "bg-rose-50 text-rose-700 border border-rose-100"
                      )}>
                        {convertMsg}
                      </div>
                    )}
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
