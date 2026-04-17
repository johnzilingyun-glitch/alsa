import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { Database, Brain, PenTool, ClipboardCheck, Search, ShieldCheck } from 'lucide-react';
import { cn } from './utils';
import type { AgentRole } from '../../types';

interface DeliberationMatrixProps {
  currentRound: number;
  totalRounds: number;
  activeExperts: string[];
  currentStep?: 'grounding' | 'reasoning' | 'drafting' | 'reviewing' | 'auditing';
}

const steps = [
  { id: 'grounding', icon: Database, label: 'analysis.matrix.grounding' },
  { id: 'reasoning', icon: Brain, label: 'analysis.matrix.reasoning' },
  { id: 'drafting', icon: PenTool, label: 'analysis.matrix.drafting' },
  { id: 'auditing', icon: ShieldCheck, label: 'analysis.matrix.auditing' },
];

export function DeliberationMatrix({ 
  currentRound, 
  totalRounds, 
  activeExperts, 
  currentStep 
}: DeliberationMatrixProps) {
  const { t } = useTranslation();

  return (
    <div className="max-w-4xl mx-auto w-full mb-12">
      <div className="p-8 rounded-[2.5rem] bg-white border border-zinc-200 shadow-sm relative overflow-hidden group">
        {/* Background Accent */}
        <div className="absolute top-0 right-0 p-8 opacity-[0.03] group-hover:opacity-[0.05] transition-opacity pointer-events-none">
          <Brain size={160} className="text-indigo-600 rotate-12" />
        </div>

        <div className="relative z-10">
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-2xl bg-indigo-600/10 text-indigo-600 border border-indigo-600/20">
                <Brain size={20} />
              </div>
              <div>
                <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] text-indigo-600">
                  {t('analysis.matrix.title')}
                </h4>
                <p className="text-[9px] text-zinc-400 font-medium uppercase tracking-wider">
                  {t('analysis.matrix.subtitle', { current: currentRound, total: totalRounds })}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono text-zinc-400">ROUND {currentRound}</span>
              <div className="flex gap-1">
                {Array.from({ length: totalRounds }).map((_, i) => (
                  <div 
                    key={i} 
                    className={cn(
                      "w-4 h-1 rounded-full transition-all duration-500",
                      i + 1 < currentRound ? "bg-emerald-500" :
                      i + 1 === currentRound ? "bg-indigo-600 animate-pulse" :
                      "bg-zinc-100"
                    )}
                  />
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {steps.map((step) => {
              const isActive = currentStep === step.id;
              const isPast = steps.findIndex(s => s.id === currentStep) > steps.findIndex(s => s.id === step.id);
              const StepIcon = step.icon;

              return (
                <div 
                  key={step.id}
                  className={cn(
                    "p-4 rounded-2xl border transition-all duration-300",
                    isActive ? "bg-indigo-600 text-white border-indigo-600 shadow-lg shadow-indigo-600/20" :
                    isPast ? "bg-emerald-50 text-emerald-600 border-emerald-100" :
                    "bg-zinc-50 text-zinc-400 border-transparent"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <StepIcon size={16} className={cn(isActive && "animate-pulse")} />
                    <span className="text-[10px] font-bold uppercase tracking-widest leading-none">
                      {t(step.label)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-8 pt-6 border-t border-zinc-100">
            <p className="text-[9px] text-zinc-400 uppercase font-bold tracking-[0.2em] mb-4">
              {t('analysis.matrix.active_agents')}
            </p>
            <div className="flex flex-wrap gap-3">
              <AnimatePresence mode="popLayout">
                {activeExperts.map((expert) => (
                  <motion.div
                    key={expert}
                    initial={{ opacity: 0, scale: 0.9, y: 10 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.9, y: -10 }}
                    className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-indigo-50 border border-indigo-100/50"
                  >
                    <div className="w-1.5 h-1.5 rounded-full bg-indigo-600 animate-pulse" />
                    <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-widest whitespace-nowrap">
                      {t(`analysis.roles.${expert}`)}
                    </span>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
