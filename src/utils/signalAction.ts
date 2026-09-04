/**
 * Signal action utilities — frontend mirror of the backend `signal_taxonomy`
 * module (python_service/app/services/signal_taxonomy.py).
 *
 * Canonical action space: buy | sell | hold | watch
 *
 * Used by the "add to signal center" entry points (SidebarSummary,
 * InstitutionalReportView) and the SignalCenter dashboard so that:
 * - free-form recommendation strings (English broker ratings, Chinese ratings)
 *   normalize to the same four values the backend extracts into
 *   `tradingPlan.action`;
 * - price parsing NEVER fabricates values (the old `parseNum(/[\d.]+/)`
 *   treated "15%" or "+15~20%" as a price of 15).
 */
import type { Market, StockAnalysis, TradingPlan } from '../types';

export type SignalAction = 'buy' | 'sell' | 'hold' | 'watch';

const EXACT_ACTIONS: Record<string, SignalAction> = {
  // canonical values (already normalized by the backend)
  buy: 'buy',
  sell: 'sell',
  hold: 'hold',
  watch: 'watch',
  // English broker ratings
  'strong buy': 'buy',
  accumulate: 'buy',
  add: 'buy',
  overweight: 'buy',
  'strong sell': 'sell',
  reduce: 'sell',
  avoid: 'sell',
  underweight: 'sell',
  neutral: 'hold',
  // Chinese ratings (kept in sync with signal_taxonomy.py)
  '买入': 'buy',
  '增持': 'buy',
  '加仓': 'buy',
  '做多': 'buy',
  '长多': 'buy',
  '超配': 'buy',
  '卖出': 'sell',
  '减持': 'sell',
  '清仓': 'sell',
  '做空': 'sell',
  '看空': 'sell',
  '避险': 'sell',
  '回避': 'sell',
  '低配': 'sell',
  '持有': 'hold',
  '中性': 'hold',
  '观望': 'watch',
};

// English tokens use word boundaries so "buyback" does not match "buy".
const CONTAINS_EN: [RegExp, SignalAction][] = [
  [/\bbuy(?:s|ing)?\b/, 'buy'],
  [/\boverweight\b/, 'buy'],
  [/\baccumulat\w*/, 'buy'],
  [/\bsell(?:s|ing)?\b/, 'sell'],
  [/\bunderweight\b/, 'sell'],
  [/\bavoid\w*/, 'sell'],
  [/\breduce\b/, 'sell'],
  [/\bhold\w*/, 'hold'],
  [/\bneutral\b/, 'hold'],
  [/\bwatch\w*/, 'watch'],
];

// CJK tokens use substring containment (mirrors signal_taxonomy.py).
const CONTAINS_ZH: [string, SignalAction][] = [
  ['买入', 'buy'],
  ['增持', 'buy'],
  ['加仓', 'buy'],
  ['做多', 'buy'],
  ['长多', 'buy'],
  ['卖出', 'sell'],
  ['减持', 'sell'],
  ['看空', 'sell'],
  ['做空', 'sell'],
  ['清仓', 'sell'],
  ['避险', 'sell'],
  ['持有', 'hold'],
  ['中性', 'hold'],
  ['观望', 'watch'],
];

