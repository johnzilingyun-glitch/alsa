import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, X, MessageSquare, Send, Zap, AlertCircle, TrendingUp, TrendingDown } from 'lucide-react';

interface AnalysisFeedbackProps {
  analysisId: string;
  symbol: string;
  onSubmitted?: () => void;
}

const FEEDBACK_OPTIONS = [
  { id: 'accurate', label: '逻辑准确', icon: Check, color: 'var(--color-positive)' },
  { id: 'too_bullish', label: '过于乐观', icon: TrendingUp, color: 'var(--color-brand-500)' },
  { id: 'too_bearish', label: '过于悲观', icon: TrendingDown, color: 'var(--color-warning)' },
  { id: 'missing_data', label: '数据遗漏', icon: AlertCircle, color: 'var(--color-negative)' },
  { id: 'logic_gap', label: '逻辑断层', icon: AlertCircle, color: 'var(--color-negative)' },
];

export const AnalysisFeedback: React.FC<AnalysisFeedbackProps> = ({ analysisId, symbol, onSubmitted }) => {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const handleSubmit = async () => {
    if (!selectedOption) return;

    setIsSubmitting(true);
    try {
      const response = await fetch('/api/brain/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'default_user', // Will be dynamic in the future
          feedback: `${FEEDBACK_OPTIONS.find(o => o.id === selectedOption)?.label}: ${comment}`,
          context: `Stock: ${symbol}, Analysis ID: ${analysisId}`,
        }),
      });

      if (response.ok) {
        setIsSubmitted(true);
        onSubmitted?.();
      }
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isSubmitted) {
    return (
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="mt-8 flex items-center justify-center space-x-3 rounded-2xl border border-titanium-200 bg-titanium-50/50 p-6 backdrop-blur-md"
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-positive/10 text-positive">
          <Check className="h-5 w-5" />
        </div>
        <div>
          <h4 className="text-sm font-bold text-titanium-900">反馈已接收</h4>
          <p className="text-xs text-titanium-600">AI 正在根据您的建议进化分析逻辑</p>
        </div>
      </motion.div>
    );
  }

  return (
    <div className="mt-8 overflow-hidden rounded-2xl border border-titanium-200 bg-titanium-50/30 backdrop-blur-xl transition-all hover:border-titanium-300">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-titanium-200 bg-titanium-100/50 px-6 py-4">
        <div className="flex items-center space-x-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-titanium-900 text-white shadow-lg">
            <Zap className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-titanium-900">EvolveR 研报反馈</h3>
            <p className="text-[10px] uppercase tracking-widest text-titanium-500">System Self-Evolution Interface</p>
          </div>
        </div>
        <div className="rounded-full bg-brain-glow/10 px-2 py-1 text-[10px] font-bold text-brain-glow animate-pulse">
          AI EVOLUTION ACTIVE
        </div>
      </div>

      {/* Body */}
      <div className="p-6">
        <p className="mb-4 text-xs font-medium text-titanium-700">这篇关于 {symbol} 的研报质量如何？您的反馈将直接优化 AI 的研判标准。</p>
        
        <div className="mb-6 flex flex-wrap gap-2">
          {FEEDBACK_OPTIONS.map((option) => {
            const Icon = option.icon;
            const isSelected = selectedOption === option.id;
            return (
              <button
                key={option.id}
                onClick={() => setSelectedOption(option.id)}
                className={`
                  flex items-center space-x-2 rounded-xl border px-3 py-2 text-xs font-semibold transition-all
                  ${isSelected 
                    ? 'border-titanium-900 bg-titanium-900 text-white shadow-md' 
                    : 'border-titanium-200 bg-white text-titanium-600 hover:border-titanium-400 hover:bg-titanium-50'}
                `}
              >
                <Icon className={`h-3.5 w-3.5 ${isSelected ? 'text-white' : ''}`} style={{ color: isSelected ? undefined : option.color }} />
                <span>{option.label}</span>
              </button>
            );
          })}
        </div>

        <AnimatePresence>
          {selectedOption && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="space-y-4"
            >
              <div className="relative">
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="提供更详细的修正意见（可选）..."
                  className="w-full rounded-xl border border-titanium-200 bg-white/50 p-4 text-xs text-titanium-900 transition-all placeholder:text-titanium-400 focus:border-titanium-500 focus:outline-none focus:ring-2 focus:ring-titanium-500/10"
                  rows={3}
                />
                <div className="absolute bottom-3 right-3 text-titanium-300">
                  <MessageSquare className="h-4 w-4" />
                </div>
              </div>

              <div className="flex justify-end">
                <button
                  onClick={handleSubmit}
                  disabled={isSubmitting}
                  className="flex items-center space-x-2 rounded-xl bg-titanium-900 px-6 py-2 text-xs font-bold text-white transition-all hover:bg-titanium-800 disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-white" />
                  ) : (
                    <>
                      <Send className="h-3.5 w-3.5" />
                      <span>提交并优化系统</span>
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Footer / Decorative */}
      <div className="bg-titanium-900 p-[1px]">
        <div className="bg-titanium-50 h-1" />
      </div>
    </div>
  );
};
