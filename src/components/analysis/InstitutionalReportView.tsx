import React, { useState, useEffect, useRef } from 'react';
import { Loader2, FileText, AlertCircle, Target, CheckCircle2, Bell, BellRing } from 'lucide-react';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { useConfigStore } from '../../stores/useConfigStore';
import { useUIStore } from '../../stores/useUIStore';
import { useMarketStore } from '../../stores/useMarketStore';
import { alertsClient } from '../../services/api/alertsClient';
import { buildSignalAlertFromAnalysis } from '../../utils/signalAction';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import type { Market } from '../../types';

/**
 * Renders the CLI-quality institutional HTML report from the Python backend.
 * Fetches the report HTML using the job ID and displays it in a sandboxed iframe.
 */
export function InstitutionalReportView() {
  const lastJobId = useAnalysisStore(s => s.lastJobId);
  const cachedReportHtml = useAnalysisStore(s => s.cachedReportHtml);
  const cachedReportJobId = useAnalysisStore(s => s.cachedReportJobId);
  const setCachedReport = useAnalysisStore(s => s.setCachedReport);
  const config = useConfigStore(s => s.config);

  // States and logic for Signal Monitoring
  const { t } = useTranslation();
  const analysis = useAnalysisStore(s => s.analysis);
  const [isAdding, setIsAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [createdAlertId, setCreatedAlertId] = useState<string | null>(null);
  const [showMonitorConfirm, setShowMonitorConfirm] = useState(false);
  const [monitoringEnabled, setMonitoringEnabled] = useState(false);
  const [isEnablingMonitor, setIsEnablingMonitor] = useState(false);
  const showToast = useUIStore(s => s.showToast);
  const feishuWebhookUrl = useConfigStore(s => s.feishuWebhookUrl);
  const setAlerts = useMarketStore(s => s.setAlerts);

  const isNotRecommended = String(analysis?.tradingPlan?.entryPrice || '').includes('不推荐') || 
                          String(analysis?.tradingPlan?.entryPrice || '').includes('Not Recommended');

  const handleAddToSignalCenter = async () => {
    if (!analysis || !analysis.stockInfo) return;
    setIsAdding(true);
    try {
      // Never fabricate prices: the old fallbacks (`|| currentPrice`,
      // `|| entry * 1.15`, `|| entry * 0.92`) silently turned a Sell plan into
      // a long signal with invented levels (see 昊华科技 regression).
      // buildSignalAlertFromAnalysis refuses to build an alert when the plan
      // lacks usable target/stop (and entry for directional buy/sell signals);
      // hold/watch signals may anchor tracking on the live price.
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
    if (!createdAlertId || !analysis) return;
    setIsEnablingMonitor(true);
    try {
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
  
  // Derive initial state from cache
  const hasCachedReport = cachedReportJobId === lastJobId && !!cachedReportHtml;
  const [html, setHtml] = useState<string | null>(hasCachedReport ? cachedReportHtml : null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Sync html from cache on remount (tab switch) without refetching
  useEffect(() => {
    if (cachedReportJobId === lastJobId && cachedReportHtml) {
      setHtml(cachedReportHtml);
    }
  }, [cachedReportJobId, cachedReportHtml, lastJobId]);

  // Fetch report only if no cache exists for this job
  useEffect(() => {
    if (!lastJobId) {
      setError('无可用的分析任务 ID');
      return;
    }

    // Skip fetch if we already have cached HTML for this job
    if (cachedReportJobId === lastJobId && cachedReportHtml) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/analysis/jobs/${lastJobId}/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        deepseekApiKey: config.deepseekApiKey || undefined,
      }),
    })
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`报告生成失败 (${res.status}): ${text}`);
        }
        return res.text();
      })
      .then((text) => {
        if (cancelled || !text) return;
        setHtml(text);
        setCachedReport(lastJobId, text);
        
        // Extract precise token usage metadata injected by Python generator
        const match = text.match(/<!-- TOKEN_USAGE: (.*?) -->/);
        if (match) {
          try {
            const usage = JSON.parse(match[1]);
            useConfigStore.getState().addTokenUsage({
              promptTokens: usage.promptTokens || 0,
              candidatesTokens: usage.candidatesTokens || 0,
              totalTokens: usage.totalTokens || 0
            });
          } catch (e) {
            console.error('Failed to parse token usage from report HTML', e);
          }
        }
        
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || '报告生成失败');
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [lastJobId, cachedReportJobId]);

  // Auto-resize iframe to content height
  useEffect(() => {
    if (!html || !iframeRef.current) return;
    const iframe = iframeRef.current;
    
    const handleLoad = () => {
      try {
        const doc = iframe.contentDocument || iframe.contentWindow?.document;
        if (doc) {
          const height = doc.documentElement.scrollHeight;
          iframe.style.height = `${height + 40}px`;
        }
      } catch { /* cross-origin, ignore */ }
    };

    iframe.addEventListener('load', handleLoad);
    return () => iframe.removeEventListener('load', handleLoad);
  }, [html]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <div className="relative">
          <Loader2 size={32} className="animate-spin text-indigo-500" />
          <div className="absolute inset-0 blur-xl bg-indigo-100 animate-pulse" />
        </div>
        <p className="text-sm font-medium text-zinc-500">正在生成专业研报...</p>
        <p className="text-[10px] text-zinc-400">后端 AI 正在提炼核心摘要、护城河、宏观分析等</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <AlertCircle size={24} className="text-amber-500" />
        <p className="text-sm font-medium text-zinc-700">{error}</p>
        <p className="text-xs text-zinc-400">可切换到「快速分析」查看已有数据</p>
      </div>
    );
  }

  if (!html) return null;

  const plan = analysis?.tradingPlan || {
    entryPrice: "市价附近 (建议区间)",
    targetPrice: "预期 +15~20%",
    stopLoss: "技术面破位 -8%",
    strategyRisks: analysis?.summary || ""
  };

  // Entry display: when the model leaves entryPrice blank, surface a
  // "现价 / 区间待定" hint (with the live price) instead of a silent blank.
  const _entryPx = analysis?.stockInfo?.price;
  const entryDisplay = /\d/.test(String(plan.entryPrice ?? ''))
    ? plan.entryPrice
    : (_entryPx ? `现价 ${_entryPx} / 区间待定` : '现价 / 区间待定');

  return (
    <div className="space-y-6">
      {analysis && (
        <div className={cn(
          "rounded-2xl p-6 border transition-all duration-300 bg-white shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-6",
          isNotRecommended 
            ? "border-rose-100 bg-rose-50/50" 
            : "border-indigo-100 bg-indigo-50/20"
        )}>
          {/* Left Side: Info & Metrics */}
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-2">
              <span className={cn(
                "p-2 rounded-lg flex items-center justify-center",
                isNotRecommended ? "bg-rose-100 text-rose-600" : "bg-indigo-100 text-indigo-600"
              )}>
                <Target size={18} />
              </span>
              <div>
                <h4 className="font-bold text-zinc-950 text-base flex items-center gap-2">
                  智能信号监控与执行计划
                  {analysis.stockInfo?.symbol && (
                    <span className="text-xs font-mono text-zinc-400 font-normal">
                      {analysis.stockInfo.symbol} · {analysis.stockInfo.market}
                    </span>
                  )}
                </h4>
                <p className="text-xs text-zinc-500">
                  基于本篇深度研报得出的量化交易模型，启动后可对入场、止盈、止损价格进行自动盯盘。
                </p>
              </div>
            </div>

            {isNotRecommended ? (
              <p className="text-xs text-rose-500 font-medium">
                {t('analysis.trading.not_recommended_desc')}
              </p>
            ) : (
              <div className="flex flex-wrap gap-x-6 gap-y-2 pt-2">
                <div className="text-xs">
                  <span className="text-zinc-400 mr-1.5">{t('analysis.conference.entry_price')}:</span>
                  <span className="font-semibold text-indigo-600 font-mono">{entryDisplay}</span>
                </div>
                <div className="text-xs">
                  <span className="text-zinc-400 mr-1.5">{t('analysis.conference.target_price')}:</span>
                  <span className="font-semibold text-emerald-600 font-mono">{plan.targetPrice}</span>
                </div>
                <div className="text-xs">
                  <span className="text-zinc-400 mr-1.5">{t('analysis.conference.stop_loss')}:</span>
                  <span className="font-semibold text-rose-500 font-mono">{plan.stopLoss}</span>
                </div>
              </div>
            )}
          </div>

          {/* Right Side: Actions / Form */}
          {!isNotRecommended && (
            <div className="flex flex-col sm:flex-row items-center gap-3">
              {showMonitorConfirm ? (
                <div className="flex items-center gap-3 bg-amber-50 border border-amber-200/80 rounded-xl p-3 animate-in fade-in slide-in-from-right-3 duration-200">
                  <div className="text-left max-w-[220px]">
                    <p className="text-xs font-bold text-amber-800 flex items-center gap-1">
                      <BellRing size={12} className="text-amber-600 animate-pulse" />
                      启动实时信号监控？
                    </p>
                    <p className="text-[10px] text-amber-600 leading-normal mt-0.5">
                      系统将持续盯盘，触及价格线时自动通过飞书发送警报。
                    </p>
                  </div>
                  <div className="flex flex-col gap-1 flex-shrink-0">
                    <button
                      onClick={handleEnableMonitoring}
                      disabled={isEnablingMonitor}
                      className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-[10px] font-bold transition-all disabled:opacity-40 whitespace-nowrap"
                    >
                      {isEnablingMonitor ? '启动中...' : '确认启动'}
                    </button>
                    <button
                      onClick={() => setShowMonitorConfirm(false)}
                      className="px-3 py-1.5 bg-zinc-200 hover:bg-zinc-300 text-zinc-700 rounded-lg text-[10px] font-medium transition-all whitespace-nowrap"
                    >
                      暂不启动
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={handleAddToSignalCenter}
                  disabled={isAdding || added}
                  className={cn(
                    "w-full sm:w-auto flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-xs font-bold transition-all shadow-sm border",
                    monitoringEnabled
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : added
                      ? "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100/50"
                      : "bg-indigo-600 hover:bg-indigo-700 text-white border-transparent"
                  )}
                >
                  {monitoringEnabled ? (
                    <>
                      <BellRing size={14} className="text-emerald-600" />
                      监控已启动
                    </>
                  ) : added ? (
                    <>
                      <CheckCircle2 size={14} className="text-amber-600" />
                      已加入信号中心 (点击开启盯盘)
                    </>
                  ) : (
                    <>
                      {isAdding ? <Loader2 size={14} className="animate-spin" /> : <Target size={14} />}
                      执行计划并启动信号监控
                    </>
                  )}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      <div className="w-full rounded-2xl border border-zinc-200 overflow-hidden bg-white shadow-sm">
        <iframe
          ref={iframeRef}
          srcDoc={html}
          className="w-full border-0"
          style={{ minHeight: '800px' }}
          sandbox="allow-same-origin"
          title="Institutional Research Report"
        />
      </div>
    </div>
  );
}
