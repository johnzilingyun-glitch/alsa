import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, BrainCircuit, Send, Loader2, Sparkles, CheckCircle, Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface BrainEvolutionModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function BrainEvolutionModal({ isOpen, onClose }: BrainEvolutionModalProps) {
  const { t } = useTranslation();
  const [feedback, setFeedback] = useState('');
  const [role, setRole] = useState('Chief Strategist');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [history, setHistory] = useState<any[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  useEffect(() => {
    if (isOpen && role) {
      fetchHistory();
    }
  }, [isOpen, role]);

  const fetchHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const res = await fetch(`/api/brain/evolution/history?role=${encodeURIComponent(role)}`);
      if (res.ok) {
        const data = await res.json();
        setHistory(data.data || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!feedback.trim()) return;

    setIsSubmitting(true);
    setSuccessMsg('');

    try {
      const res = await fetch('/api/brain/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, feedback })
      });

      if (!res.ok) throw new Error('Failed to submit feedback');

      setSuccessMsg('Feedback submitted successfully. The AI will evolve based on your input.');
      setFeedback('');
      fetchHistory();
      setTimeout(() => {
        setSuccessMsg('');
      }, 3000);
    } catch (err) {
      console.error(err);
      alert('Error submitting feedback');
    } finally {
      setIsSubmitting(false);
    }
  };

  const ROLES = [
    'Technical Analyst',
    'Fundamental Analyst',
    'Sentiment Analyst',
    'Risk Manager',
    'Contrarian Strategist',
    'Deep Research Specialist',
    'Professional Reviewer',
    'Chief Strategist'
  ];

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        />

        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 20 }}
          className="relative w-full max-w-xl bg-white dark:bg-zinc-900 border border-border rounded-xl shadow-2xl overflow-hidden flex flex-col"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-border bg-zinc-50 dark:bg-zinc-800/50">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10 text-primary">
                <BrainCircuit className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-foreground">🧠 进化 AI (Evolve AI)</h2>
                <p className="text-sm text-muted-foreground mt-1">Submit postmortem feedback to mutate AI instructions</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 rounded-lg hover:bg-muted text-muted-foreground transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Form */}
          <div className="p-6 overflow-y-auto max-h-[70vh]">
            {successMsg ? (
              <div className="flex flex-col items-center justify-center py-12 text-center space-y-4">
                <div className="w-16 h-16 bg-green-500/20 text-green-500 rounded-full flex items-center justify-center">
                  <CheckCircle className="w-8 h-8" />
                </div>
                <h3 className="text-lg font-medium text-foreground">Evolution Triggered!</h3>
                <p className="text-muted-foreground max-w-sm">{successMsg}</p>
              </div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-6">
                
                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Target Expert Role</label>
                  <select
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    className="w-full h-10 px-3 py-2 rounded-lg bg-background border border-input text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  >
                    {ROLES.map(r => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-foreground">Feedback & Postmortem Notes</label>
                  <p className="text-xs text-muted-foreground mb-2">
                    Describe what went wrong or how the AI can improve its logic. The GEP Brain Manager will use this to mutate the role's instructions.
                  </p>
                  <textarea
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    placeholder="e.g. The Chief Strategist ignored the macro risks associated with rising treasury yields..."
                    className="w-full min-h-[150px] p-4 rounded-lg bg-background border border-input text-foreground resize-y focus:outline-none focus:ring-2 focus:ring-primary/50"
                    required
                  />
                </div>

                <div className="flex justify-end gap-3 pt-4 border-t border-border">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                  >
                    Close
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting || !feedback.trim()}
                    className="flex items-center gap-2 px-6 py-2 text-sm font-medium text-white bg-primary hover:bg-primary/90 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSubmitting ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        Mutate & Evolve
                      </>
                    )}
                  </button>
                </div>

              </form>
            )}

            {/* History Section */}
            <div className="mt-8 pt-6 border-t border-border">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-4">
                <Clock className="w-4 h-4 text-muted-foreground" />
                Evolution History ({role})
              </h3>
              
              {isLoadingHistory ? (
                <div className="flex items-center justify-center py-4">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : history.length === 0 ? (
                <p className="text-sm text-muted-foreground italic text-center py-4">No evolution records found for this role.</p>
              ) : (
                <div className="space-y-4">
                  {history.map((gene: any, idx: number) => (
                    <div key={gene.id} className={`p-4 rounded-lg border ${gene.is_alpha ? 'bg-primary/5 border-primary/20' : 'bg-muted/30 border-border'}`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold bg-background border px-2 py-0.5 rounded text-foreground">v{gene.version}</span>
                          {gene.is_alpha && <span className="text-[10px] font-bold text-primary uppercase tracking-wider bg-primary/10 px-1.5 py-0.5 rounded">Current Alpha</span>}
                        </div>
                        <span className="text-xs text-muted-foreground">{new Date(gene.created_at).toLocaleString()}</span>
                      </div>
                      
                      {gene.feedback_logs && gene.feedback_logs.length > 0 && (
                        <div className="mb-3 p-2 bg-background/50 rounded border border-border/50">
                          <p className="text-xs font-semibold text-muted-foreground mb-1">Triggered by Feedback:</p>
                          <ul className="list-disc pl-4 text-xs text-foreground space-y-1">
                            {gene.feedback_logs.map((log: string, i: number) => (
                              <li key={i}>{log}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground mb-1">Evolved Instructions:</p>
                        <p className="text-sm text-foreground whitespace-pre-wrap font-mono text-xs bg-background p-3 rounded border border-border/50">
                          {gene.content}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
