import React, { useState, useEffect, useRef, memo } from 'react';
import { Download, Bell, History, Clock, Settings, Loader2, Search, TrendingUp, Zap, BarChart3, Microscope, Languages, Menu, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Market, AnalysisLevel } from '../../types';
import { useUIStore, selectLoading } from '../../stores/useUIStore';
import { useMarketStore } from '../../stores/useMarketStore';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { useConfigStore } from '../../stores/useConfigStore';

interface HeaderProps {
  onSearch: (e: React.FormEvent) => void;
  onResetToHome: () => void;
  onTriggerDailyReport: () => void;
  onOpenHistory: () => void;
  onFetchAdminData: () => void;
}

export const Header = memo(function Header({ onSearch, onResetToHome, onTriggerDailyReport, onOpenHistory, onFetchAdminData }: HeaderProps) {
  const { t, i18n } = useTranslation();
  const loading = useUIStore(selectLoading);
  const { isTriggeringReport, showAdminPanel, setShowAdminPanel, setIsSettingsOpen, analysisLevel, setAnalysisLevel } = useUIStore();
  const { dailyReport } = useMarketStore();
  const { symbol, setSymbol, market, setMarket } = useAnalysisStore();
  const { language, setLanguage } = useConfigStore();

  const isComposing = useRef(false);
  const [localSymbol, setLocalSymbol] = useState(symbol);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const searchContainerRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    setLocalSymbol(symbol);
  }, [symbol]);

  const toggleLanguage = () => {
    const newLang = language === 'en' ? 'zh-CN' : 'en';
    setLanguage(newLang);
    i18n.changeLanguage(newLang);
  };

  // Fetch suggestions
  useEffect(() => {
    const controller = new AbortController();

    const fetchSuggestions = async () => {
      if (!localSymbol || localSymbol.trim().length < 1 || isComposing.current) {
        setSuggestions([]);
        setShowSuggestions(false);
        return;
      }

      try {
        const params = new URLSearchParams();
        params.set('input', localSymbol);
        params.set('market', market);
        
        const res = await fetch(`/api/stock/suggest?${params.toString()}`, { signal: controller.signal });
        if (res.ok) {
          const data = await res.json();
          setSuggestions(data);
          setShowSuggestions(data.length > 0);
          setSelectedIndex(-1);
        }
      } catch (e: any) {
        if (e.name !== 'AbortError') console.error('Failed to fetch suggestions:', e);
      }
    };

    const timeout = setTimeout(fetchSuggestions, 300);
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [localSymbol, market]);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectSuggestion = (s: any) => {
    const finalSym = s.symbol || s.fullSymbol;
    setSymbol(finalSym);
    setLocalSymbol(finalSym);
    if (s.market) {
      setMarket(s.market as Market);
    }
    setShowSuggestions(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions || suggestions.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => (prev + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => (prev - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      handleSelectSuggestion(suggestions[selectedIndex]);
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  return (
    <header className="mb-12 animate-premium text-zinc-950 dark:text-white relative z-10">
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
              aria-label={language === 'en' ? 'Switch to Chinese' : '切换为英文'}
              title={language === 'en' ? 'Switch to Chinese' : '切换为英文'}
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
              onClick={onTriggerDailyReport}
              disabled={isTriggeringReport}
              className="btn-secondary h-12 px-5 rounded-xl disabled:opacity-50"
              aria-label={t('header.triggerBrief')}
            >
              {isTriggeringReport ? <Loader2 size={16} className="animate-spin" /> : <Bell size={16} strokeWidth={1.5} />}
              <span className="text-sm">{t('header.triggerBrief')}</span>
            </button>
            <button
              onClick={onOpenHistory}
              className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
              aria-label={t('header.history')}
              title={t('header.history')}
            >
              <History size={20} strokeWidth={1.5} />
            </button>
            <button
              onClick={() => {
                setShowAdminPanel(!showAdminPanel);
                if (!showAdminPanel) onFetchAdminData();
              }}
              className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
              aria-label={t('header.sysLogs')}
              title={t('header.sysLogs')}
            >
              <Clock size={20} strokeWidth={1.5} />
            </button>
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="btn-secondary w-12 h-12 p-0 flex items-center justify-center rounded-xl"
              aria-label={t('header.settings')}
              title={t('header.settings')}
            >
              <Settings size={20} strokeWidth={1.5} />
            </button>
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
                  <Languages size={18} /> {language === 'en' ? '切换中文' : 'English'}
                </button>
                <button onClick={() => { onTriggerDailyReport(); setShowMobileMenu(false); }} disabled={isTriggeringReport} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors disabled:opacity-50">
                  <Bell size={18} /> {t('header.triggerBrief')}
                </button>
                <button onClick={() => { onOpenHistory(); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                  <History size={18} /> {t('header.history')}
                </button>
                <button onClick={() => { setShowAdminPanel(!showAdminPanel); if (!showAdminPanel) onFetchAdminData(); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                  <Clock size={18} /> {t('header.sysLogs')}
                </button>
                <button onClick={() => { setIsSettingsOpen(true); setShowMobileMenu(false); }} className="flex w-full items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors">
                  <Settings size={18} /> {t('header.settings')}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Search Bar Container */}
      <div className="mt-12 flex flex-col gap-3">
        <form onSubmit={onSearch} className="flex flex-col gap-4 sm:flex-row items-stretch relative" ref={searchContainerRef}>
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

        <div className="relative flex-1 group">
          <div className="absolute left-5 top-1/2 -translate-y-1/2 text-zinc-400 group-focus-within:text-indigo-600 transition-colors">
            <Search size={20} strokeWidth={1.5} />
          </div>
          <input
            type="text"
            placeholder={t('header.searchPlaceholder')}
            value={localSymbol}
            aria-label={t('header.searchPlaceholder')}
            aria-autocomplete="list"
            aria-expanded={showSuggestions && suggestions.length > 0}
            aria-controls="search-suggestions"
            role="combobox"
            onCompositionStart={() => { isComposing.current = true; }}
            onCompositionEnd={(e) => {
              isComposing.current = false;
              const val = e.currentTarget.value;
              setLocalSymbol(val);
              // Store as is for suggestions, will uppercase on submit
            }}
            onChange={(e) => {
              const val = e.target.value;
              setLocalSymbol(val);
              if (!isComposing.current) {
                setSymbol(val);
              }
            }}
            onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
            onKeyDown={handleKeyDown}
            className="h-14 w-full font-medium text-base rounded-xl border border-zinc-200 bg-white pl-14 pr-6 text-zinc-950 transition-all placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40 shadow-sm shadow-zinc-900/5 group-hover:border-zinc-300"
          />

          {/* Suggestions Dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-2 z-[60] overflow-hidden rounded-2xl border border-zinc-100 bg-white/95 backdrop-blur-xl shadow-2xl shadow-indigo-600/10 animate-in fade-in slide-in-from-top-2 duration-200">
              <div className="p-1.5" id="search-suggestions" role="listbox" aria-label="Search suggestions">
                {suggestions.map((s, idx) => (
                  <button
                    key={`suggestion-${s.symbol}-${idx}`}
                    type="button"
                    role="option"
                    aria-selected={idx === selectedIndex}
                    onClick={() => handleSelectSuggestion(s)}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={`flex w-full items-center justify-between px-4 py-3 rounded-xl transition-all ${
                      idx === selectedIndex ? 'bg-indigo-50 text-indigo-700' : 'text-zinc-700 hover:bg-zinc-50'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${idx === selectedIndex ? 'bg-indigo-100 text-indigo-600' : 'bg-zinc-100 text-zinc-500'}`}>
                        {s.symbol}
                      </span>
                      <span className="font-bold text-sm">{s.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                       {s.exchange && <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">{s.exchange}</span>}
                       {idx === selectedIndex && <Zap size={12} className="text-indigo-400 animate-pulse" />}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

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
              className={`flex items-center gap-1.5 px-4 text-sm font-medium transition-all ${
                analysisLevel === level
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
          className="btn-primary h-14 px-10 rounded-xl shadow-indigo-600/10 shadow-xl disabled:opacity-50 disabled:cursor-not-allowed transition-all"
        >
          {loading ? (
            <Loader2 className="animate-spin" size={20} />
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
  );
});
