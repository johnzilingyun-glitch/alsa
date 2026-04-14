import React from 'react';
import { Target, TrendingUp, TrendingDown, AlertTriangle, BarChart3, Zap } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import type { BacktestTimeSeries, SystematicBias, StockAnalysis } from '../../types';

interface PredictionAccuracyProps {
  timeSeries: BacktestTimeSeries;
  bias: SystematicBias | null;
  previousAnalysis: StockAnalysis | null;
  currentSentiment: string;
}

function getAccuracyColor(accuracy: number) {
  if (accuracy >= 70) return 'text-emerald-600 bg-emerald-50 border-emerald-100';
  if (accuracy >= 40) return 'text-amber-600 bg-amber-50 border-amber-100';
  return 'text-rose-500 bg-rose-50 border-rose-100';
}

function getAccuracyBarColor(accuracy: number) {
  if (accuracy >= 70) return 'bg-emerald-500';
  if (accuracy >= 40) return 'bg-amber-500';
  return 'bg-rose-500';
}

export function PredictionAccuracy({ timeSeries, bias, previousAnalysis, currentSentiment }: PredictionAccuracyProps) {
  const { t } = useTranslation();
  const { entries, overallAccuracy, directionAccuracy, profitFactor, sharpeRatio, longestWinStreak, maxConsecutiveLosses } = timeSeries;

  if (entries.length === 0) return null;

  const previousSentiment = previousAnalysis?.sentiment;
  const previousRecommendation = previousAnalysis?.recommendation;
  const sentimentChanged = previousSentiment && previousSentiment !== currentSentiment;

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-medium uppercase tracking-widest text-zinc-500">
          <Target size={16} className="text-indigo-500" />
          {t('analysis.prediction.track_record')}
        </h3>
        <span className="text-[10px] text-zinc-400">
          {t('analysis.prediction.based_on', { count: entries.length })}
        </span>
      </div>

      {/* Overall Accuracy Badge */}
      <div className="flex items-center gap-4">
        <div className={cn('flex items-center gap-2 rounded-2xl border px-4 py-2 text-2xl font-bold', getAccuracyColor(overallAccuracy))}>
          {overallAccuracy}%
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-zinc-700">{t('analysis.prediction.overall_accuracy')}</p>
          <p className="text-[10px] text-zinc-400">{t('analysis.prediction.accuracy_formula')}</p>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="p-3 rounded-xl bg-zinc-50/50 border border-zinc-200/30 space-y-1">
          <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400">{t('analysis.prediction.direction')}</p>
          <div className="flex items-center gap-1.5">
            <div className="flex-1 h-1.5 rounded-full bg-zinc-200 overflow-hidden">
              <div className={cn('h-full rounded-full', getAccuracyBarColor(directionAccuracy))} style={{ width: `${Math.min(directionAccuracy, 100)}%` }} />
            </div>
            <span className="text-xs font-semibold text-zinc-600">{Math.round(directionAccuracy)}%</span>
          </div>
        </div>
        <div className="p-3 rounded-xl bg-zinc-50/50 border border-zinc-200/30 space-y-1">
          <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400">{t('analysis.prediction.profit_factor')}</p>
          <p className={cn('text-sm font-semibold', profitFactor >= 1.5 ? 'text-emerald-600' : profitFactor >= 1 ? 'text-amber-600' : 'text-rose-500')}>
            {profitFactor === Infinity ? '∞' : profitFactor.toFixed(2)}
          </p>
        </div>
        <div className="p-3 rounded-xl bg-zinc-50/50 border border-zinc-200/30 space-y-1">
          <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400">{t('analysis.prediction.sharpe_ratio')}</p>
          <p className={cn('text-sm font-semibold', sharpeRatio > 0 ? 'text-emerald-600' : 'text-rose-500')}>
            {sharpeRatio.toFixed(2)}
          </p>
        </div>
        <div className="p-3 rounded-xl bg-zinc-50/50 border border-zinc-200/30 space-y-1">
          <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400">{t('analysis.prediction.streaks')}</p>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-emerald-600 font-semibold flex items-center gap-0.5">
              <Zap size={10} /> {longestWinStreak}W
            </span>
            <span className="text-rose-500 font-semibold">{maxConsecutiveLosses}L</span>
          </div>
        </div>
      </div>

      {/* Sentiment Trend */}
      {sentimentChanged && previousRecommendation && (
        <div className="flex items-center gap-3 p-3 rounded-xl bg-indigo-50/60 border border-indigo-100">
          {currentSentiment === 'Bullish' ? (
            <TrendingUp size={16} className="text-emerald-500 shrink-0" />
          ) : currentSentiment === 'Bearish' ? (
            <TrendingDown size={16} className="text-rose-500 shrink-0" />
          ) : (
            <BarChart3 size={16} className="text-zinc-400 shrink-0" />
          )}
          <p className="text-xs text-zinc-600">
            <span className="font-medium">{t('analysis.prediction.sentiment_shift')}:</span>{' '}
            <span className={cn(
              'font-semibold',
              previousSentiment === 'Bullish' ? 'text-emerald-600' : previousSentiment === 'Bearish' ? 'text-rose-500' : 'text-zinc-500'
            )}>
              {previousSentiment}
            </span>
            {' → '}
            <span className={cn(
              'font-semibold',
              currentSentiment === 'Bullish' ? 'text-emerald-600' : currentSentiment === 'Bearish' ? 'text-rose-500' : 'text-zinc-500'
            )}>
              {currentSentiment}
            </span>
            <span className="text-zinc-400 ml-2">({previousRecommendation} → {t('analysis.prediction.current')})</span>
          </p>
        </div>
      )}

      {/* Bias Warning */}
      {bias?.hasBias && (
        <div className={cn(
          'flex items-start gap-2 p-3 rounded-xl border text-xs',
          bias.severity === 'high' ? 'bg-rose-50 border-rose-200 text-rose-600' :
          bias.severity === 'medium' ? 'bg-amber-50 border-amber-200 text-amber-600' :
          'bg-zinc-50 border-zinc-200 text-zinc-500'
        )}>
          <AlertTriangle size={14} className="mt-0.5 shrink-0" />
          <p>
            <span className="font-semibold">{t('analysis.prediction.bias_detected')}:</span>{' '}
            {bias.biasType === 'bullish_drift' ? t('analysis.prediction.bullish_drift') : t('analysis.prediction.bearish_drift')}
            {' '}({bias.consecutiveCount} {t('analysis.prediction.consecutive')})
          </p>
        </div>
      )}
    </div>
  );
}
