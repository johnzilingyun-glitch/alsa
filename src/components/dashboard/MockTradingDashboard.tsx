import { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, RefreshCw, TrendingUp, DollarSign, BarChart3, Wallet, Plus, Trash2, Activity, AlertTriangle, Clock, Combine } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { useUIStore } from '../../stores/useUIStore';
import {
  listMockAccounts, createMockAccount, deleteMockAccount,
  getPortfolio, getPortfolioWithPrices, listTrades, listSnapshots, listAnomalies,
  type MockAccount, type PortfolioSummary, type MockTrade, type Snapshot, type AnomalyEntry
} from '../../services/api/mockTradingClient';
import { getQuotes } from '../../services/api/stockClient';
import { TradeTicketModal } from './TradeTicketModal';
import { AccountMergeModal } from './AccountMergeModal';

type TabId = 'portfolio' | 'trades' | 'anomalies';

const MARKET_OPTIONS = [
  { value: 'A-Share', label: 'A股 · CNY', currency: 'CNY', default: 1000000 },
  { value: 'HK-Share', label: '港股 · HKD', currency: 'HKD', default: 2000000 },
  { value: 'US-Share', label: '美股 · USD', currency: 'USD', default: 1000000 },
  { value: 'Global', label: '全球组合 · CNY', currency: 'CNY', default: 1000000 },
];

const PIE_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6', '#06b6d4', '#ec4899'];

