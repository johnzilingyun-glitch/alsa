import React, { useMemo } from 'react';
import {
  MessageSquare, Send, Loader2, Share2, CheckCircle2, ChevronDown, ChevronUp
} from 'lucide-react';
import { motion } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import { useUIStore, selectIsChatting } from '../../stores/useUIStore';
import { useAnalysisStore } from '../../stores/useAnalysisStore';

interface ChatSectionProps {
  onSendChatReport: () => void;
  onChat: (message?: string) => void;
}

export function ChatSection({ onSendChatReport, onChat }: ChatSectionProps) {
  const { t } = useTranslation();
  const [isCollapsed, setIsCollapsed] = React.useState(false);
  const isChatting = useUIStore(selectIsChatting);
  const { isGeneratingReport, isSendingReport, reportStatus } = useUIStore();
  const { chatMessage, setChatMessage, chatHistory } = useAnalysisStore();

  const chatPrompts = useMemo(() => [
    t('analysis.chat_prompts.chase_or_wait'),
    t('analysis.chat_prompts.three_month_risk'),
    t('analysis.chat_prompts.stable_plan'),
  ], [t]);

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="rounded-2xl border border-zinc-200 bg-white p-8">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-indigo-600">
          <MessageSquare size={20} />
          <h2 className="text-xl font-semibold">{t('analysis.tools.chat_title')}</h2>
        </div>
        <button
          onClick={onSendChatReport}
          disabled={isGeneratingReport || isSendingReport || !chatHistory || chatHistory.length === 0}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium transition-all",
            reportStatus === 'success' 
              ? "bg-indigo-100 text-indigo-600 border border-indigo-600/50"
              : reportStatus === 'error'
              ? "bg-rose-500/20 text-rose-400 border border-rose-500/50"
              : "bg-zinc-50 border border-zinc-200 hover:bg-zinc-100 text-zinc-500"
          )}
        >
          {isGeneratingReport ? (
            <>
              <Loader2 className="animate-spin" size={12} />
              {t('analysis.actions.generating_report')}
            </>
          ) : isSendingReport ? (
            <>
              <Loader2 className="animate-spin" size={12} />
              {t('analysis.actions.sending_to_feishu')}
            </>
          ) : reportStatus === 'success' ? (
            <>
              <CheckCircle2 size={12} />
              {t('analysis.actions.sent')}
            </>
          ) : (
            <>
              <Share2 size={12} />
              {t('analysis.actions.feishu_discussion')}
            </>
          )}
        </button>
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className="p-2 hover:bg-zinc-100 rounded-xl text-zinc-400 hover:text-indigo-600 transition-all ml-1"
          title={isCollapsed ? "展开" : "收起"}
        >
          {isCollapsed ? <ChevronDown size={18} /> : <ChevronUp size={18} />}
        </button>
      </div>
      
      <AnimatePresence>
        {!isCollapsed && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden"
          >
            <p className="mb-4 text-sm leading-relaxed text-zinc-400">{t('analysis.tools.chat_description')}</p>

            <div className="mb-4 flex flex-wrap gap-2">
              {chatPrompts.map((p, i) => (
                <button key={`chat-prompt-${p.substring(0, 20)}-${i}`} type="button" onClick={() => void onChat(p)} disabled={isChatting} className="rounded-full border border-zinc-200 bg-zinc-50/80 px-3 py-1.5 text-xs text-zinc-500 transition-colors hover:border-indigo-600/50 hover:text-zinc-950 disabled:cursor-not-allowed disabled:opacity-60">
                  {p}
                </button>
              ))}
            </div>

            <div className="mb-6 max-h-96 space-y-4 overflow-y-auto pr-2 custom-scrollbar" role="log" aria-live="polite" aria-label="Chat history">
              {chatHistory?.map((msg, idx) => (
                <div key={`chat-msg-${msg.id || 'no-id'}-${idx}`} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm ${msg.role === 'user' ? 'rounded-tr-none bg-emerald-600 text-zinc-950' : 'rounded-tl-none bg-zinc-50 text-zinc-500'}`}>
                    {msg.content}
                  </div>
                </div>
              ))}
              {isChatting && (
                <div className="flex justify-start">
                  <div className="loading-pulse rounded-2xl rounded-tl-none bg-zinc-50 px-4 py-2 text-sm text-zinc-400">{t('analysis.tools.ai_thinking')}</div>
                </div>
              )}
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={chatMessage}
                onChange={(e) => setChatMessage(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && void onChat()}
                placeholder={t('analysis.tools.ask_ai_placeholder')}
                className="flex-1 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2 text-zinc-950 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-600/50"
              />
              <button onClick={() => void onChat()} disabled={isChatting || !chatMessage.trim()} className="flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-zinc-950 transition-all hover:bg-indigo-700 disabled:opacity-50">
                <Send size={16} />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
