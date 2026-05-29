export interface Quote {
  symbol: string;
  price: number;
  change?: number;
  changePercent?: number;
  market?: string;
  name?: string;
}

/**
 * Fetch real-time quotes for a list of symbols.
 */
export async function getQuotes(symbols: string[]): Promise<Quote[]> {
  if (!symbols || symbols.length === 0) return [];
  const symbolList = symbols.join(',');
  const res = await fetch(`/api/market/quotes?symbols=${symbolList}`);
  if (!res.ok) return [];
  const json = await res.json();
  
  if (json && json.data && Array.isArray(json.data)) {
    return json.data;
  }
  if (Array.isArray(json)) {
    return json;
  }
  return [];
}
