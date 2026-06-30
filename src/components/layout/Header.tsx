import React, { useState, useEffect, useRef, memo, lazy, Suspense } from 'react';
import { Download, History, Clock, Settings, Loader2, Search, TrendingUp, Zap, BarChart3, Microscope, Languages, Menu, X, Target, Activity, BrainCircuit, Wrench, BarChart2, Users, LogOut } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { Market, AnalysisLevel } from '../../types';
import { useUIStore, selectLoading } from '../../stores/useUIStore';
import { useMarketStore } from '../../stores/useMarketStore';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { useConfigStore } from '../../stores/useConfigStore';
import { useAuthStore } from '../../stores/useAuthStore';
import { StockSearchInput } from '../shared/StockSearchInput';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

const BrainEvolutionModal = lazy(() => import('../dashboard/BrainEvolutionModal').then(m => ({ default: m.BrainEvolutionModal })));

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface HeaderProps {
  onSearch: (e: React.FormEvent) => void;
  onResetToHome: () => void;
  onOpenHistory: () => void;
  onOpenSignals: () => void;
  onFetchAdminData: () => void;
}

export const Header = memo(function Header({
  onSearch, onResetToHome, onOpenHistory, onOpenSignals, onFetchAdminData
}: HeaderProps) {
  const { t, i18n } = useTranslation();
  const loading = useUIStore(selectLoading);
  const { showAdminPanel, setShowAdminPanel, showAdminManagement, setShowAdminManagement, setIsSettingsOpen, analysisLevel, setAnalysisLevel, serviceStatus, setShowIBKRDashboard, setShowMockTradingDashboard, setShowBacktestPanel } = useUIStore();
  const { dailyReport, activeAlertStatus } = useMarketStore();
  const { symbol, setSymbol, market, setMarket } = useAnalysisStore();
  const { language, setLanguage } = useConfigStore();
  const { user, logout } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const [showBrainEvolution, setShowBrainEvolution] = useState(false);
  const [showToolbox, setShowToolbox] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const toolboxRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const toggleLanguage = () => {
    const newLang = language === 'en' ? 'zh-CN' : 'en';
    setLanguage(newLang);
    i18n.changeLanguage(newLang);
  };

  // Click outside to close dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (toolboxRef.current && !toolboxRef.current.contains(e.target as Node)) {
        setShowToolbox(false);
      }
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectSuggestion = (selectedSymbol: string, selectedMarket?: string) => {
    setSymbol(selectedSymbol);
    if (selectedMarket) {
      setMarket(selectedMarket as Market);
    }
  };

  return (
    <>
      <header className="mb-12 animate-premium text-zinc-950 dark:text-white relative z-10">
        {/* Service Status Banner */}
        <AnimatePresence>
          {serviceStatus === 'quota_exhausted' && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="mb-8 overflow-hidden"
            >
              <div className="bg-rose-500/10 border border-rose-500/20 rounded-2xl p-4 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-rose-500/20 flex items-center justify-center text-rose-500">
                    <Zap size={16} />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-rose-600">{t('errors.quota_exhausted_title')}</p>
                    <p className="text-xs text-rose-500/80">{t('errors.quota_exhausted_desc')}</p>
                  </div>
                </div>
                <a
                  href="https://aistudio.google.com/app/billing"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-shrink-0 px-4 py-2 bg-rose-500 text-white text-xs font-bold rounded-xl hover:bg-rose-600 transition-colors"
                >
                  {t('common.go_to_ai_studio')}
                </a>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          <div className="cursor-pointer" onClick={onResetToHome}>
            <div className="flex items-center gap-2 mb-3">
              <div className="h-6 w-1 bg-indigo-600 rounded-full" />
              <span className="text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-400">
                {t('header.brand')}
              </span>
            </div>
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
              {t('header.title')}
            </h1>
            <p className="mt-4 text-zinc-500 font-medium max-w-xl leading-relaxed">
              {t('header.subtitle')}
            </p>
          </div>

          <div className="flex items-center gap-3 flex-shrink-0">
            {/* Desktop: show all buttons */}
            <div className="hidden md:flex items-center gap-3">
              <button
                onClick={toggleLanguage}
                className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl overflow-hidden relative group"
                aria-label={t('header.toggleLanguage')}
                title={t('header.toggleLanguage')}
              >
                <Languages size={20} strokeWidth={1.5} className="group-hover:scale-110 transition-transform" />
                <span className="absolute bottom-1 right-1 text-[8px] font-bold opacity-70">
                  {language === 'en' ? 'EN' : 'ZH'}
                </span>
              </button>

              {dailyReport && (
                <button
                  onClick={() => {
                    const blob = new Blob([dailyReport], { type: 'text/markdown' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `Daily_Market_Report_${new Date().toISOString().split('T')[0]}.md`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                  }}
                  className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
                  aria-label={t('header.downloadReport')}
                  title={t('header.downloadReport')}
                >
                  <Download size={20} strokeWidth={1.5} />
                </button>
              )}
              <button
                onClick={onOpenHistory}
                className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
                aria-label={t('header.history')}
                title={t('header.history')}
              >
                <History size={20} strokeWidth={1.5} />
              </button>
              <button
                onClick={onOpenSignals}
                className={cn(
                  "btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl relative overflow-hidden group transition-all duration-500",
                  activeAlertStatus === 'gold' ? "bg-yellow-500 text-white border-yellow-400 hover:bg-yellow-600 shadow-[0_0_20px_rgba(234,179,8,0.4)]" :
                    activeAlertStatus === 'red' ? "bg-rose-500 text-white border-rose-400 hover:bg-rose-600 shadow-[0_0_20px_rgba(244,63,94,0.4)]" :
                      activeAlertStatus === 'indigo' ? "bg-indigo-600 text-white border-indigo-500 hover:bg-indigo-700 shadow-[0_0_20px_rgba(79,70,229,0.4)]" : ""
                )}
                aria-label="Trade Signals"
                title="交易信号监控"
              >
                <Target size={20} className={cn("transition-transform group-hover:scale-110", activeAlertStatus !== 'neutral' && "animate-pulse")} />
                {activeAlertStatus !== 'neutral' && (
                  <span className="absolute inset-0 bg-white/20 animate-ping pointer-events-none" />
                )}
              </button>
              <button
                onClick={() => setShowIBKRDashboard(true)}
                className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
                aria-label="IBKR Dashboard"
                title="IBKR 实盘仪表盘"
              >
                <BarChart3 size={20} strokeWidth={1.5} />
              </button>
              <button
                onClick={() => setShowMockTradingDashboard(true)}
                className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
                aria-label="模拟交易"
                title="AI 模拟交易看板"
              >
                <Activity size={20} strokeWidth={1.5} />
              </button>
              <button
                onClick={() => useUIStore.getState().setShowPredictionDashboard(true)}
                className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
                aria-label="预测准确率"
                title="AI 预测准确率看板"
              >
                <TrendingUp size={20} strokeWidth={1.5} />
              </button>
              <button
                onClick={() => useUIStore.getState().setShowThsAnalysis(true)}
                className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
                aria-label="同花顺分析"
                title="同花顺高级分析"
              >
                <Search size={20} strokeWidth={1.5} />
              </button>
              <button
                onClick={() => setShowBacktestPanel(true)}
                className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl relative overflow-hidden group"
                aria-label="回测"
                title="AI 量化回测引擎"
              >
                <BarChart2 size={20} strokeWidth={1.5} className="group-hover:scale-110 transition-transform" />
              </button>

              <button
                onClick={() => setIsSettingsOpen(true)}
                className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
                aria-label={t('header.settings')}
                title={t('header.settings')}
              >
                <Settings size={20} strokeWidth={1.5} />
              </button>

              {/* Toolbox Dropdown */}
              <div className="relative" ref={toolboxRef}>
                <button
                  onClick={() => setShowToolbox(!showToolbox)}
                  className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
                  aria-label="Toolbox"
                  title="Toolbox"
                >
                  <Wrench size={20} strokeWidth={1.5} />
                </button>
                {showToolbox && (
                  <div className="absolute top-14 right-0 z-50 bg-white rounded-2xl shadow-2xl border border-zinc-200 p-3 min-w-[200px] space-y-1 animate-in fade-in slide-in-from-top-2">
                    <button onClick={() => { setShowAdminPanel(!showAdminPanel); if (!showAdminPanel) onFetchAdminData(); setShowToolbox(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                      <Activity size={18} /> {t('header.sysLogs')}
                    </button>
                    {isAdmin && (
                      <button onClick={() => { window.location.hash = '#/admin'; setShowToolbox(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-rose-600 hover:bg-rose-50 transition-colors">
                        <Users size={18} /> 后台管理
                      </button>
                    )}
                    <button onClick={() => { setShowBrainEvolution(true); setShowToolbox(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-purple-600 hover:bg-purple-50 transition-colors">
                      <BrainCircuit size={18} /> 🧠 进化 AI
                    </button>
                  </div>
                )}
              </div>

              {/* User dropdown */}
              {user && (
                <div className="relative" ref={userMenuRef}>
                  <button
                    onClick={() => setShowUserMenu(!showUserMenu)}
                    className="w-10 h-10 rounded-full bg-indigo-600 text-white flex items-center justify-center text-sm font-bold hover:bg-indigo-700 transition-colors"
                    title={user.display_name || user.username}
                  >
                    {(user.display_name || user.username || '?')[0].toUpperCase()}
                  </button>
                  {showUserMenu && (
                    <div className="absolute top-14 right-0 z-50 bg-white rounded-2xl shadow-2xl border border-zinc-200 p-3 min-w-[180px] space-y-1 animate-in fade-in slide-in-from-top-2">
                      <div className="px-3 py-2">
                        <p className="text-sm font-semibold text-zinc-900">{user.display_name || user.username}</p>
                        <p className="text-xs text-zinc-400 mt-0.5">@{user.username} · {user.role}</p>
                      </div>
                      <div className="border-t border-zinc-100" />
                      <button onClick={() => { logout(); setShowUserMenu(false); }} className="flex w-full items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium text-rose-600 hover:bg-rose-50 transition-colors">
                        <LogOut size={16} /> 登出
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Mobile: hamburger menu */}
            <div className="md:hidden relative">
              <button
                onClick={() => setShowMobileMenu(!showMobileMenu)}
                className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
                aria-label="Menu"
                aria-expanded={showMobileMenu}
              >
                {showMobileMenu ? <X size={20} strokeWidth={1.5} /> : <Menu size={20} strokeWidth={1.5} />}
              </button>
              {showMobileMenu && (
                <div className="absolute top-14 right-0 z-50 bg-white rounded-2xl shadow-2xl border border-zinc-200 p-3 min-w-[200px] space-y-1 animate-in fade-in slide-in-from-top-2">
                  <button onClick={() => { toggleLanguage(); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                    <Languages size={18} /> {t('header.toggleLanguage')}
                  </button>
                  <button onClick={() => { onOpenHistory(); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                    <History size={18} /> {t('header.history')}
                  </button>
                  <button onClick={() => { setShowAdminPanel(!showAdminPanel); if (!showAdminPanel) onFetchAdminData(); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                    <Activity size={18} /> {t('header.sysLogs')}
                  </button>
                  {isAdmin && (
                    <button onClick={() => { window.location.hash = '#/admin'; setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-rose-600 hover:bg-rose-50 transition-colors">
                      <Users size={18} /> 后台管理
                    </button>
                  )}
                  <button onClick={() => { setShowIBKRDashboard(true); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                    <BarChart3 size={18} /> IBKR 实盘
                  </button>
                  <button onClick={() => { setShowMockTradingDashboard(true); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                    <Activity size={18} /> 模拟交易
                  </button>
                  <button onClick={() => { useUIStore.getState().setShowPredictionDashboard(true); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                    <TrendingUp size={18} /> 预测准确率
                  </button>
                  <button onClick={() => { useUIStore.getState().setShowThsAnalysis(true); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                    <Search size={18} /> 同花顺分析
                  </button>
                  <button onClick={() => { setShowBacktestPanel(true); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                    <BarChart2 size={18} /> 量化回测
                  </button>
                  <button onClick={() => { setIsSettingsOpen(true); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                    <Settings size={18} /> {t('header.settings')}
                  </button>

                  <button onClick={() => { setShowBrainEvolution(true); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-purple-600 hover:bg-purple-50 transition-colors">
                    <BrainCircuit size={18} /> 🧠 进化 AI
                  </button>
                  {user && (
                    <button onClick={() => { logout(); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-rose-600 hover:bg-rose-50 transition-colors">
                      <LogOut size={18} /> 登出
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Search Bar Container */}
        <div className="mt-12 flex flex-col gap-3">
          <form onSubmit={onSearch} className="flex flex-col gap-4 sm:flex-row items-stretch relative">
            <div className="relative group flex-shrink-0">
              <select
                value={market}
                onChange={(e) => setMarket(e.target.value as Market)}
                className="h-14 w-full sm:w-48 cursor-pointer appearance-none rounded-xl border border-zinc-200 bg-white px-5 pr-12 text-sm font-semibold text-zinc-700 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40 hover:bg-zinc-50"
              >
                <option value="A-Share">{t('markets.aShare')}</option>
                <option value="HK-Share">{t('markets.hkShare')}</option>
                <option value="US-Share">{t('markets.usShare')}</option>
              </select>
              <div className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-zinc-400">
                <TrendingUp size={16} strokeWidth={1.5} />
              </div>
            </div>

            <StockSearchInput
              value={symbol}
              market={market}
              placeholder={t('header.searchPlaceholder')}
              className="flex-1"
              inputClassName="h-14 text-base pl-14 pr-6 font-medium text-zinc-950 shadow-sm shadow-zinc-900/5"
              onChange={setSymbol}
              onSelect={handleSelectSuggestion}
            />

            {/* Analysis Level Selector */}
            <div className="flex rounded-xl border border-zinc-200 bg-white overflow-hidden h-14 flex-shrink-0">
              {([
                { level: 'quick' as AnalysisLevel, icon: Zap, label: t('levels.quick') },
                { level: 'standard' as AnalysisLevel, icon: BarChart3, label: t('levels.standard') },
                { level: 'deep' as AnalysisLevel, icon: Microscope, label: t('levels.deep') },
              ] as const).map(({ level, icon: Icon, label }) => (
                <button
                  key={level}
                  type="button"
                  onClick={() => setAnalysisLevel(level)}
                  className={`flex items-center gap-1.5 px-4 text-sm font-medium transition-all ${analysisLevel === level
                      ? 'bg-indigo-600 text-white'
                      : 'text-zinc-500 hover:bg-zinc-50 hover:text-zinc-700'
                    }`}
                >
                  <Icon size={15} strokeWidth={1.5} />
                  <span>{label}</span>
                </button>
              ))}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary h-14 px-10 rounded-xl shadow-indigo-600/10 shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="animate-spin" size={18} />
                  <span className="text-sm font-semibold">
                    {t('header.addToQueue', '加入队列')}
                  </span>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <span className="text-sm font-semibold">
                    {t('header.startAnalysis')}
                  </span>
                </div>
              )}
            </button>
          </form>
        </div>
      </header>
      {showBrainEvolution && (
        <Suspense fallback={null}>
          <BrainEvolutionModal
            isOpen={showBrainEvolution}
            onClose={() => setShowBrainEvolution(false)}
          />
        </Suspense>
      )}
    </>
  );
});
