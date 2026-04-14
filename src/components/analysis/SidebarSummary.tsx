import React from 'react';
import { ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import type { StockAnalysis } from '../../types';

interface SidebarSummaryProps {
  analysis: StockAnalysis;
}

export function SidebarSummary({ analysis }: SidebarSummaryProps) {
  const { t } = useTranslation();

  return (
    <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
      <div className="space-y-4 premium-card p-8">
        <h3 className="flex items-center gap-2 text-lg font-medium text-zinc-950">
          {t('analysis.info.summary')}
        </h3>
        <p className="text-sm leading-relaxed text-zinc-500 font-medium">{analysis.summary}</p>
      </div>

      {analysis.tradingPlan && (
        <div className={cn(
          "space-y-4 rounded-2xl p-8 border transition-all duration-500",
          analysis.tradingPlan.entryPrice === '不推荐' 
            ? "border-rose-500/20 bg-rose-500/5 shadow-[0_0_40px_-15px_rgba(244,63,94,0.1)]" 
            : "border-indigo-100 bg-indigo-600/5 shadow-[0_0_40px_-15px_rgba(16,185,129,0.1)]"
        )}>
          <h3 className={cn(
            "flex items-center gap-2 text-xl font-semibold tracking-tight",
            analysis.tradingPlan.entryPrice === '不推荐' ? "text-rose-400" : "text-indigo-600"
          )}>
            {t('analysis.conference.execution_plan')} {analysis.tradingPlan.entryPrice === '不推荐' && `(${t('analysis.scenarios.low')})`}
          </h3>
          {analysis.tradingPlan.entryPrice !== '不推荐' ? (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
              <div className="p-3 rounded-2xl bg-white border border-zinc-200">
                <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.conference.entry_price')}</p>
                <p className="text-sm font-medium text-indigo-600">{analysis.tradingPlan.entryPrice}</p>
              </div>
              <div className="p-3 rounded-2xl bg-white border border-zinc-200">
                <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.conference.target_price')}</p>
                <p className="text-sm font-medium text-indigo-600">{analysis.tradingPlan.targetPrice}</p>
              </div>
              <div className="p-3 rounded-2xl bg-white border border-zinc-200">
                <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.conference.stop_loss')}</p>
                <p className="text-sm font-medium text-rose-400">{analysis.tradingPlan.stopLoss}</p>
              </div>
            </div>
          ) : (
            <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-center">
              <p className="text-sm font-medium text-rose-400">当前估值或风险不符合安全边际要求，暂不推荐买入计划。</p>
            </div>
          )}
          <div className="p-4 rounded-2xl bg-white border border-zinc-200">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-2">{t('analysis.conference.tactical_strategy')}</p>
            <p className="text-sm leading-relaxed text-zinc-500 italic">{analysis.tradingPlan.strategy}</p>
          </div>
          {analysis.tradingPlan.strategyRisks && (
            <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20">
              <p className="text-[10px] font-medium uppercase tracking-widest text-rose-400 mb-2 flex items-center gap-2">
                {t('analysis.conference.risk_warning')}
              </p>
              <p className="text-xs text-rose-200/80 leading-relaxed italic">
                {analysis.tradingPlan.strategyRisks}
              </p>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
