import { Market, MarketOverview, StockAnalysis } from "../types";

export async function getMarketOverview(): Promise<MarketOverview> {
  const response = await fetch('/api/market/overview');
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to fetch market overview');
  }
  return response.json();
}

export async function analyzeStock(symbol: string, market: Market): Promise<StockAnalysis> {
  const response = await fetch('/api/market/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol, market }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to analyze stock');
  }
  return response.json();
}

export async function sendChatMessage(
  message: string,
  analysis: StockAnalysis
): Promise<string> {
  const response = await fetch('/api/market/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, analysis }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Failed to send chat message');
  }
  const data = await response.json();
  return data.response;
}
