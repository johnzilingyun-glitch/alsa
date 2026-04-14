import { useEffect, useCallback, useRef, useState } from 'react';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import type { Market } from '../types';

const VALID_MARKETS = new Set(['A-Share', 'HK-Share', 'US-Share']);

function getUrlParams(): { symbol?: string; market?: Market } {
  const params = new URLSearchParams(window.location.search);
  const symbol = params.get('symbol') || undefined;
  const marketRaw = params.get('market');
  const market = marketRaw && VALID_MARKETS.has(marketRaw) ? (marketRaw as Market) : undefined;
  return { symbol, market };
}

function setUrlParams(symbol: string | undefined, market: string | undefined) {
  const url = new URL(window.location.href);
  if (symbol) {
    url.searchParams.set('symbol', symbol);
  } else {
    url.searchParams.delete('symbol');
  }
  if (market) {
    url.searchParams.set('market', market);
  } else {
    url.searchParams.delete('market');
  }
  window.history.replaceState(null, '', url.toString());
}

/**
 * Syncs stock symbol/market with URL search params.
 * - On mount, reads ?symbol=&market= from URL and returns initial params
 * - When analysis appears/disappears, updates URL accordingly.
 */
export function useUrlState() {
  const analysis = useAnalysisStore(s => s.analysis);
  const [initialUrlParams] = useState(() => getUrlParams());

  // Sync analysis state → URL
  useEffect(() => {
    if (analysis) {
      setUrlParams(analysis.stockInfo?.symbol, analysis.stockInfo?.market);
    } else {
      setUrlParams(undefined, undefined);
    }
  }, [analysis]);

  return { initialUrlParams };
}
