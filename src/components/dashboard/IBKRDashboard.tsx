import { useState, useEffect, useCallback, useRef } from 'react';
import { ArrowLeft, RefreshCw, TrendingUp, DollarSign, BarChart3, Wallet, X, Search, CandlestickChart, Link2 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from 'recharts';
import { createChart, ColorType, CrosshairMode, CandlestickSeries, HistogramSeries, LineSeries } from 'lightweight-charts';
import { useTranslation } from 'react-i18next';
import { StockSearchInput } from '../shared/StockSearchInput';
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
  const { t } = useTranslation();
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
  const [chartSymbol, setChartSymbol] = useState('');

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
      setError(e.message || t('ibkr.load_failed'));
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
    { id: 'portfolio', label: t('ibkr.tab_portfolio'), icon: <Wallet size={16} /> },
    { id: 'chart', label: t('ibkr.tab_chart'), icon: <CandlestickChart size={16} /> },
    { id: 'options', label: t('ibkr.tab_options'), icon: <Link2 size={16} /> },
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
              <h1 className="text-xl font-bold text-zinc-900">{t('ibkr.title')}</h1>
              <p className="text-xs text-zinc-500 flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full inline-block ${connected ? 'bg-emerald-500' : 'bg-red-500'}`} />
                {connected ? t('ibkr.connected') : t('ibkr.disconnected')}
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
              <span className="text-sm hidden sm:inline">{t('ibkr.refresh')}</span>
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
        {activeTab === 'portfolio' && !connected && !loading && (
          <div className="flex items-center justify-center py-16">
            <div className="max-w-md w-full text-center">
              <div className="w-20 h-20 mx-auto mb-6 rounded-2xl bg-indigo-50 flex items-center justify-center">
                <Wallet size={36} className="text-indigo-600" />
              </div>
              <h2 className="text-2xl font-bold text-zinc-900 mb-2">{t('ibkr.login_title')}</h2>
              <p className="text-sm text-zinc-500 mb-8">{t('ibkr.login_desc')}</p>
              <div className="space-y-3">
                <a
                  href="https://localhost:5000"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full h-12 bg-indigo-600 text-white font-medium text-sm rounded-xl hover:bg-indigo-700 transition-colors flex items-center justify-center gap-2"
                >
                  <ArrowLeft size={16} className="rotate-[135deg]" />
                  {t('ibkr.login_open')}
                </a>
                <button onClick={loadData} className="w-full h-12 border border-zinc-200 text-zinc-700 font-medium text-sm rounded-xl hover:bg-zinc-50 transition-colors flex items-center justify-center gap-2">
                  <RefreshCw size={16} />
                  {t('ibkr.login_refresh')}
                </button>
              </div>
              <div className="mt-8 p-4 bg-zinc-50 rounded-xl text-left">
                <p className="text-xs font-medium text-zinc-700 mb-2">{t('ibkr.login_steps')}</p>
                <ol className="text-xs text-zinc-500 space-y-1.5 list-decimal list-inside">
                  <li>{t('ibkr.login_step1')}</li>
                  <li>{t('ibkr.login_step2')}</li>
                  <li>{t('ibkr.login_step3')}</li>
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
                  <SummaryCard icon={<Wallet size={20} />} label={t('ibkr.account_value')} value={account ? fmt(account.netLiquidation, account.currency) : '--'} color="indigo" />
                  <SummaryCard icon={<DollarSign size={20} />} label={t('ibkr.daily_pnl')} value={dailyPnl ? fmtPnL(dailyPnl.dailyPnl) : '--'} color={dailyPnl && dailyPnl.dailyPnl >= 0 ? 'emerald' : 'rose'} />
                  <SummaryCard icon={<TrendingUp size={20} />} label={t('ibkr.unrealized_pnl')} value={dailyPnl ? fmtPnL(dailyPnl.unrealizedPnl) : '--'} color={dailyPnl && dailyPnl.unrealizedPnl >= 0 ? 'emerald' : 'rose'} />
                  <SummaryCard icon={<BarChart3 size={20} />} label={t('ibkr.positions_count')} value={`${positions.length} ${t('ibkr.positions_unit')}`} color="zinc" />
                </div>
                {monthlyPnL.length > 0 && (
                  <div className="mb-8 p-6 bg-white border border-zinc-200 rounded-2xl">
                    <h2 className="text-lg font-bold text-zinc-900 mb-4">{t('ibkr.monthly_pnl')}</h2>
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={monthlyPnL}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                        <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                        <YAxis tick={{ fontSize: 12 }} tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
                        <Tooltip formatter={(value: any) => [`${(Number(value) * 100).toFixed(2)}%`, t('ibkr.monthly_return')]} contentStyle={{ borderRadius: '12px', border: '1px solid #e4e4e7' }} />
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
                    <h3 className="text-lg font-bold text-zinc-900 mb-1">{selectedPosition.ticker} {t('ibkr.daily_pnl_title')}</h3>
                    <p className="text-sm text-zinc-500 mb-4">{selectedPosition.name}</p>
                    {dailyLoading ? <div className="flex justify-center py-12"><RefreshCw size={24} className="animate-spin text-indigo-500" /></div>
                      : dailyData.length > 0 ? (
                        <ResponsiveContainer width="100%" height={200}>
                          <LineChart data={dailyData}><CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" /><XAxis dataKey="date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #e4e4e7' }} /><Line type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={2} dot={false} /></LineChart>
                        </ResponsiveContainer>
                      ) : <p className="text-zinc-400 text-sm text-center py-8">{t('ibkr.no_daily_data')}</p>}
                  </div>
                )}
                <div className="p-6 bg-white border border-zinc-200 rounded-2xl">
                  <h2 className="text-lg font-bold text-zinc-900 mb-2">{t('ibkr.position_detail')}</h2>
                  <p className="text-xs text-zinc-400 mb-4">{t('ibkr.position_hint')}</p>
                  {positions.length === 0 ? <p className="text-zinc-400 text-center py-8">{t('ibkr.no_positions')}</p> : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead><tr className="border-b border-zinc-100 text-zinc-500">
                          <th className="text-left py-3 px-2 font-medium">{t('ibkr.col_stock')}</th>
                          <th className="text-right py-3 px-2 font-medium">{t('ibkr.col_position')}</th>
                          <th className="text-right py-3 px-2 font-medium">{t('ibkr.col_cost')}</th>
                          <th className="text-right py-3 px-2 font-medium">{t('ibkr.col_price')}</th>
                          <th className="text-right py-3 px-2 font-medium cursor-pointer hover:text-indigo-600" onClick={() => handleSort('mktValue')}>{t('ibkr.col_market_value')}{sortField === 'mktValue' && (sortDir === 'desc' ? '↓' : '↑')}</th>
                          <th className="text-right py-3 px-2 font-medium cursor-pointer hover:text-indigo-600" onClick={() => handleSort('unrealizedPnl')}>{t('ibkr.col_pnl')}{sortField === 'unrealizedPnl' && (sortDir === 'desc' ? '↓' : '↑')}</th>
                          <th className="text-right py-3 px-2 font-medium cursor-pointer hover:text-indigo-600" onClick={() => handleSort('pnlPercent')}>{t('ibkr.col_change')}{sortField === 'pnlPercent' && (sortDir === 'desc' ? '↓' : '↑')}</th>
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

// ===== Parent Chart Tab with Engine Toggle =====
function ChartTab({ symbol, onSymbolChange }: { symbol: string; onSymbolChange: (s: string) => void }) {
  const [engine, setEngine] = useState<'local' | 'tradingview'>('local');

  return (
    <div className="flex flex-col h-full">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex bg-zinc-100 p-1 rounded-xl">
          <button
            onClick={() => setEngine('local')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              engine === 'local' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'
            }`}
          >
            本地引擎 (国内推荐)
          </button>
          <button
            onClick={() => setEngine('tradingview')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              engine === 'tradingview' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'
            }`}
          >
            TradingView (海外节点)
          </button>
        </div>
      </div>
      <div className="flex-1">
        {engine === 'local' ? (
          <LocalChartTab symbol={symbol} onSymbolChange={onSymbolChange} />
        ) : (
          <TradingViewChartTab symbol={symbol} onSymbolChange={onSymbolChange} />
        )}
      </div>
    </div>
  );
}

// ===== Local KLineChart Tab (Replaces TradingView) =====
function LocalChartTab({ symbol, onSymbolChange }: { symbol: string; onSymbolChange: (s: string) => void }) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const chartDataRef = useRef<any[]>([]);
  const maDataRef = useRef<{ma5: any[], ma20: any[], ma100: any[]}>({ma5: [], ma20: [], ma100: []});
  const legendRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);
  const [chartMarket, setChartMarket] = useState<string>('US-Share');
  const [activeInterval, setActiveInterval] = useState<string>('1d');
  const activeIntervalRef = useRef(activeInterval);

  useEffect(() => {
    activeIntervalRef.current = activeInterval;
  }, [activeInterval]);

  // 1. Initialize Lightweight Chart once
  useEffect(() => {
    if (!containerRef.current) return;
    
    console.log("[LightweightCharts] Initializing chart...");
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'white' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: '#dfdfdf',
      },
      timeScale: {
        borderColor: '#dfdfdf',
        timeVisible: true,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#ef4444',
      downColor: '#10b981',
      borderVisible: false,
      wickUpColor: '#ef4444',
      wickDownColor: '#10b981',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#26a69a',
      priceFormat: {
        type: 'volume',
      },
      priceScaleId: 'volume', // Overlay using a new scale id
    });

    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.8, // volume covers bottom 20%
        bottom: 0,
      },
    });

    const ma5Series = chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 2, crosshairMarkerVisible: false });
    const ma20Series = chart.addSeries(LineSeries, { color: '#8b5cf6', lineWidth: 2, crosshairMarkerVisible: false });
    const ma100Series = chart.addSeries(LineSeries, { color: '#ec4899', lineWidth: 2, crosshairMarkerVisible: false });

    chart.subscribeCrosshairMove((param) => {
      if (!legendRef.current) return;
      
      if (param.time && param.seriesData.has(candleSeries)) {
        const data: any = param.seriesData.get(candleSeries);
        const candleList = chartDataRef.current;
        
        let prevData = null;
        if (candleList && candleList.length > 0) {
           const idx = candleList.findIndex((c: any) => c.time === param.time);
           if (idx > 0) prevData = candleList[idx - 1];
        }
        
        const maData = {
          ma5: param.seriesData.get(ma5Series),
          ma20: param.seriesData.get(ma20Series),
          ma100: param.seriesData.get(ma100Series)
        };
        renderIbkrLegend(legendRef.current, data, prevData, maData);
        legendRef.current.style.opacity = '1';
      } else {
        // When mouse leaves, show the latest candle
        const candleList = chartDataRef.current;
        if (candleList && candleList.length > 0) {
          const latest = candleList[candleList.length - 1];
          const prev = candleList.length > 1 ? candleList[candleList.length - 2] : null;
          const { ma5, ma20, ma100 } = maDataRef.current;
          const latestMaData = {
            ma5: ma5 && ma5.length > 0 ? ma5[ma5.length - 1] : undefined,
            ma20: ma20 && ma20.length > 0 ? ma20[ma20.length - 1] : undefined,
            ma100: ma100 && ma100.length > 0 ? ma100[ma100.length - 1] : undefined
          };
          renderIbkrLegend(legendRef.current, latest, prev, latestMaData);
          legendRef.current.style.opacity = '1';
        } else {
          legendRef.current.style.opacity = '0';
        }
      }
    });

    chartRef.current = { chart, candleSeries, volumeSeries, ma5Series, ma20Series, ma100Series };

    return () => {
      console.log("[LightweightCharts] Disposing chart...");
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  // 2. Fetch and apply data
  useEffect(() => {
    if (!symbol || !chartRef.current) return;
    
    let isMounted = true;
    let pollTimer: any = null;
    
    const loadData = async (isInitial = true) => {
      try {
        if (isInitial) setLoading(true);
        console.log(`[LightweightCharts] Loading data for ${symbol} @ ${activeInterval}`);
        
        const currentInterval = activeInterval;
        let apiPeriod = '1y';
        if (currentInterval === '1wk') apiPeriod = '5y';
        if (currentInterval === '1mo' || currentInterval === '1y') apiPeriod = 'max';
        if (currentInterval === '15m' || currentInterval === '1h') apiPeriod = '1mo'; // 1 month is enough for intraday

        let reqInterval = currentInterval;
        if (currentInterval === '1y') reqInterval = '1mo'; // Fetch monthly and aggregate

        console.log(`[LightweightCharts] Fetching /api/market/history/${symbol}?period=${apiPeriod}&interval=${reqInterval}`);
        const res = await fetch(`/api/market/history/${symbol}?period=${apiPeriod}&interval=${reqInterval}`);
        if (!res.ok) throw new Error(`Fetch failed: ${res.status} ${res.statusText}`);
        const result = await res.json();
        
        if (!isMounted) return;

        let chartData: any[] = [];
        if (result.success && result.data && Array.isArray(result.data)) {
          chartData = result.data.map((item: any) => {
            // Safely parse Beijing time to timestamp
            let dateStr = item.date;
            if (dateStr.includes(' ') && !dateStr.includes('+')) {
              dateStr = dateStr.replace(' ', 'T') + '+08:00';
            }
            return {
              timestamp: new Date(dateStr).getTime(),
              dateStr: item.date,
              open: Number(item.open),
              high: Number(item.high),
              low: Number(item.low),
              close: Number(item.close),
              volume: Number(item.volume || 0),
              turnover: Number(item.amount || 0)
            };
          });

          // Aggregate monthly data into yearly data
          if (currentInterval === '1y') {
            const yearlyMap = new Map();
            for (const b of chartData) {
              if (!b.dateStr) continue;
              const year = b.dateStr.substring(0, 4);
              if (!yearlyMap.has(year)) {
                yearlyMap.set(year, {
                  timestamp: new Date(`${year}-12-31`).getTime(),
                  dateStr: `${year}-12-31`,
                  open: b.open,
                  high: b.high,
                  low: b.low,
                  close: b.close,
                  volume: b.volume,
                  turnover: b.turnover
                });
              } else {
                const ex = yearlyMap.get(year);
                ex.high = Math.max(ex.high, b.high);
                ex.low = Math.min(ex.low, b.low);
                ex.close = b.close;
                ex.volume += b.volume;
                ex.turnover += b.turnover;
                ex.timestamp = Math.max(ex.timestamp, b.timestamp);
                ex.dateStr = `${year}-12-31`;
              }
            }
            chartData = Array.from(yearlyMap.values());
          }
          
          // Ensure strictly monotonically increasing timestamps
          chartData.sort((a: any, b: any) => a.timestamp - b.timestamp);
        } else {
          console.error("[LightweightCharts] Invalid data returned from API:", result);
          if (isMounted) setChartError(t('ibkr.load_failed'));
        }
        
        if (isMounted) {
          if (chartData.length === 0) {
            setChartError("暂无K线数据");
          } else {
            setChartError(null);
          }
          console.log(`[LightweightCharts] Applying ${chartData.length} bars to chart...`);
          if (chartRef.current) {
            const { candleSeries, volumeSeries, ma5Series, ma20Series, ma100Series } = chartRef.current;
            
            const formatTime = (d: any) => {
               if (currentInterval.includes('m') || currentInterval.includes('h')) {
                 return Math.floor(d.timestamp / 1000); // Unix timestamp for intraday
               }
               // Lightweight charts prefers 'YYYY-MM-DD' for daily or higher resolution
               if (d.dateStr && /^\d{4}-\d{2}-\d{2}/.test(d.dateStr)) {
                 return d.dateStr.split(' ')[0]; // Extract just the date part if it contains time
               }
               return Math.floor(d.timestamp / 1000);
            };

            const candleData = [];
            const volumeData = [];
            let lastTime: string | number | null = null;

            for (const d of chartData) {
              const time = formatTime(d);
              if (time === lastTime) continue; // Deduplicate by the exact time index expected by Lightweight Charts
              lastTime = time;

              candleData.push({
                time: time as any,
                open: d.open,
                high: d.high,
                low: d.low,
                close: d.close,
              });
              
              volumeData.push({
                time: time as any,
                value: d.volume,
                color: d.close >= d.open ? '#ef444488' : '#10b98188',
              });
            }

            try {
              if (candleData.length > 0) {
                chartDataRef.current = candleData;
                candleSeries.setData(candleData);
                volumeSeries.setData(volumeData);
                
                // Calculate MA
                const calcMA = (data: any[], period: number) => {
                  const result = [];
                  for (let i = 0; i < data.length; i++) {
                    if (i < period - 1) continue;
                    let sum = 0;
                    for (let j = 0; j < period; j++) {
                      sum += data[i - j].close;
                    }
                    result.push({ time: data[i].time, value: sum / period });
                  }
                  return result;
                };
                const ma5Data = calcMA(candleData, 5);
                const ma20Data = calcMA(candleData, 20);
                const ma100Data = calcMA(candleData, 100);
                
                maDataRef.current = { ma5: ma5Data, ma20: ma20Data, ma100: ma100Data };

                ma5Series.setData(ma5Data);
                ma20Series.setData(ma20Data);
                ma100Series.setData(ma100Data);

                if (isInitial) {
                  chartRef.current.chart.timeScale().fitContent();
                }
                
                // Show latest candle in legend immediately
                if (legendRef.current) {
                  const latest = candleData[candleData.length - 1];
                  const prev = candleData.length > 1 ? candleData[candleData.length - 2] : null;
                  renderIbkrLegend(legendRef.current, latest, prev);
                  legendRef.current.style.opacity = '1';
                }
              }
            } catch (err: any) {
              console.error("[LightweightCharts] Error setting data:", err);
              if (isInitial) setChartError(`渲染失败: ${err.message || '未知错误'}`);
            }
            
            // Poll for real-time updates every 5 seconds if intraday or daily
            if (['15m', '1h', '1d'].includes(currentInterval) && isMounted) {
              pollTimer = setTimeout(() => loadData(false), 5000);
            }
          }
        }
      } catch (e: any) {
        console.error("[LightweightCharts] Failed to load data:", e);
        if (isMounted && isInitial) setChartError(`请求失败: ${e.message}`);
      } finally {
        if (isMounted && isInitial) setLoading(false);
      }
    };
    
    loadData(true);
    
    return () => {
      isMounted = false;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [symbol, activeInterval]);

  const handleSymbolSelect = (sym: string, market?: string) => {
    if (market) setChartMarket(market);
    onSymbolChange(sym);
  };

  const handleSubmit = (sym: string) => {
    onSymbolChange(sym);
  };

  return (
    <div className="flex flex-col h-full w-full">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3 w-full">
          <div className="relative flex-shrink-0">
            <select
              value={chartMarket}
              onChange={(e) => setChartMarket(e.target.value)}
              className="h-10 w-28 cursor-pointer appearance-none rounded-xl border border-zinc-200 bg-white px-4 pr-10 text-sm font-semibold text-zinc-700 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40 hover:bg-zinc-50"
            >
              <option value="A-Share">A 股</option>
              <option value="HK-Share">港股</option>
              <option value="US-Share">美股</option>
            </select>
            <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400">
              <TrendingUp size={14} />
            </div>
          </div>
          <StockSearchInput
            value={symbol}
            market={chartMarket}
            placeholder={t('ibkr.chart_placeholder')}
            className="flex-1 max-w-md h-10"
            onSelect={handleSymbolSelect}
            onSubmit={handleSubmit}
          />
          <button
            type="button"
            onClick={() => handleSubmit(symbol)}
            className="h-10 px-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl flex items-center justify-center transition-colors"
          >
            <Search size={16} />
          </button>
          <div className="ml-auto flex items-center gap-2 bg-zinc-100 p-1 rounded-xl">
            {[
              { label: '15分', value: '15m' },
              { label: '小时', value: '1h' },
              { label: '日线', value: '1d' },
              { label: '周线', value: '1wk' },
              { label: '月线', value: '1mo' },
              { label: '年线', value: '1y' }
            ].map(int => (
              <button
                key={int.value}
                onClick={() => setActiveInterval(int.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                  activeInterval === int.value
                    ? 'bg-white text-zinc-900 shadow-sm'
                    : 'text-zinc-500 hover:text-zinc-700'
                }`}
              >
                {int.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="border border-zinc-200 rounded-2xl overflow-hidden relative flex-1 min-h-[450px]">
        {/* Floating Legend */}
        <div 
          ref={legendRef} 
          className="absolute top-3 left-3 z-10 pointer-events-none transition-opacity duration-150"
          style={{ opacity: 0 }}
        />
        {/* Explicit position absolute to guarantee full coverage and prevent 0-height rendering issues */}
        <div ref={containerRef} className="absolute inset-0 bg-white" />
        {loading && (
          <div className="absolute inset-0 bg-white/50 backdrop-blur-sm flex items-center justify-center z-10">
            <RefreshCw size={32} className="animate-spin text-indigo-600" />
          </div>
        )}
        {chartError && (
          <div className="absolute inset-0 bg-white/80 flex items-center justify-center z-20 text-red-500 font-medium">
            {chartError}
          </div>
        )}
        {!symbol && !loading && (
          <div className="absolute inset-0 bg-white/80 flex items-center justify-center z-20 text-zinc-500 font-medium">
            <Search size={20} className="mr-2 text-zinc-400" /> 请在上方输入框搜索股票代码以查看行情
          </div>
        )}
      </div>
      <p className="mt-3 text-xs text-zinc-400 text-center">K线图表由 Lightweight Charts 提供极速渲染支持</p>
    </div>
  );
}
function renderIbkrLegend(
  el: HTMLDivElement,
  data: { open: number; high: number; low: number; close: number } | undefined | null,
  prevData?: { close: number } | null,
  maData?: { ma5?: unknown; ma20?: unknown; ma100?: unknown },
): void {
  el.replaceChildren();
  if (!data) return;

  const safe = (value: number | undefined | null) => (
    value != null && Number.isFinite(value) ? value.toFixed(2) : '--'
  );
  const open = safe(data.open);
  const high = safe(data.high);
  const low = safe(data.low);
  const close = safe(data.close);

  let change = data.close - data.open;
  let percent = data.open !== 0 ? (change / data.open) * 100 : 0;
  if (prevData?.close && Number.isFinite(prevData.close)) {
    change = data.close - prevData.close;
    percent = prevData.close !== 0 ? (change / prevData.close) * 100 : 0;
  }

  const sign = change > 0 ? '+' : '';
  const colorClass = change > 0 ? 'text-red-500' : (change < 0 ? 'text-emerald-500' : 'text-zinc-600');
  const wrapper = document.createElement('div');
  wrapper.className = 'flex items-center gap-3 bg-white/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-zinc-200 shadow-sm text-[11px] md:text-[13px] font-medium tracking-wide flex-wrap';

  appendIbkrLegendMetric(wrapper, 'High', high, colorClass);
  appendIbkrLegendMetric(wrapper, 'Open', open, colorClass);
  appendIbkrLegendMetric(wrapper, 'Low', low, colorClass);
  appendIbkrLegendMetric(wrapper, 'Close', close, `${colorClass} font-bold`);
  appendIbkrLegendMetric(wrapper, 'Last', close, colorClass);
  appendIbkrLegendText(wrapper, `${sign}${percent.toFixed(2)}%`, `${colorClass} ml-2 font-semibold`);
  appendIbkrMovingAverage(wrapper, 'MA5', getSeriesValue(maData?.ma5), 'text-[#f59e0b] ml-2');
  appendIbkrMovingAverage(wrapper, 'MA20', getSeriesValue(maData?.ma20), 'text-[#8b5cf6] ml-2');
  appendIbkrMovingAverage(wrapper, 'MA100', getSeriesValue(maData?.ma100), 'text-[#ec4899] ml-2');

  el.appendChild(wrapper);
}

function appendIbkrLegendMetric(parent: HTMLElement, label: string, value: string, valueClass: string): void {
  const item = document.createElement('span');
  const labelNode = document.createElement('span');
  labelNode.className = 'text-zinc-400 mr-1';
  labelNode.textContent = label;
  const valueNode = document.createElement('span');
  valueNode.className = valueClass;
  valueNode.textContent = value;
  item.append(labelNode, valueNode);
  parent.appendChild(item);
}

function appendIbkrLegendText(parent: HTMLElement, value: string, className: string): void {
  const node = document.createElement('span');
  node.className = className;
  node.textContent = value;
  parent.appendChild(node);
}

function getSeriesValue(point: unknown): number | undefined {
  if (typeof point !== 'object' || point === null || !('value' in point)) return undefined;
  const value = (point as { value?: unknown }).value;
  return typeof value === 'number' ? value : undefined;
}

function appendIbkrMovingAverage(parent: HTMLElement, label: string, value: number | undefined, className: string): void {
  if (value == null || !Number.isFinite(value)) return;
  appendIbkrLegendText(parent, `${label}: ${value.toFixed(2)}`, className);
}

// ===== TradingView Chart Tab =====
function TradingViewChartTab({ symbol, onSymbolChange }: { symbol: string; onSymbolChange: (s: string) => void }) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [tvMarket, setTvMarket] = useState<string>('US-Share');

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

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [symbol]);

  const handleSymbolSelect = (sym: string, market?: string) => {
    if (market) setTvMarket(market);
    onSymbolChange(sym);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="mb-6 flex items-center gap-3">
        <div className="relative flex-shrink-0">
          <select
            value={tvMarket}
            onChange={(e) => setTvMarket(e.target.value)}
            className="h-12 w-36 cursor-pointer appearance-none rounded-xl border border-zinc-200 bg-white px-4 pr-10 text-sm font-semibold text-zinc-700 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40 hover:bg-zinc-50"
          >
            <option value="A-Share">A 股</option>
            <option value="HK-Share">港股</option>
            <option value="US-Share">美股</option>
          </select>
          <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400">
            <TrendingUp size={14} />
          </div>
        </div>
        <StockSearchInput
          value={symbol}
          market={tvMarket}
          placeholder={t('ibkr.chart_placeholder')}
          className="flex-1 max-w-md"
          onSelect={handleSymbolSelect}
          onSubmit={(sym) => onSymbolChange(sym)}
        />
        <button
          type="button"
          onClick={() => onSymbolChange(symbol)}
          className="h-12 px-6 bg-indigo-600 text-white font-medium text-sm rounded-xl hover:bg-indigo-700 transition-colors flex-shrink-0"
        >
          {t('ibkr.chart_view')}
        </button>
      </div>
      <div className="border border-zinc-200 rounded-2xl overflow-hidden" style={{ height: 'calc(100vh - 340px)', minHeight: '450px' }}>
        <div ref={containerRef} className="tradingview-widget-container h-full w-full" />
      </div>
      <p className="mt-3 text-xs text-zinc-400 text-center">{t('ibkr.chart_powered_by')}</p>
    </div>
  );
}

// ===== Options Chain Tab =====
function OptionsTab() {
  const { t } = useTranslation();
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
      if (results.length === 0) setError(t('ibkr.options_not_found'));
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
          <input type="text" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder={t('ibkr.options_placeholder')} className="w-full h-12 pl-11 pr-4 rounded-xl border border-zinc-200 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40" />
        </div>
        <button type="submit" disabled={loading} className="h-12 px-6 bg-indigo-600 text-white font-medium text-sm rounded-xl hover:bg-indigo-700 transition-colors disabled:opacity-50">
          {loading ? <RefreshCw size={16} className="animate-spin" /> : t('ibkr.options_search')}
        </button>
      </form>

      {error && (
        <div className="mb-6 p-4 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700">
          {error}
          {!selectedContract && <p className="mt-1 text-rose-500 text-xs">{t('ibkr.options_need_gateway')}</p>}
        </div>
      )}

      {searchResults.length > 0 && (
        <div className="mb-6 p-4 border border-zinc-200 rounded-2xl">
          <h3 className="text-sm font-bold text-zinc-700 mb-3">{t('ibkr.options_results')}</h3>
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
              <span className="text-xs text-zinc-500">{t('ibkr.options_expiry')}</span>
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
          <h3 className="text-lg font-bold text-zinc-900 mb-4">{t('ibkr.options_chain')} · {selectedContract?.symbol} · {selectedMonth}</h3>
          {strikes.call && strikes.put ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-zinc-100">
                  <th className="text-center py-2 px-3 font-medium text-emerald-600" colSpan={2}>{t('ibkr.options_call')}</th>
                  <th className="text-center py-2 px-3 font-bold text-zinc-900 bg-zinc-50">{t('ibkr.options_strike')}</th>
                  <th className="text-center py-2 px-3 font-medium text-rose-600" colSpan={2}>{t('ibkr.options_put')}</th>
                </tr></thead>
                <tbody>
                  {(strikes.call || []).map((strike: number) => (
                    <tr key={strike} className="border-b border-zinc-50 hover:bg-zinc-50">
                      <td className="py-2 px-3 text-center"><button onClick={() => handleLoadChain(strike, 'C')} className="text-xs text-indigo-600 hover:underline">{t('ibkr.options_view')}</button></td>
                      <td className="py-2 px-3 text-right text-emerald-600 font-medium">C</td>
                      <td className="py-2 px-3 text-center font-bold text-zinc-900 bg-zinc-50">{strike}</td>
                      <td className="py-2 px-3 text-left text-rose-600 font-medium">P</td>
                      <td className="py-2 px-3 text-center"><button onClick={() => handleLoadChain(strike, 'P')} className="text-xs text-indigo-600 hover:underline">{t('ibkr.options_view')}</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="text-zinc-400 text-center py-8">{t('ibkr.options_no_data')}</p>}
        </div>
      )}

      {optionChain.length > 0 && (
        <div className="mt-6 p-6 bg-white border border-zinc-200 rounded-2xl">
          <h3 className="text-sm font-bold text-zinc-700 mb-3">{t('ibkr.options_detail')}</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-zinc-100 text-zinc-500">
                <th className="text-left py-2 px-2">{t('ibkr.options_col_contract')}</th><th className="text-right py-2 px-2">{t('ibkr.options_col_strike')}</th><th className="text-right py-2 px-2">{t('ibkr.options_col_type')}</th><th className="text-right py-2 px-2">{t('ibkr.options_col_expiry')}</th><th className="text-right py-2 px-2">{t('ibkr.options_col_conid')}</th>
              </tr></thead>
              <tbody>
                {optionChain.map((opt: any, i: number) => (
                  <tr key={i} className="border-b border-zinc-50">
                    <td className="py-2 px-2 font-medium">{opt.symbol || opt.ticker}</td>
                    <td className="text-right py-2 px-2">{opt.strike}</td>
                    <td className="text-right py-2 px-2">{opt.right === 'C' ? t('ibkr.options_type_call') : t('ibkr.options_type_put')}</td>
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
          <h3 className="text-lg font-bold text-zinc-700 mb-2">{t('ibkr.options_view_chain')}</h3>
          <p className="text-sm text-zinc-500 max-w-md mx-auto">{t('ibkr.options_search_hint')}</p>
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