import React, { useState } from 'react';
import { ExternalLink, Target, CheckCircle2, Bell, BellRing } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import type { StockAnalysis, Market } from '../../types';
import { alertsClient } from '../../services/api/alertsClient';
import { useUIStore } from '../../stores/useUIStore';
import { useConfigStore } from '../../stores/useConfigStore';

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
  const isNotRecommended = analysis.tradingPlan?.entryPrice?.includes('不推荐') || 
                          analysis.tradingPlan?.entryPrice?.includes('Not Recommended');

  const handleAddToSignalCenter = async () => {
    if (!analysis.tradingPlan || !analysis.stockInfo) return;
    setIsAdding(true);
    try {
      const { entryPrice, targetPrice, stopLoss } = analysis.tradingPlan as any;
      const parseNum = (s: string) => {
        const match = String(s || '').match(/[\d.]+/);
        return match ? parseFloat(match[0]) : 0;
      };
      const entry = parseNum(entryPrice);
      const target = parseNum(targetPrice);
      const stop = parseNum(stopLoss);
      
      if (entry > 0 && target > 0 && stop > 0) {
        const result = await alertsClient.create({
          symbol: analysis.stockInfo.symbol,
          name: analysis.stockInfo.name,
          market: analysis.stockInfo.market as Market,
          entry_price: entry,
          target_price: target,
          stop_loss: stop,
          currency: analysis.stockInfo.currency || 'CNY',
        });
        setAdded(true);
        setCreatedAlertId(result.alert_id);
        setShowMonitorConfirm(true);
        showToast('已添加至信号中心，请确认是否启动实时监控', 'success');
      } else {
        showToast('交易计划中未能提取有效的数值，无法添加', 'error');
      }
    } catch (e: any) {
      showToast('添加失败: ' + e.message, 'error');
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
    } catch (e: any) {
      showToast('启动监控失败: ' + e.message, 'error');
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
        <p className="text-sm leading-relaxed text-zinc-500 font-medium prose prose-sm prose-zinc max-w-none prose-p:my-1 prose-strong:text-zinc-700">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{analysis.summary || ''}</ReactMarkdown>
        </p>
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
              <p className="text-xs text-rose-200/80 leading-relaxed italic prose prose-sm max-w-none prose-p:my-0 prose-strong:text-rose-300 [&_*]:text-rose-200/80">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{analysis.tradingPlan.strategyRisks || ''}</ReactMarkdown>
              </p>
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
                  {!feishuWebhookUrl && (
                    <p className="text-xs text-rose-500 mb-2">
                      ⚠ 未配置飞书 Webhook URL，请在系统设置中配置后再启用监控。
                    </p>
                  )}
                  <div className="flex gap-2">
                    <button
                      onClick={handleEnableMonitoring}
                      disabled={isEnablingMonitor || !feishuWebhookUrl}
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