export function MockTradingDashboard() {
  const { setShowMockTradingDashboard } = useUIStore();
  const [accounts, setAccounts] = useState<MockAccount[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<MockAccount | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [trades, setTrades] = useState<MockTrade[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyEntry[]>([]);
  const [activeTab, setActiveTab] = useState<TabId>('portfolio');
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showTradeTicket, setShowTradeTicket] = useState(false);
  const [showMerge, setShowMerge] = useState(false);
  const [newName, setNewName] = useState('');
  const [newMarket, setNewMarket] = useState('Global');
  const [newInitialBalance, setNewInitialBalance] = useState<string>('');

  const loadAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const accs = await listMockAccounts();
      setAccounts(accs);
      if (accs.length > 0 && !selectedAccount) {
        setSelectedAccount(accs[0]);
      }
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  const loadAccountData = useCallback(async (acc: MockAccount) => {
    try {
      // Fetch initial portfolio to get symbols
      let pf = await getPortfolio(acc.account_id).catch(() => null);
      if (pf && pf.positions.length > 0) {
        // Fetch live quotes
        const symbols = pf.positions.map(p => p.symbol);
        const quotes = await getQuotes(symbols).catch(() => []);
        const priceMap: Record<string, number> = {};
        quotes.forEach(q => { priceMap[q.symbol] = q.price; });
        
        // Fetch updated portfolio with live prices
        pf = await getPortfolioWithPrices(acc.account_id, priceMap).catch(() => pf);
      }

      const [tr, sn, an] = await Promise.all([
        listTrades(acc.account_id).catch(() => []),
        listSnapshots(acc.account_id).catch(() => []),
        listAnomalies(acc.account_id).catch(() => []),
      ]);
      setPortfolio(pf);
      setTrades(tr);
      setSnapshots(sn);
      setAnomalies(an);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  useEffect(() => {
    if (selectedAccount) loadAccountData(selectedAccount);
  }, [selectedAccount, loadAccountData]);

  // 3-minute polling for live prices
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (selectedAccount && portfolio && portfolio.positions.length > 0) {
      interval = setInterval(async () => {
        try {
          const symbols = portfolio.positions.map(p => p.symbol);
          const quotes = await getQuotes(symbols);
          const priceMap: Record<string, number> = {};
          quotes.forEach(q => {
            if (q.price) priceMap[q.symbol] = q.price;
          });
          const updatedPf = await getPortfolioWithPrices(selectedAccount.account_id, priceMap);
          setPortfolio(updatedPf);
        } catch (e) {
          console.error("Failed to update live prices:", e);
        }
      }, 3 * 60 * 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [selectedAccount, portfolio]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const initBal = newInitialBalance ? Number(newInitialBalance) : undefined;
      await createMockAccount(newName.trim(), newMarket, initBal);
      setShowCreate(false);
      setNewName('');
      setNewInitialBalance('');
      await loadAccounts();
    } catch (e) { console.error(e); }
  };

  const handleDelete = async (accId: string) => {
    try {
      await deleteMockAccount(accId);
      if (selectedAccount?.account_id === accId) setSelectedAccount(null);
      await loadAccounts();
    } catch (e) { console.error(e); }
  };

  const fmt = (val: number, currency = 'CNY') => new Intl.NumberFormat('zh-CN', { style: 'currency', currency, minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(val);
  const fmtPnL = (val: number, currency = 'CNY') => (val >= 0 ? '+' : '') + fmt(val, currency);

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'portfolio', label: '持仓组合', icon: <Wallet size={16} /> },
    { id: 'trades', label: '交易记录', icon: <BarChart3 size={16} /> },
    { id: 'anomalies', label: '异常日志', icon: <AlertTriangle size={16} /> },
  ];

  const currency = selectedAccount?.currency || 'CNY';

  return (
    <div className="fixed inset-0 z-50 bg-white overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/95 backdrop-blur-sm border-b border-zinc-200">
        <div className="max-w-7xl mx-auto px-4 md:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => setShowMockTradingDashboard(false)} className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-zinc-100 transition-colors">
              <ArrowLeft size={20} />
            </button>
            <div>
              <h1 className="text-xl font-bold text-zinc-900">AI 模拟交易看板</h1>
              <p className="text-xs text-zinc-500">Paper Trading Dashboard · {accounts.length} 个账号</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {accounts.length > 1 && (
              <button onClick={() => setShowMerge(true)} className="h-10 px-4 border border-zinc-200 text-zinc-700 text-sm font-medium rounded-xl hover:bg-zinc-50 transition-colors flex items-center gap-2">
                <Combine size={16} /> 合并账号
              </button>
            )}
            <button onClick={() => setShowCreate(true)} className="h-10 px-4 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 transition-colors flex items-center gap-2">
                <Plus size={16} /> 新建账号
            </button>
            <button onClick={loadAccounts} disabled={loading} className="h-10 px-4 border border-zinc-200 text-sm font-medium rounded-xl hover:bg-zinc-50 transition-colors flex items-center gap-2 disabled:opacity-50">
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 md:px-8 py-6">
        {/* Account Selector */}
        {accounts.length > 0 && (
          <div className="flex gap-3 mb-6 overflow-x-auto pb-2 custom-scrollbar">
            {accounts.map(acc => (
              <button
                key={acc.account_id}
                onClick={() => setSelectedAccount(acc)}
                className={`flex-shrink-0 px-5 py-3 rounded-2xl border transition-all text-left ${
                  selectedAccount?.account_id === acc.account_id
                    ? 'bg-indigo-50 border-indigo-200 shadow-sm'
                    : 'bg-white border-zinc-100 hover:border-zinc-200'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div>
                    <p className="font-bold text-sm text-zinc-900">{acc.name}</p>
                    <p className="text-[10px] text-zinc-400 font-mono uppercase tracking-widest">
                      {acc.market} · {acc.currency}
                    </p>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(acc.account_id); }}
                    className="opacity-0 group-hover:opacity-100 w-7 h-7 flex items-center justify-center rounded-lg hover:bg-rose-50 text-zinc-300 hover:text-rose-500 transition-all"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Summary Cards */}
        {selectedAccount && portfolio && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <SummaryCard icon={<Wallet size={20} />} label="总资产" value={fmt(portfolio.total_equity, currency)} color="indigo" />
              <SummaryCard icon={<DollarSign size={20} />} label="可用资金" value={fmt(portfolio.current_cash, currency)} color="zinc" />
              <SummaryCard
                icon={<TrendingUp size={20} />}
                label="累计盈亏"
                value={fmtPnL(portfolio.total_pnl, currency)}
                subtitle={`${portfolio.total_pnl_pct >= 0 ? '+' : ''}${portfolio.total_pnl_pct.toFixed(2)}%`}
                color={portfolio.total_pnl >= 0 ? 'emerald' : 'rose'}
              />
              <SummaryCard icon={<BarChart3 size={20} />} label="持仓数" value={`${portfolio.positions.length} 只`} color="zinc" />
            </div>

            {/* Tabs & Manual Trade */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center bg-zinc-100 rounded-xl p-1 w-fit">
                {tabs.map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1.5 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                      activeTab === tab.id ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'
                    }`}
                  >
                    {tab.icon}{tab.label}
                    {tab.id === 'anomalies' && anomalies.length > 0 && (
                      <span className="ml-1 w-5 h-5 flex items-center justify-center text-[10px] font-bold bg-rose-500 text-white rounded-full">{anomalies.length}</span>
                    )}
                  </button>
                ))}
              </div>
              
              <button 
                onClick={() => setShowTradeTicket(true)}
                className="h-10 px-4 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-bold rounded-xl transition-colors shadow-sm shadow-emerald-500/20"
              >
                手动买卖
              </button>
            </div>

            {/* Portfolio Tab */}
            {activeTab === 'portfolio' && (
              <div className="space-y-6">
                {/* Equity Curve */}
                {snapshots.length > 1 && (
                  <div className="p-6 bg-white border border-zinc-200 rounded-2xl">
                    <h3 className="text-lg font-bold text-zinc-900 mb-4">资产曲线</h3>
                    <ResponsiveContainer width="100%" height={280}>
                      <LineChart data={snapshots}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="snapshot_date" tick={{ fontSize: 11 }} />
                        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => fmt(v, currency)} />
                        <Tooltip formatter={(v: any) => [fmt(Number(v), currency), '总资产']} contentStyle={{ borderRadius: '12px', border: '1px solid #e4e4e7' }} />
                        <Line type="monotone" dataKey="total_equity" stroke="#6366f1" strokeWidth={2.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {/* Portfolio Allocation Pie + Position Table */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  {portfolio.positions.length > 0 && (
                    <div className="p-6 bg-white border border-zinc-200 rounded-2xl">
                      <h3 className="text-sm font-bold text-zinc-900 mb-4">仓位分布</h3>
                      <ResponsiveContainer width="100%" height={220}>
                        <PieChart>
                          <Pie
                            data={[
                              { name: '现金', value: portfolio.current_cash },
                              ...portfolio.positions.map(p => ({ name: p.symbol, value: p.market_value || p.shares * p.average_cost })),
                            ]}
                            cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3} dataKey="value"
                            label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                          >
                            {[portfolio.current_cash, ...portfolio.positions.map(p => p.market_value || 0)].map((_, i) => (
                              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip formatter={(v: any) => [fmt(Number(v), currency), '']} />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}

                  <div className={`p-6 bg-white border border-zinc-200 rounded-2xl ${portfolio.positions.length > 0 ? 'lg:col-span-2' : 'lg:col-span-3'}`}>
                    <h3 className="text-sm font-bold text-zinc-900 mb-4">持仓明细</h3>
                    {portfolio.positions.length === 0 ? (
                      <div className="text-center py-12 text-zinc-400">
                        <Activity size={48} className="mx-auto opacity-10 mb-4" />
                        <p className="text-sm">暂无持仓 · 当AI信号触发时将自动建仓</p>
                      </div>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-zinc-100 text-zinc-500">
                              <th className="text-left py-3 px-2 font-medium">股票</th>
                              <th className="text-right py-3 px-2 font-medium">持仓</th>
                              <th className="text-right py-3 px-2 font-medium">成本</th>
                              <th className="text-right py-3 px-2 font-medium">市值</th>
                              <th className="text-right py-3 px-2 font-medium">盈亏</th>
                              <th className="text-right py-3 px-2 font-medium">收益率</th>
                            </tr>
                          </thead>
                          <tbody>
                            {portfolio.positions.map(pos => (
                              <tr key={pos.symbol} className="border-b border-zinc-50 hover:bg-zinc-50 transition-colors">
                                <td className="py-3 px-2 font-semibold text-zinc-900">{pos.symbol}</td>
                                <td className="text-right py-3 px-2 text-zinc-700">{pos.shares}</td>
                                <td className="text-right py-3 px-2 text-zinc-700">{pos.average_cost.toFixed(2)}</td>
                                <td className="text-right py-3 px-2 text-zinc-700">{fmt(pos.market_value || pos.shares * pos.average_cost, currency)}</td>
                                <td className={`text-right py-3 px-2 font-medium ${(pos.unrealized_pnl || 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                  {fmtPnL(pos.unrealized_pnl || 0, currency)}
                                </td>
                                <td className={`text-right py-3 px-2 font-medium ${(pos.unrealized_pnl_pct || 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                  {(pos.unrealized_pnl_pct || 0) >= 0 ? '+' : ''}{(pos.unrealized_pnl_pct || 0).toFixed(2)}%
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Trades Tab */}
            {activeTab === 'trades' && (
              <div className="p-6 bg-white border border-zinc-200 rounded-2xl">
                <h3 className="text-lg font-bold text-zinc-900 mb-4">交易记录</h3>
                {trades.length === 0 ? (
                  <div className="text-center py-16 text-zinc-400">
                    <Clock size={48} className="mx-auto opacity-10 mb-4" />
                    <p className="text-sm">暂无交易记录</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-zinc-100 text-zinc-500">
                          <th className="text-left py-3 px-2 font-medium">时间</th>
                          <th className="text-left py-3 px-2 font-medium">股票</th>
                          <th className="text-center py-3 px-2 font-medium">方向</th>
                          <th className="text-right py-3 px-2 font-medium">数量</th>
                          <th className="text-right py-3 px-2 font-medium">价格</th>
                          <th className="text-right py-3 px-2 font-medium">实现盈亏</th>
                          <th className="text-center py-3 px-2 font-medium">触发源</th>
                        </tr>
                      </thead>
                      <tbody>
                        {trades.map(t => (
                          <tr key={t.trade_id} className="border-b border-zinc-50 hover:bg-zinc-50 transition-colors">
                            <td className="py-3 px-2 text-zinc-500 text-xs">{new Date(t.timestamp).toLocaleString('zh-CN')}</td>
                            <td className="py-3 px-2 font-semibold text-zinc-900">{t.symbol}</td>
                            <td className="text-center py-3 px-2">
                              <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-bold ${t.action === 'BUY' ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                                {t.action === 'BUY' ? '买入' : '卖出'}
                              </span>
                            </td>
                            <td className="text-right py-3 px-2 text-zinc-700">{t.shares}</td>
                            <td className="text-right py-3 px-2 text-zinc-700">{t.execution_price.toFixed(2)}</td>
                            <td className={`text-right py-3 px-2 font-medium ${t.realized_pnl != null ? (t.realized_pnl >= 0 ? 'text-emerald-600' : 'text-rose-600') : 'text-zinc-300'}`}>
                              {t.realized_pnl != null ? fmtPnL(t.realized_pnl, currency) : '--'}
                            </td>
                            <td className="text-center py-3 px-2">
                              <span className={`text-[10px] font-bold uppercase tracking-wider ${t.trigger_source === 'AI_SIGNAL' ? 'text-indigo-600' : 'text-zinc-400'}`}>
                                {t.trigger_source === 'AI_SIGNAL' ? '🤖 AI信号' : '✋ 手动'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Anomalies Tab */}
            {activeTab === 'anomalies' && (
              <div className="space-y-3">
                <h3 className="text-lg font-bold text-zinc-900">异常波动日志</h3>
                <p className="text-xs text-zinc-400 mb-4">个股日涨跌 &gt; ±7% 或账户总资产日波动 &gt; ±3% 时自动记录</p>
                {anomalies.length === 0 ? (
                  <div className="text-center py-16 text-zinc-400 bg-white border border-zinc-200 rounded-2xl">
                    <AlertTriangle size={48} className="mx-auto opacity-10 mb-4" />
                    <p className="text-sm">暂无异常记录 · 系统运行正常</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {anomalies.map(a => (
                      <div key={a.log_id} className={`p-5 rounded-2xl border ${a.event_type === 'SPIKE' ? 'bg-emerald-50/30 border-emerald-200' : 'bg-rose-50/30 border-rose-200'}`}>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className={`text-lg ${a.event_type === 'SPIKE' ? '' : ''}`}>
                              {a.event_type === 'SPIKE' ? '🚀' : '💥'}
                            </span>
                            <span className="font-bold text-zinc-900">{a.symbol || '账户总体'}</span>
                            <span className={`text-sm font-bold ${a.event_type === 'SPIKE' ? 'text-emerald-600' : 'text-rose-600'}`}>
                              {a.magnitude_pct > 0 ? '+' : ''}{a.magnitude_pct.toFixed(2)}%
                            </span>
                          </div>
                          <span className="text-xs text-zinc-400">{new Date(a.timestamp).toLocaleString('zh-CN')}</span>
                        </div>
                        {a.news_reasoning && (
                          <p className="text-xs text-zinc-600 italic bg-white/50 rounded-lg p-3 border border-zinc-100">
                            "{a.news_reasoning}"
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        {/* Empty State */}
        {!selectedAccount && !loading && (
          <div className="flex items-center justify-center py-24">
            <div className="max-w-md w-full text-center">
              <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-indigo-50 flex items-center justify-center">
                <Activity size={36} className="text-indigo-600" />
              </div>
              <h2 className="text-2xl font-bold text-zinc-900 mb-2">AI 模拟交易</h2>
              <p className="text-sm text-zinc-500 mb-8">创建模拟账号，让 AI 策略在模拟盘验证效果</p>
              <button
                onClick={() => setShowCreate(true)}
                className="h-12 px-8 bg-indigo-600 text-white font-medium text-sm rounded-xl hover:bg-indigo-700 transition-colors flex items-center gap-2 mx-auto"
              >
                <Plus size={16} /> 创建第一个模拟账号
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Create Account Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-zinc-900/20 backdrop-blur-md" onClick={() => setShowCreate(false)} />
          <div className="relative w-full max-w-md bg-white rounded-3xl shadow-2xl p-8 space-y-5">
            <h3 className="text-lg font-bold text-zinc-900">新建模拟账号</h3>
            <div>
              <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">账号名称</label>
              <input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder="例: A股价值投资组合"
                className="w-full px-4 py-3 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
              />
            </div>
            <div>
              <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-2">市场类型</label>
              <div className="grid grid-cols-3 gap-2">
                {MARKET_OPTIONS.map(m => (
                  <button
                    key={m.value}
                    onClick={() => { setNewMarket(m.value); setNewInitialBalance(m.default.toString()); }}
                    className={`px-3 py-3 rounded-xl text-xs font-bold border transition-all ${
                      newMarket === m.value
                        ? 'border-indigo-500 bg-indigo-50 text-indigo-700'
                        : 'border-zinc-200 text-zinc-500 hover:border-zinc-300'
                    }`}
                  >
                    <div>{m.label}</div>
                    <div className="text-[10px] font-normal text-zinc-400 mt-1">推荐 {m.default.toLocaleString()}</div>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">自定义初始资金 (选填)</label>
              <input
                type="number"
                value={newInitialBalance}
                onChange={e => setNewInitialBalance(e.target.value)}
                placeholder="默认使用市场推荐金额"
                className="w-full px-4 py-3 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
              />
            </div>
            <div className="flex gap-3">
              <button onClick={() => setShowCreate(false)} className="flex-1 py-3 rounded-xl border border-zinc-200 text-xs font-bold text-zinc-500 hover:bg-zinc-50">取消</button>
              <button onClick={handleCreate} disabled={!newName.trim()} className="flex-1 py-3 rounded-xl bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700 disabled:opacity-50">创建账号</button>
            </div>
          </div>
        </div>
      )}

      {/* Trade Ticket Modal */}
      {showTradeTicket && selectedAccount && (
        <TradeTicketModal
          account={selectedAccount}
          onClose={() => setShowTradeTicket(false)}
          onSuccess={() => loadAccountData(selectedAccount)}
        />
      )}

      {/* Account Merge Modal */}
      {showMerge && (
        <AccountMergeModal
          accounts={accounts}
          onClose={() => setShowMerge(false)}
          onSuccess={() => loadAccounts()}
        />
      )}
    </div>
  );
}

function SummaryCard({ icon, label, value, subtitle, color }: { icon: React.ReactNode; label: string; value: string; subtitle?: string; color: string }) {
  const colorMap: Record<string, string> = {
    indigo: 'bg-indigo-50 text-indigo-600 border-indigo-100',
    emerald: 'bg-emerald-50 text-emerald-600 border-emerald-100',
    rose: 'bg-rose-50 text-rose-600 border-rose-100',
    zinc: 'bg-zinc-50 text-zinc-600 border-zinc-100',
  };
  return (
    <div className={`p-5 rounded-2xl border ${colorMap[color] || colorMap.zinc}`}>
      <div className="flex items-center gap-2 mb-2 opacity-70">{icon}<span className="text-xs font-medium">{label}</span></div>
      <p className="text-xl font-bold">{value}</p>
      {subtitle && <p className="text-xs font-medium mt-0.5">{subtitle}</p>}
    </div>
  );
}
