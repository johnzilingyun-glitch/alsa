import React, { useState } from 'react';
import { MessageSquare } from 'lucide-react';
import { motion, AnimatePresence, useDragControls } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { useUIStore, selectIsDiscussing } from '../../stores/useUIStore';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { useDiscussionStore } from '../../stores/useDiscussionStore';
import { useMarketStore } from '../../stores/useMarketStore';
import { usePredictionTrackRecord } from '../../hooks/usePredictionTrackRecord';
import { DiscussionPanel } from '../DiscussionPanel';
import { AnalysisActionBar } from './AnalysisActionBar';
import { ConferenceResults } from './ConferenceResults';
import { StockHeroCard } from './StockHeroCard';
import { SidebarSummary } from './SidebarSummary';
import { ScorePanel } from './ScorePanel';
import { ChatSection } from './ChatSection';
import { AnalysisFeedback } from './AnalysisFeedback';

interface AnalysisResultProps {
  onResetToHome: () => void;
  onExportFullReport: () => void;
  onSendStockReport: () => void;
  onSendDiscussionReport: () => void;
  onSendChatReport: () => void;
  onDiscussionQuestion: (question: string) => void;
  onGenerateNewConclusion: () => void;
  onChat: (message?: string) => void;
}

export function AnalysisResult({
  onResetToHome,
  onExportFullReport,
  onSendStockReport,
  onSendDiscussionReport,
  onSendChatReport,
  onDiscussionQuestion,
  onGenerateNewConclusion,
  onChat,
}: AnalysisResultProps) {
  const { t } = useTranslation();
  const [isDiscussionFullscreen, setIsDiscussionFullscreen] = useState(false);
  const dragControls = useDragControls();

  const isDiscussing = useUIStore(selectIsDiscussing);
  const { showDiscussion, setShowDiscussion } = useUIStore();
  const { analysis } = useAnalysisStore();
  const { discussionMessages } = useDiscussionStore();
  const { watchlist, setWatchlist } = useMarketStore();
  const trackRecord = usePredictionTrackRecord(analysis);

  const toggleWatchlist = async () => {
    if (!analysis?.stockInfo) return;
    const stock = {
      symbol: analysis.stockInfo.symbol,
      name: analysis.stockInfo.name,
      market: analysis.stockInfo.market as any
    };
    const isStarred = watchlist.some(w => w.symbol === stock.symbol);
    try {
      if (isStarred) {
        const res = await fetch(`/api/watchlist/${stock.symbol}?market=${stock.market}`, { method: 'DELETE' });
        if (res.ok) setWatchlist(watchlist.filter(w => w.symbol !== stock.symbol));
      } else {
        const res = await fetch('/api/watchlist/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(stock)
        });
        if (res.ok) {
          const newItem = await res.json();
          setWatchlist([...watchlist, newItem]);
        }
      }
    } catch (err) {
      console.error('Failed to toggle watchlist:', err);
    }
  };

  if (!analysis) return null;

  return (
    <motion.main
      key={analysis.stockInfo?.symbol}
      initial={{ opacity: 1, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-8"
      role="main"
      aria-label={`${analysis.stockInfo?.name} Analysis`}
    >
      <AnalysisActionBar
        onResetToHome={onResetToHome}
        onExportFullReport={onExportFullReport}
        onSendStockReport={onSendStockReport}
      />

      <ConferenceResults
        analysis={analysis}
        onSendDiscussionReport={onSendDiscussionReport}
      />

      {/* Floating Discussion Panel */}
      <AnimatePresence>
        {showDiscussion && (
          <div className={`fixed inset-0 z-50 flex items-center justify-center pointer-events-none ${isDiscussionFullscreen ? 'p-0' : 'p-4 md:p-8'}`}>
            {!isDiscussionFullscreen && (
              <motion.div 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="absolute inset-0 bg-zinc-900/10 backdrop-blur-sm pointer-events-auto" 
                onClick={() => setShowDiscussion(false)} 
              />
            )}
            
            <motion.div
              drag={!isDiscussionFullscreen}
              dragMomentum={false}
              dragListener={false}
              dragControls={dragControls}
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ 
                opacity: 1, 
                scale: 1, 
                y: 0,
                width: isDiscussionFullscreen ? '100%' : '100%',
                height: isDiscussionFullscreen ? '100%' : '85vh',
              }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className={`relative z-10 flex flex-col overflow-hidden pointer-events-auto bg-white border border-zinc-200 shadow-2xl ${ isDiscussionFullscreen ? 'rounded-none border-0 max-w-none w-full h-full' : 'rounded-3xl w-full md:max-w-5xl' }`}
              role="dialog"
              aria-label="Expert Discussion"
              aria-modal="true"
            >
              <DiscussionPanel 
                onSendMessage={onDiscussionQuestion}
                onGenerateNewConclusion={onGenerateNewConclusion}
                onClose={() => setShowDiscussion(false)}
                isFullscreen={isDiscussionFullscreen}
                onToggleFullscreen={() => setIsDiscussionFullscreen(!isDiscussionFullscreen)}
                onPointerDownDrag={(e) => dragControls.start(e)}
              />
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Floating Chat Button */}
      {(isDiscussing || discussionMessages.length > 0) && !showDiscussion && (
        <button
          onClick={() => setShowDiscussion(true)}
          className="fixed bottom-8 right-8 p-4 rounded-2xl bg-emerald-600 text-zinc-950 shadow-[0_0_30px_-5px_rgba(16,185,129,0.5)] hover:bg-indigo-700 hover:scale-105 transition-all z-40 group flex items-center justify-center border border-emerald-400/30"
        >
          <MessageSquare size={24} />
          {isDiscussing && (
            <span className="absolute -top-1 -right-1 flex h-4 w-4">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-4 w-4 bg-rose-500 border-2 border-zinc-200"></span>
            </span>
          )}
          <span className="absolute right-full mr-4 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap bg-zinc-50 text-zinc-500 text-xs px-3 py-1.5 rounded-xl border border-zinc-200 font-medium">
            {t('analysis.conference.expand_meeting')}
          </span>
        </button>
      )}

      {/* Main Analysis Grid */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <div className="space-y-8 lg:col-span-2">
          <StockHeroCard 
            analysis={analysis} 
            isStarred={watchlist.some(w => w.symbol === analysis.stockInfo?.symbol)}
            onToggleWatchlist={toggleWatchlist} 
          />
          <SidebarSummary analysis={analysis} />
        </div>

        <div className="space-y-8">
          <ScorePanel analysis={analysis} trackRecord={trackRecord} />
          <ChatSection onSendChatReport={onSendChatReport} onChat={onChat} />
        </div>
      </div>

      {/* Silver Titanium Feedback System (EvolveR) */}
      <div className="max-w-4xl mx-auto pb-12">
        <AnalysisFeedback 
          analysisId={analysis.id || ''} 
          symbol={analysis.stockInfo?.symbol || ''} 
        />
      </div>
    </motion.main>
  );
}
