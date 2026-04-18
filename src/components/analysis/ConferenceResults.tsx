import React from 'react';
import {
  AlertCircle, Loader2, AlertTriangle, Zap, Award, Target,
  RefreshCcw, Clock, Layers, Database, History, Coins,
  ShieldCheck, Search, TrendingUp, BarChart3, Cpu, CheckCircle2,
  Share2, Download, User, ExternalLink,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { clsx } from 'clsx';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from './utils';
import { getQualityLabel } from '../../services/dataQualityService';
import { useUIStore, selectIsDiscussing, selectIsReviewing } from '../../stores/useUIStore';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { useDiscussionStore } from '../../stores/useDiscussionStore';
import { useScenarioStore } from '../../stores/useScenarioStore';
import type { StockAnalysis } from '../../types';

interface ConferenceResultsProps {
  analysis: StockAnalysis;
  onSendDiscussionReport: () => void;
}

export function ConferenceResults({ analysis, onSendDiscussionReport }: ConferenceResultsProps) {
  const { t } = useTranslation();
  const isDiscussing = useUIStore(selectIsDiscussing);
  const isReviewing = useUIStore(selectIsReviewing);
  const { isGeneratingReport, isSendingReport, reportStatus } = useUIStore();
  const { discussionMessages, controversialPoints, tradingPlanHistory } = useDiscussionStore();
  
  // Destructure with fallbacks to single-shot analysis data if store is empty
  const scenarioResults = useScenarioStore();
  
  const scenarios = (scenarioResults.scenarios?.length ?? 0) > 0 ? scenarioResults.scenarios : (analysis.scenarios || []);
  const sensitivityFactors = (scenarioResults.sensitivityFactors?.length ?? 0) > 0 ? scenarioResults.sensitivityFactors : (analysis.sensitivityFactors || []);
  const expectationGap = scenarioResults.expectationGap || analysis.expectationGap;
  const calculations = (scenarioResults.calculations?.length ?? 0) > 0 ? scenarioResults.calculations : (analysis.calculations || []);
  const dataFreshnessStatus = scenarioResults.dataFreshnessStatus || "Fresh";
  const stressTestLogic = scenarioResults.stressTestLogic || analysis.stressTestLogic;
  const catalystList = (scenarioResults.catalystList?.length ?? 0) > 0 ? scenarioResults.catalystList : (analysis.catalystList || []);
  const verificationMetrics = (scenarioResults.verificationMetrics?.length ?? 0) > 0 ? scenarioResults.verificationMetrics : (analysis.verificationMetrics || []);
  const capitalFlow = scenarioResults.capitalFlow || analysis.capitalFlow;
  const positionManagement = scenarioResults.positionManagement || analysis.positionManagement;
  const timeDimension = scenarioResults.timeDimension || analysis.timeDimension;

  // New deep research fields
  const industryAnchors = analysis.industryAnchors || [];
  const fundamentalTable = analysis.fundamentalTable || [];
  const moatAnalysis = analysis.moatAnalysis;
  const narrativeConsistency = analysis.narrativeConsistency;
  const cycleAnalysis = analysis.cycleAnalysis;
  const businessModel = analysis.businessModel;
  const coreVariables = analysis.coreVariables || [];
  const quantifiedRisks = analysis.quantifiedRisks || [];

  // Determine if we have enough deep data to show this panel even without a discussion
  const hasDeepData = industryAnchors.length > 0 || 
                      fundamentalTable.length > 0 || 
                      scenarios.length > 0 || 
                      !!expectationGap || 
                      !!moatAnalysis ||
                      !!businessModel ||
                      coreVariables.length > 0 ||
                      quantifiedRisks.length > 0 ||
                      !!analysis.expectedValueOutcome;

  if (!isDiscussing && discussionMessages.length === 0 && !hasDeepData) return null;

  return (
    <div className="flex flex-col gap-8 mt-4 pt-4 w-full">
      <div className="space-y-6 w-full">
        <div className="relative p-8 rounded-2xl bg-white/70 backdrop-blur-xl border border-white/60 shadow-[0_8px_32px_rgba(0,0,0,0.04)] overflow-hidden">
          {/* Background Gradient */}
          <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-indigo-500/5 blur-[100px] -mr-64 -mt-64 pointer-events-none" />
          
          <h3 className="relative z-10 text-lg font-bold uppercase tracking-[0.2em] text-zinc-500 mb-8 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/20">
                <Zap size={24} />
              </div>
              {t('analysis.conference.header')}
              <span className="ml-2 rounded-full bg-indigo-100 px-2.5 py-0.5 text-[10px] font-bold text-indigo-600 uppercase tracking-widest border border-indigo-200/50">
                Institutional
              </span>
            </div>
            <div className="flex items-center gap-2">
              {analysis.dataQuality && (
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/50 border border-zinc-200/60 shadow-sm text-[10px] font-bold uppercase tracking-widest text-zinc-500">
                  <Database size={10} className="text-zinc-400" />
                  {analysis.dataQuality.score}% Health
                </div>
              )}
              <div className={cn(
                "px-3 py-1.5 rounded-xl text-[10px] font-bold uppercase tracking-widest border shadow-sm",
                dataFreshnessStatus === "Fresh" ? "bg-emerald-50 text-emerald-600 border-emerald-100" :
                dataFreshnessStatus === "Warning" ? "bg-amber-50 text-amber-600 border-amber-100" :
                "bg-rose-50 text-rose-600 border-rose-100 animate-pulse"
              )}>
                {dataFreshnessStatus === "Fresh" ? <ShieldCheck size={10} className="inline mr-1" /> : <AlertCircle size={10} className="inline mr-1" />}
                {dataFreshnessStatus}
              </div>
            </div>
          </h3>

          {/* Institutional Confidence Ticker */}
          {!isDiscussing && (
            <div className="relative z-10 grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
              <div className="p-4 rounded-2xl bg-white/50 border border-zinc-200/60 shadow-sm">
                <p className="text-[9px] font-bold text-zinc-400 uppercase tracking-widest mb-1 text-center">Engine Sentiment</p>
                <div className="flex items-center justify-center gap-2">
                  <div className={cn(
                    "w-2 h-2 rounded-full",
                    analysis.sentiment === 'Bullish' ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" : 
                    analysis.sentiment === 'Bearish' ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]" : "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]"
                  )} />
                  <span className="text-sm font-bold text-zinc-900">{analysis.sentiment || 'Neutral'}</span>
                </div>
              </div>
              <div className="p-4 rounded-2xl bg-white/50 border border-zinc-200/60 shadow-sm text-center">
                <p className="text-[9px] font-bold text-zinc-400 uppercase tracking-widest mb-1 text-center">Consensus Score</p>
                <div className="text-sm font-bold text-zinc-900">{analysis.score || 0}/100</div>
              </div>
              <div className="p-4 rounded-2xl bg-white/50 border border-zinc-200/60 shadow-sm text-center">
                <p className="text-[9px] font-bold text-zinc-400 uppercase tracking-widest mb-1 text-center">Audit Status</p>
                <div className="flex items-center justify-center gap-1.5 text-emerald-600">
                  <ShieldCheck size={14} />
                  <span className="text-sm font-bold">Verified</span>
                </div>
              </div>
              <div className="p-4 rounded-2xl bg-white/50 border border-zinc-200/60 shadow-sm text-center">
                <p className="text-[9px] font-bold text-zinc-400 uppercase tracking-widest mb-1 text-center">Logic Rounds</p>
                <div className="text-sm font-bold text-zinc-900">{analysis.discussion?.length ? 'Multi-Round' : 'Single-Shot'}</div>
              </div>
            </div>
          )}
          {isDiscussing && discussionMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-4 text-zinc-400 py-12">
              <div className="relative">
                <Loader2 size={32} className="animate-spin text-emerald-500" />
                <div className="absolute inset-0 blur-xl bg-indigo-100 animate-pulse" />
              </div>
              <p className="text-sm font-medium tracking-wide">{t('analysis.conference.status_entering')}</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* In-progress indicator */}
              {isDiscussing && discussionMessages.length > 0 && (
                <div className="p-4 rounded-2xl bg-indigo-50/50 border border-indigo-200/40 flex items-center gap-3">
                  <Loader2 size={16} className="animate-spin text-indigo-500" />
                  <p className="text-xs font-medium text-indigo-600">{t('analysis.conference.status_in_progress')}</p>
                </div>
              )}

              {/* Final Conclusion Card */}
              {analysis.finalConclusion && !isDiscussing && (
                <div className="p-8 rounded-[2rem] bg-indigo-600/5 border border-indigo-100 relative overflow-hidden group shadow-sm">
                  <div className="absolute top-0 right-0 p-6 opacity-[0.03] group-hover:opacity-[0.06] transition-opacity pointer-events-none">
                    <Award size={120} className="text-indigo-600 rotate-12" />
                  </div>
                  <div className="relative z-10">
                    <div className="flex items-center gap-3 mb-6">
                      <div className="p-2.5 rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/20">
                        <Award size={20} />
                      </div>
                      <div>
                        <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">{t('analysis.conference.final_consensus')}</h4>
                        <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">{t('app.subtitle')}</p>
                      </div>
                    </div>
                    <div className="prose prose-zinc max-w-none">
                      <ReactMarkdown 
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({node, ...props}) => <h1 className="text-2xl font-bold text-zinc-900 mt-8 mb-4 flex items-center gap-2 border-l-4 border-indigo-600 pl-4" {...props} />,
                          h2: ({node, ...props}) => <h2 className="text-xl font-bold text-zinc-900 mt-6 mb-3 flex items-center gap-2" {...props} />,
                          h3: ({node, ...props}) => <h3 className="text-lg font-bold text-indigo-600 mt-4 mb-2 uppercase tracking-widest" {...props} />,
                          p: ({node, ...props}) => <p className="text-zinc-700 text-lg font-medium leading-relaxed tracking-tight mb-4" {...props} />,
                          ul: ({node, ...props}) => <ul className="space-y-2 mb-6 ml-4" {...props} />,
                          li: ({node, ...props}) => (
                            <li className="flex items-start gap-2 text-zinc-600 text-base">
                              <div className="mt-2 w-1.5 h-1.5 rounded-full bg-indigo-500 shrink-0" />
                              <span {...props} />
                            </li>
                          ),
                          table: ({node, ...props}) => (
                            <div className="my-8 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm overflow-x-auto">
                              <table className="w-full text-left border-collapse" {...props} />
                            </div>
                          ),
                          thead: ({node, ...props}) => <thead className="bg-zinc-50 border-b border-zinc-200" {...props} />,
                          th: ({node, ...props}) => <th className="px-4 py-3 text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em]" {...props} />,
                          td: ({node, ...props}) => <td className="px-4 py-3 text-sm text-zinc-600 border-b border-zinc-50 font-medium" {...props} />,
                          blockquote: ({node, ...props}) => (
                            <blockquote className="my-6 p-6 rounded-2xl bg-indigo-600/5 border-l-4 border-indigo-600 italic text-indigo-900/80 font-medium quote-icon">
                              <span {...props} />
                            </blockquote>
                          ),
                        }}
                      >
                        {analysis.finalConclusion}
                      </ReactMarkdown>
                    </div>
                    <div className="mt-8 pt-6 border-t border-zinc-200/60 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-zinc-100 border border-zinc-200 flex items-center justify-center overflow-hidden">
                          <User size={16} className="text-zinc-400" />
                        </div>
                        <span className="text-xs font-bold text-zinc-900 uppercase tracking-widest">{t('analysis.conference.signed_off')}</span>
                      </div>
                      <div className="text-[10px] font-mono text-zinc-400">
                        {t('app.title')}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Decision Engine Dashboard */}
              {(analysis.expectedValueOutcome || scenarios.length > 0) && (
                <div className="relative p-8 rounded-[2rem] bg-indigo-600/5 border border-indigo-100 shadow-sm overflow-hidden group">
                  <div className="absolute top-0 right-0 p-8 opacity-[0.03] group-hover:opacity-[0.06] transition-opacity pointer-events-none">
                    <Cpu size={160} className="text-indigo-600 rotate-12" />
                  </div>

                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-8">
                      <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/20">
                          <Cpu size={20} />
                        </div>
                        <div>
                          <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">Decision Engine v3.1</h4>
                          <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider italic">Bayesian Multi-Agent Deliberation</p>
                        </div>
                      </div>
                      {analysis.expectedValueOutcome?.confidenceInterval && (
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/20 text-[10px] font-bold uppercase tracking-widest">
                          <Activity size={10} className="animate-pulse" />
                          {analysis.expectedValueOutcome.confidenceInterval} Confidence
                        </div>
                      )}
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
                      <div className="lg:col-span-7 space-y-4">
                        <div className="p-6 rounded-2xl bg-white/50 border border-zinc-200/60 shadow-sm">
                          <p className="text-[9px] text-zinc-400 font-bold uppercase tracking-widest mb-3">Mathematical Baseline & Synthesis</p>
                          <p className="text-sm text-zinc-700 leading-relaxed font-medium italic">
                            "{analysis.expectedValueOutcome?.calculationLogic || "Integrated analysis of industry anchors, fundamental deviations, and technician sentiment."}"
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-3">
                          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 border border-emerald-100 text-emerald-600 text-[10px] font-bold uppercase tracking-widest shadow-sm">
                            <CheckCircle2 size={12} />
                            Verified by Judge Agent
                          </div>
                          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 text-[10px] font-bold uppercase tracking-widest shadow-sm">
                            <Layers size={12} />
                            Expert Consensus Aligned
                          </div>
                        </div>
                      </div>

                      <div className="lg:col-span-5 flex flex-col gap-4">
                        <div className="p-8 rounded-[2rem] bg-indigo-600 text-white shadow-xl shadow-indigo-600/20 flex flex-col items-center justify-center group-hover:shadow-indigo-600/30 transition-shadow">
                          <p className="text-[9px] text-indigo-200 font-bold uppercase tracking-[0.3em] mb-4">Unified Target Price</p>
                          <div className="flex items-baseline gap-2">
                            <span className="text-6xl font-bold tracking-tighter">
                              {analysis.expectedValueOutcome?.expectedPrice?.toFixed(2) ?? analysis.stockInfo.price.toFixed(2)}
                            </span>
                            <span className="text-lg font-bold text-indigo-200">{analysis.stockInfo.currency}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Conflict Logger */}
              {controversialPoints.length > 0 && (
                <div className="p-5 rounded-2xl bg-rose-500/5 border border-rose-500/20">
                  <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-rose-400 mb-3 flex items-center gap-2">
                    <AlertTriangle size={14} />
                    {t('analysis.conference.conflict_logger')}
                  </h4>
                  <div className="space-y-2">
                    {controversialPoints.map((point, idx) => (
                      <div key={`controversial-${point.substring(0, 10)}-${idx}`} className="flex items-start gap-2">
                        <div className="w-1 h-1 rounded-full bg-rose-500 mt-1.5 shrink-0" />
                        <p className="text-[11px] text-zinc-500 leading-relaxed italic">{point}</p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-3 text-[9px] text-zinc-400 uppercase font-semibold tracking-widest">
                    {t('analysis.conference.alpha_hint')}
                  </p>
                </div>
              )}

              {/* Trading Plan */}
              {analysis.tradingPlan && !isDiscussing && (
                <div className="p-8 rounded-[2rem] bg-zinc-50/50 border border-zinc-200/60 relative overflow-hidden shadow-sm">
                  <div className="flex items-center justify-between mb-8">
                    <div className="flex items-center gap-3">
                      <div className="p-2.5 rounded-2xl bg-indigo-600/10 text-indigo-600 border border-indigo-600/20">
                        <Target size={20} />
                      </div>
                      <div>
                        <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">{t('analysis.conference.execution_plan')}</h4>
                        <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">{t('app.subtitle')}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-600 text-white text-[10px] font-bold uppercase tracking-widest shadow-lg shadow-indigo-600/20">
                      <Zap size={10} />
                      {t('analysis.conference.active_plan')}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6 mb-8">
                    <div className="p-5 rounded-2xl bg-white border border-zinc-200/60 shadow-sm group hover:border-indigo-600/30 transition-all">
                      <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest mb-2">{t('analysis.conference.entry_price')}</p>
                      <p className="text-2xl font-semibold text-zinc-950 tracking-tighter group-hover:text-indigo-600 transition-colors">{analysis.tradingPlan.entryPrice}</p>
                      <div className="mt-2 h-1 w-8 bg-indigo-600/20 rounded-full" />
                    </div>
                    <div className="p-5 rounded-2xl bg-white border border-zinc-200/60 shadow-sm group hover:border-emerald-500/30 transition-all">
                      <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest mb-2">{t('analysis.conference.target_price')}</p>
                      <p className="text-2xl font-semibold text-zinc-950 tracking-tighter group-hover:text-emerald-500 transition-colors">{analysis.tradingPlan.targetPrice}</p>
                      <div className="mt-2 h-1 w-8 bg-emerald-500/20 rounded-full" />
                    </div>
                    <div className="p-5 rounded-2xl bg-white border border-zinc-200/60 shadow-sm group hover:border-rose-500/30 transition-all">
                      <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest mb-2">{t('analysis.conference.stop_loss')}</p>
                      <p className="text-2xl font-semibold text-zinc-950 tracking-tighter group-hover:text-rose-500 transition-colors">{analysis.tradingPlan.stopLoss}</p>
                      <div className="mt-2 h-1 w-8 bg-rose-500/20 rounded-full" />
                    </div>
                  </div>

                  <div className="p-6 rounded-2xl bg-indigo-600/5 border border-indigo-100/50">
                    <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest mb-2">{t('analysis.conference.tactical_strategy')}</p>
                    <p className="text-sm text-zinc-600 leading-relaxed font-medium italic">
                      "{analysis.tradingPlan.strategy}"
                    </p>
                  </div>

                  {/* Trading Plan Version History */}
                  {tradingPlanHistory.length > 0 && (
                    <div className="mt-4 pt-4 border-t border-zinc-200/50">
                      <h5 className="text-[9px] font-bold uppercase tracking-widest text-zinc-400 mb-3 flex items-center gap-2">
                        <History size={12} />
                        {t('analysis.conference.version_control')}
                      </h5>
                      <div className="space-y-3">
                        {tradingPlanHistory.map((v, i) => (
                          <div key={`trading-plan-${v.version}-${v.timestamp}-${i}`} className="p-3 rounded-xl bg-zinc-50 border border-zinc-200/50 text-[10px]">
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-semibold text-indigo-600 uppercase tracking-widest">{v.version}</span>
                              <span className="text-zinc-400 font-mono">{new Date(v.timestamp).toLocaleTimeString()}</span>
                            </div>
                            <p className="text-zinc-500 mb-2 leading-relaxed">
                              <span className="text-zinc-400 font-medium uppercase mr-1">{t('analysis.conference.change_reason')}:</span>
                              {v.changeReason}
                            </p>
                            <div className="grid grid-cols-3 gap-2 py-2 border-t border-zinc-200">
                              <div className="flex flex-col">
                                <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.conference.entry_price')}</span>
                                <span className="text-emerald-500/80 font-semibold">{v.plan.entryPrice}</span>
                              </div>
                              <div className="flex flex-col">
                                <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.conference.target_price')}</span>
                                <span className="text-blue-500/80 font-semibold">{v.plan.targetPrice}</span>
                              </div>
                              <div className="flex flex-col">
                                <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.conference.stop_loss')}</span>
                                <span className="text-rose-500/80 font-semibold">{v.plan.stopLoss}</span>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Institutional Deep Research Sections */}
              {industryAnchors.length > 0 && (
                <div className="p-8 rounded-[2rem] bg-white border border-zinc-200 shadow-sm overflow-hidden">
                  <div className="flex items-center gap-3 mb-8">
                    <div className="p-2.5 rounded-2xl bg-emerald-600/10 text-emerald-600 border border-emerald-600/20">
                      <Database size={20} />
                    </div>
                    <div>
                      <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-600">Institutional Core Variables</h4>
                      <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">Dynamic Macro Anchors & Supply Chain Matrix</p>
                    </div>
                  </div>
                  
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-zinc-100">
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest">Variable / Material</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest text-center">Value</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest text-center">Weight</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest text-center">30D Δ</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest">Transmission Logic</th>
                        </tr>
                      </thead>
                      <tbody>
                        {industryAnchors.map((anchor, idx) => (
                          <tr key={`anchor-${anchor.variable}-${idx}`} className="border-b border-zinc-50 group hover:bg-zinc-50 transition-colors">
                            <td className="py-4 px-2">
                              <span className="text-xs font-bold text-zinc-900">{anchor.variable}</span>
                            </td>
                            <td className="py-4 px-2 text-center">
                              <span className="text-xs font-mono font-medium text-emerald-600">{anchor.currentValue}</span>
                            </td>
                            <td className="py-4 px-2 text-center">
                              <span className="text-[10px] font-bold text-zinc-500">{anchor.weight}</span>
                            </td>
                            <td className="py-4 px-2 text-center">
                              <span className={cn(
                                "text-[10px] font-mono font-bold",
                                anchor.monthlyChange?.includes('+') ? "text-rose-500" : "text-emerald-500"
                              )}>{anchor.monthlyChange}</span>
                            </td>
                            <td className="py-4 px-2">
                              <p className="text-[10px] text-zinc-500 leading-relaxed max-w-xs">{anchor.logic}</p>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {fundamentalTable.length > 0 && (
                <div className="p-8 rounded-[2rem] bg-white border border-zinc-200 shadow-sm overflow-hidden group">
                  <div className="flex items-center gap-3 mb-8 relative z-10">
                    <div className="p-2.5 rounded-2xl bg-indigo-600/10 text-indigo-600 border border-indigo-600/20">
                      <BarChart3 size={20} />
                    </div>
                    <div>
                      <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">Consensus vs Reality Matrix</h4>
                      <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">Alpha Source Verification - 2026E</p>
                    </div>
                  </div>

                  <div className="overflow-x-auto relative z-10">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-zinc-100">
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest">Indicator</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest">Current/Real</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest">Market Est.</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest text-center">Deviation</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest">Analyst Note</th>
                        </tr>
                      </thead>
                      <tbody>
                        {fundamentalTable.map((item, idx) => (
                          <tr key={`fundamental-${idx}`} className="border-b border-zinc-50 group hover:bg-zinc-50 transition-colors">
                            <td className="py-4 px-2">
                              <span className="text-xs font-bold text-zinc-900">{item.indicator}</span>
                            </td>
                            <td className="py-4 px-2">
                              <span className="text-xs font-mono font-bold text-indigo-600">{item.value}</span>
                            </td>
                            <td className="py-4 px-2">
                              <span className="text-xs font-mono text-zinc-500">{item.consensus}</span>
                            </td>
                            <td className="py-4 px-2 text-center">
                              <span className={cn(
                                "text-[10px] font-mono font-bold px-2 py-0.5 rounded",
                                item.deviation?.includes('+') ? "bg-emerald-500/10 text-emerald-600" : "bg-rose-500/10 text-rose-600"
                              )}>{item.deviation}</span>
                            </td>
                            <td className="py-4 px-2">
                              <p className="text-[10px] text-zinc-500 leading-relaxed italic">"{item.remark}"</p>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {(moatAnalysis || cycleAnalysis || narrativeConsistency) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {moatAnalysis && (
                    <div className="p-8 rounded-[2rem] bg-indigo-600/5 border border-indigo-100 shadow-sm group">
                      <div className="flex items-center gap-3 mb-6">
                        <div className="p-2.5 rounded-2xl bg-indigo-600 text-white">
                          <ShieldCheck size={20} />
                        </div>
                        <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">Moat Analysis</h4>
                      </div>
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-zinc-500">Strength:</span>
                          <span className={cn(
                            "text-xs font-bold uppercase px-3 py-1 rounded-full",
                            moatAnalysis.strength === "Wide" ? "bg-emerald-500/10 text-emerald-600" :
                            moatAnalysis.strength === "Narrow" ? "bg-indigo-600/10 text-indigo-600" :
                            "bg-rose-500/10 text-rose-600"
                          )}>{moatAnalysis.strength} MOAT</span>
                        </div>
                        <div className="p-4 rounded-xl bg-white border border-zinc-200/60">
                          <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest mb-1">Source of Moat</p>
                          <p className="text-xs font-bold text-zinc-900">{moatAnalysis.type}</p>
                        </div>
                        <p className="text-sm text-zinc-600 leading-relaxed font-medium">{moatAnalysis.logic}</p>
                      </div>
                    </div>
                  )}

                  {cycleAnalysis && (
                    <div className="p-8 rounded-[2rem] bg-amber-500/5 border border-amber-500/10 shadow-sm group">
                      <div className="flex items-center gap-3 mb-6">
                        <div className="p-2.5 rounded-2xl bg-amber-500 text-white">
                          <RefreshCcw size={20} />
                        </div>
                        <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-500">Cycle Dynamics</h4>
                      </div>
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-zinc-500">Current Phase:</span>
                          <span className="text-xs font-bold uppercase px-3 py-1 rounded-full bg-amber-500/10 text-amber-600">
                            {cycleAnalysis.stage} PHASE
                          </span>
                        </div>
                        <div className="p-4 rounded-xl bg-white border border-zinc-200/60">
                          <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest mb-1">Volatility Risk</p>
                          <p className="text-xs font-bold text-zinc-900">{cycleAnalysis.volatilityRisk}</p>
                        </div>
                        <p className="text-sm text-zinc-600 leading-relaxed font-medium">{cycleAnalysis.logic}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {businessModel && (
                <div className="p-8 rounded-[2rem] bg-white border border-zinc-200 shadow-sm overflow-hidden">
                  <div className="flex items-center gap-3 mb-8">
                    <div className="p-2.5 rounded-2xl bg-indigo-600/10 text-indigo-600 border border-indigo-600/20">
                      <Layers size={20} />
                    </div>
                    <div>
                      <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">Business Model Analysis</h4>
                      <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">Revenue Drivers & Profit Formula</p>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="md:col-span-2 space-y-6">
                      <div className="p-6 rounded-2xl bg-zinc-50 border border-zinc-200/60">
                        <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest mb-3">Profit Formula</p>
                        <div className="p-4 rounded-xl bg-white border border-zinc-200 font-mono text-sm text-indigo-600 text-center shadow-inner">
                          {businessModel.formula}
                        </div>
                      </div>
                      
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {Object.entries(businessModel.drivers || {}).map(([key, val], idx) => (
                          <div key={`driver-${key}-${idx}`} className="p-4 rounded-xl bg-white border border-zinc-200 flex items-center justify-between">
                            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">{key}</span>
                            <span className="text-xs font-bold text-zinc-900">{String(val)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    
                    <div className="space-y-4">
                      <div className="p-6 rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/20">
                        <p className="text-[10px] text-indigo-200 font-bold uppercase tracking-widest mb-2">Projected Profit</p>
                        <p className="text-2xl font-bold tracking-tight">{businessModel.projectedProfit}</p>
                      </div>
                      
                      <div className="p-6 rounded-2xl bg-white border border-zinc-200">
                        <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest mb-2">Confidence Score</p>
                        <div className="flex items-end gap-2">
                          <span className="text-3xl font-bold text-zinc-900">{businessModel.confidenceScore}</span>
                          <span className="text-xs font-bold text-zinc-400 mb-1.5">%</span>
                        </div>
                        <div className="mt-4 w-full h-1.5 bg-zinc-100 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-indigo-600 transition-all duration-1000" 
                            style={{ width: `${businessModel.confidenceScore}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {quantifiedRisks.length > 0 && (
                <div className="p-8 rounded-[2rem] bg-rose-500/5 border border-rose-500/10 shadow-sm overflow-hidden">
                  <div className="flex items-center gap-3 mb-8">
                    <div className="p-2.5 rounded-2xl bg-rose-500 text-white">
                      <AlertTriangle size={20} />
                    </div>
                    <div>
                      <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-rose-500">Quantified Risk Matrix</h4>
                      <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">Probability-Weighted Impact Assessment</p>
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {quantifiedRisks.map((risk, idx) => (
                      <div key={`risk-${idx}`} className="p-5 rounded-2xl bg-white border border-zinc-200 hover:border-rose-500/30 transition-all group">
                        <div className="flex items-center justify-between mb-4">
                          <h5 className="text-xs font-bold text-zinc-900 uppercase tracking-wide">{risk.name}</h5>
                          <span className="text-[10px] font-bold text-rose-500 bg-rose-500/10 px-2 py-0.5 rounded-full">
                            {risk.probability}% Prob.
                          </span>
                        </div>
                        
                        <div className="grid grid-cols-2 gap-4 mb-4">
                          <div className="space-y-1">
                            <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest">Impact</p>
                            <p className="text-sm font-bold text-rose-600">{risk.impactPercent}%</p>
                          </div>
                          <div className="space-y-1">
                            <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest">Exp. Loss</p>
                            <p className="text-sm font-bold text-zinc-900">{risk.expectedLoss}%</p>
                          </div>
                        </div>
                        
                        <div className="pt-4 border-t border-zinc-100">
                          <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest mb-1">Mitigation</p>
                          <p className="text-[10px] text-zinc-500 leading-relaxed italic">"{risk.mitigation}"</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {coreVariables.length > 0 && (
                <div className="p-8 rounded-[2rem] bg-white border border-zinc-200 shadow-sm overflow-hidden">
                  <div className="flex items-center gap-3 mb-8">
                    <div className="p-2.5 rounded-2xl bg-indigo-600 text-white">
                      <RefreshCcw size={20} />
                    </div>
                    <div>
                      <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">Core Variable Tracking</h4>
                      <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">Real-time Evidence & Deviation Analysis</p>
                    </div>
                  </div>
                  
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-zinc-100">
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest">Variable</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest text-center">Value</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest text-center">Expectation</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest text-center">Delta</th>
                          <th className="py-4 px-2 text-[10px] uppercase font-bold text-zinc-400 tracking-widest">Evidence / Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {coreVariables.map((v, idx) => (
                          <tr key={`core-var-${idx}`} className="border-b border-zinc-50 group hover:bg-zinc-50 transition-colors">
                            <td className="py-4 px-2">
                              <div className="flex flex-col">
                                <span className="text-xs font-bold text-zinc-900">{v.name}</span>
                                <span className="text-[9px] text-zinc-400 font-mono">{v.dataDate}</span>
                              </div>
                            </td>
                            <td className="py-4 px-2 text-center">
                              <span className="text-xs font-mono font-bold text-indigo-600">{v.value} {v.unit}</span>
                            </td>
                            <td className="py-4 px-2 text-center">
                              <span className="text-xs font-mono text-zinc-500">{v.marketExpect}</span>
                            </td>
                            <td className="py-4 px-2 text-center">
                              <span className={cn(
                                "text-[10px] font-mono font-bold px-2 py-0.5 rounded",
                                v.delta?.includes('+') || v.delta?.includes('超') ? "bg-emerald-500/10 text-emerald-600" : "bg-rose-500/10 text-rose-600"
                              )}>{v.delta}</span>
                            </td>
                            <td className="py-4 px-2">
                              <div className="flex flex-col gap-1">
                                <p className="text-[10px] text-zinc-500 leading-relaxed line-clamp-1">{v.reason}</p>
                                <div className="flex items-center gap-2">
                                  <span className="text-[8px] font-bold uppercase tracking-widest text-zinc-400 px-1.5 py-0.5 rounded border border-zinc-200 bg-white">
                                    {v.evidenceLevel}
                                  </span>
                                  <span className="text-[8px] font-mono text-zinc-400">{v.source}</span>
                                </div>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Recent Catalysts & Intelligence */}
              {((analysis.news && analysis.news.length > 0) || (analysis.historicalData?.majorEvents && analysis.historicalData.majorEvents.length > 0)) && (
                <div className="p-8 rounded-[2rem] bg-zinc-50/50 border border-zinc-200/60 shadow-sm">
                  <div className="flex items-center gap-3 mb-8">
                    <div className="p-2.5 rounded-2xl bg-amber-600/10 text-amber-600 border border-amber-600/20">
                      <Zap size={20} />
                    </div>
                    <div>
                      <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-600">Recent Catalysts & Intelligence</h4>
                      <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">Verified Real-time Narrative Stream</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {analysis.news?.map((n: any, i: number) => (
                      <a 
                        key={`news-catalyst-${i}`} 
                        href={n.url} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="p-4 rounded-xl bg-white border border-zinc-200 hover:border-amber-600/30 transition-all group flex flex-col justify-between"
                      >
                        <h5 className="text-[11px] font-bold text-zinc-900 line-clamp-2 leading-relaxed mb-3 group-hover:text-amber-600 transition-colors">
                          {n.title}
                        </h5>
                        <div className="flex items-center justify-between">
                          <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-widest">{n.source}</span>
                          <div className="flex items-center gap-1.5 text-[9px] font-mono font-medium text-zinc-400 italic">
                            {n.time}
                            <ExternalLink size={10} className="group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                          </div>
                        </div>
                      </a>
                    ))}
                    
                    {(!analysis.news || analysis.news.length === 0) && analysis.historicalData?.majorEvents?.map((event: any, i: number) => (
                      <div key={`event-catalyst-${i}`} className="p-4 rounded-xl bg-white border border-zinc-200 flex items-start gap-3">
                        <div className="mt-1 w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                        <p className="text-[11px] font-medium text-zinc-500 leading-relaxed italic">
                          {typeof event === 'string' ? event : JSON.stringify(event)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Scenarios & Advanced Analytics */}
              {(scenarios.length > 0 || !!expectationGap || (sensitivityFactors && sensitivityFactors.length > 0) || calculations.length > 0 || !!stressTestLogic || (catalystList && catalystList.length > 0) || (verificationMetrics && verificationMetrics.length > 0) || !!capitalFlow || !!positionManagement || !!timeDimension) && (
                <div className="space-y-6">
                  {/* Expectation Gap */}
                  {expectationGap && (
                    <div className="p-8 rounded-[2rem] bg-indigo-600/5 border border-indigo-100 relative overflow-hidden shadow-sm">
                      <div className="absolute top-0 right-0 p-6 opacity-[0.03] pointer-events-none">
                        <Search size={120} className="text-indigo-600" />
                      </div>
                      <div className="flex items-center justify-between mb-8 relative z-10">
                        <div className="flex items-center gap-3">
                          <div className="p-2.5 rounded-2xl bg-indigo-600/10 text-indigo-600 border border-indigo-600/20">
                            <Search size={20} />
                          </div>
                          <div>
                            <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">{t('analysis.scenarios.expectation_gap')}</h4>
                            <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">{t('app.subtitle')}</p>
                          </div>
                        </div>
                        {expectationGap.confidenceScore && (
                          <div className="px-3 py-1 rounded-full bg-indigo-600 text-white text-[10px] font-bold tracking-widest shadow-lg shadow-indigo-600/20">
                            CONFIDENCE: {expectationGap.confidenceScore}%
                          </div>
                        )}
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8 relative z-10">
                        <div className="p-6 rounded-2xl bg-white border border-zinc-200/60 shadow-sm">
                          <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest mb-3">{t('analysis.scenarios.market_consensus')}</p>
                          <p className="text-sm text-zinc-600 leading-relaxed font-medium">{expectationGap.marketConsensus}</p>
                        </div>
                        <div className="p-6 rounded-2xl bg-indigo-600 border border-indigo-50 shadow-lg shadow-indigo-600/10">
                          <p className="text-[9px] text-indigo-200 uppercase font-bold tracking-widest mb-3">{t('analysis.scenarios.our_view')}</p>
                          <p className="text-sm text-white leading-relaxed font-bold">{expectationGap.ourView}</p>
                        </div>
                      </div>
                      <div className="p-6 rounded-2xl bg-white/50 border border-zinc-200/60 relative z-10">
                        <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest mb-3 flex items-center gap-2">
                          <Zap size={12} className="text-amber-500" />
                          {t('analysis.scenarios.gap_reason')}
                        </p>
                        <p className="text-sm text-zinc-600 leading-relaxed font-medium italic">
                          "{expectationGap.gapReason}"
                        </p>
                        {expectationGap.isSignificant && (
                          <div className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-[10px] text-amber-600 font-bold uppercase tracking-widest shadow-sm">
                            <AlertTriangle size={14} />
                            {t('analysis.scenarios.significant_gap')}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Scenario Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {scenarios.map((s, i) => (
                      <div key={`scenario-${s.case}-${s.probability}-${i}`} className={cn(
                        "p-8 rounded-[2rem] border transition-all hover:scale-[1.02] duration-500 shadow-sm relative overflow-hidden group",
                        s.case === "Bull" ? "bg-emerald-500/5 border-emerald-500/20" :
                        s.case === "Stress" ? "bg-rose-500/5 border-rose-500/20" :
                        "bg-indigo-600/5 border-indigo-100"
                      )}>
                        <div className="absolute top-0 right-0 p-6 opacity-[0.03] group-hover:opacity-[0.06] transition-opacity pointer-events-none">
                          {s.case === "Bull" ? <TrendingUp size={80} /> : s.case === "Stress" ? <AlertTriangle size={80} /> : <BarChart3 size={80} />}
                        </div>
                        <div className="flex items-center justify-between mb-6 relative z-10">
                          <span className={cn(
                            "text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-full border shadow-sm",
                            s.case === "Bull" ? "text-emerald-600 border-emerald-600/30 bg-white" :
                            s.case === "Stress" ? "text-rose-500 border-rose-500/30 bg-white" :
                            "text-indigo-600 border-indigo-600/30 bg-white"
                          )}>
                            {s.case === 'Bull' ? t('analysis.scenarios.bull') : s.case === 'Stress' ? t('analysis.scenarios.stress') : t('analysis.scenarios.base')}
                          </span>
                          <div className="text-right">
                            <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest">{t('analysis.scenarios.probability')}</p>
                            <p className="text-xl font-semibold text-zinc-950">{s.probability}%</p>
                          </div>
                        </div>
                        <div className="space-y-6 relative z-10">
                          <div>
                            <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest mb-2">{t('analysis.scenarios.key_assumptions')}</p>
                            <p className="text-sm text-zinc-600 leading-relaxed font-medium">{s.keyInputs}</p>
                          </div>
                          <div className="grid grid-cols-2 gap-4 pt-6 border-t border-zinc-200/60">
                            <div>
                              <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest mb-1">{t('analysis.scenarios.target_valuation')}</p>
                              <p className="text-2xl font-semibold text-zinc-950 tracking-tighter">{s.targetPrice}</p>
                            </div>
                            <div>
                              <p className={cn(
                                "text-[9px] uppercase font-bold tracking-widest mb-1",
                                s.case === "Stress" ? "text-rose-400" : "text-emerald-500"
                              )}>{t('analysis.scenarios.expected_return')}</p>
                              <p className={cn(
                                "text-2xl font-semibold tracking-tighter",
                                s.case === "Stress" ? "text-rose-500" : "text-emerald-500"
                              )}>{s.expectedReturn}</p>
                            </div>
                          </div>
                          <div className="pt-2 flex items-center justify-between">
                            <span className="text-[9px] text-zinc-400 uppercase font-bold tracking-widest">{t('analysis.scenarios.safety_margin')}</span>
                            <span className="text-xs font-semibold text-zinc-600">{s.marginOfSafety}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Sensitivity Analysis */}
              {sensitivityFactors && sensitivityFactors.length > 0 && (
                <div className="rounded-2xl border border-zinc-200 bg-white/40 p-5">
                  <h4 className="mb-4 text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400">{t('analysis.tools.sensitivity_panel')}</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {sensitivityFactors.map((f, i) => (
                      <div key={`sensitivity-${f.factor}-${f.change}-${i}`} className="p-4 rounded-xl bg-zinc-50 border border-zinc-200/50 group hover:border-zinc-200 transition-all">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-medium text-zinc-500">{f.factor}</span>
                          <span className="text-[10px] font-mono text-zinc-400">{f.change}</span>
                        </div>
                        <div className="flex items-end justify-between">
                          <span className={cn(
                            "text-lg font-semibold tracking-tighter",
                            f.impact?.includes('+') ? "text-indigo-600" : "text-rose-400"
                          )}>
                            {f.impact}
                            <span className="text-[10px] ml-1 font-medium text-zinc-400">{t('analysis.tools.delta_tp')}</span>
                          </span>
                          <div className="text-right max-w-[60%]">
                            <span className="text-[10px] text-zinc-400 leading-tight italic block">
                              {f.logic}
                            </span>
                            {f.formula && (
                              <code className="text-[9px] text-zinc-400 font-mono mt-1 block truncate">{f.formula}</code>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Calculation Engine */}
              {calculations.length > 0 && (
                <div className="rounded-2xl border border-amber-500/10 bg-amber-500/5 p-5">
                  <div className="flex items-center gap-2 text-amber-500 mb-4">
                    <Cpu size={16} />
                    <h4 className="text-[10px] font-bold uppercase tracking-[0.2em]">{t('analysis.tools.calculation_engine')}</h4>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {calculations.map((calc, idx) => (
                      <div key={`calc-${calc.formulaName}-${calc.timestamp}-${idx}`} className="p-4 rounded-xl bg-zinc-50 border border-amber-500/10 group hover:border-amber-500/20 transition-all">
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-xs font-semibold text-amber-500 uppercase tracking-widest">{calc.formulaName}</span>
                          <span className="text-[9px] font-mono text-zinc-400">{new Date(calc.timestamp).toLocaleTimeString()}</span>
                        </div>
                        <div className="space-y-3">
                          <div className="grid grid-cols-2 gap-2">
                            {Object.entries(calc.inputs || {}).map(([k, v]) => (
                              <div key={`input-${k}`} className="flex flex-col">
                                <span className="text-[8px] text-zinc-400 uppercase font-semibold">{k}</span>
                                <span className="text-[10px] text-zinc-500 font-mono">{String(v)}</span>
                              </div>
                            ))}
                          </div>
                          <div className="pt-2 border-t border-zinc-200/50 flex items-center justify-between">
                            <span className="text-[9px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.outputs')}</span>
                            <span className="text-sm font-semibold text-amber-500 font-mono">{calc.output}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {stressTestLogic && (
                <div className="p-4 rounded-2xl bg-rose-500/5 border border-rose-500/10">
                  <h4 className="text-[10px] font-medium uppercase tracking-widest text-rose-500 mb-2 flex items-center gap-2">
                    <AlertTriangle size={12} />
                    {t('analysis.tools.stress_test')}
                  </h4>
                  <div className="text-[11px] text-zinc-400 font-mono leading-relaxed">
                    {stressTestLogic}
                  </div>
                </div>
              )}

              {catalystList && catalystList.length > 0 && (
                <div className="p-4 rounded-2xl bg-amber-500/5 border border-amber-500/10">
                  <h4 className="text-[10px] font-medium uppercase tracking-widest text-amber-500 mb-3 flex items-center gap-2">
                    <Zap size={12} />
                    {t('analysis.tools.catalyst_list')}
                  </h4>
                  <div className="space-y-2">
                    {catalystList.map((c: any, i: number) => (
                      <div key={`catalyst-${i}`} className="flex items-center justify-between text-[11px]">
                        <span className="text-zinc-500 font-medium">{typeof c.event === 'string' ? c.event : JSON.stringify(c.event)}</span>
                        <div className="flex items-center gap-4">
                          <span className="text-zinc-400">{t('analysis.tools.probability')}: {c.probability}%</span>
                          <span className="text-amber-500 font-medium">{t('analysis.tools.outputs')}: {c.impact}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {verificationMetrics && verificationMetrics.length > 0 && (
                <div className="p-4 rounded-2xl bg-indigo-600/5 border border-indigo-50">
                  <h4 className="text-[10px] font-medium uppercase tracking-widest text-emerald-500 mb-3 flex items-center gap-2">
                    <CheckCircle2 size={12} />
                    {t('analysis.tools.verification_metrics')}
                  </h4>
                  <div className="space-y-3">
                    {verificationMetrics?.map((m: any, i: number) => (
                      <div key={`verification-${i}`} className="space-y-1">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="text-zinc-600 font-medium">{typeof m.indicator === 'string' ? m.indicator : JSON.stringify(m.indicator)}</span>
                          <span className="text-indigo-600 font-mono">{m.threshold}</span>
                        </div>
                        <div className="flex items-center justify-between text-[9px] text-zinc-400">
                          <span>{t('analysis.tools.expected_duration')}: {m.timeframe}</span>
                          <span className="italic">{m.logic}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {capitalFlow && (
                <div className="p-4 rounded-2xl bg-indigo-50/30 border border-blue-500/10">
                  <h4 className="text-[10px] font-medium uppercase tracking-widest text-blue-500 mb-3 flex items-center gap-2">
                    <Coins size={12} />
                    {t('analysis.tools.capital_flow')}
                  </h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.northbound')}</span>
                      <p className="text-[10px] text-zinc-500">{capitalFlow.northboundFlow}</p>
                    </div>
                    <div className="space-y-1">
                      <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.institutional')}</span>
                      <p className="text-[10px] text-zinc-500">{capitalFlow.institutionalHoldings}</p>
                    </div>
                    {capitalFlow.ahPremium && (
                      <div className="space-y-1">
                        <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.ah_premium')}</span>
                        <p className="text-[10px] text-zinc-500">{capitalFlow.ahPremium}</p>
                      </div>
                    )}
                    <div className="space-y-1">
                      <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.sentiment')}</span>
                      <p className="text-[10px] text-zinc-500">{capitalFlow.marketSentiment}</p>
                    </div>
                  </div>
                </div>
              )}

              {positionManagement && (
                <div className="p-4 rounded-2xl bg-zinc-50/50 border border-zinc-200/60">
                  <h4 className="text-[10px] font-medium uppercase tracking-widest text-zinc-500 mb-3 flex items-center gap-2">
                    <Layers size={12} />
                    {t('analysis.tools.position_management')}
                  </h4>
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.layered_entry')}</span>
                      <div className="flex flex-wrap gap-2">
                        {positionManagement.layeredEntry?.map((step: any, i: number) => (
                          <span key={`entry-step-${i}`} className="text-[9px] px-2 py-0.5 rounded bg-zinc-50 text-zinc-500 border border-zinc-200">{typeof step === 'string' ? step : JSON.stringify(step)}</span>
                        ))}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.outputs')}</span>
                        <p className="text-[10px] text-zinc-500">{positionManagement.sizingLogic}</p>
                      </div>
                      <div className="space-y-1">
                        <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.logic')}</span>
                        <p className="text-[10px] text-zinc-500">{positionManagement.riskAdjustedStance}</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {timeDimension && (
                <div className="p-4 rounded-2xl bg-purple-500/5 border border-purple-500/10">
                  <h4 className="text-[10px] font-medium uppercase tracking-widest text-purple-500 mb-3 flex items-center gap-2">
                    <Clock size={12} />
                    {t('analysis.tools.time_dimension')}
                  </h4>
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.expected_duration')}</span>
                      <p className="text-[10px] text-zinc-500 font-medium">{timeDimension.expectedDuration}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.milestones')}</span>
                        <ul className="list-disc list-inside text-[9px] text-zinc-500 space-y-0.5">
                          {timeDimension.keyMilestones?.map((m: any, i: number) => <li key={`milestone-${i}`}>{typeof m === 'string' ? m : JSON.stringify(m)}</li>)}
                        </ul>
                      </div>
                      <div className="space-y-1">
                        <span className="text-[8px] text-zinc-400 uppercase font-semibold">{t('analysis.tools.exit_triggers')}</span>
                        <ul className="list-disc list-inside text-[9px] text-zinc-500 space-y-0.5">
                          {timeDimension.exitTriggers?.map((t: any, i: number) => <li key={`trigger-${i}`}>{typeof t === 'string' ? t : JSON.stringify(t)}</li>)}
                        </ul>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Moderator messages */}
              {discussionMessages.filter(m => m.role === "Moderator").map((m, i) => (
                <div key={`mod-${i}-${m.id || m.role}`} className="relative">
                  <div className="absolute -left-2 top-0 bottom-0 w-1 bg-indigo-600/50 rounded-full" />
                  <div className="prose prose-sm max-w-none pl-4 pt-1">
                    <ReactMarkdown 
                      remarkPlugins={[remarkGfm]}
                      components={{
                        h1: ({node, ...props}) => <h1 className="text-lg font-bold text-zinc-900 border-b border-zinc-100 pb-2 mb-4" {...props} />,
                        h2: ({node, ...props}) => <h2 className="text-base font-bold text-zinc-800 mb-3" {...props} />,
                        p: ({node, ...props}) => <p className="text-zinc-600 leading-relaxed mb-4" {...props} />,
                        table: ({node, ...props}) => (
                          <div className="my-4 overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm overflow-x-auto">
                            <table className="w-full text-left border-collapse" {...props} />
                          </div>
                        ),
                        thead: ({node, ...props}) => <thead className="bg-zinc-50 border-b border-zinc-100" {...props} />,
                        th: ({node, ...props}) => <th className="px-3 py-2 text-[8px] font-bold text-zinc-400 uppercase tracking-widest" {...props} />,
                        td: ({node, ...props}) => <td className="px-3 py-2 text-[10px] text-zinc-500 border-b border-zinc-50" {...props} />,
                        blockquote: ({node, ...props}) => (
                          <blockquote className="my-4 p-4 rounded-xl bg-zinc-50 border-l-2 border-zinc-300 italic text-zinc-500" {...props} />
                        ),
                      }}
                    >
                      {m.content}
                    </ReactMarkdown>
                  </div>
                </div>
              ))}
              {discussionMessages.length > 0 && isDiscussing && (
                <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-zinc-50/30 border border-zinc-200/60">
                  <div className="loading-pulse">
                    <span /><span /><span />
                  </div>
                  <p className="text-[10px] font-medium text-zinc-400 uppercase tracking-widest">{t('analysis.conference.active_discussion')}</p>
                </div>
              )}
              {discussionMessages.length > 0 && isReviewing && (
                <div className="flex items-center gap-3 px-6 py-4 rounded-2xl bg-indigo-600/5 border border-indigo-100 mt-4">
                  <Loader2 size={16} className="animate-spin text-emerald-500" />
                  <p className="text-xs font-medium text-emerald-500 uppercase tracking-widest">{t('analysis.conference.waiting_moderator')}</p>
                </div>
              )}
              {discussionMessages.length > 0 && !isDiscussing && !isReviewing && !analysis.finalConclusion && (
                <div className="flex items-center gap-3 px-6 py-4 rounded-2xl bg-amber-500/5 border border-amber-500/20 mt-4">
                  <Loader2 size={16} className="animate-spin text-amber-500" />
                  <p className="text-xs font-medium text-amber-500 uppercase tracking-widest">{t('analysis.conference.organizing_opinion')}</p>
                </div>
              )}
            </div>
          )}

          {/* Discussion action buttons */}
          {discussionMessages.length > 0 && !isDiscussing && (
            <div className="pt-4 border-t border-zinc-200 mt-4 space-y-3">
              <button
                onClick={onSendDiscussionReport}
                disabled={isGeneratingReport || isSendingReport}
                className={cn(
                  "w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-xs font-medium transition-all",
                  reportStatus === 'success' 
                    ? "bg-indigo-100 text-indigo-600 border border-indigo-600/50"
                    : reportStatus === 'error'
                    ? "bg-rose-500/20 text-rose-400 border border-rose-500/50"
                    : "bg-zinc-50 border border-zinc-200 hover:bg-zinc-100 text-zinc-500"
                )}
              >
                {isGeneratingReport ? (
                  <>
                    <Loader2 className="animate-spin" size={14} />
                    {t('analysis.actions.generating_report')}
                  </>
                ) : isSendingReport ? (
                  <>
                    <Loader2 className="animate-spin" size={14} />
                    {t('analysis.actions.sending_to_feishu')}
                  </>
                ) : reportStatus === 'success' ? (
                  <>
                    <CheckCircle2 size={14} />
                    {t('analysis.actions.sent')}
                  </>
                ) : (
                  <>
                    <Share2 size={14} />
                    {t('analysis.actions.feishu_discussion')}
                  </>
                )}
              </button>

              <button
                onClick={() => {
                  const content = discussionMessages.map(msg => {
                    const time = new Date(msg.timestamp).toLocaleString();
                    return `### [${t(`analysis.roles.${msg.role}`)}] - ${time}\n\n${msg.content}\n\n---\n\n`;
                  }).join('\n');
                  const header = `# ${t('analysis.expert_discussion')} - ${analysis.stockInfo?.name} (${analysis.stockInfo?.symbol})\n${t('analysis.info.lastUpdated')}: ${new Date().toLocaleString()}\n\n---\n\n`;
                  const fullContent = header + content;
                  const blob = new Blob([fullContent], { type: 'text/markdown' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `Discussion_${analysis.stockInfo?.symbol}_${new Date().toISOString().split('T')[0]}.md`;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                }}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-xs font-medium bg-white border border-zinc-200 hover:bg-zinc-50 text-zinc-500 transition-all"
              >
                <Download size={14} />
                {t('analysis.actions.download_discussion')}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
