import type { StockAnalysis } from "../types";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface DriftSignal {
  field: string;
  aiValue: number;
  apiValue: number;
  driftPct: number;
  threshold: number;
  unit?: string;
}

export interface CommodityDrift {
  varName: string;
  aiValue: number;
  apiValue: number;
  apiName: string;
  unit: string;
}

export interface DriftResult {
  signals: DriftSignal[];
  commodityDrifts: CommodityDrift[];
  correctedData: Record<string, any>;
  hasDrift: boolean;
}

// ─── Pure Helpers ─────────────────────────────────────────────────────────────

/** Relative drift between two positive numbers. Returns 0 if api ≤ 0. */
export const relDrift = (ai: number, api: number): number =>
  api > 0 ? Math.abs(ai - api) / api : 0;

/** Adaptive price threshold: low-price stocks tolerate more relative drift. */
export const priceDriftThreshold = (price: number): number =>
  price < 5 ? 0.05 : price < 20 ? 0.03 : price < 100 ? 0.02 : 0.015;

/** Extract a numeric value from AI's fundamentalTable by keyword match. */
export const extractFromFundamentalTable = (
  table: Array<{ indicator: string; value: string }> | undefined,
  ...keywords: string[]
): number | null => {
  if (!table) return null;
  for (const kw of keywords) {
    const row = table.find(r =>
      r.indicator.toLowerCase().includes(kw) || r.value?.toLowerCase().includes(kw)
    );
    if (row) {
      const num = parseFloat(row.value.replace(/[^0-9.\-]/g, ''));
      if (!isNaN(num)) return num;
    }
  }
  return null;
};

// ─── Thresholds (named for readability) ───────────────────────────────────────

const THRESHOLDS = {
  volume: 0.30,      // 30% — intraday volume changes fast
  marketCap: 0.05,   // 5%  — derived from price × shares, tight
  pe: 0.15,          // 15% — trailing vs forward calc variations
  open: 0.02,        // 2%  — fixed once market opens
  commodity: 0.10,   // 10% — commodity data may lag
} as const;

// ─── Commodity Alias Mapping ──────────────────────────────────────────────────

const COMMODITY_ALIASES: Record<string, string[]> = {
  'GC=F':     ['gold', '黄金', '伦敦金', 'xau', '金价'],
  'HG=F':     ['copper', '铜', 'lme铜', '铜价', '伦铜'],
  'CL=F':     ['oil', '原油', 'wti', '油价', 'crude', '石油'],
  'SI=F':     ['silver', '白银', '银价'],
  'USDCNY=X': ['usdcny', '美元人民币', '汇率', 'usd/cny', '美元兑人民币'],
};

/** Build a lowercase keyword → { price, name, unit } lookup from API commodity data. */
function buildCommodityMap(commoditiesData: any[]): Map<string, { price: number; name: string; unit: string }> {
  const map = new Map<string, { price: number; name: string; unit: string }>();
  for (const c of commoditiesData) {
    if (c.price == null || Number(c.price) <= 0) continue;
    const entry = { price: Number(c.price), name: c.name, unit: c.unit || '' };
    const aliases = COMMODITY_ALIASES[c.symbol] || [];
    const keys = [c.name?.toLowerCase(), c.symbol?.toLowerCase(), ...aliases.map((a: string) => a.toLowerCase())];
    for (const key of keys) {
      if (key) map.set(key, entry);
    }
  }
  return map;
}

/** Fuzzy-match a variable name against the commodity lookup. */
function findCommodityMatch(name: string, map: Map<string, { price: number; name: string; unit: string }>) {
  const lower = name.toLowerCase();
  for (const [key, val] of map) {
    if (lower.includes(key) || key.includes(lower)) return val;
  }
  return null;
}

// ─── Detector Functions ───────────────────────────────────────────────────────

