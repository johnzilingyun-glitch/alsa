import React, { useState } from 'react';
import {
  BarChart3, PieChart, TrendingUp, TrendingDown, Clock, Info,
  Award, ShieldCheck, MessageSquare, History, RefreshCcw,
  LayoutGrid, CheckCircle2, Coins, AlertTriangle,
  ExternalLink, Star, ChevronDown, ChevronUp
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import type { StockAnalysis } from '../../types';

interface StockHeroCardProps {
  analysis: StockAnalysis;
  isStarred?: boolean;
  onToggleWatchlist?: () => void;
}

/** Collapsible markdown section with max-height toggle */
const AnalysisMarkdown = ({ content, maxLines = 12 }: { content: string; maxLines?: number }) => {
  const [expanded, setExpanded] = useState(false);
  if (!content) return null;
  
  return (
    <div className="relative">
      <div 
        className={cn(
          "prose prose-sm prose-zinc max-w-none",
          "prose-headings:text-zinc-800 prose-headings:font-semibold prose-headings:tracking-tight",
          "prose-h1:text-base prose-h1:mt-4 prose-h1:mb-2",
          "prose-h2:text-sm prose-h2:mt-3 prose-h2:mb-1.5",
          "prose-h3:text-xs prose-h3:mt-2 prose-h3:mb-1",
          "prose-p:text-[13px] prose-p:leading-[1.7] prose-p:text-zinc-600 prose-p:my-1.5",
          "prose-strong:text-zinc-800 prose-strong:font-semibold",
          "prose-table:text-[12px] prose-th:px-2 prose-th:py-1.5 prose-th:text-left prose-th:font-semibold prose-th:text-zinc-700 prose-th:bg-zinc-50 prose-th:border-b prose-th:border-zinc-200",
          "prose-td:px-2 prose-td:py-1 prose-td:text-zinc-600 prose-td:border-b prose-td:border-zinc-100",
          "prose-li:text-[13px] prose-li:text-zinc-600 prose-li:my-0.5",
          "prose-hr:my-3 prose-hr:border-zinc-200/60",
          !expanded && `max-h-[${maxLines * 1.7}rem] overflow-hidden`
        )}
        style={!expanded ? { maxHeight: `${maxLines * 1.5}rem` } : undefined}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
      {!expanded && (
        <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-white to-transparent pointer-events-none" />
      )}
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-indigo-500 hover:text-indigo-700 transition-colors"
      >
        {expanded ? <><ChevronUp size={14} /> 收起</> : <><ChevronDown size={14} /> 展开全部</>}
      </button>
    </div>
  );
};

export function StockHeroCard({ analysis, isStarred, onToggleWatchlist }: StockHeroCardProps) {
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
            {onToggleWatchlist && (
              <button
                onClick={(e) => { e.stopPropagation(); onToggleWatchlist(); }}
                className={cn(
                  "ml-4 p-2 rounded-xl border transition-all duration-300",
                  isStarred 
                    ? "bg-amber-500 text-white border-amber-400 shadow-lg shadow-amber-500/20" 
                    : "bg-white text-zinc-300 border-zinc-200 hover:border-amber-400 hover:text-amber-500"
                )}
                title={isStarred ? "从收藏中移除" : "添加到收藏"}
              >
                <Star size={20} fill={isStarred ? "currentColor" : "none"} strokeWidth={2} />
              </button>
            )}
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
            <AnalysisMarkdown content={analysis.technicalAnalysis} />
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
             <AnalysisMarkdown content={analysis.fundamentalAnalysis} />
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
