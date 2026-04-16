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
                <Award size={14} />
                绝对安全边际 (Deep Value)
              </div>
            )}
            {analysis.moatAnalysis && analysis.moatAnalysis.strength !== "None" && (
              <div className="px-3 py-1.5 rounded-xl bg-indigo-600/10 border border-indigo-600/20 text-[10px] font-bold text-indigo-600 uppercase tracking-widest flex items-center gap-2 shadow-sm">
                <ShieldCheck size={14} />
                护城河: {analysis.moatAnalysis.strength === "Wide" ? "宽阔" : "狭窄"} ({analysis.moatAnalysis.type})
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
                叙事一致性: {analysis.narrativeConsistency.score}%
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
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-400">最后更新 (Last Sync)</p>
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
      <div className="grid grid-cols-1 gap-6 border-t border-zinc-200/50 pt-8 md:grid-cols-2">
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-500">
            <BarChart3 size={16} className="text-emerald-500" />
            技术面分析
          </div>
          <p className="text-sm leading-relaxed text-zinc-500">{analysis.technicalAnalysis}</p>
        </div>
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium text-zinc-500">
            <PieChart size={16} className="text-blue-500" />
            基本面分析 (结合安全边际)
          </div>
          <p className="text-sm leading-relaxed text-zinc-500">{analysis.fundamentalAnalysis}</p>
        </div>
      </div>

      {/* Technical Indicators Grid (NEW) */}
      {analysis.technicalIndicators && (
        <div className="mt-8 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5 border-t border-zinc-200/50 pt-8">
          <div className="p-3 rounded-2xl bg-zinc-50/40 border border-zinc-200/40">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-1">均线 MA5 / MA20 / MA60</p>
            <p className="text-sm font-mono font-medium text-zinc-700">
              {analysis.technicalIndicators.ma5} / {analysis.technicalIndicators.ma20} / {analysis.technicalIndicators.ma60}
            </p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/40 border border-zinc-200/40">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-1">短期支撑 / 阻力</p>
            <p className="text-sm font-mono font-medium text-zinc-700">
              {analysis.technicalIndicators.supportShort} / {analysis.technicalIndicators.resistanceShort}
            </p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/40 border border-zinc-200/40">
            <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 mb-1">长期支撑 / 阻力</p>
            <p className="text-sm font-mono font-medium text-zinc-700">
              {analysis.technicalIndicators.supportLong} / {analysis.technicalIndicators.resistanceLong}
            </p>
          </div>
          <div className="p-3 rounded-2xl bg-emerald-50/40 border border-emerald-200/30">
            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-600/60 mb-1">5日 / 20日 均量</p>
            <p className="text-sm font-mono font-medium text-emerald-700">
              {analysis.technicalIndicators.avgVolume5} / {analysis.technicalIndicators.avgVolume20}
            </p>
          </div>
          <div className="p-3 rounded-2xl bg-blue-50/40 border border-blue-200/30">
            <p className="text-[10px] font-bold uppercase tracking-widest text-blue-600/60 mb-1">技术形态感知</p>
            <p className="text-sm font-medium text-blue-700 truncate">
              {analysis.technicalIndicators.ma5 && analysis.stockInfo?.price && analysis.stockInfo.price > analysis.technicalIndicators.ma5 ? '多头占优' : '空头占优'}
            </p>
          </div>
        </div>
      )}

      {/* Fundamentals Grid */}
      {analysis.fundamentals && (
        <div className="mt-8 grid grid-cols-2 gap-4 md:grid-cols-4 lg:grid-cols-6 border-t border-zinc-200/50 pt-8">
          <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">市盈率 PE</p>
            <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.pe}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">市净率 PB</p>
            <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.pb}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">净资产收益率 ROE</p>
            <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.roe}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">每股收益 EPS</p>
            <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.eps}</p>
          </div>
          <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">营收增长</p>
            <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.revenueGrowth}</p>
          </div>
          <div className="p-3 rounded-2xl bg-indigo-50 border border-indigo-100">
            <p className="text-[10px] font-medium uppercase tracking-widest text-emerald-500/60 mb-1">估值水位</p>
            <p className="text-sm font-medium text-indigo-600">{analysis.fundamentals.valuationPercentile}</p>
          </div>
          {analysis.fundamentals.netProfitGrowth && (
            <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
              <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">净利增长</p>
              <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.netProfitGrowth}</p>
            </div>
          )}
          {analysis.fundamentals.debtToEquity && (
            <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
              <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">资产负债率</p>
              <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.debtToEquity}</p>
            </div>
          )}
          {analysis.fundamentals.grossMargin && (
            <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
              <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">毛利率</p>
              <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.grossMargin}</p>
            </div>
          )}
          {analysis.fundamentals.netMargin && (
            <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
              <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">净利率</p>
              <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.netMargin}</p>
            </div>
          )}
          {analysis.fundamentals.dividendYield && (
            <div className="p-3 rounded-2xl bg-zinc-50/30 border border-zinc-200/30">
              <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">股息率</p>
              <p className="text-sm font-medium text-zinc-600">{analysis.fundamentals.dividendYield}</p>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
