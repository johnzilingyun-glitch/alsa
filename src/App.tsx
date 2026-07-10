import { useState, useEffect, useRef, lazy, Suspense } from 'react';
import { AnimatePresence } from 'motion/react';
import { Loader2 } from 'lucide-react';

import { useTranslation } from 'react-i18next';
import { useStockAnalysis } from './hooks/useStockAnalysis';
import { useDiscussion } from './hooks/useDiscussion';
import { useChat } from './hooks/useChat';
import { useReporting } from './hooks/useReporting';
import { useMarketData } from './hooks/useMarketData';
import { useUrlState } from './hooks/useUrlState';
import { useI18nSync } from './hooks/useI18nSync';
import { useUIStore } from './stores/useUIStore';
import { useMarketStore } from './stores/useMarketStore';
import { useAnalysisStore } from './stores/useAnalysisStore';
import { useDiscussionStore } from './stores/useDiscussionStore';
import { useScenarioStore } from './stores/useScenarioStore';
import { useConfigStore } from './stores/useConfigStore';
import { useStatsStore } from './stores/useStatsStore';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ErrorNotice } from './components/ErrorNotice';
import { TokenUsage } from './components/dashboard/TokenUsage';
import { Header } from './components/layout/Header';
import { ConfirmDialog } from './components/shared/ConfirmDialog';
import { Toast } from './components/shared/Toast';
import { NotificationBubbles } from './components/shared/NotificationBubbles';
import { AuthGuard } from './components/auth/AuthGuard';

if (import.meta.env.DEV && typeof window !== 'undefined') {
  (window as any).useAnalysisStore = useAnalysisStore;
}

// Lazy-load conditionally rendered large components
const SettingsModal = lazy(() => import('./components/SettingsModal').then(m => ({ default: m.SettingsModal })));
const HistoryModal = lazy(() => import('./components/HistoryModal').then(m => ({ default: m.HistoryModal })));
const AnalysisResult = lazy(() => import('./components/analysis/AnalysisResult').then(m => ({ default: m.AnalysisResult })));
const AdminPanel = lazy(() => import('./components/admin/AdminPanel').then(m => ({ default: m.AdminPanel })));
const SystemMonitor = lazy(() => import('./components/admin/SystemMonitor').then(m => ({ default: m.SystemMonitor })));
const UserManagement = lazy(() => import('./components/admin/UserManagement').then(m => ({ default: m.UserManagement })));
const IncidentConsole = lazy(() => import('./components/admin/IncidentConsole').then(m => ({ default: m.IncidentConsole })));

const AnalysisLoadingPulse = lazy(() => import('./components/analysis/AnalysisLoadingPulse').then(m => ({ default: m.AnalysisLoadingPulse })));
const SignalCenter = lazy(() => import('./components/dashboard/SignalCenter').then(m => ({ default: m.SignalCenter })));
const HistorySelectionDialog = lazy(() => import('./components/analysis/HistorySelectionDialog').then(m => ({ default: m.HistorySelectionDialog })));
const MarketOverview = lazy(() => import('./components/dashboard/MarketOverview').then(m => ({ default: m.MarketOverview })));
const DetailModal = lazy(() => import('./components/shared/DetailModal').then(m => ({ default: m.DetailModal })));
const IBKRDashboard = lazy(() => import('./components/dashboard/IBKRDashboard').then(m => ({ default: m.IBKRDashboard })));
const MockTradingDashboard = lazy(() => import('./components/dashboard/MockTradingDashboard').then(m => ({ default: m.MockTradingDashboard })));
const BacktestPanel = lazy(() => import('./components/dashboard/BacktestPanel').then(m => ({ default: m.BacktestPanel })));
const PredictionDashboard = lazy(() => import('./components/dashboard/PredictionDashboard').then(m => ({ default: m.PredictionDashboard })));
const ThsAnalysis = lazy(() => import('./components/dashboard/ThsAnalysis').then(m => ({ default: m.ThsAnalysis })));
const NewArchCompare = lazy(() => import('./components/NewArchCompare').then(m => ({ default: m.NewArchCompare })));

