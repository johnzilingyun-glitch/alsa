import { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from 'motion/react';
import { X, Languages, History, Monitor, BarChart3, Activity, TrendingUp, BarChart2, Settings, BrainCircuit, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '../../stores/useUIStore';
import { useMarketStore } from '../../stores/useMarketStore';
import { useConfigStore } from '../../stores/useConfigStore';

interface MobileNavProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenHistory: () => void;
  onFetchAdminData: () => void;
  onShowBrainEvolution: () => void;
}

export function MobileNav({ isOpen, onClose, onOpenHistory, onFetchAdminData, onShowBrainEvolution }: MobileNavProps) {
  const { t } = useTranslation();
  const { showAdminPanel, setShowAdminPanel, setIsSettingsOpen, setShowIBKRDashboard, setShowMockTradingDashboard, setShowBacktestPanel, setShowPredictionDashboard, setShowThsAnalysis } = useUIStore();
  const { language, setLanguage } = useConfigStore();
  const { activeAlertStatus } = useMarketStore();
  const x = useMotionValue(320);
  const overlayOpacity = useTransform(x, [0, 320], [0.4, 0]);
  const navRef = useRef<HTMLDivElement>(null);

  const toggleLanguage = useCallback(() => {
    const newLang = language === 'en' ? 'zh-CN' : 'en';
    setLanguage(newLang);
  }, [language, setLanguage]);

  const close = useCallback(() => {
    animate(x, 320, { duration: 0.25, ease: [0.16, 1, 0.3, 1] }).then(onClose);
  }, [x, onClose]);

  useEffect(() => {
    if (isOpen) {
      animate(x, 0, { duration: 0.3, ease: [0.16, 1, 0.3, 1] });
    }
  }, [isOpen, x]);

  useEffect(() => {
    document.body.style.overflow = isOpen ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [isOpen]);

  if (!isOpen) return null;

  const navItems = [
    { icon: Languages, label: t('header.toggleLanguage'), onClick: () => { toggleLanguage(); close(); } },
    { icon: History, label: t('header.history'), onClick: () => { onOpenHistory(); close(); } },
    { icon: Monitor, label: '系统监控', onClick: () => { setShowAdminPanel(!showAdminPanel); if (!showAdminPanel) onFetchAdminData(); close(); } },
    { icon: BarChart3, label: 'IBKR 实盘', onClick: () => { setShowIBKRDashboard(true); close(); } },
    { icon: Activity, label: '模拟交易', onClick: () => { setShowMockTradingDashboard(true); close(); } },
    { icon: TrendingUp, label: '预测准确率', onClick: () => { setShowPredictionDashboard(true); close(); } },
    { icon: Search, label: '同花顺分析', onClick: () => { useUIStore.getState().setShowThsAnalysis(true); close(); } },
    { icon: BarChart2, label: '量化回测', onClick: () => { setShowBacktestPanel(true); close(); } },
    { icon: BarChart3, label: '同花顺分析', onClick: () => { setShowThsAnalysis(true); close(); } },
    { icon: Settings, label: t('header.settings'), onClick: () => { setIsSettingsOpen(true); close(); } },
    { icon: BrainCircuit, label: '进化 AI', onClick: () => { onShowBrainEvolution(); close(); }, accent: true },
  ];

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[150] md:hidden">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{ opacity: overlayOpacity }}
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={close}
          />
          <motion.div
            ref={navRef}
            initial={{ x: 320 }}
            animate={{ x: 0 }}
            exit={{ x: 320 }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="absolute right-0 top-0 h-full w-[280px] bg-white shadow-2xl flex flex-col"
          >
            <div className="flex items-center justify-between p-5 border-b border-zinc-100">
              <span className="text-sm font-bold text-zinc-900">导航</span>
              <button
                onClick={close}
                className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-zinc-50 transition-colors"
                aria-label="关闭菜单"
              >
                <X size={20} strokeWidth={1.5} />
              </button>
            </div>

            <nav className="flex-1 overflow-y-auto p-3 space-y-1">
              {navItems.map((item) => (
                <button
                  key={item.label}
                  onClick={item.onClick}
                  className={`flex w-full items-center gap-3 px-4 py-3.5 rounded-xl text-sm font-medium transition-colors min-h-[44px] ${
                    item.accent
                      ? 'text-purple-600 hover:bg-purple-50'
                      : 'text-zinc-600 hover:bg-zinc-50'
                  }`}
                >
                  <item.icon size={18} strokeWidth={1.5} />
                  {item.label}
                  {item.label === t('header.toggleLanguage') && (
                    <span className="ml-auto text-xs text-zinc-400">
                      {language === 'en' ? 'EN' : 'ZH'}
                    </span>
                  )}
                </button>
              ))}
            </nav>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