function checkStockFields(
  analysis: StockAnalysis,
  realtimeData: any,
  apiPrice: number,
): DriftSignal[] {
  const signals: DriftSignal[] = [];
  const table = analysis.fundamentalTable;

  // Price
  const priceThreshold = priceDriftThreshold(apiPrice);
  const pDrift = relDrift(analysis.stockInfo.price, apiPrice);
  if (apiPrice > 0 && pDrift > priceThreshold) {
    signals.push({ field: 'Price', aiValue: analysis.stockInfo.price, apiValue: apiPrice, driftPct: pDrift, threshold: priceThreshold });
  }

  // Volume
  if (realtimeData.volume != null) {
    const apiVol = Number(realtimeData.volume);
    const aiVol = extractFromFundamentalTable(table, 'volume', '成交量', 'vol');
    if (apiVol > 0 && aiVol != null && relDrift(aiVol, apiVol) > THRESHOLDS.volume) {
      signals.push({ field: 'Volume', aiValue: aiVol, apiValue: apiVol, driftPct: relDrift(aiVol, apiVol), threshold: THRESHOLDS.volume });
    }
  }

  // Market Cap
  if (realtimeData.marketCap != null) {
    const apiMCap = Number(realtimeData.marketCap);
    const aiMCap = extractFromFundamentalTable(table, 'market cap', '市值');
    if (apiMCap > 0 && aiMCap != null && relDrift(aiMCap, apiMCap) > THRESHOLDS.marketCap) {
      signals.push({ field: 'MarketCap', aiValue: aiMCap, apiValue: apiMCap, driftPct: relDrift(aiMCap, apiMCap), threshold: THRESHOLDS.marketCap });
    }
  }

  // P/E Ratio
  if (realtimeData.pe != null) {
    const apiPE = Number(realtimeData.pe);
    const aiFundPE = analysis.fundamentals?.pe ? parseFloat(analysis.fundamentals.pe.replace(/[^0-9.\-]/g, '')) : null;
    const aiTablePE = extractFromFundamentalTable(table, 'p/e', 'pe', '市盈率');
    const aiPE = aiFundPE ?? aiTablePE;
    if (apiPE > 0 && aiPE != null && !isNaN(aiPE) && relDrift(aiPE, apiPE) > THRESHOLDS.pe) {
      signals.push({ field: 'PE', aiValue: aiPE, apiValue: apiPE, driftPct: relDrift(aiPE, apiPE), threshold: THRESHOLDS.pe });
    }
  }

  // Open Price
  if (realtimeData.open != null) {
    const apiOpen = Number(realtimeData.open);
    const aiOpen = extractFromFundamentalTable(table, 'open', '开盘');
    if (apiOpen > 0 && aiOpen != null && relDrift(aiOpen, apiOpen) > THRESHOLDS.open) {
      signals.push({ field: 'Open', aiValue: aiOpen, apiValue: apiOpen, driftPct: relDrift(aiOpen, apiOpen), threshold: THRESHOLDS.open });
    }
  }

  return signals;
}

function checkCommodityVariables(
  analysis: StockAnalysis,
  commoditiesData: any[],
): { signals: DriftSignal[]; commodityDrifts: CommodityDrift[] } {
  const signals: DriftSignal[] = [];
  const commodityDrifts: CommodityDrift[] = [];
  if (commoditiesData.length === 0) return { signals, commodityDrifts };

  const commodityMap = buildCommodityMap(commoditiesData);

  const checkVar = (name: string, rawValue: string | number) => {
    const match = findCommodityMatch(name, commodityMap);
    if (!match) return;
    const aiVal = typeof rawValue === 'number' ? rawValue : parseFloat(String(rawValue).replace(/[^0-9.\-]/g, ''));
    if (isNaN(aiVal) || aiVal <= 0) return;
    const drift = relDrift(aiVal, match.price);
    if (drift > THRESHOLDS.commodity) {
      signals.push({ field: `CoreVar:${name}`, aiValue: aiVal, apiValue: match.price, driftPct: drift, threshold: THRESHOLDS.commodity, unit: match.unit });
      commodityDrifts.push({ varName: name, aiValue: aiVal, apiValue: match.price, apiName: match.name, unit: match.unit });
    }
  };

  for (const cv of analysis.coreVariables ?? []) checkVar(cv.name, cv.value);
  for (const anchor of analysis.industryAnchors ?? []) checkVar(anchor.variable, anchor.currentValue);

  return { signals, commodityDrifts };
}

// ─── Main Entry Point ─────────────────────────────────────────────────────────