export default function App() {
  console.log('App is rendering');
  const { t, i18n } = useTranslation();
  const language = useConfigStore(s => s.language);

  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isSignalsOpen, setIsSignalsOpen] = useState(false);

  const watchlist = useMarketStore(s => s.watchlist);
  const setWatchlist = useMarketStore(s => s.setWatchlist);
  const setAlerts = useMarketStore(s => s.setAlerts);

  const recordSession = useStatsStore(s => s.recordSession);
  useEffect(() => {
    // Count every page load/refresh as a visit
    recordSession();
  }, [recordSession]);

  // Granular UI store selection to avoid render loops
  const analysisError = useUIStore(s => s.analysisError);
  const showAdminPanel = useUIStore(s => s.showAdminPanel);
  const showIBKRDashboard = useUIStore(s => s.showIBKRDashboard);
  const showMockTradingDashboard = useUIStore(s => s.showMockTradingDashboard);
  const showBacktestPanel = useUIStore(s => s.showBacktestPanel);
  const showPredictionDashboard = useUIStore(s => s.showPredictionDashboard);
  const showThsAnalysis = useUIStore(s => s.showThsAnalysis);
  const setShowDiscussion = useUIStore(s => s.setShowDiscussion);
  const setIsSettingsOpen = useUIStore(s => s.setIsSettingsOpen);

  const analysis = useAnalysisStore(s => s.analysis);
  const setAnalysis = useAnalysisStore(s => s.setAnalysis);
  const setSymbol = useAnalysisStore(s => s.setSymbol);
  const setMarket = useAnalysisStore(s => s.setMarket);
  const setChatHistory = useAnalysisStore(s => s.setChatHistory);
  const resetAnalysis = useAnalysisStore(s => s.resetAnalysis);
  const setLastJobId = useAnalysisStore(s => s.setLastJobId);

  const setDiscussionResults = useDiscussionStore(s => s.setDiscussionResults);
  const resetDiscussion = useDiscussionStore(s => s.resetDiscussion);

  const setScenarioResults = useScenarioStore(s => s.setScenarioResults);
  const resetScenario = useScenarioStore(s => s.resetScenario);

  // Custom hooks for business logic
  const { handleSearch, resetToHome, fetchAdminData, historyDialogOpen, historyDialogItems, pendingSearchSymbol, setHistoryDialogOpen, doStartAnalysis, loadHistoryResult, loadBackgroundResult } = useStockAnalysis();
  const { handleDiscussionQuestion, handleGenerateNewConclusion } = useDiscussion(fetchAdminData);
  const { handleChat } = useChat(fetchAdminData);
  const { fetchMarketDashboard: fetchMarketOverview } = useMarketData(fetchAdminData);
  const {
    handleSendStockReport,
    handleSendChatReport,
    handleSendDiscussionReport,
    handleSendHistoryToFeishu,
    handleExportFullReport,
    handleExportPdf,
    handleExportShareCard,
  } = useReporting(fetchAdminData);

  // URL state sync: auto-search from ?symbol=&market= on first load
  const { initialUrlParams } = useUrlState();
  const hasAutoSearched = useRef(false);

  useEffect(() => {
    if (hasAutoSearched.current || !initialUrlParams.symbol) return;
    
    const targetSymbol = initialUrlParams.symbol;
    const targetMarket = initialUrlParams.market || 'US-Share';
    
    setSymbol(targetSymbol);
    setMarket(targetMarket);
    
    hasAutoSearched.current = true;
    handleSearch(undefined, targetSymbol, targetMarket);
  }, [initialUrlParams, setSymbol, setMarket, handleSearch]);

  // Watch for model or API key changes, but only trigger AI enrichment when settings modal is CLOSED.
  // This prevents multiple re-renders and rate limit calls while typing.
  const isSettingsOpen = useUIStore(s => s.isSettingsOpen);
  const prevSettingsOpen = useRef(isSettingsOpen);
  const initialConfigRef = useRef({ model: '', apiKey: '', deepseekApiKey: '' });

  useEffect(() => {
    const currentConfig = useConfigStore.getState().config;
    
    if (isSettingsOpen && !prevSettingsOpen.current) {
      // Record initial values when modal opens
      initialConfigRef.current = { 
        model: currentConfig?.model || '', 
        apiKey: currentConfig?.apiKey || '', 
        deepseekApiKey: (currentConfig as any)?.deepseekApiKey || '' 
      };
    } else if (!isSettingsOpen && prevSettingsOpen.current) {
      // Checked when modal closes
      const oldCfg = initialConfigRef.current;
      const changed = 
        oldCfg.model !== currentConfig?.model || 
        oldCfg.apiKey !== currentConfig?.apiKey || 
        oldCfg.deepseekApiKey !== (currentConfig as any)?.deepseekApiKey;

      if (changed && !analysis) {
        console.log('[App] Settings saved with model/key changes, triggering AI enrichment');
        void fetchMarketOverview(true);
      }
    }
    prevSettingsOpen.current = isSettingsOpen;
  }, [isSettingsOpen, analysis, fetchMarketOverview]);

  // Restoration: Initialize watchlist & alerts (deferred — not needed for first paint)
  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const [wlRes, alRes] = await Promise.all([
          fetch('/api/watchlist/'),
          fetch('/api/alerts/')
        ]);
        if (wlRes.ok) {
          const wlData = await wlRes.json();
          if (wlData?.items) setWatchlist(wlData.items);
        }
        if (alRes.ok) {
          const alData = await alRes.json();
          setAlerts(Array.isArray(alData) ? alData : alData?.items || []);
        }
      } catch (e) {
        console.error('Failed to initialize market data:', e);
      }
    }, 1500);
    return () => clearTimeout(timer);
  }, [setWatchlist, setAlerts]);

  useEffect(() => {
    i18n.changeLanguage(language);
  }, [language, i18n]);

  // Hash-based routing for admin page
  const [hashRoute, setHashRoute] = useState(window.location.hash.slice(1) || '/');
  const hashRoutePath = hashRoute.split('?')[0] || '/';
  useEffect(() => {
    const onHashChange = () => setHashRoute(window.location.hash.slice(1) || '/');
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  return (
    <AuthGuard>
    <div className="min-h-screen bg-zinc-50 text-zinc-600 font-sans selection:bg-indigo-600/10 transition-colors duration-500">
      {/* Subtle Background Decoration */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-[10%] left-[15%] h-[40%] w-[40%] rounded-full bg-indigo-600/5 blur-[120px]" />
        <div className="absolute bottom-[10%] right-[15%] h-[30%] w-[30%] rounded-full bg-violet-500/5 blur-[120px]" />
      </div>

      <div className="relative z-10 mx-auto max-w-7xl px-6 py-12 md:px-12">
        {/* Admin management page (hash route) */}
        {hashRoutePath === '/admin' || hashRoutePath.startsWith('/admin/') ? (
          <div className="space-y-8">
            <div className="flex items-center gap-4 mb-4">
              <button onClick={() => { window.location.hash = '#/'; }} className="text-sm text-indigo-600 hover:text-indigo-700 font-medium">
                ← 返回首页
              </button>
              <h1 className="text-xl font-bold text-zinc-900">后台管理</h1>
            </div>
            {/* Admin sub-navigation */}
            <div className="flex items-center gap-2 border-b border-zinc-200 pb-3">
              <button
                onClick={() => { window.location.hash = '#/admin'; }}
                className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors ${
                  hashRoutePath === '/admin'
                    ? 'bg-indigo-100 text-indigo-700'
                    : 'text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100'
                }`}
              >
                系统监控
              </button>
              <button
                onClick={() => { window.location.hash = '#/admin/users'; }}
                className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors ${
                  hashRoutePath === '/admin/users'
                    ? 'bg-indigo-100 text-indigo-700'
                    : 'text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100'
                }`}
              >
                用户管理
              </button>
              <button
                onClick={() => { window.location.hash = '#/admin/incidents'; }}
                className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors ${
                  hashRoutePath === '/admin/incidents'
                    ? 'bg-indigo-100 text-indigo-700'
                    : 'text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100'
                }`}
              >
                故障快照
              </button>
            </div>
            {hashRoutePath === '/admin' ? (
              <>
                <ErrorBoundary fallback="系统监控加载失败，请刷新后重试">
                  <Suspense fallback={<div className="flex items-center justify-center py-12"><Loader2 size={24} className="animate-spin text-indigo-500" /></div>}>
                    <SystemMonitor />
                  </Suspense>
                </ErrorBoundary>
                <ErrorBoundary fallback="管理面板加载失败，请刷新后重试">
                  <Suspense fallback={null}>
                    <AdminPanel />
                  </Suspense>
                </ErrorBoundary>
              </>
            ) : hashRoutePath === '/admin/users' ? (
              <ErrorBoundary fallback="用户管理加载失败，请刷新后重试">
                <Suspense fallback={<div className="flex items-center justify-center py-12"><Loader2 size={24} className="animate-spin text-indigo-500" /></div>}>
                  <UserManagement />
                </Suspense>
              </ErrorBoundary>
            ) : hashRoutePath === '/admin/incidents' ? (
              <ErrorBoundary fallback="故障快照页面加载失败，请刷新后重试">
                <Suspense fallback={<div className="flex items-center justify-center py-12"><Loader2 size={24} className="animate-spin text-indigo-500" /></div>}>
                  <IncidentConsole />
                </Suspense>
              </ErrorBoundary>
            ) : (
              <ErrorBoundary fallback="系统监控加载失败，请刷新后重试">
                <Suspense fallback={<div className="flex items-center justify-center py-12"><Loader2 size={24} className="animate-spin text-indigo-500" /></div>}>
                  <SystemMonitor />
                </Suspense>
              </ErrorBoundary>
            )}
          </div>
        ) : hashRoutePath === '/v2' ? (
          <ErrorBoundary fallback="新架构对比页面加载失败，请刷新后重试">
            <Suspense fallback={<div className="flex items-center justify-center py-12"><Loader2 size={24} className="animate-spin text-indigo-500" /></div>}>
              <NewArchCompare />
            </Suspense>
          </ErrorBoundary>
        ) : (
        <>
        {isHistoryOpen && (
          <Suspense fallback={null}>
          <HistoryModal 
            isOpen={isHistoryOpen} 
            onClose={() => setIsHistoryOpen(false)} 
            onSelect={(item) => {
              if (item.type === 'sector') {
                if (item.jobId) {
                  window.open(`/api/sector/report/${item.jobId}`, '_blank');
                } else {
                  window.location.hash = `#/sector-analysis/${item.id}`;
                }
                setIsHistoryOpen(false);
                return;
              }

              setAnalysis(item);
              setSymbol(item.stockInfo?.symbol || '');
              setMarket(item.stockInfo?.market || 'A-Share');
              setLastJobId(item.job_id || item.jobId || item._jobId || item.analysis_id || item.analysisId || item.id || null);
              
              if (item.chatHistory) {
                setChatHistory(item.chatHistory);
              } else {
                setChatHistory([]);
              }

              if (item.discussion) {
                const discussionData = {
                  ...item,
                  messages: item.discussion,
                  finalConclusion: item.finalConclusion || '',
                  tradingPlan: item.tradingPlan,
                  verificationMetrics: item.verificationMetrics,
                  capitalFlow: item.capitalFlow
                };
                setDiscussionResults(discussionData);
                setScenarioResults(discussionData);
                setShowDiscussion(true);
              } else {
                resetAnalysis();
                resetDiscussion();
                resetScenario();
                setShowDiscussion(false);
              }
              
              setIsHistoryOpen(false);
            }}
          />
          </Suspense>
        )}
        {isSignalsOpen && (
          <ErrorBoundary fallback="信号中心加载失败，请关闭后重试" onError={(e) => console.error('[SignalCenter Error]', e.message, e.stack)}>
          <Suspense fallback={null}>
          <SignalCenter
            isOpen={isSignalsOpen}
            onClose={() => setIsSignalsOpen(false)}
          />
          </Suspense>
          </ErrorBoundary>
        )}

        <Header
          onSearch={handleSearch}
          onResetToHome={resetToHome}
          onOpenHistory={() => setIsHistoryOpen(true)}
          onOpenSignals={() => setIsSignalsOpen(true)}
          onFetchAdminData={fetchAdminData}
        />

        <TokenUsage />

        <AnimatePresence mode="wait">
          {analysisError && (
            <div className="mb-8">
              <ErrorNotice
                title={t('errors.analysis_failed')}
                message={analysisError}
                onRetry={() => handleSearch({ preventDefault: () => {} } as React.FormEvent)}
                onOpenSettings={() => setIsSettingsOpen(true)}
              />
            </div>
          )}

          {analysis && analysis.stockInfo && typeof analysis.stockInfo === 'object' && !Array.isArray(analysis.stockInfo) ? (
            <ErrorBoundary fallback="分析组件加载失败，请刷新页面重试" onError={() => { resetAnalysis(); }}>
            <Suspense fallback={
              <div className="space-y-6 stagger-children">
                <div className="h-16 skeleton" />
                <div className="h-64 skeleton" />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="h-32 skeleton" />
                  <div className="h-32 skeleton" />
                  <div className="h-32 skeleton" />
                </div>
              </div>
            }>
            <AnalysisResult
              onResetToHome={resetToHome}
              onExportFullReport={handleExportFullReport}
              onExportPdf={handleExportPdf}
              onExportShareCard={handleExportShareCard}
              onSendStockReport={handleSendStockReport}
              onSendDiscussionReport={handleSendDiscussionReport}
              onSendChatReport={handleSendChatReport}
              onDiscussionQuestion={handleDiscussionQuestion}
              onGenerateNewConclusion={handleGenerateNewConclusion}
              onChat={handleChat}
            />
            </Suspense>
            </ErrorBoundary>
          ) : (
            <ErrorBoundary fallback="Market overview encountered an error">
            <Suspense fallback={
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="h-20 rounded-xl bg-zinc-100 animate-pulse" />
                  <div className="h-20 rounded-xl bg-zinc-100 animate-pulse" style={{animationDelay:'0.15s'}} />
                  <div className="h-20 rounded-xl bg-zinc-100 animate-pulse" style={{animationDelay:'0.3s'}} />
                </div>
                <div className="h-64 rounded-xl bg-zinc-100 animate-pulse" style={{animationDelay:'0.45s'}} />
              </div>
            }>
            <MarketOverview
              onFetchMarketOverview={(force) => void fetchMarketOverview(force)}
            />
            </Suspense>
            </ErrorBoundary>
          )}
        </AnimatePresence>

        <Suspense fallback={null}><SettingsModal /></Suspense>

        {showAdminPanel && <ErrorBoundary fallback="Admin panel encountered an error"><Suspense fallback={null}><AdminPanel /></Suspense></ErrorBoundary>}

        {showIBKRDashboard && <Suspense fallback={null}><IBKRDashboard /></Suspense>}
        {showMockTradingDashboard && <Suspense fallback={null}><MockTradingDashboard /></Suspense>}
        {showBacktestPanel && <Suspense fallback={null}><BacktestPanel isOpen={showBacktestPanel} onClose={() => useUIStore.getState().setShowBacktestPanel(false)} /></Suspense>}
        {showPredictionDashboard && <Suspense fallback={null}><PredictionDashboard isOpen={showPredictionDashboard} onClose={() => useUIStore.getState().setShowPredictionDashboard(false)} /></Suspense>}
        {showThsAnalysis && <Suspense fallback={null}><ThsAnalysis /></Suspense>}
        
        <Suspense fallback={null}><AnalysisLoadingPulse /></Suspense>
        </>
        )}
      </div>

      <Suspense fallback={null}><DetailModal onSendHistoryToFeishu={handleSendHistoryToFeishu} /></Suspense>

      <footer className="mx-auto mt-16 max-w-7xl border-t border-zinc-200 px-4 py-10 md:px-8">
        <div className="flex flex-col items-center justify-between gap-6 section-label md:flex-row">
          <p>© 2026 {t('common.app_name')}</p>
          <div className="flex gap-8">
            <button onClick={(e) => { e.preventDefault(); useUIStore.getState().showToast('功能开发中，敬请期待', 'info'); }} className="text-zinc-400 transition-colors duration-200 hover:text-zinc-500">{t('common.footer.data_sources')}</button>
            <button onClick={(e) => { e.preventDefault(); useUIStore.getState().showToast('功能开发中，敬请期待', 'info'); }} className="text-zinc-400 transition-colors duration-200 hover:text-zinc-500">{t('common.footer.terms')}</button>
            <button onClick={(e) => { e.preventDefault(); useUIStore.getState().showToast('功能开发中，敬请期待', 'info'); }} className="text-zinc-400 transition-colors duration-200 hover:text-zinc-500">{t('common.footer.privacy')}</button>
          </div>
        </div>
      </footer>

      {/* Global Overlays */}
      <NotificationBubbles onViewResult={(job) => loadBackgroundResult(job as any)} />
      <ConfirmDialog />
      <Toast />
      {historyDialogOpen && (
        <Suspense fallback={null}>
          <HistorySelectionDialog
            isOpen={historyDialogOpen}
            symbol={pendingSearchSymbol}
            items={historyDialogItems}
            onSelect={loadHistoryResult}
            onForceNew={() => doStartAnalysis(pendingSearchSymbol)}
            onClose={() => setHistoryDialogOpen(false)}
          />
        </Suspense>
      )}
    </div>
    </AuthGuard>
  );
}
