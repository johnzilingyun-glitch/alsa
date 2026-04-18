import { useEffect, useState, memo } from 'react';
import { 
  Bell, TrendingUp, Target, ShieldAlert, CheckCircle2, 
  Trash2, ExternalLink, ArrowRight, Activity 
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { useMarketStore } from '../../stores/useMarketStore';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { alertsClient, SearchAlert } from '../../services/api/alertsClient';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const InstitutionalAlertPanel = memo(function InstitutionalAlertPanel() {
  const { t, i18n } = useTranslation();
  const { 
    searchAlerts, setAlerts, alertPrices, updateAlertPrice 
  } = useMarketStore();
  const { setSymbol, setMarket } = useAnalysisStore();
  const [loading, setLoading] = useState(false);

  // Fetch alerts on mount
  useEffect(() => {
    async function init() {
      try {
        setLoading(true);
        const data = await alertsClient.list();
        setAlerts(data.items || []);
      } catch (e) {
        console.error('Failed to fetch alerts:', e);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, [setAlerts]);

  // Poll for prices every 30 seconds
  useEffect(() => {
    if (searchAlerts.length === 0) return;

    async function updatePrices() {
      // For each alert, fetch current price
      // In a real app, we'd have a batch endpoint /api/alerts/prices
      for (const alert of searchAlerts) {
        try {
          // This is a placeholder for actual price fetching
          // Assuming /api/stock/a_spot or similar exists from research
          const res = await fetch(`/api/stock/a_spot?symbol=${alert.symbol}`);
          const data = await res.json();
          if (data.success && data.data) {
            const price = data.data['最新价'] || data.data.price;
            if (price) updateAlertPrice(alert.symbol, price);
          } else {
            // Fallback for US/HK if needed
            // res = await fetch(`/api/stock/quote?symbol=${alert.symbol}&market=${alert.market}`);
          }
        } catch (e) {
          console.warn(`Failed to fetch price for ${alert.symbol}:`, e);
        }
      }
    }

    updatePrices();
    const interval = setInterval(updatePrices, 30000); // 30s as per research
    return () => clearInterval(interval);
  }, [searchAlerts, updateAlertPrice]);

  const handleDelete = async (id: number) => {
    try {
      await alertsClient.delete(id);
      setAlerts(searchAlerts.filter(a => a.id !== id));
    } catch (e) {
      console.error(e);
    }
  };

  const getAlertStatus = (alert: SearchAlert) => {
    const currentPrice = alertPrices[alert.symbol];
    if (!currentPrice) return 'neutral';

    if (currentPrice >= alert.target_price) return 'target_hit';
    if (currentPrice <= alert.stop_loss) return 'stop_loss_hit';
    
    // Entry zone: within 2% of entry price
    const entryDiff = Math.abs(currentPrice - alert.entry_price) / alert.entry_price;
    if (entryDiff <= 0.02) return 'entry_zone';
    
    return 'neutral';
  };

  if (searchAlerts.length === 0 && !loading) return null;

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-zinc-950">
          <Bell size={24} className="text-indigo-600" />
          {t('admin.history.title', 'AI 智能决策预警')}
          <span className="ml-2 rounded-full bg-indigo-50 px-2.5 py-0.5 text-[10px] font-bold text-indigo-600 uppercase tracking-widest border border-indigo-100">
            Institutional
          </span>
        </h2>
        <div className="flex items-center gap-2 text-[10px] font-medium text-zinc-400 uppercase tracking-[0.2em]">
          <Activity size={12} className="animate-pulse" />
          Live Monitoring
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <AnimatePresence mode="popLayout">
          {searchAlerts.map((alert) => {
            const currentPrice = alertPrices[alert.symbol];
            const status = getAlertStatus(alert);
            const isTargetHit = status === 'target_hit';
            const isStopHit = status === 'stop_loss_hit';
            const isEntryZone = status === 'entry_zone';

            return (
              <motion.div
                key={alert.id}
                layout
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ 
                  opacity: 1, 
                  scale: 1,
                  borderColor: isTargetHit ? 'rgba(234, 179, 8, 0.5)' : 
                              isStopHit ? 'rgba(244, 63, 94, 0.5)' : 
                              isEntryZone ? 'rgba(79, 70, 229, 0.5)' : 'rgba(228, 228, 231, 0.6)'
                }}
                exit={{ opacity: 0, scale: 0.95 }}
                className={cn(
                  "relative group overflow-hidden rounded-2xl border bg-white p-5 transition-all duration-500",
                  isTargetHit && "shadow-[0_0_20px_rgba(234,179,8,0.15)] ring-1 ring-yellow-400/30",
                  isStopHit && "shadow-[0_0_20px_rgba(244,63,94,0.15)] ring-1 ring-rose-400/30",
                  isEntryZone && "shadow-[0_0_20px_rgba(79,70,229,0.15)] ring-1 ring-indigo-400/30",
                  !isTargetHit && !isStopHit && !isEntryZone && "hover:border-zinc-300 hover:shadow-md"
                )}
              >
                {/* Background glow for hits */}
                {isTargetHit && <div className="absolute inset-0 bg-yellow-50/30 pointer-events-none animate-pulse" />}
                {isStopHit && <div className="absolute inset-0 bg-rose-50/30 pointer-events-none animate-pulse" />}
                {isEntryZone && <div className="absolute inset-0 bg-indigo-50/30 pointer-events-none animate-pulse" />}

                <div className="relative z-10 space-y-4">
                  <div className="flex items-start justify-between">
                    <div 
                      className="cursor-pointer" 
                      onClick={() => { setSymbol(alert.symbol); setMarket(alert.market); }}
                    >
                      <h3 className="text-sm font-bold text-zinc-950 group-hover:text-indigo-600 transition-colors">
                        {alert.name || alert.symbol}
                      </h3>
                      <p className="font-mono text-[10px] text-zinc-400 uppercase tracking-wider">
                        {alert.symbol} · {alert.market}
                      </p>
                    </div>
                    <button 
                      onClick={() => handleDelete(alert.id!)}
                      className="opacity-0 group-hover:opacity-100 p-1.5 text-zinc-400 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-all"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-0.5">Price</p>
                      <div className="flex items-baseline gap-1">
                        <span className="text-xl font-semibold tracking-tighter">
                          {currentPrice ? currentPrice.toFixed(2) : '---'}
                        </span>
                        <span className="text-[10px] text-zinc-400">{alert.currency}</span>
                      </div>
                    </div>
                    {status !== 'neutral' && (
                      <div className={cn(
                        "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider",
                        isTargetHit ? "bg-yellow-100 text-yellow-700" :
                        isStopHit ? "bg-rose-100 text-rose-700" :
                        "bg-indigo-100 text-indigo-700"
                      )}>
                        <Activity size={10} className="animate-pulse" />
                        {isTargetHit ? 'Target Hit' : isStopHit ? 'Stop Loss' : 'Entry Zone'}
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-3 gap-2 pt-3 border-t border-zinc-100">
                    <div className="space-y-1">
                      <p className="text-[8px] font-bold text-zinc-400 uppercase tracking-[0.15em]">Buy</p>
                      <p className={cn("text-xs font-medium", isEntryZone ? "text-indigo-600 font-bold" : "text-zinc-600")}>
                        {alert.entry_price}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-[8px] font-bold text-zinc-400 uppercase tracking-[0.15em]">T.P</p>
                      <p className={cn("text-xs font-medium", isTargetHit ? "text-yellow-600 font-bold" : "text-zinc-600")}>
                        {alert.target_price}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="text-[8px] font-bold text-zinc-400 uppercase tracking-[0.15em]">S.L</p>
                      <p className={cn("text-xs font-medium", isStopHit ? "text-rose-600 font-bold" : "text-zinc-600")}>
                        {alert.stop_loss}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Status indicator line at bottom */}
                <div className={cn(
                  "absolute bottom-0 left-0 h-1 transition-all duration-500",
                  isTargetHit ? "bg-yellow-500 w-full" : 
                  isStopHit ? "bg-rose-500 w-full" : 
                  isEntryZone ? "bg-indigo-500 w-full" : "bg-zinc-100 w-0 group-hover:w-full"
                )} />
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </section>
  );
});
