import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ShieldAlert, AlertTriangle, Info, X } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function ConfirmDialog() {
  const { confirmDialog, hideConfirm } = useUIStore();

  if (!confirmDialog) return null;

  const { isOpen, title, message, onConfirm, type } = confirmDialog;

  const handleConfirm = () => {
    onConfirm();
    hideConfirm();
  };

  const getIcon = () => {
    switch (type) {
      case 'danger': return <ShieldAlert className="text-rose-500" size={24} />;
      case 'warning': return <AlertTriangle className="text-amber-500" size={24} />;
      default: return <Info className="text-indigo-500" size={24} />;
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
          {/* Backdrop with ultra blur */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={hideConfirm}
            className="absolute inset-0 bg-zinc-950/40 backdrop-blur-xl"
          />
          
          {/* Modal Surface */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="relative w-full max-w-md overflow-hidden rounded-3xl border border-white/20 bg-white/80 p-8 shadow-2xl backdrop-blur-2xl"
          >
            <div className="flex flex-col items-center text-center">
              {/* Icon Circle */}
              <div className={cn(
                "mb-6 flex h-16 w-16 items-center justify-center rounded-2xl shadow-inner",
                type === 'danger' ? "bg-rose-50" : type === 'warning' ? "bg-amber-50" : "bg-indigo-50"
              )}>
                {getIcon()}
              </div>

              <h3 className="mb-2 text-xl font-bold text-zinc-950 tracking-tight">
                {title}
              </h3>
              <p className="mb-8 text-sm font-medium text-zinc-500 leading-relaxed">
                {message}
              </p>

              <div className="flex w-full gap-3">
                <button
                  onClick={hideConfirm}
                  className="flex-1 rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm font-bold text-zinc-600 transition-all hover:bg-zinc-50 hover:border-zinc-300 active:scale-95"
                >
                  取消
                </button>
                <button
                  onClick={handleConfirm}
                  className={cn(
                    "flex-1 rounded-xl px-4 py-3 text-sm font-bold text-white shadow-lg transition-all active:scale-95",
                    type === 'danger' ? "bg-rose-500 shadow-rose-500/20 hover:bg-rose-600" : 
                    type === 'warning' ? "bg-amber-500 shadow-amber-500/20 hover:bg-amber-600" : 
                    "bg-indigo-600 shadow-indigo-600/20 hover:bg-indigo-700"
                  )}
                >
                  确认
                </button>
              </div>
            </div>

            {/* Close button */}
            <button
              onClick={hideConfirm}
              className="absolute right-4 top-4 rounded-full p-2 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-900"
            >
              <X size={18} />
            </button>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
