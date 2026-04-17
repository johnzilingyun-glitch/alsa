import { useDecisionStore } from '../stores/useDecisionStore';
import { submitJournalEntry, fetchJournalEntries, JournalEntry } from '../services/api/journalClient';

export function useDecisionJournal() {
  const submit = async (entry: JournalEntry) => {
    try {
      await submitJournalEntry(entry);
      // Backend handles persistence, we just update local cache if needed
      useDecisionStore.getState().addEntry({
          symbol: entry.symbol,
          market: 'A-Share', // Default for manual entries if undefined
          name: entry.symbol, // Fallback to symbol if name is missing
          action: entry.action as any,
          priceAtDecision: entry.price_at_decision,
          confidence: entry.confidence,
          reasoning: entry.reasoning || '',
          analysisId: 'manual',
      });
    } catch (err) {
      console.error('Failed to submit journal entry:', err);
    }
  };

  const sync = async () => {
    try {
      const entries = await fetchJournalEntries();
      // Update store with remote entries
    } catch (err) {
      console.error('Failed to sync journal:', err);
    }
  };

  return { submit, sync };
}
