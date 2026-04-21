import type { MarketOverview } from '../types';

export async function getHistoryContext(): Promise<any[]> {
  try {
    // Add cache-buster to avoid getting cached HTML fallback pages
    const response = await fetch(`/api/history/context?t=${Date.now()}`);
    if (response.ok) {
      const contentType = response.headers?.get('content-type');
      if (contentType && contentType.includes('text/html')) {
        const text = await response.text();
        console.error('Received HTML instead of JSON for history context. Response body:', text.substring(0, 500));
        return [];
      }
      const text = await response.text();
      try {
        return JSON.parse(text);
      } catch (parseErr) {
        console.error('Failed to parse history context JSON. Response text:', text.substring(0, 500));
        throw parseErr;
      }
    } else {
      const errorText = await response.text();
      console.error(`Failed to fetch history context: ${response.status} ${response.statusText}`, errorText.substring(0, 500));
    }
  } catch (err) {
    console.error('Failed to fetch history context:', err);
  }
  return [];
}

export async function getMarketHistoryByDate(date: string, market: string): Promise<MarketOverview | null> {
  try {
    const response = await fetch(`/api/history/market?date=${encodeURIComponent(date)}&market=${encodeURIComponent(market)}`);
    if (response.ok) {
      return await response.json();
    }
    return null;
  } catch (err) {
    console.error('Failed to fetch market history by date:', err);
    return null;
  }
}

export async function getAvailableMarketDates(market: string): Promise<string[]> {
  try {
    const response = await fetch(`/api/history/dates?market=${encodeURIComponent(market)}`);
    if (response.ok) {
      return await response.json();
    }
    return [];
  } catch (err) {
    console.error('Failed to fetch available market dates:', err);
    return [];
  }
}

export async function getPreviousStockAnalysis(symbol: string): Promise<any | null> {
  try {
    const history = await getHistoryContext();
    // History items are saved as { ...analysisData, type, id, generatedAt } (flat, no .data wrapper)
    const previous = history
      .filter((item: any) => {
        const isStock = item.type === 'stock' || (item.stockInfo && !item.indices);
        if (!isStock) return false;
        const sym = item.stockInfo?.symbol;
        return sym === symbol;
      })
      .sort((a: any, b: any) => {
        const timeA = new Date(a.generatedAt || a.stockInfo?.lastUpdated || 0).getTime();
        const timeB = new Date(b.generatedAt || b.stockInfo?.lastUpdated || 0).getTime();
        return timeB - timeA;
      });

    // Return the most recent one (since save hasn't happened yet for current run)
    return previous.length > 0 ? previous[0] : null;
  } catch (err) {
    console.error('Failed to get previous stock analysis:', err);
    return null;
  }
}

export async function saveAnalysisToHistory(type: 'market' | 'stock', data: any) {
  try {
    const response = await fetch('/api/history/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, data })
    });
    if (!response.ok) {
      const errorData = await response.json();
      console.error('Save analysis API error:', errorData);
      throw new Error(errorData.error || 'Failed to save analysis');
    }
  } catch (err) {
    console.error('Failed to save analysis to history:', err);
    if (err instanceof Error) {
      console.error('Error name:', err.name);
      console.error('Error message:', err.message);
      if (err.stack) console.error('Error stack:', err.stack);
    }
  }
}

export async function deleteHistoryItem(id: string): Promise<boolean> {
  try {
    const response = await fetch(`/api/history/${id}`, {
      method: 'DELETE'
    });
    return response.ok;
  } catch (err) {
    console.error('Failed to delete history item:', err);
    return false;
  }
}

export async function logOptimization(field: string, oldValue: any, newValue: any, description: string) {
  try {
    await fetch('/api/logs/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field, oldValue, newValue, description })
    });
  } catch (err) {
    console.error('Failed to log optimization:', err);
  }
}
