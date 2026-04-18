import { Market } from '../../types';

export interface SearchAlert {
  id?: number;
  symbol: string;
  name: string;
  market: Market;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  currency?: string;
  status?: string;
  created_at?: string;
}

export const alertsClient = {
  create: async (alert: SearchAlert) => {
    const res = await fetch('/api/alerts/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(alert)
    });
    if (!res.ok) throw new Error('Failed to create alert');
    return res.json();
  },

  list: async () => {
    const res = await fetch('/api/alerts/');
    if (!res.ok) throw new Error('Failed to fetch alerts');
    return res.json();
  },

  delete: async (id: number) => {
    const res = await fetch(`/api/alerts/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete alert');
    return res.json();
  }
};
