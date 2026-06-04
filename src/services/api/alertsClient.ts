import { Market } from '../../types';

export interface SearchAlert {
  id?: number;
  alert_id?: string;
  symbol: string;
  name: string;
  market: Market;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  currency?: string;
  status?: string;
  created_at?: string;
  // Postmortem fields
  exit_price?: number;
  exit_date?: string;
  outcome_category?: string;
  realized_return_pct?: number;
  mae_pct?: number;
  mfe_pct?: number;
  postmortem_notes?: string;
  decision_quality_score?: number;
  lessons_learned?: string;
}

export interface PostmortemPayload {
  exit_price: number;
  outcome_category: 'TRUE_POSITIVE' | 'FALSE_POSITIVE' | 'MISSED' | 'REGIME_MISMATCH';
  mae_pct?: number;
  mfe_pct?: number;
  notes?: string;
  decision_quality?: number;
}

export interface ThesisPayload {
  thesis?: string;
  invalidation_criteria?: string;
  thesis_stage?: 'IDEA' | 'WATCHING' | 'ENTERED' | 'EXITED' | 'POSTMORTEM';
  lessons_learned?: string;
}

export interface CatalystItem {
  catalyst_id?: string;
  alert_id: string;
  symbol: string;
  event_type: 'earnings' | 'product_launch' | 'regulatory' | 'macro' | 'conference' | 'other';
  description: string;
  expected_date?: string;
  impact_direction?: 'bullish' | 'bearish' | 'neutral';
  impact_magnitude?: 'high' | 'medium' | 'low';
  status?: 'pending' | 'occurred' | 'cancelled';
  actual_result?: string;
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

  delete: async (id: string | number) => {
    const res = await fetch(`/api/alerts/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete alert');
    return res.json();
  },

  recordPostmortem: async (alertId: string, payload: PostmortemPayload) => {
    const res = await fetch(`/api/alerts/${alertId}/postmortem`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Failed to record postmortem');
    return res.json();
  },

  listClosed: async () => {
    const res = await fetch('/api/alerts/closed');
    if (!res.ok) throw new Error('Failed to fetch closed alerts');
    return res.json();
  },

  updateThesis: async (alertId: string, payload: ThesisPayload) => {
    const res = await fetch(`/api/alerts/${alertId}/thesis`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Failed to update thesis');
    return res.json();
  },

  // --- Catalyst Calendar ---
  createCatalyst: async (payload: Omit<CatalystItem, 'catalyst_id' | 'status' | 'actual_result' | 'created_at'>) => {
    const res = await fetch('/api/alerts/catalysts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Failed to create catalyst');
    return res.json();
  },

  listCatalysts: async (symbol: string): Promise<{ items: CatalystItem[] }> => {
    const res = await fetch(`/api/alerts/catalysts/${symbol}`);
    if (!res.ok) throw new Error('Failed to fetch catalysts');
    return res.json();
  },

  updateCatalyst: async (catalystId: string, update: { status?: string; actual_result?: string }) => {
    const params = new URLSearchParams();
    if (update.status) params.set('status', update.status);
    if (update.actual_result) params.set('actual_result', update.actual_result);
    const res = await fetch(`/api/alerts/catalysts/${catalystId}?${params}`, { method: 'PATCH' });
    if (!res.ok) throw new Error('Failed to update catalyst');
    return res.json();
  }
};