// Prefix negation → conservative watch ("不建议买入" / "Not Buy" can never
// become a directional signal).
const NEGATION_PREFIX_ZH = ['不', '非', '别', '勿', '莫', '避免', '暂缓'];
const NEGATION_PREFIX_EN = /^(?:not|don'?t|do\s+not|never)\b/;

/**
 * Normalize a free-form recommendation/action string to buy/sell/hold/watch.
 * Unknown or ambiguous input resolves to 'watch' (conservative default,
 * same as the backend).
 */
export function normalizeSignalAction(raw: unknown): SignalAction {
  if (raw == null) return 'watch';
  const normalized = String(raw).trim().toLowerCase();
  if (!normalized) return 'watch';
  if (NEGATION_PREFIX_ZH.some((p) => normalized.startsWith(p))) return 'watch';
  if (NEGATION_PREFIX_EN.test(normalized)) return 'watch';

  const exact = EXACT_ACTIONS[normalized];
  if (exact) return exact;

  const hits = new Set<SignalAction>();
  for (const [pattern, action] of CONTAINS_EN) {
    if (pattern.test(normalized)) hits.add(action);
  }
  for (const [token, action] of CONTAINS_ZH) {
    if (normalized.includes(token)) hits.add(action);
  }
  if (hits.size === 1) return [...hits][0];
  // no hit, or conflicting groups ("buy or sell") → conservative watch
  return 'watch';
}

/**
 * Parse a trading-plan price field into a positive number, or 0 when the value
 * is not a usable absolute price.
 *
 * Hardened rules (replaces the old `parseNum(/[\d.]+/)` that happily read
 * "15%" as a price of 15):
 * - percentages are rejected: "15%", "+15~20%", "-8%"
 * - hedged/qualifier text is rejected: "约26.5", "26.5左右", "市价附近"
 * - range strings take the midpoint: "25.8-26.5" → 26.15 (direction-agnostic
 *   anchor, symmetric for long/short signals)
 * - a plain number with optional unit suffix passes: "26.5", "26.5元"
 */
export function parsePlanPrice(raw: unknown): number {
  if (typeof raw === 'number') {
    return Number.isFinite(raw) && raw > 0 ? raw : 0;
  }
  const s = String(raw ?? '').trim();
  if (!s) return 0;
  if (s.includes('%')) return 0; // percentage, not an absolute price
  if (/约|左右|附近|上下|待定|市价|现价|区间/.test(s)) return 0; // hedged text
  const range = s.match(/(\d+(?:\.\d+)?)\s*[-–~至]\s*(\d+(?:\.\d+)?)/);
  if (range) {
    const lo = parseFloat(range[1]);
    const hi = parseFloat(range[2]);
    if (lo > 0 && hi > 0 && hi >= lo) return (lo + hi) / 2;
    return 0;
  }
  const match = s.match(/(\d+(?:\.\d+)?)/);
  if (!match) return 0;
  const value = parseFloat(match[1]);
  return value > 0 ? value : 0;
}

/**
 * Resolve the entry price of a trading plan.
 *
 * Priority (per the backend `_extract_structured_fields` contract):
 * 1. `tradingPlan.entryPrice` — numeric string written by the new backend
 *    extraction (ranges like "25.8-26.5" fall back to the midpoint rule
 *    inside parsePlanPrice);
 * 2. `tradingPlan.entryLow` / `entryHigh` — explicit range fields, midpoint.
 *    Midpoint (rather than a conservative end) because the entry price acts
 *    as a monitoring anchor (entry ±2% zone) in the signal center: it must
 *    be direction-agnostic and must not depend on the reliability of the
 *    action label for legacy data.
 * 3. 0 — missing; the caller must refuse to fabricate.
 */
export function resolvePlanEntry(plan: Partial<TradingPlan> | null | undefined): number {
  const direct = parsePlanPrice(plan?.entryPrice);
  if (direct > 0) return direct;
  const lo = parsePlanPrice(plan?.entryLow);
  const hi = parsePlanPrice(plan?.entryHigh);
  if (lo > 0 && hi > 0) return (lo + hi) / 2;
  if (lo > 0) return lo;
  if (hi > 0) return hi;
  return 0;
}

/**
 * Resolve trade direction for a stored alert.
 *
 * Explicit action wins ('sell' → short, 'buy' → long). hold/watch signals and
 * legacy rows without an action fall back to the price-geometry heuristic
 * (target < entry ⇒ short) — the exact same fallback the backend
 * signal_monitor_service uses, so frontend badges and Feishu notifications
 * never disagree.
 */
export function alertIsShort(alert: {
  action?: SignalAction;
  target_price: number;
  entry_price: number;
}): boolean {
  if (alert.action === 'sell') return true;
  if (alert.action === 'buy') return false;
  return alert.target_price > 0 && alert.entry_price > 0 && alert.target_price < alert.entry_price;
}

export interface SignalAlertDraft {
  symbol: string;
  name: string;
  market: Market;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  currency: string;
  action: SignalAction;
}

export type SignalAlertBuild =
  | { ok: true; draft: SignalAlertDraft }
  | { ok: false; reason: string };

/**
 * Build a SearchAlert create-payload from a StockAnalysis without ever
 * fabricating prices (regression: a Sell plan without entry prices used to be
 * silently turned into a long signal with +15% target / -8% stop).
 *
 * Rules:
 * - target/stop are the monitoring lines — without them there is nothing to
 *   watch, refuse.
 * - buy/sell signals must anchor on a real entry level; refuse when missing.
 * - hold/watch signals may use the live price as a *tracking anchor* (the
 *   signal center is a monitor, not an order ticket) — the action badge makes
 *   the semantics explicit, and the live price is real market data, not a
 *   fabricated plan level.
 */
export function buildSignalAlertFromAnalysis(analysis: StockAnalysis): SignalAlertBuild {
  const info = analysis.stockInfo;
  if (!info) return { ok: false, reason: '缺少股票信息，无法加入信号中心' };

  const plan: Partial<TradingPlan> = analysis.tradingPlan ?? {};
  // Explicit structured action wins; derive from recommendation otherwise
  // (frontend-direct Gemini path has no tradingPlan.action field).
  const action = normalizeSignalAction(plan.action ?? analysis.recommendation);

  const entry = resolvePlanEntry(plan);
  const target = parsePlanPrice(plan.targetPrice);
  const stop = parsePlanPrice(plan.stopLoss);
  const currentPrice = info.price || 0;

  if (target <= 0) return { ok: false, reason: '交易计划缺少有效的目标价，无法加入信号中心' };
  if (stop <= 0) return { ok: false, reason: '交易计划缺少有效的止损价，无法加入信号中心' };

  let entryPrice = entry;
  if (entryPrice <= 0) {
    if (action === 'buy' || action === 'sell') {
      return { ok: false, reason: '交易计划缺少入场价，无法加入信号中心' };
    }
    if (currentPrice <= 0) {
      return { ok: false, reason: '交易计划缺少入场价且无最新行情，无法加入信号中心' };
    }
    entryPrice = currentPrice;
  }

  return {
    ok: true,
    draft: {
      symbol: info.symbol,
      name: info.name,
      market: info.market,
      entry_price: entryPrice,
      target_price: target,
      stop_loss: stop,
      currency: info.currency || 'CNY',
      action,
    },
  };
}
