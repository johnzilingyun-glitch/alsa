import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { AgentRole } from '../types';
import { motion, AnimatePresence } from 'motion/react';
import { 
  User, Shield, BarChart3, PieChart, MessageSquare, Loader2, Download, Search, Zap, Send, 
  UserCheck, ExternalLink, AlertTriangle, Award, X, Maximize2, Minimize2, 
  CheckCircle2, ShieldCheck, ShieldAlert, Cpu, Layers, Target, History, RotateCcw, Database, 
  Calculator, Table, Activity, Clock, ArrowRight, Info, Share2, ChevronDown, ChevronUp
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { useTranslation } from 'react-i18next';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import { useAnalysisStore } from '../stores/useAnalysisStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';
import { useUIStore, selectIsDiscussing, selectIsReviewing } from '../stores/useUIStore';
import { useConfigStore } from '../stores/useConfigStore';
import { getQualityLabel } from '../services/dataQualityService';
import { sendAnalysisToFeishu } from '../services/feishuService';
import { ExpertReportCard } from './analysis/ExpertReportCard';
import { DeliberationMatrix } from './analysis/DeliberationMatrix';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const roleIcons: Record<AgentRole, React.ReactNode> = {
  "Technical Analyst": <BarChart3 size={18} />,
  "Fundamental Analyst": <PieChart size={18} />,
  "Sentiment Analyst": <MessageSquare size={18} />,
  "Risk Manager": <Shield size={18} />,
  "Contrarian Strategist": <Zap size={18} />,
  "Deep Research Specialist": <Search size={18} />,
  "Professional Reviewer": <UserCheck size={18} />,
  "Chief Strategist": <Award size={18} />,
  "Moderator": <User size={18} />,
  "Aggressive Risk Analyst": <ShieldAlert size={18} />,
  "Conservative Risk Analyst": <ShieldCheck size={18} />,
  "Neutral Risk Analyst": <Shield size={18} />,
  "Bull Researcher": <Search size={18} />,
  "Bear Researcher": <Search size={18} />,
  "Value Investing Sage": <Database size={18} />,
  "Growth Visionary": <Target size={18} />,
  "Macro Hedge Titan": <Activity size={18} />,
};

// Role color and icon mappings remain as they are visual/functional.
const roleColors: Record<AgentRole, string> = {
  "Technical Analyst": "text-indigo-600 bg-indigo-50 border-indigo-200/60",
  "Fundamental Analyst": "text-emerald-600 bg-emerald-50 border-emerald-200/60",
  "Sentiment Analyst": "text-purple-600 bg-purple-50 border-purple-200/60",
  "Risk Manager": "text-rose-600 bg-rose-50 border-rose-200/60",
  "Contrarian Strategist": "text-orange-600 bg-orange-50 border-orange-200/60",
  "Deep Research Specialist": "text-cyan-600 bg-cyan-50 border-cyan-200/60",
  "Professional Reviewer": "text-blue-600 bg-blue-50 border-blue-200/60",
  "Chief Strategist": "text-amber-600 bg-amber-50 border-amber-200/60",
  "Moderator": "text-zinc-600 bg-zinc-50 border-zinc-200/60",
  "Aggressive Risk Analyst": "text-red-600 bg-red-50 border-red-200/60",
  "Conservative Risk Analyst": "text-green-600 bg-green-50 border-green-200/60",
  "Neutral Risk Analyst": "text-blue-600 bg-blue-50 border-blue-200/60",
  "Bull Researcher": "text-orange-600 bg-orange-50 border-orange-200/60",
  "Bear Researcher": "text-slate-600 bg-slate-50 border-slate-200/60",
  "Value Investing Sage": "text-teal-600 bg-teal-50 border-teal-200/60",
  "Growth Visionary": "text-fuchsia-600 bg-fuchsia-50 border-fuchsia-200/60",
  "Macro Hedge Titan": "text-cyan-700 bg-cyan-50 border-cyan-200/60",
};

interface DiscussionPanelProps {
  onSendMessage?: (message: string) => void;
  onGenerateNewConclusion?: () => void;
  onClose?: () => void;
  isFullscreen?: boolean;
  onToggleFullscreen?: () => void;
  onPointerDownDrag?: (e: React.PointerEvent) => void;
}

export const DiscussionPanel: React.FC<DiscussionPanelProps> = ({
  onSendMessage,
  onGenerateNewConclusion,
  onClose,
  isFullscreen,
  onToggleFullscreen,
  onPointerDownDrag
}) => {
  const { t } = useTranslation();
  const { analysis } = useAnalysisStore();
  const { 
    discussionMessages: messages, 
    analystWeights, 
    currentRound, 
    totalRounds,
    activeExperts,
    currentStep,
    expectedValueOutcome: discussionExpectedValue,
    sensitivityMatrix: discussionSensitivity
  } = useDiscussionStore();

  const isDiscussing = useUIStore(selectIsDiscussing);
  const isReviewing = useUIStore(selectIsReviewing);

  const { feishuWebhookUrl, setFeishuWebhookUrl } = useConfigStore();
  const [showFeishuConfig, setShowFeishuConfig] = useState(false);
  const [tempWebhook, setTempWebhook] = useState(feishuWebhookUrl);
  const [isSendingToFeishu, setIsSendingToFeishu] = useState(false);
  const [shareStatus, setShareStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [isInputCollapsed, setIsInputCollapsed] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = React.useState('');
  const stockSymbol = analysis?.stockInfo?.symbol;
  const dataVerification = analysis?.dataVerification;

  const getWeightInfo = (role: AgentRole) => {
    return analystWeights?.find(w => w.role === role);
  };

  useLayoutEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isDiscussing]);

  const handleSend = () => {
    if (inputValue.trim() && onSendMessage) {
      onSendMessage(inputValue.trim());
      setInputValue('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleDownload = () => {
    if (messages.length === 0) return;

    const content = messages.map(msg => {
      const time = new Date(msg.timestamp).toLocaleString();
      const roleName = t(`analysis.roles.${msg.role}`);
      return `### [${roleName}] - ${time}\n\n${msg.content}\n\n---\n\n`;
    }).join('\n');

    const header = `# ${t('analysis.expert_discussion')} - ${stockSymbol || '未知股票'}\n${t('analysis.info.lastUpdated')}: ${new Date().toLocaleString()}\n\n---\n\n`;
    const fullContent = header + content;

    const blob = new Blob([fullContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `AI_Discussion_${stockSymbol || 'Report'}_${new Date().toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleFeishuShare = async () => {
    if (!feishuWebhookUrl) {
      setTempWebhook('');
      setShowFeishuConfig(true);
      return;
    }

    setIsSendingToFeishu(true);
    setShareStatus('loading');
    try {
      const success = await sendAnalysisToFeishu(analysis!, feishuWebhookUrl);
      if (success) {
        setShareStatus('success');
        setTimeout(() => setShareStatus('idle'), 3000);
      } else {
        setShareStatus('error');
        setTimeout(() => setShareStatus('idle'), 3000);
      }
    } catch (error) {
      console.error(error);
      setShareStatus('error');
      setTimeout(() => setShareStatus('idle'), 3000);
    } finally {
      setIsSendingToFeishu(false);
    }
  };

  const saveFeishuWebhook = () => {
    if (!tempWebhook.trim() || !tempWebhook.includes('feishu.cn')) {
      setShareStatus('error');
      setTimeout(() => setShareStatus('idle'), 3000);
      return;
    }
    setFeishuWebhookUrl(tempWebhook.trim());
    setShowFeishuConfig(false);
    setTimeout(handleFeishuShare, 100);
  };

  return (
    <div className="flex flex-col h-full bg-white overflow-hidden relative shadow-3xl">
      {/* Background Decoration */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-10%] right-[-10%] w-[50%] h-[50%] bg-indigo-500/5 blur-[120px]" />
        <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] bg-violet-500/5 blur-[120px]" />
      </div>

      {/* Header Bar */}
      <div className="px-8 py-6 border-b border-zinc-100 bg-white/70 backdrop-blur-xl flex items-center justify-between relative z-10 shadow-sm">
        <div className="flex items-center gap-6">
          <div
            className="group relative cursor-grab active:cursor-grabbing p-2 hover:bg-zinc-100 rounded-2xl transition-all"
            onPointerDown={onPointerDownDrag}
          >
            <div className="w-3.5 h-3.5 rounded-full bg-indigo-600 shadow-lg shadow-indigo-600/30 animate-pulse" />
          </div>
          <div>
            <h3 className="text-sm font-bold tracking-tight text-zinc-950 uppercase flex items-center gap-2">
              {t('analysis.expert_discussion')}
              <span className="text-[9px] font-bold text-zinc-400 border border-zinc-200 px-1.5 py-0.5 rounded-md">LIVE</span>
            </h3>
            <p className="text-[10px] font-medium text-zinc-400 mt-0.5 tracking-wider">{t('app.subtitle')}</p>
          </div>
          
          <div className="ml-6 hidden md:flex items-center gap-3">
            <div className="h-6 w-px bg-zinc-100" />
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-zinc-50 border border-zinc-100">
              <Target size={12} className="text-zinc-400" />
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{stockSymbol || 'GLOBAL MONITOR'}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 mr-3">
            {messages.length > 0 && !isDiscussing && (
              <button
                onClick={handleDownload}
                className="btn-secondary h-10 px-4 rounded-xl text-[10px] tracking-wider uppercase border-zinc-100 shadow-sm"
              >
                <Download size={14} />
                {t('analysis.actions.download_discussion')}
              </button>
            )}

            {messages.length > 0 && !isDiscussing && (
              <button
                onClick={handleFeishuShare}
                disabled={isSendingToFeishu}
                className={cn(
                  "btn-primary h-10 px-5 rounded-xl text-[10px] tracking-wider uppercase shadow-indigo-600/5",
                  shareStatus === "success" && "bg-emerald-500 hover:bg-emerald-600",
                  shareStatus === "error" && "bg-rose-500 hover:bg-rose-600"
                )}
              >
                {shareStatus === "loading" ? <Loader2 size={14} className="animate-spin" /> : 
                shareStatus === "success" ? <CheckCircle2 size={14} /> : 
                shareStatus === "error" ? <AlertTriangle size={14} /> : <Share2 size={14} />}
                {shareStatus === "loading" ? t('analysis.actions.sending_to_feishu') : shareStatus === "success" ? t('analysis.actions.sent') : t('analysis.actions.feishu_discussion')}
              </button>
            )}
          </div>

          {isDiscussing && (
            <div className="flex items-center gap-3 px-4 py-1.5 rounded-full bg-indigo-50 border border-indigo-100">
              <Loader2 size={14} className="animate-spin text-indigo-600 shrink-0" />
              <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-widest">
                {currentRound > 0 ? t('analysis.conference.round', { n: currentRound }) : t('analysis.conference.status_entering')}
              </span>
            </div>
          )}

          <div className="flex h-10 w-[1px] bg-zinc-100 mx-1" />

          {onToggleFullscreen && (
            <button
              onClick={onToggleFullscreen}
              className="p-2.5 hover:bg-zinc-100 rounded-xl text-zinc-400 hover:text-zinc-950 transition-all"
            >
              {isFullscreen ? <Minimize2 size={18} /> : <Maximize2 size={18} />}
            </button>
          )}

          {onClose && (
            <button
              onClick={onClose}
              className="p-2.5 hover:bg-zinc-100 rounded-xl text-zinc-400 hover:text-rose-500 transition-all"
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-8 md:px-12 py-10 space-y-12 bg-white relative custom-scrollbar"
        role="log"
        aria-live="polite"
        aria-label="Expert discussion messages"
      >
        {/* Progress Matrix */}
        {isDiscussing && totalRounds > 0 && (
          <DeliberationMatrix 
            currentRound={currentRound}
            totalRounds={totalRounds}
            activeExperts={activeExperts}
            currentStep={currentStep}
          />
        )}

        {/* Performance Review (Backtest) */}
        {analysis?.backtestResult && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="max-w-4xl mx-auto bg-indigo-50/80 border border-indigo-600/30 rounded-2xl p-6 relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 p-8 opacity-5">
              <RotateCcw size={120} className="text-indigo-600 rotate-12" />
            </div>
            
            <div className="relative z-10 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-xl bg-indigo-600/20 flex items-center justify-center border border-indigo-600/30">
                    <History size={20} className="text-indigo-600" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold uppercase tracking-widest text-indigo-600">{t('analysis.prediction.track_record')} (Learning Loop)</h4>
                    <p className="text-[10px] text-zinc-400">{t('analysis.info.lastUpdated')}: {new Date(analysis.backtestResult.previousDate).toLocaleString()}</p>
                  </div>
                </div>
                <div className="text-right">
                  <span className={`text-xs font-semibold px-3 py-1 rounded-full border ${ analysis.backtestResult.actualReturn.startsWith('+') ? 'bg-emerald-500/8 border-emerald-500/15 text-emerald-500' : 'bg-rose-500/6 border-rose-500/15 text-rose-500' }`}>
                    {t('analysis.prediction.streaks')}: {analysis.backtestResult.actualReturn}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-zinc-100/80 rounded-xl p-3 border border-zinc-200/60">
                  <p className="text-[10px] text-zinc-400 uppercase font-medium mb-1">{t('analysis.info.summary')}</p>
                  <p className="text-sm font-semibold text-zinc-950">{analysis.backtestResult.previousRecommendation}</p>
                </div>
                <div className="bg-zinc-100/80 rounded-xl p-3 border border-zinc-200/60 col-span-2">
                  <p className="text-[10px] text-indigo-600 uppercase font-medium mb-1">{t('analysis.expert_discussion')} Wisdom</p>
                  <p className="text-xs text-zinc-600 leading-relaxed italic">"{analysis.backtestResult.learningPoint}"</p>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {/* Expected Value Center */}
        {(discussionExpectedValue || analysis?.expectedValueOutcome) && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="max-w-4xl mx-auto space-y-6"
          >
            {(() => {
              const evData = discussionExpectedValue || analysis?.expectedValueOutcome;
              return (
                <>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded-xl bg-indigo-600/10 flex items-center justify-center border border-indigo-600/15">
                        <Calculator size={18} className="text-indigo-600" />
                      </div>
                      <h4 className="text-sm font-bold uppercase tracking-wider text-indigo-600">{t('tools.expected_value_center')} (Expected Value)</h4>
                    </div>
                    <div className="text-right">
                      <p className="text-[10px] text-zinc-400 uppercase font-semibold">{t('scenarios.target_valuation')}</p>
                      <p className="text-2xl font-semibold text-zinc-950 tracking-tighter">${evData.expectedPrice}</p>
                    </div>
                  </div>
 
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div className="bg-white border border-zinc-200/60 rounded-2xl p-5 space-y-4">
                      <div className="flex items-center gap-2 border-b border-zinc-200/60 pb-3">
                        <Activity size={16} className="text-indigo-600" />
                        <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">{t('scenarios.gap_reason')}</span>
                      </div>
                      <div className="bg-zinc-100/80 rounded-xl p-4 border border-zinc-200/60 font-mono text-xs text-indigo-500/80 leading-relaxed italic">
                        "{evData.calculationLogic}"
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-zinc-400 mt-2">
                        <span>{t('analysis.info.ai_confidence')}: <span className="text-zinc-500 font-medium">{evData.confidenceInterval}</span></span>
                        <span className="flex items-center gap-1"><Shield size={10} /> {t('analysis.info.data_verification_passed')}</span>
                      </div>
                    </div>
 
                    {(() => {
                      const matrix = discussionSensitivity || analysis?.sensitivityMatrix;
                      return matrix && (
                        <div className="bg-white border border-zinc-200/60 rounded-2xl p-5 space-y-4">
                          <div className="flex items-center gap-2 border-b border-zinc-200/60 pb-3">
                            <Table size={16} className="text-emerald-500" />
                            <span className="text-[11px] font-bold uppercase tracking-widest text-zinc-500">{t('tools.sensitivity_panel')}</span>
                          </div>
                          <div className="space-y-2">
                            {matrix.map((row: any, idx: number) => (
                              <div key={`smr-${row.variable}-${idx}`} className="flex items-center justify-between text-[11px] py-1 border-b border-zinc-200/60 last:border-0">
                                <div className="flex items-center gap-2">
                                  <span className="text-zinc-400 w-20 truncate">{row.variable}</span>
                                  <span className="text-zinc-400 font-mono italic">{row.change}</span>
                                  <ArrowRight size={10} className="text-zinc-300" />
                                </div>
                                <div className="text-right">
                                  <span className={cn(
                                    "font-semibold tracking-tighter mr-2",
                                    row.profitImpact?.includes('+') ? "text-emerald-500" : 
                                    row.profitImpact?.includes('-') ? "text-rose-500" : "text-zinc-500"
                                  )}>
                                    {row.profitImpact || '-'}
                                  </span>
                                  <span className="text-[9px] text-zinc-300 flex items-center gap-0.5 justify-end">
                                    <Clock size={8} /> {row.timeLag}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                </>
              );
            })()}
          </motion.div>
        )}

        <AnimatePresence initial={false}>
          {messages.map((msg, i) => {
            const msgKey = msg.id || `${msg.role}-${msg.timestamp}-${i}`;
            const weightInfo = getWeightInfo(msg.role);
            
            const verification = dataVerification?.find(v => v.source === msg.role);
            
            return (
              <ExpertReportCard 
                key={msgKey}
                message={msg}
                isExpert={weightInfo?.isExpert}
                expertiseArea={weightInfo?.expertiseArea}
                references={msg.references}
                isVerified={verification?.isVerified}
                auditDetail={verification?.discrepancy}
              />
            );
          })}
        </AnimatePresence>

        {messages.length === 0 && !isDiscussing && (
          <div className="flex-1 flex flex-col items-center justify-center text-zinc-200 py-32 space-y-6">
            <Activity size={64} strokeWidth={1} className="text-zinc-100" />
            <div className="text-center space-y-2">
              <p className="text-sm font-bold uppercase tracking-[0.3em] text-zinc-300">{t('analysis.conference.status_entering')}</p>
              <p className="text-[10px] uppercase font-bold tracking-[0.1em] text-zinc-400">{t('app.description')}</p>
            </div>
          </div>
        )}
      </div>

      {/* Footer / Input */}
      {messages.length > 0 && !isDiscussing && onSendMessage && (
        <div className="border-t border-zinc-100 bg-white relative z-10 shadow-[0_-12px_40px_-20px_rgba(0,0,0,0.05)]">
          {/* Collapse Toggle Button */}
          <div className="flex justify-center -mt-3.5 relative z-20">
            <button
              onClick={() => setIsInputCollapsed(!isInputCollapsed)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white border border-zinc-200 text-zinc-400 hover:text-indigo-600 hover:border-indigo-200 transition-all shadow-sm hover:shadow-md"
              title={isInputCollapsed ? t('common.expand') : t('common.collapse')}
            >
              {isInputCollapsed ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              <span className="text-[9px] font-bold uppercase tracking-widest">{isInputCollapsed ? t('common.expand') : t('common.collapse')}</span>
            </button>
          </div>

          <AnimatePresence>
            {!isInputCollapsed && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.3, ease: "easeInOut" }}
                className="overflow-hidden"
              >
                <div className="p-8">
                  <div className="relative flex flex-col gap-4 max-w-4xl mx-auto">
                    <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600">
                  <Cpu size={14} className="animate-pulse" />
                  <span className="text-xs font-bold uppercase tracking-wider">{t('analysis.expert_discussion')} (Automated Routing)</span>
                </div>
                <span className="text-[10px] text-zinc-400 font-medium">{t('analysis.actions.ask_analyst')}</span>
              </div>
              {onGenerateNewConclusion && (
                <button
                  onClick={onGenerateNewConclusion}
                  disabled={isReviewing}
                  className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-white text-zinc-600 hover:bg-zinc-50 border border-zinc-200 text-sm font-medium transition-all disabled:opacity-50"
                >
                  <Award size={16} />
                  {t('analysis.conference.final_consensus')}
                </button>
              )}
            </div>
            <div className="flex-1 relative">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('header.searchPlaceholder')}
                className="w-full input-premium px-6 py-4 pr-16 text-base h-[60px] resize-none rounded-2xl"
                rows={1}
                disabled={isReviewing}
              />
              <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2">
                {isReviewing ? (
                  <Loader2 size={24} className="animate-spin text-indigo-600" />
                ) : (
                  <button
                    onClick={handleSend}
                    disabled={!inputValue.trim()}
                    className="p-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white disabled:bg-zinc-100 disabled:text-zinc-400 transition-all shadow-sm active:scale-[0.98]"
                  >
                    <Send size={20} />
                  </button>
                )}
              </div>
            </div>
          </div>
          <p className="mt-3 text-[10px] text-zinc-400 px-2 flex items-center gap-1.5 font-bold uppercase tracking-wider max-w-4xl mx-auto">
            <Zap size={14} className="text-indigo-600" />
                    {t('analysis.conference.alpha_hint')}
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Feishu Config Modal */}
      <AnimatePresence>
        {showFeishuConfig && (
          <div className="absolute inset-0 z-[100] flex items-center justify-center bg-zinc-900/10 backdrop-blur-xl p-10">
            <motion.div 
              initial={{ scale: 0.98, opacity: 0, y: 10 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.98, opacity: 0, y: 10 }}
              className="w-full max-w-lg bg-white border border-zinc-200 rounded-[2.5rem] p-10 shadow-2xl relative overflow-hidden"
            >
              <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/5 blur-[80px] -z-10" />
              
              <div className="flex items-center gap-6 mb-10">
                <div className="p-4 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100/50 shadow-sm">
                  <Share2 size={28} strokeWidth={1.5} />
                </div>
                <div>
                  <h3 className="text-2xl font-bold text-zinc-950 tracking-tight">飞书同步系统</h3>
                  <p className="text-[10px] text-zinc-400 font-bold uppercase tracking-[0.2em] mt-0.5">Institutional Delivery Configuration</p>
                </div>
              </div>

              <div className="space-y-8">
                <div className="space-y-4">
                  <label className="block text-[10px] font-bold text-zinc-400 uppercase tracking-[0.3em]">Feishu Webhook Endpoint</label>
                  <div className="relative group">
                    <input 
                      type="text" 
                      value={tempWebhook}
                      onChange={(e) => setTempWebhook(e.target.value)}
                      placeholder="https://open.feishu.cn/..."
                      className="input-premium h-12 pr-10 font-mono text-sm"
                      autoFocus
                    />
                    <div className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-300">
                      <ExternalLink size={16} />
                    </div>
                  </div>
                </div>
                
                <div className="p-5 rounded-2xl bg-indigo-50/50 border border-indigo-100/50 flex gap-4 items-start">
                  <Info size={18} className="text-indigo-400 mt-0.5 shrink-0" strokeWidth={2} />
                  <p className="text-xs text-indigo-600 font-medium leading-relaxed">
                    配置完成后，分析记录将以 <span className="font-bold">互动式卡片</span> 形式实时推送到工作群。
                  </p>
                </div>

                <div className="flex gap-4 pt-4">
                  <button 
                    onClick={() => setShowFeishuConfig(false)}
                    className="flex-1 h-12 rounded-xl bg-zinc-50 hover:bg-zinc-100 text-zinc-500 text-xs font-bold uppercase tracking-widest transition-all"
                  >
                    {t('common.cancel')}
                  </button>
                  <button 
                    onClick={saveFeishuWebhook}
                    className="flex-1 h-12 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold uppercase tracking-widest shadow-xl shadow-indigo-600/10 transition-all active:scale-[0.98]"
                  >
                    {t('common.save_push')}
                  </button>
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
