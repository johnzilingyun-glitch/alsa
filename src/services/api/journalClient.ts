export interface JournalEntry {
  symbol: string;
  market: string;
  action: 'buy' | 'sell' | 'hold';
  price_at_decision: number;
  confidence: number;
  reasoning?: string;
  analysis_id?: string;
}

export async function submitJournalEntry(entry: JournalEntry): Promise<void> {
  const res = await fetch('/api/journal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  });
  if (!res.ok) throw new Error('Failed to submit journal entry');
}

export async function fetchJournalEntries(): Promise<JournalEntry[]> {
  const res = await fetch('/api/journal');
  if (!res.ok) return [];
  const data = await res.json();
  return data.items || [];
}
