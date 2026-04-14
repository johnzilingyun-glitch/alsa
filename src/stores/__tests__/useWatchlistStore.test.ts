import { describe, it, expect, beforeEach } from 'vitest';
import { useWatchlistStore } from '../../stores/useWatchlistStore';

describe('useWatchlistStore', () => {
  beforeEach(() => {
    useWatchlistStore.setState({
      items: [],
      isScanning: false,
      lastScanTime: null,
    });
  });

  it('has correct initial state', () => {
    const state = useWatchlistStore.getState();
    expect(state.items).toEqual([]);
    expect(state.isScanning).toBe(false);
    expect(state.lastScanTime).toBeNull();
  });

  it('adds item to watchlist', () => {
    useWatchlistStore.getState().addItem('600519', '贵州茅台', 'A-Share');
    const items = useWatchlistStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0].symbol).toBe('600519');
    expect(items[0].name).toBe('贵州茅台');
    expect(items[0].market).toBe('A-Share');
    expect(items[0].alertThreshold).toBe(15);
    expect(items[0].scoreHistory).toEqual([]);
    expect(items[0].alertHistory).toEqual([]);
  });

  it('removes item from watchlist', () => {
    useWatchlistStore.getState().addItem('600519', '贵州茅台', 'A-Share');
    const id = useWatchlistStore.getState().items[0].id;
    useWatchlistStore.getState().removeItem(id);
    expect(useWatchlistStore.getState().items).toHaveLength(0);
  });

  it('updates notes', () => {
    useWatchlistStore.getState().addItem('AAPL', 'Apple', 'US-Share');
    const id = useWatchlistStore.getState().items[0].id;
    useWatchlistStore.getState().updateNotes(id, 'Watch for earnings');
    expect(useWatchlistStore.getState().items[0].notes).toBe('Watch for earnings');
  });

  it('updates score history', () => {
    useWatchlistStore.getState().addItem('AAPL', 'Apple', 'US-Share');
    const id = useWatchlistStore.getState().items[0].id;
    const snapshot = { date: '2026-04-01', score: 75, price: 150, recommendation: 'Buy' };
    useWatchlistStore.getState().updateScore(id, snapshot);
    expect(useWatchlistStore.getState().items[0].scoreHistory).toHaveLength(1);
    expect(useWatchlistStore.getState().items[0].scoreHistory[0].score).toBe(75);
  });

  it('sets last quick scan result', () => {
    useWatchlistStore.getState().addItem('AAPL', 'Apple', 'US-Share');
    const id = useWatchlistStore.getState().items[0].id;
    const scanResult = { score: 80, sentiment: 'Bullish', recommendation: 'Buy', summary: 'Strong', timestamp: '2026-04-01T10:00:00Z' };
    useWatchlistStore.getState().setLastQuickScan(id, scanResult);
    expect(useWatchlistStore.getState().items[0].lastQuickScan?.score).toBe(80);
  });

  it('adds alert to item', () => {
    useWatchlistStore.getState().addItem('AAPL', 'Apple', 'US-Share');
    const id = useWatchlistStore.getState().items[0].id;
    const alert = { id: 'alert-1', type: 'score_drop' as const, message: 'Score dropped 20 points', triggeredAt: '2026-04-01T10:00:00Z', acknowledged: false };
    useWatchlistStore.getState().addAlert(id, alert);
    expect(useWatchlistStore.getState().items[0].alertHistory).toHaveLength(1);
  });

  it('acknowledges alert', () => {
    useWatchlistStore.getState().addItem('AAPL', 'Apple', 'US-Share');
    const itemId = useWatchlistStore.getState().items[0].id;
    const alert = { id: 'alert-1', type: 'score_drop' as const, message: 'Drop', triggeredAt: '2026-04-01', acknowledged: false };
    useWatchlistStore.getState().addAlert(itemId, alert);
    useWatchlistStore.getState().acknowledgeAlert(itemId, 'alert-1');
    expect(useWatchlistStore.getState().items[0].alertHistory[0].acknowledged).toBe(true);
  });

  it('does not add duplicate symbols', () => {
    useWatchlistStore.getState().addItem('AAPL', 'Apple', 'US-Share');
    useWatchlistStore.getState().addItem('AAPL', 'Apple', 'US-Share');
    expect(useWatchlistStore.getState().items).toHaveLength(1);
  });
});
