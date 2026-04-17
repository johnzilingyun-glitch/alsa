import { useEffect } from 'react';
import { useWatchlistStore } from '../stores/useWatchlistStore';
import { fetchWatchlist, addToWatchlist, removeFromWatchlist } from '../services/api/watchlistClient';

export function useWatchlistSync() {
  const { items, setItems } = useWatchlistStore() as any;

  // Initial sync from backend
  useEffect(() => {
    async function sync() {
      try {
        const remoteList = await fetchWatchlist();
        // Since we want the backend to be the source of truth
        setItems(remoteList.map((item: any, idx: number) => ({
          id: `wl-sync-${idx}`,
          symbol: item.symbol,
          name: item.name || '',
          market: item.market as any,
          addedAt: new Date().toISOString(),
          notes: '',
          alertThreshold: 15,
          scoreHistory: [],
          alertHistory: [],
        })));
      } catch (err) {
        console.error('Failed to sync watchlist:', err);
      }
    }
    sync();
  }, [setItems]);

  const add = async (symbol: string, name: string, market: string) => {
    try {
      await addToWatchlist({ symbol, name, market });
      // Update local store after successful backend update
      useWatchlistStore.getState().addItem(symbol, name, market as any);
    } catch (err) {
      console.error('Failed to add to remote watchlist:', err);
    }
  };

  const remove = async (symbol: string, market: string) => {
    try {
      await removeFromWatchlist(symbol, market);
      useWatchlistStore.getState().removeItem(symbol);
    } catch (err) {
      console.error('Failed to remove from remote watchlist:', err);
    }
  };

  return { add, remove };
}
