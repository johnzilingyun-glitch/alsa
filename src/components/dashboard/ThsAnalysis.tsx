import { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  ArrowLeft, Search, Loader2, TrendingUp, TrendingDown, BarChart3,
  Layers, Newspaper, Target, RefreshCw, ChevronRight, X,
  LineChart as LineChartIcon, DollarSign, Activity, Zap
} from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';
import {
  thsSearch, thsKlines, thsDepth, thsBigOrder, thsIndustry, thsConcept,
  thsBlockConstituents, thsBlockQuote, thsWencai, thsNews, thsQuoteCn, thsQuoteAuto, getMarketType,
  type ThsSymbol, type KlineBar, type DepthRecord
} from '../../services/api/thsClient';
import {
  Line, LineChart, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts';
import { ThsKlineChart } from './ThsKlineChart';


type Tab = 'overview' | 'kline' | 'depth' | 'bigorder' | 'sectors' | 'wencai' | 'news';

export function ThsAnalysis() {
  const { setShowThsAnalysis } = useUIStore();

  // Search state
  const [searchInput, setSearchInput] = useState('');
  const [searchResults, setSearchResults] = useState<ThsSymbol[]>([]);
  const [searching, setSearching] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Selected stock
  const [selectedStock, setSelectedStock] = useState<ThsSymbol | null>(null);
  const [tab, setTab] = useState<Tab>('overview');

  // Data states
  const [quote, setQuote] = useState<any>(null);
  const [klines, setKlines] = useState<KlineBar[]>([]);
  const [klineInterval, setKlineInterval] = useState('5m');
  const [depth, setDepth] = useState<DepthRecord[]>([]);
  const [bigOrder, setBigOrder] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // Sector browser
  const [industryList, setIndustryList] = useState<any[]>([]);
  const [conceptList, setConceptList] = useState<any[]>([]);
  const [selectedSector, setSelectedSector] = useState<any>(null);
  const [sectorConstituents, setSectorConstituents] = useState<any[]>([]);
  const [sectorQuote, setSectorQuote] = useState<any>(null);
  const [sectorTab, setSectorTab] = useState<'industry' | 'concept'>('industry');

  // Sector K-line
  const [sectorKlines, setSectorKlines] = useState<KlineBar[]>([]);
  const [sectorKlineInterval, setSectorKlineInterval] = useState('day');
  const [sectorKlineLoading, setSectorKlineLoading] = useState(false);

  // Wencai
  const [wencaiQuery, setWencaiQuery] = useState('');
  const [wencaiResults, setWencaiResults] = useState<any[]>([]);
  const [wencaiLoading, setWencaiLoading] = useState(false);

  // News
  const [news, setNews] = useState<any[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);

  // Debounce search
  const searchTimer = useRef<ReturnType<typeof setTimeout>>(null);
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!searchInput.trim() || searchInput.trim().length < 1) {
      setSearchResults([]);
      setShowSuggestions(false);
      return;
    }
    searchTimer.current = setTimeout(async () => {
      setSearching(true);
      try {
        const results = await thsSearch(searchInput.trim());
        setSearchResults(results);
        setShowSuggestions(results.length > 0);
      } catch { setSearchResults([]); }
      finally { setSearching(false); }
    }, 400);
    return () => { if (searchTimer.current) clearTimeout(searchTimer.current); };
  }, [searchInput]);

  // Select stock
  const selectStock = useCallback(async (stock: ThsSymbol) => {
    setSelectedStock(stock);
    setSearchInput(stock.Name);
    setShowSuggestions(false);
    setTab('overview');
    setLoading(true);
    try {
      // THS SDK is NOT thread-safe — sequential calls required; auto-route HK/US/CN market
      const quoteData = await thsQuoteAuto(stock, '基础数据');
      setQuote(quoteData.data?.[0] || null);
      const klineData = await thsKlines(stock.THSCODE, 'day', 60);
      setKlines(klineData.data || []);
    } catch (e) { console.error('[THS]', e); }
    finally { setLoading(false); }
  }, []);

  // Tab data loading — sequential THS calls, cancelled on re-run
  const tabAbortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!selectedStock) return;
    // Cancel any in-flight THS request from previous render
    if (tabAbortRef.current) tabAbortRef.current.abort();
    const controller = new AbortController();
    tabAbortRef.current = controller;
    const code = selectedStock.THSCODE;

    (async () => {
      try {
        if (tab === 'kline') {
          setLoading(true);
          const d = await thsKlines(code, klineInterval, klineInterval === 'day' ? 60 : 120);
          if (!controller.signal.aborted) setKlines(d.data || []);
        } else if (tab === 'depth') {
          setLoading(true);
          const d = await thsDepth([code]);
          if (!controller.signal.aborted) setDepth(d.data || []);
        } else if (tab === 'bigorder') {
          setLoading(true);
          const d = await thsBigOrder(code);
          if (!controller.signal.aborted) setBigOrder(d.data || []);
        }
      } catch (e) {
        if (!controller.signal.aborted) console.error('[THS tab]', e);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();

    return () => controller.abort();
  }, [tab, klineInterval, selectedStock]);

  // Load sectors on first visit
  useEffect(() => {
    if (tab === 'sectors' && industryList.length === 0) {
      thsIndustry().then(d => setIndustryList(d.data || [])).catch(console.error);
      thsConcept().then(d => setConceptList(d.data || [])).catch(console.error);
    }
    if (tab === 'news' && news.length === 0) {
      setNewsLoading(true);
      thsNews().then(d => setNews(d.data || [])).catch(console.error).finally(() => setNewsLoading(false));
    }
  }, [tab, industryList.length, news.length]);

  // Sector K-line interval change → re-fetch
  useEffect(() => {
    if (!selectedSector) return;
    let cancelled = false;
    const code = selectedSector.代码;
    setSectorKlineLoading(true);
    thsKlines(code, sectorKlineInterval, sectorKlineInterval === 'day' ? 60 : 120)
      .then((d) => { if (!cancelled) setSectorKlines(d.data || []); })
      .catch(console.error)
      .finally(() => { if (!cancelled) setSectorKlineLoading(false); });
    return () => { cancelled = true; };
  }, [sectorKlineInterval, selectedSector]);

  // Select sector
  const selectSector = useCallback(async (sector: any) => {
    setSelectedSector(sector);
    setLoading(true);
    try {
      const [quoteData, constData, klineData] = await Promise.all([
        thsBlockQuote(sector.代码, '基础数据'),
        thsBlockConstituents(sector.代码),
        thsKlines(sector.代码, 'day', 60).catch(() => ({ data: [] as KlineBar[] })),
      ]);
      setSectorQuote(quoteData.data?.[0] || null);
      setSectorConstituents(constData.data || []);
      setSectorKlines(klineData.data || []);
      setSectorKlineInterval('day');
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  // Wencai search
  const handleWencai = useCallback(async () => {
    if (!wencaiQuery.trim()) return;
    setWencaiLoading(true);
    try {
      const d = await thsWencai(wencaiQuery.trim());
      setWencaiResults(d.data || []);
    } catch (e) { console.error(e); }
    finally { setWencaiLoading(false); }
  }, [wencaiQuery]);

  const formatNum = (v: any) => {
    if (v == null || v === '' || v === '--') return '--';
    const n = Number(v);
    if (isNaN(n)) return String(v);
    if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + '亿';
    if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + '万';
    return n.toFixed(2);
  };

  return (
    <div className="fixed inset-0 z-50 bg-zinc-50 overflow-y-auto">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white/95 backdrop-blur-sm border-b border-zinc-200">
        <div className="max-w-7xl mx-auto px-4 md:px-8 py-4 flex items-center gap-4">
          <button onClick={() => setShowThsAnalysis(false)} className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-zinc-100 transition-colors">
            <ArrowLeft size={20} />
          </button>
          <div className="flex-1 relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
            <input
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && searchResults.length > 0) selectStock(searchResults[0]); }}
              onFocus={() => searchResults.length > 0 && setShowSuggestions(true)}
              placeholder="输入股票名称、代码或拼音搜索..."
              className="w-full pl-10 pr-4 py-3 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400"
            />
            {searching && <Loader2 size={16} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-zinc-400" />}
            {showSuggestions && searchResults.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-zinc-200 rounded-xl shadow-lg max-h-72 overflow-y-auto z-50">
                {searchResults.slice(0, 10).map((s, i) => (
                  <button key={i} onClick={() => selectStock(s)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-50 text-left text-sm">
                    <div>
                      <span className="font-medium text-zinc-900">{s.Name}</span>
                      <span className="ml-2 text-xs text-zinc-400">{s.THSCODE}</span>
                    </div>
                    <span className="text-xs text-zinc-400">{s.MarketDisplay}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 md:px-8 py-6">
        {!selectedStock ? (
          <EmptyState onSelectSample={selectStock} />
        ) : (
          <div className="space-y-6">
            {/* Stock header */}
            <StockHeader stock={selectedStock} quote={quote} loading={loading} />

            {/* Tabs */}
            <div className="flex gap-1 bg-zinc-100 p-1 rounded-xl overflow-x-auto">
              {([
                { id: 'overview', label: '行情概览', icon: BarChart3 },
                { id: 'kline', label: 'K线', icon: LineChartIcon },
                { id: 'depth', label: '盘口', icon: Layers },
                { id: 'bigorder', label: '大单', icon: DollarSign },
                { id: 'sectors', label: '板块', icon: Target },
                { id: 'wencai', label: '问财', icon: Zap },
                { id: 'news', label: '资讯', icon: Newspaper },
              ] as const).map(t => (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
                    tab === t.id ? 'bg-white text-indigo-600 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'
                  }`}>
                  <t.icon size={14} />
                  {t.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            {tab === 'overview' && <OverviewTab quote={quote} klines={klines} />}
            {tab === 'kline' && (
              <div className="bg-white rounded-2xl border border-zinc-200 p-6">
                <ThsKlineChart
                  data={klines}
                  interval={klineInterval}
                  onIntervalChange={setKlineInterval}
                  loading={loading}
                />
              </div>
            )}
            {tab === 'depth' && <DepthTab data={depth} loading={loading} />}
            {tab === 'bigorder' && <BigOrderTab data={bigOrder} loading={loading} formatNum={formatNum} />}
            {tab === 'sectors' && (
              <SectorsTab
                industryList={industryList} conceptList={conceptList}
                sectorTab={sectorTab} setSectorTab={setSectorTab}
                selectedSector={selectedSector} sectorQuote={sectorQuote}
                sectorConstituents={sectorConstituents} selectSector={selectSector}
                loading={loading} formatNum={formatNum}
                onSelectStock={selectStock}
                sectorKlines={sectorKlines}
                sectorKlineInterval={sectorKlineInterval}
                onSectorKlineIntervalChange={setSectorKlineInterval}
                sectorKlineLoading={sectorKlineLoading}
              />
            )}
            {tab === 'wencai' && (
              <WencaiTab query={wencaiQuery} setQuery={setWencaiQuery} results={wencaiResults}
                loading={wencaiLoading} onSearch={handleWencai} onSelectStock={selectStock} />
            )}
            {tab === 'news' && <NewsTab data={news} loading={newsLoading} />}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────

function EmptyState({ onSelectSample }: { onSelectSample?: (s: ThsSymbol) => void }) {
  const samples: ThsSymbol[] = [
    { THSCODE: 'USHA600519', Name: '贵州茅台', MarketStr: 'USHA', Code: '600519', MarketDisplay: '沪A' },
    { THSCODE: 'UHKG00700', Name: '腾讯控股', MarketStr: 'UHKG', Code: '00700', MarketDisplay: '港股' },
    { THSCODE: 'UNQQAAPL', Name: '苹果公司', MarketStr: 'UNQQ', Code: 'AAPL', MarketDisplay: '美股' },
    { THSCODE: 'UNQQNVDA', Name: '英伟达', MarketStr: 'UNQQ', Code: 'NVDA', MarketDisplay: '美股' },
  ];

  return (
    <div className="flex flex-col items-center justify-center py-32 text-center">
      <div className="w-20 h-20 rounded-2xl bg-indigo-50 flex items-center justify-center mb-6">
        <BarChart3 size={36} className="text-indigo-500" />
      </div>
      <h2 className="text-xl font-bold text-zinc-900 mb-2">同花顺高级分析</h2>
      <p className="text-sm text-zinc-500 max-w-md">
        输入股票名称、代码或拼音开始分析。全流程支持A股、港股、美股行情与K线，以及板块分析、问财选股等功能。
      </p>
      <div className="mt-8 flex flex-wrap justify-center gap-3 text-xs">
        {samples.map(s => (
          <button key={s.THSCODE} onClick={() => onSelectSample?.(s)}
            className="px-3.5 py-2 bg-zinc-50 hover:bg-indigo-50 hover:text-indigo-600 rounded-xl transition-all font-medium text-zinc-700 border border-zinc-100">
            {s.Name} <span className="text-[10px] text-zinc-400 font-normal">({s.MarketDisplay})</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function StockHeader({ stock, quote, loading }: { stock: ThsSymbol; quote: any; loading: boolean }) {
  const price = quote?.['价格'] || quote?.['最新价'] || quote?.['收盘价'];
  const prevClose = quote?.['昨收价'] || 0;
  const chg = price && prevClose ? ((price - prevClose) / prevClose * 100) : 0;
  const isUp = chg >= 0;

  return (
    <div className="bg-white rounded-2xl border border-zinc-200 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-900">{stock.Name}</h1>
          <p className="text-sm text-zinc-400 font-mono">{stock.THSCODE} · {stock.MarketDisplay}</p>
        </div>
        <div className="text-right">
          {loading ? (
            <Loader2 size={24} className="animate-spin text-zinc-300" />
          ) : price ? (
            <>
              <p className="text-3xl font-bold font-mono text-zinc-900">{Number(price).toFixed(2)}</p>
              <p className={`text-sm font-medium ${isUp ? 'text-emerald-600' : 'text-rose-500'}`}>
                {isUp ? '+' : ''}{Number(chg).toFixed(2)}%
              </p>
            </>
          ) : (
            <p className="text-lg text-zinc-300">--</p>
          )}
        </div>
      </div>
      {quote && (
        <div className="grid grid-cols-4 md:grid-cols-8 gap-4 mt-4 pt-4 border-t border-zinc-100">
          {[
            ['开盘', quote['开盘价']], ['最高', quote['最高价']], ['最低', quote['最低价']],
            ['昨收', quote['昨收价']], ['成交量', quote['成交量']], ['成交额', quote['总金额']],
            ['换手率', quote['换手率']], ['量比', quote['量比']],
          ].map(([label, val]) => (
            <div key={label} className="text-center">
              <p className="text-[10px] text-zinc-400 mb-0.5">{label}</p>
              <p className="text-xs font-medium text-zinc-700 font-mono">
                {val != null && val !== '' && val !== '--' ? (typeof val === 'number' ? val.toFixed(2) : val) : '--'}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function OverviewTab({ quote, klines }: { quote: any; klines: KlineBar[] }) {
  if (!quote) return <div className="text-center py-12 text-zinc-400 text-sm">加载中...</div>;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div className="bg-white rounded-2xl border border-zinc-200 p-6">
        <h3 className="text-sm font-medium text-zinc-500 mb-4">行情数据</h3>
        <div className="space-y-3">
          {Object.entries(quote).slice(0, 12).map(([k, v]) => (
            <div key={k} className="flex justify-between text-sm">
              <span className="text-zinc-400">{k}</span>
              <span className="font-medium text-zinc-700 font-mono">{String(v ?? '--')}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="bg-white rounded-2xl border border-zinc-200 p-6">
        <h3 className="text-sm font-medium text-zinc-500 mb-4">近期走势</h3>
        {klines.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={klines.map((b, i) => ({ idx: i, close: b['收盘价'] }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="idx" tick={false} />
              <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10 }} />
              <Tooltip />
              <Line type="monotone" dataKey="close" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-[250px] flex items-center justify-center text-zinc-300 text-sm">无K线数据</div>
        )}
      </div>
    </div>
  );
}

function DepthTab({ data, loading }: { data: DepthRecord[]; loading: boolean }) {
  if (loading) return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-zinc-300" /></div>;
  if (!data.length) return <div className="text-center py-12 text-zinc-400 text-sm">无盘口数据（当前港股/美股市场仅提供基础行情与K线，五档盘口针对A股开放）</div>;

  const row = data[0];
  const bids = [1, 2, 3, 4, 5].map(i => ({ price: row[`买${i}价`], vol: row[`买${i}量`] }));
  const asks = [1, 2, 3, 4, 5].map(i => ({ price: row[`卖${i}价`], vol: row[`卖${i}量`] }));

  return (
    <div className="bg-white rounded-2xl border border-zinc-200 p-6">
      <h3 className="text-sm font-medium text-zinc-500 mb-4">五档盘口</h3>
      <div className="grid grid-cols-2 gap-8">
        <div>
          <p className="text-xs font-bold text-emerald-600 mb-2">买盘</p>
          {bids.map((b, i) => (
            <div key={i} className="flex justify-between py-1.5 border-b border-zinc-50 text-sm">
              <span className="text-zinc-500">买{i + 1}</span>
              <span className="font-mono text-emerald-600">{b.price ?? '--'}</span>
              <span className="font-mono text-zinc-400">{b.vol ?? '--'}</span>
            </div>
          ))}
        </div>
        <div>
          <p className="text-xs font-bold text-rose-500 mb-2">卖盘</p>
          {asks.map((a, i) => (
            <div key={i} className="flex justify-between py-1.5 border-b border-zinc-50 text-sm">
              <span className="text-zinc-500">卖{i + 1}</span>
              <span className="font-mono text-rose-500">{a.price ?? '--'}</span>
              <span className="font-mono text-zinc-400">{a.vol ?? '--'}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function BigOrderTab({ data, loading, formatNum }: { data: any[]; loading: boolean; formatNum: (v: any) => string }) {
  if (loading) return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-zinc-300" /></div>;
  if (!data.length) return <div className="text-center py-12 text-zinc-400 text-sm">无大单数据（当前港股/美股市场仅提供基础行情与K线，大单监控针对A股开放）</div>;

  const totalBuy = data.filter(r => r['成交方向']?.includes('买')).reduce((s, r) => s + (r['总金额'] || 0), 0);
  const totalSell = data.filter(r => r['成交方向']?.includes('卖')).reduce((s, r) => s + (r['总金额'] || 0), 0);

  return (
    <div className="bg-white rounded-2xl border border-zinc-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-zinc-500">大单流向</h3>
        <div className="flex gap-4 text-xs">
          <span className="text-emerald-600">买入: {formatNum(totalBuy)}</span>
          <span className="text-rose-500">卖出: {formatNum(totalSell)}</span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-zinc-400 border-b border-zinc-100">
              <th className="text-left py-2 font-medium">时间</th>
              <th className="text-left py-2 font-medium">方向</th>
              <th className="text-right py-2 font-medium">数量</th>
              <th className="text-right py-2 font-medium">金额</th>
            </tr>
          </thead>
          <tbody>
            {data.slice(0, 30).map((r, i) => (
              <tr key={i} className="border-b border-zinc-50 hover:bg-zinc-50">
                <td className="py-2 font-mono text-xs text-zinc-500">{String(r['时间'] || '').slice(11, 19)}</td>
                <td className={`py-2 font-medium ${r['成交方向']?.includes('买') ? 'text-emerald-600' : 'text-rose-500'}`}>
                  {r['成交方向'] || '--'}
                </td>
                <td className="py-2 text-right font-mono text-zinc-600">{r['成交量']?.toLocaleString() ?? '--'}</td>
                <td className="py-2 text-right font-mono text-zinc-700">{formatNum(r['总金额'])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SectorsTab({ industryList, conceptList, sectorTab, setSectorTab, selectedSector, sectorQuote,
  sectorConstituents, selectSector, loading, formatNum, onSelectStock,
  sectorKlines, sectorKlineInterval, onSectorKlineIntervalChange, sectorKlineLoading }: {
  industryList: any[]; conceptList: any[]; sectorTab: 'industry' | 'concept';
  setSectorTab: (v: 'industry' | 'concept') => void; selectedSector: any; sectorQuote: any;
  sectorConstituents: any[]; selectSector: (s: any) => void; loading: boolean;
  formatNum: (v: any) => string; onSelectStock: (s: ThsSymbol) => void;
  sectorKlines: KlineBar[]; sectorKlineInterval: string;
  onSectorKlineIntervalChange: (v: string) => void; sectorKlineLoading: boolean;
}) {
  const list = sectorTab === 'industry' ? industryList : conceptList;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="bg-white rounded-2xl border border-zinc-200 p-4 max-h-[600px] overflow-y-auto">
        <div className="flex gap-1 mb-3 bg-zinc-100 p-0.5 rounded-lg">
          <button onClick={() => setSectorTab('industry')}
            className={`flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              sectorTab === 'industry' ? 'bg-white text-indigo-600 shadow-sm' : 'text-zinc-500'
            }`}>申万行业 ({industryList.length})</button>
          <button onClick={() => setSectorTab('concept')}
            className={`flex-1 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              sectorTab === 'concept' ? 'bg-white text-indigo-600 shadow-sm' : 'text-zinc-500'
            }`}>概念板块 ({conceptList.length})</button>
        </div>
        <div className="space-y-1">
          {list.map((s, i) => (
            <button key={i} onClick={() => selectSector(s)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-all ${
                selectedSector?.代码 === s.代码 ? 'bg-indigo-50 text-indigo-700 font-medium' : 'text-zinc-600 hover:bg-zinc-50'
              }`}>
              {s.名称}
            </button>
          ))}
        </div>
      </div>
      <div className="lg:col-span-2 space-y-4">
        {selectedSector ? (
          <>
            <div className="bg-white rounded-2xl border border-zinc-200 p-6">
              <h3 className="font-bold text-zinc-900 mb-3">{selectedSector.名称}</h3>
              {sectorQuote ? (
                <div className="grid grid-cols-3 md:grid-cols-6 gap-4">
                  {Object.entries(sectorQuote).slice(0, 6).map(([k, v]) => (
                    <div key={k} className="text-center">
                      <p className="text-[10px] text-zinc-400">{k}</p>
                      <p className="text-xs font-medium text-zinc-700 font-mono">{String(v ?? '--')}</p>
                    </div>
                  ))}
                </div>
              ) : loading ? <Loader2 className="animate-spin text-zinc-300" /> : <p className="text-sm text-zinc-400">无行情数据</p>}
            </div>
            <div className="bg-white rounded-2xl border border-zinc-200 p-6">
              <ThsKlineChart
                data={sectorKlines}
                interval={sectorKlineInterval}
                onIntervalChange={onSectorKlineIntervalChange}
                loading={sectorKlineLoading}
                height={350}
              />
            </div>
            <div className="bg-white rounded-2xl border border-zinc-200 p-6">
              <h3 className="text-sm font-medium text-zinc-500 mb-3">成分股 ({sectorConstituents.length})</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {sectorConstituents.slice(0, 20).map((c, i) => (
                  <button key={i} onClick={() => onSelectStock({ THSCODE: c.代码, Name: c.名称, MarketStr: '', Code: '', MarketDisplay: '' })}
                    className="text-left px-3 py-2 rounded-lg bg-zinc-50 hover:bg-indigo-50 text-sm text-zinc-700 hover:text-indigo-700 transition-all">
                    {c.名称}
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="bg-white rounded-2xl border border-zinc-200 p-12 text-center text-zinc-400 text-sm">
            选择一个板块查看详情
          </div>
        )}
      </div>
    </div>
  );
}

function WencaiTab({ query, setQuery, results, loading, onSearch, onSelectStock }: {
  query: string; setQuery: (v: string) => void; results: any[];
  loading: boolean; onSearch: () => void; onSelectStock: (s: ThsSymbol) => void;
}) {
  const presets = [
    '今日涨停，非ST', '连续3年ROE大于15%，非ST',
    '均线多头排列，MACD金叉', '主力净流入前20，非ST',
  ];
  return (
    <div className="bg-white rounded-2xl border border-zinc-200 p-6">
      <h3 className="text-sm font-medium text-zinc-500 mb-4">问财自然语言选股</h3>
      <div className="flex gap-2 mb-4">
        <input value={query} onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && onSearch()}
          placeholder="输入选股条件，如：连续3日主力净流入，换手率大于5%"
          className="flex-1 px-4 py-2.5 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20" />
        <button onClick={onSearch} disabled={loading}
          className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
          查询
        </button>
      </div>
      <div className="flex flex-wrap gap-2 mb-4">
        {presets.map(p => (
          <button key={p} onClick={() => { setQuery(p); }}
            className="px-3 py-1.5 bg-zinc-50 text-zinc-600 rounded-lg text-xs hover:bg-zinc-100 transition-colors">
            {p}
          </button>
        ))}
      </div>
      {results.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-zinc-400 border-b border-zinc-100">
                {results[0] && Object.keys(results[0]).slice(0, 6).map(k => (
                  <th key={k} className="text-left py-2 font-medium px-2">{k}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {results.slice(0, 20).map((r, i) => (
                <tr key={i} className="border-b border-zinc-50 hover:bg-zinc-50 cursor-pointer"
                  onClick={() => {
                    const code = r['股票代码'] || '';
                    const name = r['股票简称'] || r['名称'] || '';
                    if (code && name) onSelectStock({ THSCODE: '', Name: name, MarketStr: '', Code: code, MarketDisplay: '' });
                  }}>
                  {Object.values(r).slice(0, 6).map((v, j) => (
                    <td key={j} className="py-2 px-2 text-xs text-zinc-600 font-mono max-w-[120px] truncate">{String(v ?? '--')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!loading && results.length === 0 && query && (
        <p className="text-center py-8 text-zinc-400 text-sm">无结果</p>
      )}
    </div>
  );
}

function NewsTab({ data, loading }: { data: any[]; loading: boolean }) {
  if (loading) return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-zinc-300" /></div>;
  if (!data.length) return <div className="text-center py-12 text-zinc-400 text-sm">无资讯</div>;

  const parseProps = (props: string) => {
    const map: Record<string, string> = {};
    if (!props) return map;
    props.split(';').forEach(p => {
      const [k, ...v] = p.split('=');
      if (k) map[k.trim()] = v.join('=').trim();
    });
    return map;
  };

  return (
    <div className="bg-white rounded-2xl border border-zinc-200 p-6">
      <h3 className="text-sm font-medium text-zinc-500 mb-4">实时资讯</h3>
      <div className="space-y-3">
        {data.slice(0, 20).map((item, i) => {
          const props = parseProps(item.Properties || '');
          return (
            <div key={i} className="flex gap-3 py-3 border-b border-zinc-50 last:border-0">
              <div className="w-2 h-2 rounded-full bg-indigo-400 mt-2 flex-shrink-0" />
              <div>
                <p className="text-sm font-medium text-zinc-800">{item.Title}</p>
                {props['summ'] && <p className="text-xs text-zinc-500 mt-1 line-clamp-2">{props['summ']}</p>}
                <p className="text-[10px] text-zinc-400 mt-1">
                  {props['source'] && <span className="mr-2">{props['source']}</span>}
                  {props['ctime'] && <span>{props['ctime']}</span>}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
