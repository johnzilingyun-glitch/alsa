import React from 'react';
import {
  BarChart3, PieChart, TrendingUp, TrendingDown, Clock, Info,
  Award, ShieldCheck, MessageSquare, History, RefreshCcw,
  LayoutGrid, CheckCircle2, Coins, AlertTriangle,
  ExternalLink,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import type { StockAnalysis } from '../../types';

interface StockHeroCardProps {
  analysis: StockAnalysis;
}

const parseStructuralText = (text: string) => {
  if (!text) return null;
  // Regex to match 【Title】content
  const parts = text.split(/(【.*?】)/).filter(Boolean);
  if (parts.length <= 1) return <p className="text-[13px] leading-[1.8] text-zinc-600">{text}</p>;

  const elements = [];
  let currentTitle = '';
  for (let i = 0; i < parts.length; i++) {
    if (parts[i].startsWith('【') && parts[i].endsWith('】')) {
      currentTitle = parts[i].slice(1, -1);
    } else {
      if (currentTitle) {
        elements.push(
          <div key={i} className="mb-4 last:mb-0">
            <span className="inline-block px-2.5 py-1 rounded-xl text-[10px] font-bold tracking-wider bg-zinc-100/80 text-indigo-700 mr-2 mb-1.5 border border-zinc-200/50 shadow-sm">
              {currentTitle}
            </span>
            <span className="text-[13px] leading-[1.8] text-zinc-600 block">
              {parts[i].trim()}
            </span>
          </div>
        );
        currentTitle = '';
      } else {
        elements.push(<p key={i} className="text-[13px] leading-[1.8] text-zinc-600 mb-3">{parts[i].trim()}</p>);
      }
    }
  }
  return <div className="space-y-1">{elements}</div>;
};

export function StockHeroCard({ analysis }: StockHeroCardProps) {
  const { t } = useTranslation();

  return (
    <div className="premium-card p-6 sm:p-10 md:p-14 relative overflow-hidden">
      <div className="absolute top-0 right-0 p-12 opacity-[0.02] pointer-events-none hidden sm:block">
        <BarChart3 size={240} className="text-zinc-900" />
      </div>
      
      {/* Stock Header */}
      <div className="mb-8 sm:mb-14 flex flex-wrap items-end justify-between gap-6 sm:gap-10 relative z-10">
        <div className="space-y-4 sm:space-y-6">
          <div className="flex items-center gap-3 sm:gap-4 flex-wrap">
            <span className="rounded-xl bg-zinc-100 px-3 sm:px-4 py-1.5 font-mono text-xs font-bold uppercase tracking-[0.2em] text-zinc-500 border border-zinc-200/60 shadow-sm">
              {analysis.stockInfo?.market}
            </span>
            <h2 className="text-3xl sm:text-5xl font-bold tracking-tighter text-zinc-950">{analysis.stockInfo?.name}</h2>
            <span className="font-mono text-lg sm:text-2xl font-medium text-zinc-400 tracking-tighter">{analysis.stockInfo?.symbol}</span>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {analysis.isDeepValue && (
              <div className="px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[10px] font-bold text-amber-600 uppercase tracking-widest flex items-center gap-2 shadow-sm">
                < Award size={14} />
                {t('analysis.info.deep_value')}
              </div>
            )}
            {analysis.moatAnalysis && analysis.moatAnalysis.strength !== "None" && (
              <div className="px-3 py-1.5 rounded-xl bg-indigo-600/10 border border-indigo-600/20 text-[10px] font-bold text-indigo-600 uppercase tracking-widest flex items-center gap-2 shadow-sm">
                <ShieldCheck size={14} />
                {t('analysis.info.moat')}: {analysis.moatAnalysis.strength === "Wide" ? t('analysis.moat.wide') : t('analysis.moat.narrow')} ({analysis.moatAnalysis.type})
              </div>
            )}
            {analysis.narrativeConsistency && (
              <div className={cn(
                "px-3 py-1.5 rounded-xl border text-[10px] font-bold uppercase tracking-widest flex items-center gap-2 shadow-sm",
                analysis.narrativeConsistency.score >= 80 ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-600" :
                analysis.narrativeConsistency.score >= 50 ? "bg-amber-500/10 border-amber-500/20 text-amber-600" :
                "bg-rose-500/10 border-rose-500/20 text-rose-600"
              )}>
                <MessageSquare size={14} />
                {t('analysis.info.narrative_consistency')}: {analysis.narrativeConsistency.score}%
              </div>
            )}
          </div>
          
          <div className="flex items-baseline gap-8 pt-4">
            <span className="text-5xl sm:text-8xl font-bold tracking-tighter text-zinc-950">
              {analysis.stockInfo?.price?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              <span className="ml-2 sm:ml-4 text-xl sm:text-3xl font-medium uppercase text-zinc-300 tracking-tight">{analysis.stockInfo?.currency}</span>
            </span>
            <div className={cn(
              'flex items-center gap-2 sm:gap-3 text-xl sm:text-3xl font-bold tracking-tight px-4 sm:px-6 py-2 rounded-[1.5rem] border shadow-sm', 
              (analysis.stockInfo?.change ?? 0) >= 0 ? 'text-emerald-600 bg-emerald-50 border-emerald-100' : 'text-rose-500 bg-rose-50 border-rose-100'
            )}>
              {(analysis.stockInfo?.change ?? 0) >= 0 ? <TrendingUp size={24} className="sm:w-8 sm:h-8" /> : <TrendingDown size={24} className="sm:w-8 sm:h-8" />}
              <span>{(analysis.stockInfo?.change ?? 0) >= 0 ? '+' : ''}{analysis.stockInfo?.change}</span>
              <span className="text-base sm:text-xl opacity-60">({analysis.stockInfo?.changePercent}%)</span>
            </div>
          </div>
        </div>
        
        <div className="text-right space-y-2 relative z-10">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-400">{t('analysis.info.lastUpdated')} (Last Sync)</p>
          <p className="text-base font-semibold text-zinc-500 flex items-center justify-end gap-2">
            <Clock size={16} className="text-zinc-300" />
            {analysis.stockInfo?.lastUpdated}
          </p>
          <div className="group relative inline-flex items-center gap-1 cursor-help">
            <Info size={12} className="text-zinc-300" />
            <span className="text-[9px] text-zinc-400 uppercase tracking-widest">{t('analysis.info.data_sources')}</span>
            <div className="absolute bottom-full right-0 mb-2 w-56 p-3 rounded-xl bg-zinc-900 text-white text-[10px] leading-relaxed opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity z-20 shadow-xl">
              <p className="font-semibold mb-1.5">{t('analysis.info.data_pipeline')}</p>
              <ul className="space-y-1 text-zinc-300">
                <li>• Yahoo Finance — {t('analysis.info.price_fundamentals')}</li>
                <li>• Sina Finance — {t('analysis.info.ashare_fallback')}</li>
                <li>• Google Gemini AI — {t('analysis.info.ai_analysis')}</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      {/* Technical & Fundamental Analysis */}
      <div className="grid grid-cols-1 gap-8 border-t border-zinc-200/50 pt-8 md:grid-cols-2">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-bold text-zinc-800">
              <BarChart3 size={16} className="text-emerald-500" />
              {t('analysis.tabs.technical')}
            </div>
          </div>
          <div className="bg-white/50 p-4 rounded-3xl border border-zinc-100/80 shadow-sm">
            {parseStructuralText(analysis.technicalAnalysis)}
          </div>
        </div>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-bold text-zinc-800">
              <PieChart size={16} className="text-blue-500" />
              {t('analysis.tabs.fundamental')}
            </div>
            <div className="px-2 py-0.5 rounded-lg bg-zinc-100 text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              {t('analysis.info.mos_combined')}
            </div>
          </div>
          <div className="bg-white/50 p-4 rounded-3xl border border-zinc-100/80 shadow-sm">
             {parseStructuralText(analysis.fundamentalAnalysis)}
          </div>
        </div>
      </div>

      {/* Technical Indicators Grid (NEW) */}
      {analysis.technicalIndicators && (
        <div className="mt-8 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5 border-t border-zinc-200/50 pt-8">
          <div className="p-3 rounded-2xl bg-zinc-50/40 border border-zinc-200/40">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.technical.ma_ribbon')}</p>
            <p className="text-sm font-mono font-medium text-zinc-700">
              {analysis.technicalIndicators.ma5} / {analysis.technicalIndicators.ma20} / {analysis.technicalIndicators.ma60}
            </p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/40 border border-zinc-200/40">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.technical.pivot_short')}</p>
            <p className="text-sm font-mono font-medium text-zinc-700">
              {analysis.technicalIndicators.supportShort} / {analysis.technicalIndicators.resistanceShort}
            </p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/40 border border-zinc-200/40">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.technical.pivot_long')}</p>
            <p className="text-sm font-mono font-medium text-zinc-700">
              {analysis.technicalIndicators.supportLong} / {analysis.technicalIndicators.resistanceLong}
            </p>
          </div>
          <div className="p-3 rounded-2xl bg-emerald-50/40 border border-emerald-200/30">
            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-600/60 mb-1">{t('analysis.technical.avg_volume')}</p>
            <p className="text-sm font-mono font-medium text-emerald-700">
              {analysis.technicalIndicators.avgVolume5} / {analysis.technicalIndicators.avgVolume20}
            </p>
          </div>
          <div className="p-3 rounded-2xl bg-blue-50/40 border border-blue-200/30">
            <p className="text-[10px] font-bold uppercase tracking-widest text-blue-600/60 mb-1">{t('analysis.technical.sentiment')}</p>
            <p className="text-sm font-medium text-blue-700 truncate">
              {analysis.technicalIndicators.ma5 && analysis.stockInfo?.price && analysis.stockInfo.price > analysis.technicalIndicators.ma5 ? t('analysis.technical.bullish_bias') : t('analysis.technical.bearish_bias')}
            </p>
          </div>
        </div>
      )}

      {/* Fundamentals Grid */}
      {analysis.fundamentals && (
        <div className="mt-8 grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-6 gap-3 border-t border-zinc-200/50 pt-8">
          {/* Top Line Metrics */}
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.market_cap')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.marketCap || "-"}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.revenue')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.revenue || "-"}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.net_profit')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.netProfit || "-"}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.non_gaap_net_profit')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.nonGaapNetProfit || "-"}</p>
          </div>

          {/* Standard Ratios */}
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.pe')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.pe}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.pb')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.pb}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.roe')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.roe}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.eps')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.eps}</p>
          </div>
          
          {/* Growth & Structure */}
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.debt_to_equity')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.debtToEquity || "-"}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/50 border border-zinc-200/30 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.fundamental_metrics.revenue_growth')}</p>
            <p className="text-sm font-semibold text-zinc-700">{analysis.fundamentals.revenueGrowth}</p>
          </div>

          {/* Dividends */}
          <div className="p-3 rounded-2xl bg-orange-50/50 border border-orange-100 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-orange-500/80 mb-1">{t('analysis.fundamental_metrics.dividend')}</p>
            <p className="text-sm font-semibold text-orange-700">{analysis.fundamentals.dividend || "-"}</p>
          </div>
          <div className="p-3 rounded-2xl bg-orange-50/50 border border-orange-100 font-mono">
            <p className="text-[10px] font-medium uppercase tracking-widest text-orange-500/80 mb-1">{t('analysis.fundamental_metrics.dividend_yield')}</p>
            <p className="text-sm font-semibold text-orange-700">{analysis.fundamentals.dividendYield || "-"}</p>
          </div>

          <div className="p-3 rounded-2xl bg-indigo-50 border border-indigo-100 font-mono lg:col-span-2 xl:col-span-6 flex items-center justify-between">
             <div className="flex items-center gap-3">
               <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
               <p className="text-[11px] font-medium uppercase tracking-widest text-emerald-600">{t('analysis.fundamental_metrics.valuation_percentile')}</p>
             </div>
             <p className="text-sm font-bold text-indigo-700">{analysis.fundamentals.valuationPercentile}</p>
          </div>
        </div>
      )}

    </div>
  );
}
