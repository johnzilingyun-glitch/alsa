import { useState, useEffect, useCallback, useRef } from 'react';
import { ArrowLeft, RefreshCw, TrendingUp, DollarSign, BarChart3, Wallet, X, Search, CandlestickChart, Link2 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from 'recharts';
import { useUIStore } from '../../stores/useUIStore';
import { 
  fetchIBKRStatus, 
  fetchAccountSummary, 
  fetchPositions, 
  fetchPnL, 
  fetchMonthlyPerformance,
  fetchDailyPnL,
  fetchOptionsStrikes,
  fetchOptionsChain,
  fetchSearchContract,
  type IBKRAccountSummary, 
  type IBKRPosition, 
  type IBKRMonthlyPnL,
  type IBKRDailyPnL 
} from '../../services/ibkrService';

type TabId = 'portfolio' | 'chart' | 'options';

export function IBKRDashboard() {
  const { setShowIBKRDashboard } = useUIStore();
  const [activeTab, setActiveTab] = useState<TabId>('portfolio');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [account, setAccount] = useState<IBKRAccountSummary | null>(null);
  const [positions, setPositions] = useState<IBKRPosition[]>([]);
  const [monthlyPnL, setMonthlyPnL] = useState<IBKRMonthlyPnL[]>([]);
  const [dailyPnl, setDailyPnl] = useState<{ dailyPnl: number; unrealizedPnl: number; realizedPnl: number } | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<IBKRPosition | null>(null);
  const [dailyData, setDailyData] = useState<IBKRDailyPnL[]>([]);
  const [dailyLoading, setDailyLoading] = useState(false);
  const [sortField, setSortField] = useState<'unrealizedPnl' | 'pnlPercent' | 'mktValue'>('unrealizedPnl');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [chartSymbol, setChartSymbol] = useState('AAPL');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const status = await fetchIBKRStatus();
      setConnected(status.connected || status.authenticated);
      if (!status.connected && !status.authenticated) {
        setLoading(false);
        return;
      }
      const [acct, pos, pnl, perf] = await Promise.all([
        fetchAccountSummary().catch(() => null),
        fetchPositions().catch(() => []),
        fetchPnL().catch(() => null),
        fetchMonthlyPerformance('12M').catch(() => []),
      ]);
      setAccount(acct);
      setPositions(pos);
      setDailyPnl(pnl);
      setMonthlyPnL(perf);
    } catch (e: any) {
      setError(e.message || '加载数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handlePositionClick = async (pos: IBKRPosition) => {
    setSelectedPosition(pos);
    setDailyLoading(true);
    try {
      const data = await fetchDailyPnL(pos.conid);
      setDailyData(data);
    } catch {
      setDailyData([]);
    } finally {
      setDailyLoading(false);
    }
  };

  const sortedPositions = [...positions].sort((a, b) => {
    const mul = sortDir === 'desc' ? -1 : 1;
    return (a[sortField] - b[sortField]) * mul;
  });

  const handleSort = (field: typeof sortField) => {
    if (sortField === field) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortField(field); setSortDir('desc'); }
  };

  const fmt = (val: number, currency = 'USD') => new Intl.NumberFormat('en-US', { style: 'currency', currency, minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(val);
  const fmtPnL = (val: number) => (val >= 0 ? '+' : '') + fmt(val);

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'portfolio', label: '持仓盈亏', icon: <Wallet size={16} /> },
    { id: 'chart', label: 'K线图表', icon: <CandlestickChart size={16} /> },
    { id: 'options', label: '期权链', icon: <Link2 size={16} /> },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-white overflow-y-auto">
      <div className="sticky top-0 z-10 bg-white/95 backdrop-blur-sm border-b border-zinc-200">
        <div className="max-w-7xl mx-auto px-4 md:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button onClick={() => setShowIBKRDashboard(false)} className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-zinc-100 transition-colors">
              <ArrowLeft size={20} />
            </button>
            <div>
              <h1 className="text-xl font-bold text-zinc-900">IBKR 实盘仪表盘</h1>
              <p className="text-xs text-zinc-500 flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full inline-block ${connected ? 'bg-emerald-500' : 'bg-red-500'}`} />
                {connected ? '已连接' : '未连接'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center bg-zinc-100 rounded-xl p-1">
              {tabs.map(tab => (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === tab.id ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'}`}>
                  {tab.icon}{tab.label}
                </button>
              ))}
            </div>
            <button onClick={loadData} disabled={loading} className="btn-secondary h-10 px-4 rounded-xl flex items-center gap-2 disabled:opacity-50">
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
              <span className="text-sm hidden sm:inline">刷新</span>
            </button>
          </div>
        </div>
        <div className="md:hidden flex border-t border-zinc-100 px-4">
          {tabs.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-medium border-b-2 transition-all ${activeTab === tab.id ? 'border-indigo-600 text-indigo-600' : 'border-transparent text-zinc-400'}`}>
              {tab.icon}{tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 md:px-8 py-8">
        {!connected && !loading && (
          <div className="flex items-center justify-center py-16">
            <div className="max-w-md w-full text-center">
              <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-indigo-50 flex items-center justify-center">
                <Wallet size={36} className="text-indigo-600" />
              </div>
              <h2 className="text-2xl font-bold text-zinc-900 mb-2">连接 IBKR 账户</h2>
              <p className="text-sm text-zinc-500 mb-8">请先在新标签页中登录 IBKR Client Portal Gateway，登录完成后回到此页面点击下方按钮</p>
              <div className="space-y-3">
                <a
                  href="https://localhost:5000"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full h-12 bg-indigo-600 text-white font-medium text-sm rounded-xl hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2"
                >
                  <ArrowLeft size={16} className="rotate-[135deg]" />
                  打开 IBKR 登录页面
                </a>
                <button onClick={loadData} className="w-full h-12 border border-zinc-200 text-zinc-700 font-medium text-sm rounded-xl hover:bg-zinc-50 transition-colors flex items-center justify-center gap-2">
                  <RefreshCw size={16} />
                  已登录，刷新连接
                </button>
              </div>
              <div className="mt-8 p-4 bg-zinc-50 rounded-xl text-left">
                <p className="text-xs font-medium text-zinc-700 mb-2">操作步骤：</p>
                <ol className="text-xs text-zinc-500 space-y-1.5 list-decimal list-inside">
                  <li>点击上方按钮打开登录页面（首次需接受证书警告）</li>
                  <li>输入 IBKR 用户名和密码完成登录</li>
                  <li>登录成功后回到此页面，点击"已登录，刷新连接"</li>
                </ol>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'portfolio' && connected && (
          <>
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <RefreshCw size={32} className="animate-spin text-indigo-600" />
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                  <SummaryCard icon={<Wallet size={20} />} label="账户净值" value={account ? fmt(account.netLiquidation, account.currency) : '--'} color="indigo" />
                  <SummaryCard icon={<DollarSign size={20} />} label="今日盈亏" value={dailyPnl ? fmtPnL(dailyPnl.dailyPnl) : '--'} color={dailyPnl && dailyPnl.dailyPnl >= 0 ? 'emerald' : 'rose'} />
                  <SummaryCard icon={<TrendingUp size={20} />} label="未实现盈亏" value={dailyPnl ? fmtPnL(dailyPnl.unrealizedPnl) : '--'} color={dailyPnl && dailyPnl.unrealizedPnl >= 0 ? 'emerald' : 'rose'} />
                  <SummaryCard icon={<BarChart3 size={20} />} label="持仓数量" value={`${positions.length} 只`} color="zinc" />
                </div>
                {monthlyPnL.length > 0 && (
                  <div className="mb-8 p-6 bg-white border border-zinc-200 rounded-2xl">
                    <h2 className="text-lg font-bold text-zinc-900 mb-4">月度盈亏走势</h2>
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={monthlyPnL}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                        <YAxis tick={{ fontSize: 12 }} tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
                        <Tooltip formatter={(value: any) => [`${(Number(value) * 100).toFixed(2)}%`, '月度收益']} contentStyle={{ borderRadius: '12px', border: '1px solid #e4e4e7' }} />
                        <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                          {monthlyPnL.map((entry, i) => <Cell key={i} fill={entry.pnl >= 0 ? '#10b981' : '#f43f5e'} />)}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
                {selectedPosition && (
                  <div className="mb-8 p-6 bg-indigo-50/50 border border-indigo-200 rounded-2xl relative">
                    <button onClick={() => setSelectedPosition(null)} className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-indigo-100"><X size={16} /></button>
                    <h3 className="text-lg font-bold text-zinc-900 mb-1">{selectedPosition.ticker} 每日盈亏</h3>
                    <p className="text-sm text-zinc-500 mb-4">{selectedPosition.name}</p>
                    {dailyLoading ? <div className="flex justify-center py-12"><RefreshCw size={24} className="animate-spin text-indigo-500" /></div>
                      : dailyData.length > 0 ? (
                        <ResponsiveContainer width="100%" height={200}>
                          <LineChart data={dailyData}><CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #e4e4e7' }} /><Line type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={2} dot={false} /></LineChart>
                        </ResponsiveContainer>
                      ) : <p className="text-zinc-400 text-sm text-center py-8">暂无每日数据</p>}
                  </div>
                )}
                <div className="p-6 bg-white border border-zinc-200 rounded-2xl">
                  <h2 className="text-lg font-bold text-zinc-900 mb-2">个股盈亏明细</h2>
                  <p className="text-xs text-zinc-400 mb-4">点击任意行查看每日盈亏走势</p>
                  {positions.length === 0 ? <p className="text-zinc-400 text-center py-8">暂无持仓数据</p> : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead><tr className="border-b border-zinc-100 text-zinc-500">
                          <th className="text-left py-3 px-2 font-medium">股票</th>
                          <th className="text-right py-3 px-2 font-medium">持仓</th>
                          <th className="text-right py-3 px-2 font-medium">成本</th>
                          <th className="text-right py-3 px-2 font-medium">现价</th>
                          <th className="text-right py-3 px-2 font-medium cursor-pointer hover:text-indigo-600" onClick={() => handleSort('mktValue')}>市值{sortField === 'mktValue' && (sortDir === 'desc' ? '↓' : '↑')}</th>
                          <th className="text-right py-3 px-2 font-medium cursor-pointer hover:text-indigo-600" onClick={() => handleSort('unrealizedPnl')}>盈亏{sortField === 'unrealizedPnl' && (sortDir === 'desc' ? '↓' : '↑')}</th>
                          <th className="text-right py-3 px-2 font-medium cursor-pointer hover:text-indigo-600" onClick={() => handleSort('pnlPercent')}>涨跌%{sortField === 'pnlPercent' && (sortDir === 'desc' ? '↓' : '↑')}</th>
                        </tr></thead>
                        <tbody>
                          {sortedPositions.map((pos) => (
                            <tr key={pos.conid} className="border-b border-zinc-50 hover:bg-zinc-50 cursor-pointer transition-colors" onClick={() => handlePositionClick(pos)}>
                              <td className="py-3 px-2"><div className="font-semibold text-zinc-900">{pos.ticker}</div><div className="text-xs text-zinc-400 truncate max-w-[120px]">{pos.name}</div></td>
                              <td className="text-right py-3 px-2 text-zinc-700">{pos.position}</td>
                              <td className="text-right py-3 px-2 text-zinc-700">{pos.avgCost.toFixed(2)}</td>
                              <td className="text-right py-3 px-2 text-zinc-700">{pos.mktPrice.toFixed(2)}</td>
                              <td className="text-right py-3 px-2 text-zinc-700">{fmt(pos.mktValue)}</td>
                              <td className={`text-right py-3 px-2 font-medium ${pos.unrealizedPnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{fmtPnL(pos.unrealizedPnl)}</td>
                              <td className={`text-right py-3 px-2 font-medium ${pos.pnlPercent >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{pos.pnlPercent >= 0 ? '+' : ''}{pos.pnlPercent.toFixed(2)}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </>
            )}
          </>
        )}

        {activeTab === 'chart' && <ChartTab symbol={chartSymbol} onSymbolChange={setChartSymbol} />}
        {activeTab === 'options' && <OptionsTab />}
      </div>
    </div>
  );
}

// ===== TradingView Chart Tab =====
function ChartTab({ symbol, onSymbolChange }: { symbol: string; onSymbolChange: (s: string) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState(symbol);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputValue.trim()) onSymbolChange(inputValue.trim().toUpperCase());
  };

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = '';
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.type = 'text/javascript';
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: symbol,
      interval: 'D',
      timezone: 'Asia/Shanghai',
      theme: 'light',
      style: '1',
      locale: 'zh_CN',
      allow_symbol_change: true,
      calendar: false,
      support_host: 'https://www.tradingview.com',
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: true,
      studies: ['MASimple@tv-basicstudies', 'Volume@tv-basicstudies'],
      withdateranges: true,
    });
    const wrapper = document.createElement('div');
    wrapper.className = 'tradingview-widget-container__widget';
    wrapper.style.height = '100%';
    wrapper.style.width = '100%';
    containerRef.current.appendChild(wrapper);
    containerRef.current.appendChild(script);
  }, [symbol]);

  return (
    <div>
      <form onSubmit={handleSubmit} className="mb-6 flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input type="text" value={inputValue} onChange={(e) => setInputValue(e.target.value)} placeholder="输入股票代码，如 AAPL, MSFT, SSE:600519" className="w-full h-12 pl-11 pr-4 rounded-xl border border-zinc-200 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40" />
        </div>
        <button type="submit" className="h-12 px-6 bg-indigo-600 text-white font-medium text-sm rounded-xl hover:bg-indigo-700 transition-colors">查看K线</button>
      </form>
      <div className="border border-zinc-200 rounded-2xl overflow-hidden" style={{ height: 'calc(100vh - 280px)', minHeight: '500px' }}>
        <div ref={containerRef} className="tradingview-widget-container h-full w-full" />
      </div>
      <p className="mt-3 text-xs text-zinc-400 text-center">K线数据由 TradingView 提供 · 支持全球股票、ETF、期货、加密货币 · 支持技术指标和画线工具</p>
    </div>
  );
}

// ===== Options Chain Tab =====
function OptionsTab() {
  const [symbol, setSymbol] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [selectedContract, setSelectedContract] = useState<any>(null);
  const [strikes, setStrikes] = useState<any>(null);
  const [optionChain, setOptionChain] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const results = await fetchSearchContract(symbol.trim().toUpperCase());
      setSearchResults(results);
      if (results.length === 0) setError('未找到该合约');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectContract = (contract: any) => {
    setSelectedContract(contract);
    setSearchResults([]);
    if (contract.sections) {
      const optMonths = contract.sections?.filter((s: any) => s.secType === 'OPT') || [];
      if (optMonths.length > 0 && optMonths[0].months) {
        setSelectedMonth(optMonths[0].months.split(';')[0] || '');
      }
    }
  };

  const handleLoadStrikes = async () => {
    if (!selectedContract || !selectedMonth) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOptionsStrikes(selectedContract.conid, 'OPT', selectedMonth);
      setStrikes(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLoadChain = async (strike: number, right: 'C' | 'P') => {
    if (!selectedContract || !selectedMonth) return;
    setLoading(true);
    try {
      const data = await fetchOptionsChain(selectedContract.conid, 'OPT', selectedMonth, strike, right);
      setOptionChain(Array.isArray(data) ? data : [data]);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedMonth && selectedContract) handleLoadStrikes();
  }, [selectedMonth]);

  return (
    <div>
      <form onSubmit={handleSearch} className="mb-6 flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input type="text" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="输入股票代码查看期权链，如 AAPL, TSLA" className="w-full h-12 pl-11 pr-4 rounded-xl border border-zinc-200 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40" />
        </div>
        <button type="submit" disabled={loading} className="h-12 px-6 bg-indigo-600 text-white font-medium text-sm rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50">
          {loading ? <RefreshCw size={16} className="animate-spin" /> : '搜索'}
        </button>
      </form>

      {error && (
        <div className="mb-6 p-4 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700">
          {error}
          {!selectedContract && <p className="mt-1 text-rose-500 text-xs">需要 IBKR Client Portal Gateway 已连接并登录</p>}
        </div>
      )}

      {searchResults.length > 0 && (
        <div className="mb-6 p-4 border border-zinc-200 rounded-2xl">
          <h3 className="text-sm font-bold text-zinc-700 mb-3">搜索结果</h3>
          <div className="space-y-2">
            {searchResults.map((r: any, i: number) => (
              <button key={i} onClick={() => handleSelectContract(r)} className="w-full text-left p-3 rounded-xl hover:bg-zinc-50 border border-zinc-100 transition-colors">
                <div className="font-semibold text-zinc-900">{r.symbol || r.ticker}</div>
                <div className="text-xs text-zinc-500">{r.companyName || r.description} · {r.exchange}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {selectedContract && (
        <div className="mb-6 p-4 bg-indigo-50/50 border border-indigo-200 rounded-2xl">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="font-bold text-zinc-900">{selectedContract.symbol || selectedContract.ticker}</h3>
              <p className="text-xs text-zinc-500">{selectedContract.companyName || selectedContract.description}</p>
            </div>
            <button onClick={() => { setSelectedContract(null); setStrikes(null); setOptionChain([]); }} className="text-zinc-400 hover:text-zinc-600"><X size={16} /></button>
          </div>
          {selectedContract.sections && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-zinc-500">到期月份：</span>
              {selectedContract.sections
                .filter((s: any) => s.secType === 'OPT')
                .flatMap((s: any) => (s.months || '').split(';').filter(Boolean))
                .slice(0, 12)
                .map((month: string) => (
                  <button key={month} onClick={() => setSelectedMonth(month)} className={`px-3 py-1 text-xs rounded-lg font-medium transition-all ${selectedMonth === month ? 'bg-indigo-600 text-white' : 'bg-white border border-zinc-200 text-zinc-600 hover:border-indigo-300'}`}>
                    {month}
                  </button>
                ))}
            </div>
          )}
        </div>
      )}

      {strikes && (
        <div className="p-6 bg-white border border-zinc-200 rounded-2xl">
          <h3 className="text-lg font-bold text-zinc-900 mb-4">期权链 · {selectedContract?.symbol} · {selectedMonth}</h3>
          {strikes.call && strikes.put ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-zinc-100">
                  <th className="text-center py-2 px-3 font-medium text-emerald-600" colSpan={2}>看涨 (Call)</th>
                  <th className="text-center py-2 px-3 font-bold text-zinc-900 bg-zinc-50">行权价</th>
                  <th className="text-center py-2 px-3 font-medium text-rose-600" colSpan={2}>看跌 (Put)</th>
                </tr></thead>
                <tbody>
                  {(strikes.call || []).map((strike: number) => (
                    <tr key={strike} className="border-b border-zinc-50 hover:bg-zinc-50">
                      <td className="py-2 px-3 text-center"><button onClick={() => handleLoadChain(strike, 'C')} className="text-xs text-indigo-600 hover:underline">查看</button></td>
                      <td className="py-2 px-3 text-right text-emerald-600 font-medium">C</td>
                      <td className="py-2 px-3 text-center font-bold text-zinc-900 bg-zinc-50">{strike}</td>
                      <td className="py-2 px-3 text-left text-rose-600 font-medium">P</td>
                      <td className="py-2 px-3 text-center"><button onClick={() => handleLoadChain(strike, 'P')} className="text-xs text-indigo-600 hover:underline">查看</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="text-zinc-400 text-center py-8">暂无期权数据。请确保 IBKR Gateway 已连接。</p>}
        </div>
      )}

      {optionChain.length > 0 && (
        <div className="mt-6 p-6 bg-white border border-zinc-200 rounded-2xl">
          <h3 className="text-sm font-bold text-zinc-700 mb-3">期权合约详情</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-zinc-100 text-zinc-500">
                <th className="text-left py-2 px-2">合约</th><th className="text-right py-2 px-2">行权价</th><th className="text-right py-2 px-2">类型</th><th className="text-right py-2 px-2">到期日</th><th className="text-right py-2 px-2">Conid</th>
              </tr></thead>
              <tbody>
                {optionChain.map((opt: any, i: number) => (
                  <tr key={i} className="border-b border-zinc-50">
                    <td className="py-2 px-2 font-medium">{opt.symbol || opt.ticker}</td>
                    <td className="text-right py-2 px-2">{opt.strike}</td>
                    <td className="text-right py-2 px-2">{opt.right === 'C' ? '看涨' : '看跌'}</td>
                    <td className="text-right py-2 px-2">{opt.maturityDate || opt.expiry}</td>
                    <td className="text-right py-2 px-2 text-zinc-400">{opt.conid}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!selectedContract && !loading && searchResults.length === 0 && (
        <div className="mt-8 p-8 border-2 border-dashed border-zinc-200 rounded-2xl text-center">
          <Link2 size={48} className="mx-auto text-zinc-300 mb-4" />
          <h3 className="text-lg font-bold text-zinc-700 mb-2">查看期权链</h3>
          <p className="text-sm text-zinc-500 max-w-md mx-auto">输入股票代码搜索，然后选择到期月份查看完整期权链。需要 IBKR Client Portal Gateway 已连接。</p>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string; color: string }) {
  const colorMap: Record<string, string> = { indigo: 'bg-indigo-50 text-indigo-600 border-indigo-100', emerald: 'bg-emerald-50 text-emerald-600 border-emerald-100', rose: 'bg-rose-50 text-rose-600 border-rose-100', zinc: 'bg-zinc-50 text-zinc-600 border-zinc-100' };
  return (
    <div className={`p-5 rounded-2xl border ${colorMap[color] || colorMap.zinc}`}>
      <div className="flex items-center gap-2 mb-2 opacity-70">{icon}<span className="text-xs font-medium">{label}</span></div>
      <p className="text-xl font-bold">{value}</p>
    </div>
  );
}