/** Build ground-truth correctedData from API sources. */
function buildCorrectedData(
  realtimeData: any,
  apiPrice: number,
  analysis: StockAnalysis,
  signals: DriftSignal[],
  commodityDrifts: CommodityDrift[],
  commoditiesData: any[],
): Record<string, any> {
  return {
    price: apiPrice,
    change: realtimeData.change != null ? Number(realtimeData.change) : analysis.stockInfo.change,
    changePercent: realtimeData.changePercent != null ? Number(realtimeData.changePercent) : analysis.stockInfo.changePercent,
    previousClose: realtimeData.previousClose != null ? Number(realtimeData.previousClose) : analysis.stockInfo.previousClose,
    dailyHigh: realtimeData.dayHigh != null ? Number(realtimeData.dayHigh) : undefined,
    dailyLow: realtimeData.dayLow != null ? Number(realtimeData.dayLow) : undefined,
    open: realtimeData.open != null ? Number(realtimeData.open) : undefined,
    volume: realtimeData.volume != null ? Number(realtimeData.volume) : undefined,
    marketCap: realtimeData.marketCap != null ? Number(realtimeData.marketCap) : undefined,
    pe: realtimeData.pe != null ? Number(realtimeData.pe) : undefined,
    lastUpdated: realtimeData.lastUpdated || analysis.stockInfo.lastUpdated,
    currency: realtimeData.currency || analysis.stockInfo.currency,
    _driftSignals: signals.map(s => `${s.field}: AI=${s.aiValue}, API=${s.apiValue} ${s.unit ?? ''} (${(s.driftPct * 100).toFixed(1)}% > ${(s.threshold * 100)}%)`.trim()),
    _commodityDrifts: commodityDrifts.length > 0 ? commodityDrifts : undefined,
    _commoditiesData: commodityDrifts.length > 0 ? commoditiesData : undefined,
  };
}

/** Enforce API ground truth onto stockInfo fields (hard override, always applied). */
export function enforceGroundTruth(analysis: StockAnalysis, realtimeData: any): void {
  const apiPrice = Number(realtimeData.price);
  analysis.stockInfo.price = apiPrice;
  if (realtimeData.change != null) analysis.stockInfo.change = Number(realtimeData.change);
  if (realtimeData.changePercent != null) analysis.stockInfo.changePercent = Number(realtimeData.changePercent);
  if (realtimeData.previousClose != null) analysis.stockInfo.previousClose = Number(realtimeData.previousClose);
  if (realtimeData.dayHigh != null) analysis.stockInfo.dailyHigh = Number(realtimeData.dayHigh);
  if (realtimeData.dayLow != null) analysis.stockInfo.dailyLow = Number(realtimeData.dayLow);
  if (realtimeData.lastUpdated) analysis.stockInfo.lastUpdated = realtimeData.lastUpdated;
  if (realtimeData.currency) analysis.stockInfo.currency = realtimeData.currency;
}

/**
 * Run multi-field drift detection: stock fields + domain commodity variables.
 * Returns structured result with signals, correctedData for prompt, and hasDrift flag.
 */
export function detectDrift(
  analysis: StockAnalysis,
  realtimeData: any,
  commoditiesData: any[],
): DriftResult {
  const apiPrice = Number(realtimeData.price);

  const stockSignals = checkStockFields(analysis, realtimeData, apiPrice);
  const { signals: commoditySignals, commodityDrifts } = checkCommodityVariables(analysis, commoditiesData);

  const allSignals = [...stockSignals, ...commoditySignals];
  const hasDrift = allSignals.length > 0;

  const correctedData = hasDrift
    ? buildCorrectedData(realtimeData, apiPrice, analysis, allSignals, commodityDrifts, commoditiesData)
    : {};

  if (hasDrift) {
    console.warn(`[AntiHallucination] Drift detected in ${allSignals.length} field(s):\n  ${allSignals.map(s => `${s.field}: AI=${s.aiValue}, API=${s.apiValue} (${(s.driftPct * 100).toFixed(1)}%)`).join('\n  ')}`);
  }

  return { signals: allSignals, commodityDrifts, correctedData, hasDrift };
}
