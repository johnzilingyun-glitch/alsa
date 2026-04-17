export interface WatchlistItem {
  symbol: string;
  name: string;
  market: string;
}

export async function fetchWatchlist(): Promise<WatchlistItem[]> {
  const res = await fetch('/api/watchlist');
  if (!res.ok) return [];
  const data = await res.json();
  return data.items || [];
}

export async function addToWatchlist(item: WatchlistItem): Promise<void> {
  const res = await fetch('/api/watchlist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item),
  });
  if (!res.ok) throw new Error('Failed to add to watchlist');
}

export async function removeFromWatchlist(symbol: string, market: string): Promise<void> {
  const res = await fetch(`/api/watchlist/${symbol}?market=${market}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to remove from watchlist');
}
