import { useState, useEffect, useCallback, memo } from 'react';
import { 
  Globe, Settings, Loader2, ExternalLink, TrendingUp, Share2, CheckCircle2,
  LayoutGrid, Coins, Star, Newspaper, Search, RefreshCw, Calendar
} from 'lucide-react';
import { motion } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { Market, MarketOverview as MarketOverviewType } from '../../types';
import { useUIStore } from '../../stores/useUIStore';
import { useMarketStore } from '../../stores/useMarketStore';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { ErrorNotice } from '../ErrorNotice';
import { getMarketHistoryByDate, getAvailableMarketDates } from '../../services/adminService';
import { InstitutionalAlertPanel } from './InstitutionalAlertPanel';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface MarketOverviewProps {
  onFetchMarketOverview: (force?: boolean) => void;
  onTriggerDailyReport: () => void;
}

export const MarketOverview = memo(function MarketOverview({ onFetchMarketOverview, onTriggerDailyReport }: MarketOverviewProps) {
  const { t, i18n } = useTranslation();
  const { 
    overviewLoading, overviewError, isGeneratingReport, isSendingReport, reportStatus,
    autoRefreshInterval, setAutoRefreshInterval, setIsSettingsOpen,
  } = useUIStore();
  const { 
    marketOverviews, marketLastUpdatedTimes, overviewMarket, setOverviewMarket 
  } = useMarketStore();
  const { setSymbol, setMarket } = useAnalysisStore();

  // History date picker state
  const [selectedDate, setSelectedDate] = useState<string>('');
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [historyData, setHistoryData] = useState<MarketOverviewType | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Deterministic News & Sectors State
  const [hotNews, setHotNews] = useState<any[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [sectorFlow, setSectorFlow] = useState<any>(null);
  const [northboundFlow, setNorthboundFlow] = useState<any>(null);
  const [flowsLoading, setFlowsLoading] = useState(false);

  const isHistoryMode = selectedDate !== '';

  // Fetch deterministic hot news independently
  useEffect(() => {
    let cancelled = false;
    async function fetchNews() {
      if (isHistoryMode) return;
      setNewsLoading(true);
      try {
        const res = await fetch(`/api/stock/news?market=${overviewMarket}`);
        if (!res.ok) throw new Error('News fetch failed');
        const data = await res.json();
        if (!cancelled) setHotNews(data);
      } catch (e) {
        console.warn(e);
      } finally {
        if (!cancelled) setNewsLoading(false);
      }
    }
    fetchNews();
    return () => { cancelled = true; };
  }, [overviewMarket, isHistoryMode]);

  // Fetch deterministic capital flows independently
  useEffect(() => {
    let cancelled = false;
    async function fetchFlows() {
      if (isHistoryMode || overviewMarket !== 'A-Share') return;
      setFlowsLoading(true);
      try {
        const [sectorsRes, northboundRes] = await Promise.all([
          fetch(`/api/stock/sectors`),
          fetch(`/api/stock/northbound`)
        ]);
        if (sectorsRes.ok && !cancelled) setSectorFlow(await sectorsRes.json());
        if (northboundRes && northboundRes.ok && !cancelled) setNorthboundFlow(await northboundRes.json());
      } catch (e) {
        console.warn("Quantitative Data Fetch failed", e);
      } finally {
        if (!cancelled) setFlowsLoading(false);
      }
    }
    fetchFlows();
    return () => { cancelled = true; };
  }, [overviewMarket, isHistoryMode]);

  // Fetch available dates when market changes
  useEffect(() => {
    let cancelled = false;
    getAvailableMarketDates(overviewMarket).then(dates => {
      if (!cancelled) setAvailableDates(dates);
    });
    return () => { cancelled = true; };
  }, [overviewMarket]);

  // Fetch history data when a date is selected
  const handleDateChange = useCallback(async (date: string) => {
    setSelectedDate(date);
    if (!date) {
      setHistoryData(null);
      return;
    }
    setHistoryLoading(true);
    try {
      const data = await getMarketHistoryByDate(date, overviewMarket);
      setHistoryData(data);
    } finally {
      setHistoryLoading(false);
    }
  }, [overviewMarket]);

  // Reset history mode when market tab changes
  useEffect(() => {
    setSelectedDate('');
    setHistoryData(null);
  }, [overviewMarket]);

  // Use history data or live data
  const displayOverview = isHistoryMode ? historyData : marketOverviews[overviewMarket];
  const displayLoading = isHistoryMode ? historyLoading : overviewLoading;

  const marketOverview = displayOverview;
  const marketLastUpdated = isHistoryMode ? undefined : marketLastUpdatedTimes[overviewMarket];

  const getSentimentText = (summary?: string) => {
    if (!summary) return t('common.neutral');
    const isBullish = summary.includes('牛') || summary.includes('涨') || summary.includes('Bullish') || summary.includes('Up');
    const isBearish = summary.includes('熊') || summary.includes('跌') || summary.includes('Bearish') || summary.includes('Down');
    if (isBullish) return t('common.bullish');
    if (isBearish) return t('common.bearish');
    return t('common.neutral');
  };

  return (
    <motion.div initial={{ opacity: 1 }} animate={{ opacity: 1 }} className="space-y-12">
      <section className="space-y-8">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between bg-white border border-zinc-200/60 px-8 py-6 rounded-2xl shadow-[0_2px_8px_rgb(0,0,0,0.04)] gap-4">
          <div className="flex items-center gap-3">
            <h2 className="flex items-center gap-3 text-2xl font-semibold tracking-tighter">
              <Globe size={28} className="text-emerald-500" />
              {t('market.overview')}
            </h2>
            
            <div className="flex items-center gap-2 text-sm ml-4 border-l border-zinc-200/60 pl-4">
              {marketLastUpdated && (
                <span className="text-zinc-400 hidden sm:inline-block">
                  {t('analysis.info.lastUpdated')}: {new Date(marketLastUpdated).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })}
                </span>
              )}
              {isHistoryMode && (
                <span className="text-amber-500 text-xs font-medium hidden sm:inline-block">
                  {t('market.viewing_history')}
                </span>
              )}
              <div className="relative flex items-center">
                <Calendar size={14} className="absolute left-2 text-zinc-400 pointer-events-none" />
                <select
                  value={selectedDate}
                  onChange={(e) => handleDateChange(e.target.value)}
                  className="bg-zinc-50 text-zinc-500 border border-zinc-200/80 rounded-xl pl-7 pr-2 py-1.5 text-xs focus:ring-1 focus:ring-indigo-600/50 outline-none hover:bg-zinc-100 transition-colors cursor-pointer"
                >
                  <option value="">{t('market.today')}</option>
                  {availableDates.map(date => (
                    <option key={date} value={date}>{date}</option>
                  ))}
                </select>
              </div>
              <select
                value={autoRefreshInterval}
                onChange={(e) => setAutoRefreshInterval(Number(e.target.value))}
                disabled={isHistoryMode}
                className="bg-zinc-50 text-zinc-500 border border-zinc-200/80 rounded-xl px-2 py-1.5 text-xs focus:ring-1 focus:ring-indigo-600/50 outline-none hover:bg-zinc-100 transition-colors cursor-pointer disabled:opacity-50"
              >
                <option value={0}>{t('common.no_auto_refresh')}</option>
                {[5, 15, 30, 60].map(n => (
                  <option key={n} value={n}>{t('common.every_n_min', { n })}</option>
                ))}
              </select>
              <button
                onClick={() => onFetchMarketOverview(true)}
                disabled={overviewLoading || isHistoryMode}
                className="p-1.5 rounded-xl bg-zinc-50 hover:bg-zinc-100 text-zinc-500 hover:text-zinc-950 ring-1 ring-zinc-200 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${displayLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1 rounded-2xl bg-zinc-50 p-1 border border-zinc-200" role="tablist" aria-label="Market selection">
              {(['A-Share', 'HK-Share', 'US-Share'] as Market[]).map((m) => (
                <button
                  key={m}
                  role="tab"
                  aria-selected={overviewMarket === m}
                  onClick={() => setOverviewMarket(m)}
                  className={cn(
                    "px-4 py-1.5 rounded-xl text-xs font-medium transition-all",
                    overviewMarket === m 
                      ? "bg-indigo-600 text-white shadow-sm" 
                      : "text-zinc-500 hover:text-zinc-600"
                  )}
                >
                  {m === 'A-Share' ? t('markets.aShare') : m === 'HK-Share' ? t('markets.hkShare') : t('markets.usShare')}
                </button>
              ))}
            </div>
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="flex h-10 w-10 items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-50 text-zinc-500 transition-all hover:border-indigo-600/30 hover:bg-blue-500/10 hover:text-indigo-600"
            >
              <Settings size={20} />
            </button>
            {overviewLoading && <Loader2 className="animate-spin text-emerald-500" size={20} />}
            <button
              onClick={onTriggerDailyReport}
              disabled={overviewLoading || isGeneratingReport || isSendingReport || !marketOverview || isHistoryMode}
              className={cn(
                "flex items-center gap-2 px-6 py-2.5 rounded-2xl text-sm font-medium transition-all shadow-sm",
                reportStatus === 'success' 
                  ? "bg-emerald-100 text-emerald-600 border border-emerald-600/50"
                  : reportStatus === 'error'
                  ? "bg-rose-500/20 text-rose-400 border border-rose-500/50"
                  : "bg-zinc-50 border border-zinc-200 hover:bg-zinc-100 text-zinc-600"
              )}
            >
              {isGeneratingReport ? (
                <>
                  <Loader2 className="animate-spin" size={16} />
                  {t('analysis.actions.generating_report')}
                </>
              ) : isSendingReport ? (
                <>
                  <Loader2 className="animate-spin" size={16} />
                  {t('analysis.actions.sending_to_feishu')}
                </>
              ) : reportStatus === 'success' ? (
                <>
                  <CheckCircle2 size={16} />
                  {t('analysis.actions.sent')}
                </>
              ) : (
                <>
                  <Share2 size={16} />
                  {t('header.triggerBrief')}
                </>
              )}
            </button>
          </div>
        </div>

        {overviewError && !isHistoryMode && (
          <div className="flex flex-col gap-4">
            <ErrorNotice
              title={t('common.error')}
              message={overviewError}
              onRetry={() => void onFetchMarketOverview(true)}
              onOpenSettings={() => setIsSettingsOpen(true)}
            />
          </div>
        )}

        {isHistoryMode && !historyLoading && !historyData && (
          <div className="text-center py-8 text-zinc-400 text-sm">
            {t('market.no_history')}
          </div>
        )}

        {/* Quick-start: Popular stocks for new users */}
        {!isHistoryMode && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-zinc-400 mr-1">{t('market.quick_analyze')}:</span>
            {(overviewMarket === 'A-Share' ? [
              { symbol: '600519', name: '茅台' },
              { symbol: '000858', name: '五粮液' },
              { symbol: '000001', name: '平安银行' },
              { symbol: '601318', name: '中国平安' },
              { symbol: '300750', name: '宁德时代' },
            ] : overviewMarket === 'HK-Share' ? [
              { symbol: '00700', name: '腾讯' },
              { symbol: '09988', name: '阿里巴巴' },
              { symbol: '01810', name: '小米' },
              { symbol: '09888', name: '百度' },
              { symbol: '03690', name: '美团' },
            ] : [
              { symbol: 'AAPL', name: 'Apple' },
              { symbol: 'NVDA', name: 'NVIDIA' },
              { symbol: 'TSLA', name: 'Tesla' },
              { symbol: 'MSFT', name: 'Microsoft' },
              { symbol: 'GOOGL', name: 'Google' },
            ]).map(stock => (
              <button
                key={stock.symbol}
                onClick={() => { setSymbol(stock.symbol); setMarket(overviewMarket); }}
                className="px-3 py-1.5 rounded-xl bg-white border border-zinc-200 text-xs font-medium text-zinc-600 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50/50 transition-all"
              >
                {stock.symbol} <span className="text-zinc-400">{stock.name}</span>
              </button>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          {(!marketOverview?.indices?.length && displayLoading) ? Array(5).fill(0).map((_, i) => (
            <div key={`skeleton-index-${i}`} className="h-24 skeleton rounded-2xl border border-zinc-200" />
          )) : marketOverview?.indices?.map((index, i) => (
            <div key={`index-${index.symbol || index.name}-${i}`} className="rounded-2xl border border-zinc-200 bg-white p-4">
              <p className="mb-1 text-xs font-medium text-zinc-400">{index.name}</p>
              <p className="text-lg font-medium tracking-tight text-zinc-950">{(index.price ?? 0).toLocaleString()}</p>
              <div className={cn('mt-1 flex items-center gap-1 font-mono text-xs', (index.change ?? 0) >= 0 ? 'text-indigo-600' : 'text-rose-500')}>
                {(index.change ?? 0) >= 0 ? '+' : ''}{index.changePercent ?? 0}%
              </div>
            </div>
          ))}
        </div>

        {marketOverview && (
          <>
            {/* AI-enriched sections: summary, sectors, commodities, recommendations */}
            {marketOverview.marketSummary ? (
            <>
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3 stagger-children">
              <div className="premium-card p-8 md:col-span-2">
                <p className="text-base italic leading-relaxed text-zinc-500 font-medium">"{marketOverview.marketSummary}"</p>
              </div>
              <div className="flex flex-col items-center justify-center premium-card p-8 text-center">
                <h3 className="mb-4 text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-400">{t('analysis.sentiment')}</h3>
                <div className={cn("text-4xl font-semibold tracking-tighter", 
                  getSentimentText(marketOverview.marketSummary) === t('common.bullish') ? "text-indigo-600" :
                  getSentimentText(marketOverview.marketSummary) === t('common.bearish') ? "text-rose-500" : "text-zinc-600"
                )}>
                  {getSentimentText(marketOverview.marketSummary)}
                </div>
                <p className="mt-3 text-[10px] font-medium text-zinc-400 uppercase tracking-widest">{t('header.brand')}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
              <div className="space-y-4 rounded-2xl border border-zinc-200/50 bg-white/30 p-6">
                <h3 className="flex items-center gap-2 text-sm font-medium uppercase tracking-widest text-zinc-400">
                  <LayoutGrid size={16} className="text-indigo-600" />
                  {t('market.hot_sectors')}
                </h3>
                <div className="space-y-3">
                  {marketOverview.sectorAnalysis?.map((sector, i) => (
                    <div key={`sector-${sector.name}-${i}`} className="rounded-xl bg-zinc-50/50 p-4 border border-zinc-200/60 shadow-sm hover:shadow-md transition-all group">
                      <div className="flex items-start justify-between mb-3">
                        <div className="space-y-1">
                          <span className="font-bold text-zinc-950 block">{sector.name}</span>
                          {sector.rotationStage && (
                            <span className={cn(
                              "text-[8px] px-1.5 py-0.5 rounded border font-bold uppercase tracking-widest",
                              sector.rotationStage.toLowerCase().includes('leading') ? "bg-indigo-600 text-white border-indigo-600" :
                              sector.rotationStage.toLowerCase().includes('improving') ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" :
                              sector.rotationStage.toLowerCase().includes('weakening') ? "bg-rose-500/10 text-rose-500 border-rose-500/20" :
                              "bg-zinc-100 text-zinc-500 border-zinc-200"
                            )}>
                              {sector.rotationStage}
                            </span>
                          )}
                        </div>
                        <span className={cn("text-[9px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider shadow-sm", 
                          sector.trend?.includes('涨') || sector.trend?.includes('强') || sector.trend?.includes('Up') || sector.trend?.includes('Strong') ? "bg-indigo-600 text-white" : "bg-rose-500 text-white"
                        )}>{sector.trend}</span>
                      </div>
                      
                      <div className="space-y-3">
                        <p className="text-xs text-zinc-600 leading-relaxed font-medium">{sector.conclusion}</p>
                        
                        {(sector.upstreamImpact || sector.downstreamImpact) && (
                          <div className="grid grid-cols-2 gap-3 pt-3 border-t border-zinc-100">
                            {sector.upstreamImpact && (
                              <div>
                                <p className="text-[8px] font-bold text-zinc-400 uppercase tracking-widest mb-1">Upstream</p>
                                <p className="text-[10px] text-zinc-500 leading-tight italic">{sector.upstreamImpact}</p>
                              </div>
                            )}
                            {sector.downstreamImpact && (
                              <div>
                                <p className="text-[8px] font-bold text-zinc-400 uppercase tracking-widest mb-1">Downstream</p>
                                <p className="text-[10px] text-zinc-500 leading-tight italic">{sector.downstreamImpact}</p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-4 rounded-2xl border border-zinc-200/50 bg-white/30 p-6">
                <h3 className="flex items-center gap-2 text-sm font-medium uppercase tracking-widest text-zinc-400">
                  <Coins size={16} className="text-amber-500" />
                  {t('market.commodity_trends')}
                </h3>
                <div className="space-y-3">
                  {marketOverview.commodityAnalysis?.map((item, i) => (
                    <div key={`commodity-${item.name}-${i}`} className="rounded-xl bg-zinc-50/30 p-3 border border-zinc-200/30">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-zinc-950">{item.name}</span>
                        <span className={cn("text-[10px] px-1.5 py-0.5 rounded-full font-medium uppercase", 
                          item.trend?.includes('涨') || item.trend?.includes('强') || item.trend?.includes('Up') || item.trend?.includes('Strong') ? "bg-indigo-100 text-indigo-600" : "bg-rose-500/20 text-rose-400"
                        )}>{item.trend}</span>
                      </div>
                      <p className="text-xs text-zinc-500 leading-relaxed">{item.expectation}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="space-y-4 rounded-2xl border border-zinc-200/50 bg-white/30 p-6">
              <h3 className="flex items-center gap-2 text-sm font-medium uppercase tracking-widest text-zinc-400">
                <Star size={16} className="text-blue-500" />
                {t('market.recommendations')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {marketOverview.recommendations?.map((rec, i) => (
                  <div key={`${rec.type}-${rec.name}-${i}`} className="rounded-xl bg-zinc-50/30 p-4 border border-zinc-200/30">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 font-medium uppercase">{rec.type}</span>
                      <span className="font-medium text-zinc-950">{rec.name}</span>
                    </div>
                    <p className="text-xs text-zinc-500 leading-relaxed">{rec.reason}</p>
                  </div>
                ))}
              </div>
            </div>
            </>
            ) : displayLoading ? (
              <div className="flex items-center justify-center gap-2 py-8 text-zinc-400 text-sm">
                <Loader2 className="animate-spin" size={16} />
                {t('market.loading_ai')}
              </div>
            ) : null}
          </>
        )}
      </section>

      <InstitutionalAlertPanel />

      <section className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <h2 className="flex items-center gap-2 text-xl font-medium text-zinc-950">
            <Newspaper size={20} className="text-indigo-600" />
            {t('market.news')}
            {newsLoading && <Loader2 className="w-4 h-4 animate-spin text-zinc-400 ml-2" />}
          </h2>
          <div className="space-y-4">
            {(newsLoading && !hotNews.length) ? Array(5).fill(0).map((_, i) => (
              <div key={`news-skeleton-${i}`} className="h-20 skeleton rounded-2xl border border-zinc-200" />
            )) : hotNews?.map((news, i) => (
              <a key={`news-${i}-${news.url || news.title}`} href={news.url} target="_blank" rel="noopener noreferrer" className="group block rounded-2xl border border-zinc-200 bg-white p-5 transition-all hover:border-indigo-600/30 hover:shadow-md">
                <div className="flex items-start justify-between gap-4">
                  <h3 className="text-sm font-medium text-zinc-950 transition-colors group-hover:text-indigo-600 leading-snug">{news.title}</h3>
                  {news.url && <ExternalLink size={14} className="mt-0.5 shrink-0 text-zinc-300 group-hover:text-indigo-400 transition-colors" />}
                </div>
                <div className="mt-3 flex items-center gap-3 font-mono text-[9px] uppercase tracking-widest text-zinc-400">
                  <span className="rounded bg-zinc-100 px-2 py-0.5 text-zinc-600 font-medium">{news.source}</span>
                  <span className="text-zinc-400">{news.time}</span>
                </div>
              </a>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          {overviewMarket === 'A-Share' && (
            <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-zinc-950 mb-4">
                <Coins size={18} className="text-indigo-600" />
                {t('analysis.panel.institutional_consensus', 'Institutional Flow')}
                {flowsLoading && <Loader2 className="w-4 h-4 animate-spin text-zinc-400 ml-2" />}
              </h2>
              
              {northboundFlow && overviewMarket === 'A-Share' && (
                <div className="mb-5 flex items-center justify-between p-3 bg-white rounded-xl border border-zinc-100">
                  <span className="text-xs font-medium text-zinc-500">北向资金 (Northbound)</span>
                  <span className={cn("text-xs font-semibold px-2 py-1 rounded bg-zinc-50", 
                    String(northboundFlow['净买额']).includes('-') ? "text-rose-500" : "text-emerald-500"
                  )}>
                    {northboundFlow['净买额']} 亿元
                  </span>
                </div>
              )}
              
              <div className="space-y-3">
                <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-400">Top Sectors (Inflow)</span>
                {sectorFlow?.topInflows?.map((sector: any, i: number) => (
                  <div key={`sector-flow-${sector['行业'] || 'unknown'}-${i}`} className="flex items-center justify-between">
                    <span className="text-sm font-medium text-zinc-700">{sector['行业']}</span>
                    <div className="flex flex-col items-end">
                      <span className="text-xs font-bold text-rose-500">{sector['主力净流入-净额']}</span>
                      <span className="text-[10px] text-zinc-400">{sector['涨跌幅']}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <h2 className="flex items-center gap-2 text-xl font-medium text-zinc-950">
            <TrendingUp size={20} className="text-amber-500" />
            {t('market.trending_search')}
          </h2>
          <div className="grid grid-cols-1 gap-3">
            {[
              { symbol: '600519', name: '贵州茅台', market: "A-Share" as Market },
              { symbol: '300750', name: '宁德时代', market: "A-Share" as Market },
              { symbol: '700', name: '腾讯控股', market: "HK-Share" as Market },
              { symbol: 'NVDA', name: '英伟达', market: "US-Share" as Market },
            ].map((stock) => (
              <button key={stock.symbol} onClick={() => { setSymbol(stock.symbol); setMarket(stock.market); }} className="group flex items-center justify-between rounded-2xl border border-zinc-200 bg-white p-4 text-left transition-all hover:border-indigo-600/50 shadow-sm">
                <div>
                  <p className="mb-0.5 font-mono text-[10px] uppercase text-zinc-400">{stock.market}</p>
                  <p className="font-medium text-zinc-950 transition-colors group-hover:text-indigo-600">{stock.symbol}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-zinc-400">{stock.name}</p>
                  <Search size={14} className="ml-auto mt-1 text-zinc-400" />
                </div>
              </button>
            ))}
          </div>
        </div>
      </section>
    </motion.div>
  );
});
