import React, { useState } from 'react';
import { ExternalLink, Target, CheckCircle2, Bell, BellRing } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import type { StockAnalysis, Market } from '../../types';
import { alertsClient } from '../../services/api/alertsClient';
import { buildSignalAlertFromAnalysis } from '../../utils/signalAction';
import { useUIStore } from '../../stores/useUIStore';
import { useConfigStore } from '../../stores/useConfigStore';
import { useMarketStore } from '../../stores/useMarketStore';

interface SidebarSummaryProps {
  analysis: StockAnalysis;
}

export function SidebarSummary({ analysis }: SidebarSummaryProps) {
  const { t } = useTranslation();
  const [isAdding, setIsAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [createdAlertId, setCreatedAlertId] = useState<string | null>(null);
  const [showMonitorConfirm, setShowMonitorConfirm] = useState(false);
  const [monitoringEnabled, setMonitoringEnabled] = useState(false);
  const [isEnablingMonitor, setIsEnablingMonitor] = useState(false);
  const showToast = useUIStore(s => s.showToast);
  const feishuWebhookUrl = useConfigStore(s => s.feishuWebhookUrl);
  const setAlerts = useMarketStore(s => s.setAlerts);
  const isNotRecommended = String(analysis.tradingPlan?.entryPrice || '').includes('不推荐') || 
                          String(analysis.tradingPlan?.entryPrice || '').includes('Not Recommended');

  // Entry display: surface a "现价 / 区间待定" hint when the model leaves entryPrice blank.
  const _entryPx = analysis.stockInfo?.price;
  const entryDisplay = /\d/.test(String(analysis.tradingPlan?.entryPrice ?? ''))
    ? analysis.tradingPlan?.entryPrice
    : (_entryPx ? `现价 ${_entryPx} / 区间待定` : '现价 / 区间待定');

  const handleAddToSignalCenter = async () => {
    if (!analysis.tradingPlan || !analysis.stockInfo) return;
    setIsAdding(true);
    try {
      // Shared no-fabrication builder: hardened price parsing (percentages,
      // hedged text and ranges are handled) + action derivation/normalization
      // from tradingPlan.action / analysis.recommendation.
      const built = buildSignalAlertFromAnalysis(analysis);
      if (!built.ok) {
        showToast(built.reason, 'error');
        return;
      }

      const result = await alertsClient.create(built.draft);
      setAdded(true);
      setCreatedAlertId(result.alert_id);
      setShowMonitorConfirm(true);
      // Optimistically push the created alert into the store so Signal Center shows it
      // instantly, even if the user opens it before a fresh GET completes.
      const cur = useMarketStore.getState().searchAlerts || [];
      setAlerts([result, ...cur.filter((a) => a.alert_id !== result.alert_id)]);
      // Reconcile with backend (authoritative list)
      alertsClient.list().then(r => setAlerts(r.items || [])).catch(() => {});
      showToast('已添加至信号中心，请确认是否启动实时监控', 'success');
    } catch (e) {
      showToast('添加失败: ' + (e instanceof Error ? e.message : String(e)), 'error');
    } finally {
      setIsAdding(false);
    }
  };

  const handleEnableMonitoring = async () => {
    if (!createdAlertId) return;
    setIsEnablingMonitor(true);
    try {
      // Extract thesis and invalidation criteria from the analysis
      const thesis = analysis.summary || '';
      const invalidation = analysis.tradingPlan?.strategyRisks || '';

      await alertsClient.enableMonitoring(createdAlertId, {
        feishu_webhook_url: feishuWebhookUrl || undefined,
        thesis: thesis.slice(0, 500),
        invalidation_criteria: invalidation.slice(0, 500),
      });
      setMonitoringEnabled(true);
      setShowMonitorConfirm(false);
      showToast('✅ 信号监控已启动！价格触发时将通过飞书实时通知', 'success');
    } catch (e) {
      showToast('启动监控失败: ' + (e instanceof Error ? e.message : String(e)), 'error');
    } finally {
      setIsEnablingMonitor(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
      <div className="space-y-4 premium-card p-8">
        <h3 className="flex items-center gap-2 text-lg font-medium text-zinc-950">
          {t('analysis.info.summary')}
        </h3>
        <div className="text-sm leading-relaxed text-zinc-500 font-medium prose prose-sm prose-zinc max-w-none prose-p:my-1 prose-strong:text-zinc-700">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{analysis.summary || ''}</ReactMarkdown>
        </div>
      </div>

      {analysis.tradingPlan && (
        <div className={cn(
          "space-y-4 rounded-2xl p-8 border transition-all duration-500",
          isNotRecommended 
            ? "border-rose-500/20 bg-rose-500/5 shadow-[0_0_40px_-15px_rgba(244,63,94,0.1)]" 
            : "border-indigo-100 bg-indigo-600/5 shadow-[0_0_40px_-15px_rgba(16,185,129,0.1)]"
        )}>
          <div className="flex items-center justify-between mb-2">
            <h3 className={cn(
              "flex items-center gap-2 text-xl font-semibold tracking-tight",
              isNotRecommended ? "text-rose-400" : "text-indigo-600"
            )}>
              {t('analysis.conference.execution_plan')} {isNotRecommended && `(${t('analysis.scenarios.low')})`}
            </h3>
            {!isNotRecommended && (
              <button
                onClick={handleAddToSignalCenter}
                disabled={isAdding || added}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all",
                  monitoringEnabled ? "bg-emerald-100 text-emerald-700" :
                  added ? "bg-amber-100 text-amber-700" : "bg-indigo-100 text-indigo-700 hover:bg-indigo-200 disabled:opacity-50"
                )}
              >
                {monitoringEnabled ? <BellRing size={14} /> : added ? <CheckCircle2 size={14} /> : <Target size={14} />}
                {monitoringEnabled ? '监控中' : added ? '已加信号中心' : '添加信号监控'}
              </button>
            )}
          </div>
          {!isNotRecommended ? (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
              <div className="p-3 rounded-2xl bg-white border border-zinc-200">
                <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{t('analysis.conference.entry_price')}</p>
                <p className="text-sm font-medium text-indigo-600">{entryDisplay}</p>
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
              <p className="text-sm font-medium text-rose-400">{t('analysis.trading.not_recommended_desc')}</p>
            </div>
          )}
          <div className="p-4 rounded-2xl bg-white border border-zinc-200">
            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-2">{t('analysis.conference.tactical_strategy')}</p>
            <div className="text-sm leading-relaxed text-zinc-500 italic prose prose-sm prose-zinc max-w-none prose-p:my-1 prose-strong:text-zinc-700 prose-strong:not-italic">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{analysis.tradingPlan.strategy || ''}</ReactMarkdown>
            </div>
          </div>
          {analysis.tradingPlan.strategyRisks && (
            <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/20">
              <p className="text-[10px] font-medium uppercase tracking-widest text-rose-400 mb-2 flex items-center gap-2">
                {t('analysis.conference.risk_warning')}
              </p>
              <div className="text-xs text-rose-200/80 leading-relaxed italic prose prose-sm max-w-none prose-p:my-0 prose-strong:text-rose-300 [&_*]:text-rose-200/80">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{analysis.tradingPlan.strategyRisks || ''}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* Signal Monitoring Confirmation Panel */}
          {showMonitorConfirm && (
            <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 animate-in slide-in-from-top-2">
              <div className="flex items-start gap-3">
                <BellRing size={20} className="text-amber-600 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-amber-800 mb-1">启动实时信号监控？</p>
                  <p className="text-xs text-amber-600 mb-3">
                    后台将持续监控该股票价格，当触及入场价/目标价/止损价时，自动通过飞书发送提醒。
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={handleEnableMonitoring}
                      disabled={isEnablingMonitor}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 transition-all"
                    >
                      <Bell size={12} />
                      {isEnablingMonitor ? '启动中...' : '确认启动监控'}
                    </button>
                    <button
                      onClick={() => setShowMonitorConfirm(false)}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-500 hover:bg-zinc-100 transition-all"
                    >
                      稍后再说
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Monitoring enabled badge */}
          {monitoringEnabled && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-emerald-50 border border-emerald-200">
              <BellRing size={14} className="text-emerald-600" />
              <span className="text-xs font-medium text-emerald-700">信号监控运行中 — 触发时将通过飞书通知</span>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
