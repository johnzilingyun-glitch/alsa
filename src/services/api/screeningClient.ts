/**
 * Idea Screening Engine — Frontend API client
 * Multi-factor stock screening with preset and custom criteria
 */

export interface ScreenPreset {
  label: string;
  description: string;
  criteria: Record<string, any>;
}

export interface ScreenResult {
  symbol: string;
  name?: string;
  sector?: string;
  market_cap_b?: number;
  pe?: number;
  pb?: number;
  roe_pct?: number;
  revenue_growth_pct?: number;
  earnings_growth_pct?: number;
  fcf_yield_pct?: number;
  dividend_yield_pct?: number;
  debt_equity?: number;
  score?: number;
  // A-Share specific
  price?: number;
  change_pct?: number;
  // Momentum specific
  pct_above_200ma?: number;
  '6m_return'?: number;
  ma50_above_ma200?: boolean;
}

export interface ScreenResponse {
  screen_type: string;
  preset: ScreenPreset | null;
  market: string;
  sector: string | null;
  criteria: Record<string, any>;
  results: ScreenResult[];
  count: number;
  error?: string;
}

export interface ScreenRequest {
  screen_type: 'value' | 'growth' | 'quality' | 'short' | 'momentum';
  market: 'US' | 'A-Share';
  sector?: string;
  custom_criteria?: Record<string, any>;
  limit?: number;
}

export const screeningClient = {
  getPresets: async (): Promise<{ presets: Record<string, ScreenPreset> }> => {
    const res = await fetch('/api/screen/presets');
    if (!res.ok) throw new Error('Failed to fetch presets');
    return res.json();
  },

  runScreen: async (request: ScreenRequest): Promise<ScreenResponse> => {
    const res = await fetch('/api/screen/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    });
    if (!res.ok) throw new Error('Failed to run screen');
    return res.json();
  }
};
