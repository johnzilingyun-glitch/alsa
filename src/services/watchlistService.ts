import type { WatchlistItem, WatchlistAlert } from '../types';

export function detectWatchlistAlert(
  item: WatchlistItem,
  newScore: number,
): WatchlistAlert | null {
  const history = item.scoreHistory;
  if (history.length === 0) return null;

  const prevScore = history[history.length - 1].score;
  const delta = newScore - prevScore;

  if (Math.abs(delta) < item.alertThreshold) return null;

  const type: WatchlistAlert['type'] = delta < 0 ? 'score_drop' : 'score_rise';
  const direction = delta < 0 ? '下降' : '上升';

  return {
    id: `alert-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    type,
    message: `${item.name} (${item.symbol}) Score ${direction} ${Math.abs(delta)} 点 (${prevScore} → ${newScore})`,
    triggeredAt: new Date().toISOString(),
    acknowledged: false,
  };
}
