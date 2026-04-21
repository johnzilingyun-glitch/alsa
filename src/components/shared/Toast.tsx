import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { CheckCircle2, AlertCircle, Info } from 'lucide-react';
import { useUIStore } from '../../stores/useUIStore';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function Toast() {
  const { toast } = useUIStore();

  if (!toast) return null;

  const { isOpen, message, type } = toast;

  const getIcon = () => {
    switch (type) {
      case 'success': return <CheckCircle2 className="text-emerald-500" size={18} />;
      case 'error': return <AlertCircle className="text-rose-500" size={18} />;
      default: return <Info className="text-indigo-500" size={18} />;
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed bottom-12 left-1/2 z-[300] -translate-x-1/2 pointer-events-none">
          <motion.div
            initial={{ opacity: 0, y: 40, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9, transition: { duration: 0.2 } }}
            className={cn(
              "flex items-center gap-3 rounded-2xl border bg-white px-6 py-4 shadow-2xl backdrop-blur-xl pointer-events-auto",
              type === 'success' ? "border-emerald-100" : type === 'error' ? "border-rose-100" : "border-indigo-100"
            )}
          >
            <div className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full shadow-inner",
              type === 'success' ? "bg-emerald-50" : type === 'error' ? "bg-rose-50" : "bg-indigo-50"
            )}>
              {getIcon()}
            </div>
            <span className="text-sm font-bold text-zinc-950 tracking-tight whitespace-nowrap">
              {message}
            </span>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
