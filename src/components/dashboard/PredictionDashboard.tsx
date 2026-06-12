import React, { useState, useEffect } from 'react';
import { Target, TrendingUp, CheckCircle, XCircle, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';

interface Prediction {
  prediction_id: string;
  job_id: string;
  symbol: string;
  market: string;
  target_price: number;
  time_horizon: string;
  status: string;
  current_price_at_prediction: number;
  actual_price_at_horizon: number | null;
  accuracy_score: number | null;
  created_at: string;
}

export const PredictionDashboard = ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) => {
  const { t } = useTranslation();
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isOpen) {
      fetchPredictions();
    }
  }, [isOpen]);

  const fetchPredictions = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/predictions/');
      const data = await res.json();
      setPredictions(data);
    } catch (e) {
      console.error('Failed to fetch predictions:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleEvaluate = async (pred: Prediction) => {
    const actualPrice = prompt(`Enter actual/current price for ${pred.symbol} to evaluate target price ${pred.target_price}:`);
    if (!actualPrice) return;
    
    try {
      await fetch(`/api/predictions/${pred.prediction_id}/evaluate?actual_price=${actualPrice}`, {
        method: 'POST'
      });
      fetchPredictions();
    } catch (e) {
      console.error(e);
    }
  };

  if (!isOpen) return null;

  const evaluated = predictions.filter(p => p.status === 'evaluated');
  const avgScore = evaluated.length > 0 
    ? evaluated.reduce((acc, p) => acc + (p.accuracy_score || 0), 0) / evaluated.length 
    : 0;

  const chartData = evaluated.map(p => ({
    symbol: p.symbol,
    score: p.accuracy_score || 0
  }));

  return (
    <div className="fixed inset-0 z-[100] bg-zinc-950/40 backdrop-blur-sm flex items-center justify-center p-4 sm:p-6">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-zinc-100">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-indigo-50 text-indigo-600 rounded-xl">
              <Target size={24} />
            </div>
            <div>
              <h2 className="text-xl font-bold text-zinc-900">AI 预测准确率跟踪</h2>
              <p className="text-sm font-medium text-zinc-500">Prediction Accuracy Dashboard</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100 rounded-xl transition-colors">
            <X size={24} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-zinc-50/50">
          
          <div className="grid grid-cols-3 gap-6">
            <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm flex items-center gap-4">
              <div className="p-3 bg-blue-50 text-blue-600 rounded-xl"><Target size={24} /></div>
              <div>
                <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">总预测次数</p>
                <p className="text-2xl font-black text-zinc-900">{predictions.length}</p>
              </div>
            </div>
            <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm flex items-center gap-4">
              <div className="p-3 bg-emerald-50 text-emerald-600 rounded-xl"><CheckCircle size={24} /></div>
              <div>
                <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">已评估</p>
                <p className="text-2xl font-black text-zinc-900">{evaluated.length}</p>
              </div>
            </div>
            <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm flex items-center gap-4">
              <div className="p-3 bg-violet-50 text-violet-600 rounded-xl"><TrendingUp size={24} /></div>
              <div>
                <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">平均准确率分数</p>
                <p className="text-2xl font-black text-zinc-900">{avgScore.toFixed(1)} / 100</p>
              </div>
            </div>
          </div>

          <div className="bg-white p-6 rounded-2xl border border-zinc-100 shadow-sm">
            <h3 className="text-sm font-bold text-zinc-900 mb-4">准确率分布</h3>
            <div className="h-48">
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f4f4f5" />
                    <XAxis dataKey="symbol" tick={{fontSize: 10}} axisLine={false} tickLine={false} />
                    <YAxis domain={[0, 100]} tick={{fontSize: 10}} axisLine={false} tickLine={false} />
                    <Tooltip cursor={{fill: '#f4f4f5'}} contentStyle={{borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'}} />
                    <Bar dataKey="score" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-zinc-400 text-sm">暂无评估数据</div>
              )}
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-zinc-100 shadow-sm overflow-hidden">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-zinc-50/80 border-b border-zinc-100 text-zinc-500">
                <tr>
                  <th className="px-6 py-4 font-bold text-xs uppercase">Symbol</th>
                  <th className="px-6 py-4 font-bold text-xs uppercase">Date</th>
                  <th className="px-6 py-4 font-bold text-xs uppercase text-right">Initial Price</th>
                  <th className="px-6 py-4 font-bold text-xs uppercase text-right">Target Price</th>
                  <th className="px-6 py-4 font-bold text-xs uppercase text-right">Actual Price</th>
                  <th className="px-6 py-4 font-bold text-xs uppercase text-center">Score</th>
                  <th className="px-6 py-4 font-bold text-xs uppercase text-center">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-50">
                {loading ? (
                  <tr><td colSpan={7} className="text-center py-8 text-zinc-400">Loading...</td></tr>
                ) : predictions.length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-8 text-zinc-400">No predictions found.</td></tr>
                ) : (
                  predictions.map(p => (
                    <tr key={p.prediction_id} className="hover:bg-zinc-50/50 transition-colors">
                      <td className="px-6 py-4 font-bold text-zinc-900">{p.symbol}</td>
                      <td className="px-6 py-4 text-zinc-500">{new Date(p.created_at).toLocaleDateString()}</td>
                      <td className="px-6 py-4 text-right text-zinc-600 font-medium">{p.current_price_at_prediction.toFixed(2)}</td>
                      <td className="px-6 py-4 text-right font-bold text-indigo-600">{p.target_price.toFixed(2)}</td>
                      <td className="px-6 py-4 text-right font-medium">
                        {p.actual_price_at_horizon !== null ? p.actual_price_at_horizon.toFixed(2) : '-'}
                      </td>
                      <td className="px-6 py-4 text-center">
                        {p.status === 'evaluated' ? (
                          <span className={`inline-flex px-2 py-1 rounded-lg text-xs font-bold ${
                            p.accuracy_score && p.accuracy_score >= 80 ? 'bg-emerald-100 text-emerald-700' :
                            p.accuracy_score && p.accuracy_score >= 50 ? 'bg-yellow-100 text-yellow-700' :
                            'bg-red-100 text-red-700'
                          }`}>
                            {p.accuracy_score?.toFixed(0)}
                          </span>
                        ) : (
                          <span className="text-zinc-400 text-xs">Pending</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-center">
                        {p.status === 'pending' && (
                          <button onClick={() => handleEvaluate(p)} className="text-xs font-bold text-indigo-600 hover:text-indigo-700">
                            Evaluate
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

        </div>
      </div>
    </div>
  );
};
