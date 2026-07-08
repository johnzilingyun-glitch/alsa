import React, { useState, useEffect } from 'react';
import { Target, TrendingUp, CheckCircle, XCircle, X, RefreshCw, BarChart3 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell, PieChart, Pie } from 'recharts';
import { useUIStore } from '../../stores/useUIStore';
import { cn } from '../analysis/utils';

interface Prediction {
  prediction_id: string;
  job_id: string;
  symbol: string;
  market: string;
  target_price: number;
  stop_loss: number | null;
  time_horizon: string;
  status: string;
  current_price_at_prediction: number;
  actual_price_at_horizon: number | null;
  accuracy_score: number | null;
  highest_price_reached: number | null;
  lowest_price_reached: number | null;
  created_at: string;
}

export const PredictionDashboard = ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) => {
  const { t } = useTranslation();
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [realtimePrices, setRealtimePrices] = useState<Record<string, number>>({});
  const [stockNames, setStockNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchPredictions();
    }
  }, [isOpen]);

  const fetchPredictions = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/predictions/');
      if (!res.ok) {
        setPredictions([]);
        return;
      }
      const data = await res.json();
      const preds = Array.isArray(data) ? data : [];
      setPredictions(preds);
      
      // Fetch realtime quotes for ALL predictions to get their names and prices
      const allSymbols = [...new Set(preds.map(p => p.symbol))];
      
      if (allSymbols.length > 0) {
        const quotesRes = await fetch(`/api/market/quotes?symbols=${allSymbols.join(',')}`);
        if (quotesRes.ok) {
          const quotesData = await quotesRes.json();
          if (quotesData.success && Array.isArray(quotesData.data)) {
            const prices: Record<string, number> = {};
            const names: Record<string, string> = {};
            for (const q of quotesData.data) {
              const quote = q as Record<string, unknown>;
              if (typeof quote.price === 'number') prices[String(quote.symbol ?? '')] = quote.price;
              if (typeof quote.name === 'string') names[String(quote.symbol ?? '')] = quote.name;
            }
            setRealtimePrices(prices);
            setStockNames(names);
          }
        }
      }
    } catch (e) {
      console.error('Failed to fetch predictions:', e);
      setPredictions([]);
    } finally {
      setLoading(false);
    }
  };

  const showToast = useUIStore(s => s.showToast);

  const handleEvaluate = async (pred: Prediction) => {
    try {
      const res = await fetch(`/api/predictions/${pred.prediction_id}/evaluate`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        showToast(body?.detail || '评估失败，请稍后重试', 'error');
        return;
      }
      showToast(`${pred.symbol} 评估完成`, 'success');
      fetchPredictions();
    } catch (e) {
      console.error(e);
      showToast('评估请求失败，请检查网络连接', 'error');
    }
  };

  const handleReset = async (pred: Prediction) => {
    try {
      const res = await fetch(`/api/predictions/${pred.prediction_id}/reset`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        showToast(body?.detail || '重置失败，请稍后重试', 'error');
        return;
      }
      showToast(`${pred.symbol} 已恢复跟踪`, 'success');
      fetchPredictions();
    } catch (e) {
      console.error(e);
      showToast('重置请求失败，请检查网络连接', 'error');
    }
  };

  const handleAutoEvaluateAll = async () => {
    try {
      setEvaluating(true);
      const res = await fetch('/api/predictions/auto_evaluate', { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        showToast(body?.detail || '自动评估失败，请稍后重试', 'error');
        return;
      }
      const data = await res.json();
      showToast(`已评估 ${data.evaluated ?? 0} 条预测`, 'success');
      await fetchPredictions();
    } catch (e) {
      console.error(e);
      showToast('自动评估请求失败，请检查网络连接', 'error');
    } finally {
      setEvaluating(false);
    }
  };

  if (!isOpen) return null;

  const evaluated = predictions.filter(p => p.status === 'evaluated');
  const winCount = evaluated.filter(p => (p.accuracy_score || 0) >= 50).length; // simple threshold
  const winRate = evaluated.length > 0 ? (winCount / evaluated.length) * 100 : 0;
  
  const avgScore = evaluated.length > 0 
    ? evaluated.reduce((acc, p) => acc + (p.accuracy_score || 0), 0) / evaluated.length 
    : 0;

  // Calculate Avg Return
  let totalReturn = 0;
  evaluated.forEach(p => {
     if (p.actual_price_at_horizon) {
       totalReturn += (p.actual_price_at_horizon - p.current_price_at_prediction) / p.current_price_at_prediction;
     }
  });
  const avgReturn = evaluated.length > 0 ? (totalReturn / evaluated.length) * 100 : 0;

  const chartData = evaluated.map(p => ({
    symbol: p.symbol,
    name: stockNames[p.symbol] || p.symbol,
    score: p.accuracy_score || 0,
    return: p.actual_price_at_horizon ? ((p.actual_price_at_horizon - p.current_price_at_prediction) / p.current_price_at_prediction) * 100 : 0
  }));

  const pieData = [
    { name: '胜 (Win)', value: winCount, color: '#10b981' },
    { name: '负 (Loss)', value: evaluated.length - winCount, color: '#f43f5e' }
  ];

  const renderProgress = (pred: Prediction, currentPrice: number) => {
    const isShort = pred.target_price < pred.current_price_at_prediction;
    const start = pred.current_price_at_prediction;
    const end = pred.target_price;
    const totalDiff = Math.abs(end - start);
    if (totalDiff === 0) return null;
    
    let progress = 0;
    if (isShort) {
       progress = start - currentPrice > 0 ? ((start - currentPrice) / totalDiff) * 100 : 0;
    } else {
       progress = currentPrice - start > 0 ? ((currentPrice - start) / totalDiff) * 100 : 0;
    }
    progress = Math.min(Math.max(progress, 0), 100);

    return (
      <div className="w-full max-w-[120px] flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-zinc-100 rounded-full overflow-hidden">
          <div 
            className={cn("h-full rounded-full transition-all", isShort ? "bg-rose-500" : "bg-emerald-500")}
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-[10px] text-zinc-500 font-mono w-6 text-right">{progress.toFixed(0)}%</span>
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-[100] bg-zinc-950/40 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-6xl h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-zinc-100">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-xl">
              <Target size={24} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-zinc-900">AI 预测准确率跟踪</h2>
              <p className="text-sm font-medium text-zinc-500">AI Prediction & Analyst Tracker</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button 
              onClick={handleAutoEvaluateAll}
              disabled={evaluating}
              className="flex items-center gap-2 px-4 py-2 bg-zinc-900 text-white text-sm font-bold rounded-xl hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={16} className={evaluating ? "animate-spin" : ""} />
              自动评估 (Auto Evaluate)
            </button>
            <button onClick={onClose} className="p-2 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 rounded-xl transition-colors">
              <X size={24} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-zinc-50/50">
          
          <div className="mb-2">
            <h3 className="text-lg font-bold text-zinc-900 flex items-center gap-2">
               <BarChart3 size={20} className="text-indigo-600" />
               统计数据看板 (DataBoard)
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm flex items-center gap-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-xl"><Target size={24} /></div>
              <div>
                <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">总预测次数 (Total)</p>
                <p className="text-2xl font-black text-zinc-900">{predictions.length}</p>
              </div>
            </div>
            <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm flex items-center gap-4">
              <div className="p-3 bg-emerald-50 text-emerald-600 rounded-xl"><CheckCircle size={24} /></div>
              <div>
                <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">胜率 (Win Rate)</p>
                <div className="flex items-end gap-2">
                   <p className="text-2xl font-black text-zinc-900">{winRate.toFixed(1)}%</p>
                   <p className="text-xs font-medium text-zinc-400 mb-1">({winCount}/{evaluated.length})</p>
                </div>
              </div>
            </div>
            <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm flex items-center gap-4">
              <div className="p-3 bg-rose-50 text-rose-600 rounded-xl"><TrendingUp size={24} /></div>
              <div>
                <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">平均回报率 (Avg Return)</p>
                <p className={cn("text-2xl font-black", avgReturn >= 0 ? "text-emerald-600" : "text-rose-600")}>
                  {avgReturn > 0 ? '+' : ''}{avgReturn.toFixed(2)}%
                </p>
              </div>
            </div>
            <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm flex items-center gap-4">
              <div className="p-3 bg-violet-50 text-violet-600 rounded-xl"><BarChart3 size={24} /></div>
              <div>
                <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">综合评分 (Accuracy Score)</p>
                <p className="text-2xl font-black text-zinc-900">{avgScore.toFixed(1)} <span className="text-sm font-medium text-zinc-400">/ 100</span></p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-zinc-100 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm whitespace-nowrap">
                <thead className="bg-zinc-50/80 border-b border-zinc-100 text-zinc-500">
                  <tr>
                    <th className="px-6 py-4 font-bold text-xs uppercase">Symbol</th>
                    <th className="px-6 py-4 font-bold text-xs uppercase">Date</th>
                    <th className="px-6 py-4 font-bold text-xs uppercase text-right">Initial Price</th>
                    <th className="px-6 py-4 font-bold text-xs uppercase text-right">Current / Actual</th>
                    <th className="px-6 py-4 font-bold text-xs uppercase text-right">Target Price</th>
                    <th className="px-6 py-4 font-bold text-xs uppercase">Return %</th>
                    <th className="px-6 py-4 font-bold text-xs uppercase">Progress</th>
                    <th className="px-6 py-4 font-bold text-xs uppercase text-center">Score</th>
                    <th className="px-6 py-4 font-bold text-xs uppercase text-center">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-50">
                  {loading ? (
                    <tr><td colSpan={9} className="text-center py-8 text-zinc-400">Loading tracking data...</td></tr>
                  ) : predictions.length === 0 ? (
                    <tr><td colSpan={9} className="text-center py-8 text-zinc-400">No predictions found.</td></tr>
                  ) : (
                    predictions.map(p => {
                      const isEvaluated = p.status === 'evaluated';
                      const activePrice = isEvaluated ? p.actual_price_at_horizon : realtimePrices[p.symbol];
                      const returnPct = activePrice ? ((activePrice - p.current_price_at_prediction) / p.current_price_at_prediction) * 100 : null;
                      
                      return (
                        <tr key={p.prediction_id} className="hover:bg-zinc-50/50 transition-colors">
                          <td className="px-6 py-4 font-bold text-zinc-900 flex flex-col justify-center">
                             <div className="flex items-center gap-2">
                               {p.symbol}
                               {!isEvaluated && <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" title="Tracking Live" />}
                             </div>
                             {stockNames[p.symbol] && (
                               <span className="text-[10px] text-zinc-400 font-medium">{stockNames[p.symbol]}</span>
                             )}
                          </td>
                          <td className="px-6 py-4 text-zinc-500 text-xs">{new Date(p.created_at).toLocaleDateString()}</td>
                          <td className="px-6 py-4 text-right text-zinc-600 font-medium">{p.current_price_at_prediction.toFixed(2)}</td>
                          <td className="px-6 py-4 text-right font-bold text-zinc-900">
                            {activePrice ? activePrice.toFixed(2) : '-'}
                          </td>
                          <td className="px-6 py-4 text-right font-bold text-indigo-600">
                            {p.target_price.toFixed(2)}
                            {p.stop_loss && <div className="text-[10px] text-zinc-400 font-normal">SL: {p.stop_loss.toFixed(2)}</div>}
                          </td>
                          <td className="px-6 py-4">
                            {returnPct !== null ? (
                              <span className={cn("font-bold text-xs", returnPct >= 0 ? "text-emerald-600" : "text-rose-600")}>
                                {returnPct > 0 ? '+' : ''}{returnPct.toFixed(2)}%
                              </span>
                            ) : '-'}
                          </td>
                          <td className="px-6 py-4">
                             {activePrice ? renderProgress(p, activePrice) : '-'}
                          </td>
                          <td className="px-6 py-4 text-center">
                            {isEvaluated ? (
                              <span className={`inline-flex px-2 py-1 rounded-lg text-xs font-bold ${
                                p.accuracy_score && p.accuracy_score >= 80 ? 'bg-emerald-100 text-emerald-700' :
                                p.accuracy_score && p.accuracy_score >= 50 ? 'bg-yellow-100 text-yellow-700' :
                                'bg-rose-100 text-rose-700'
                              }`}>
                                {p.accuracy_score?.toFixed(0)}
                              </span>
                            ) : (
                              <span className="text-zinc-400 text-xs px-2 py-1 bg-zinc-100 rounded-lg">Pending</span>
                            )}
                          </td>
                          <td className="px-6 py-4 text-center">
                            {isEvaluated ? (
                              <button onClick={() => handleReset(p)} className="text-xs font-bold text-amber-600 hover:text-amber-700 bg-amber-50 px-3 py-1.5 rounded-lg hover:bg-amber-100 transition-colors">
                                Reset
                              </button>
                            ) : (
                              <button onClick={() => handleEvaluate(p)} className="text-xs font-bold text-indigo-600 hover:text-indigo-700 bg-indigo-50 px-3 py-1.5 rounded-lg hover:bg-indigo-100 transition-colors">
                                Evaluate
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
          
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm lg:col-span-2">
              <h3 className="text-sm font-bold text-zinc-900 mb-4">准确率分布 (Accuracy Distribution)</h3>
              <div className="h-48">
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f4f4f5" />
                      <XAxis dataKey="name" tick={{fontSize: 10}} axisLine={false} tickLine={false} />
                      <YAxis domain={[0, 100]} tick={{fontSize: 10}} axisLine={false} tickLine={false} />
                      <Tooltip cursor={{fill: '#f4f4f5'}} contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'}} />
                      <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                        {chartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.score >= 50 ? '#10b981' : '#f43f5e'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-zinc-400 text-sm">暂无评估数据</div>
                )}
              </div>
            </div>

            <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm">
              <h3 className="text-sm font-bold text-zinc-900 mb-4">胜负比例 (Win/Loss Ratio)</h3>
              <div className="h-48">
                {evaluated.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={pieData}
                        cx="50%"
                        cy="50%"
                        innerRadius={40}
                        outerRadius={70}
                        paddingAngle={5}
                        dataKey="value"
                      >
                        {pieData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'}} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-full flex items-center justify-center text-zinc-400 text-sm">暂无评估数据</div>
                )}
              </div>
              <div className="flex justify-center gap-4 mt-2">
                 <div className="flex items-center gap-1.5 text-xs text-zinc-600"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500"/>胜 {winCount}</div>
                 <div className="flex items-center gap-1.5 text-xs text-zinc-600"><span className="w-2.5 h-2.5 rounded-full bg-rose-500"/>负 {evaluated.length - winCount}</div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};
