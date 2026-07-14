import { CoreVariable, IndustryAnchor, StockAnalysis } from "../../types";

/**
 * Anchor Discovery System
 * ────────────────────────
 * Maps stock industries to their Single Source of Truth (SSoT) variables.
 * Automatically extracts relevant commodity prices into the analysis context.
 */

const INDUSTRY_MAP: Record<string, string[]> = {
  "新能源": ["碳酸锂", "光伏级多晶硅", "LME镍", "10年期国债收益率"],
  "锂电池": ["碳酸锂", "LME镍", "LME钴"],
  "光伏": ["光伏级多晶硅", "白银", "10年期国债收益率"],
  "芯片": ["费城半导体指数", "10年期国债收益率", "关键稀有金属"],
  "房地产": ["10年期国债收益率", "螺纹钢", "水泥价格"],
  "贵金属": ["黄金", "白银", "美元指数"],
  "传统能源": ["布伦特原油", "WTI原油", "动力煤"],
  "基础化工": ["原油", "天然气", "纯碱"],
  "黑色金属": ["铁矿石", "螺纹钢", "焦煤"],
  "消费": ["CPI", "恐慌指数VIX", "美元/离岸人民币"],
};

/**
 * Upstream commodities feed (yfinance via /api/market/commodities) returns
 * quotes keyed by ticker symbol with English shortNames (e.g. "GC=F" →
 * "Gold Aug 26", "USDCNY=X" → "USD/CNY"). The anchor names in INDUSTRY_MAP /
 * macroNames below are Chinese ("黄金", "10年期国债收益率", ...), so the two
 * never matched and industryAnchors / coreVariables stayed empty — which is
 * exactly the "30日趋势 / 大宗商品价格 没数据" bug. This map bridges them.
 */
const COMMODITY_NAME_MAP: Record<string, string> = {
  "GC=F": "黄金",
  "CL=F": "WTI原油",
  "USDCNY=X": "美元/离岸人民币",
  "^VIX": "恐慌指数VIX",
  "^TNX": "10年期国债收益率",
  "gold": "黄金",
  "crude oil": "WTI原油",
  "wti": "WTI原油",
  "brent": "布伦特原油",
  "usd/cny": "美元/离岸人民币",
  "usd/cnh": "美元/离岸人民币",
  "cboe volatility index": "恐慌指数VIX",
  "cboe interest rate 10 year": "10年期国债收益率",
};

function resolveCommodityVarName(c: any): string {
  if (c?.symbol && COMMODITY_NAME_MAP[c.symbol]) return COMMODITY_NAME_MAP[c.symbol];
  const lower = (c?.name || "").toString().toLowerCase();
  if (COMMODITY_NAME_MAP[lower]) return COMMODITY_NAME_MAP[lower];
  return c?.name ?? c?.symbol ?? "";
}

export function discoverIndustryAnchors(analysis: Partial<StockAnalysis>, commodities: any[]): { coreVariables: CoreVariable[], industryAnchors: IndustryAnchor[] } {
  const coreVariables: CoreVariable[] = [];
  const industryAnchors: IndustryAnchor[] = [];
  const summary = (analysis.summary || "").toLowerCase();
  const name = (analysis.stockInfo?.name || "").toLowerCase();
  const today = new Date().toISOString().split('T')[0];

  // 1. Identify relevant industries
  const matchedIndustries = Object.keys(INDUSTRY_MAP).filter(industry => 
    summary.includes(industry.toLowerCase()) || name.includes(industry.toLowerCase())
  );

  // 2. Map industries to variable names
  const targetVarNames = new Set<string>();
  matchedIndustries.forEach(ind => {
    INDUSTRY_MAP[ind].forEach(v => targetVarNames.add(v));
  });

  // 3. Match with real-time commodities data
  commodities.forEach(c => {
    const varName = resolveCommodityVarName(c);
    const trend = c.change30d != null ? c.change30d : c.changePercent;
    if (targetVarNames.has(varName)) {
      coreVariables.push({
        name: varName,
        value: c.price,
        unit: c.unit || c.currency || "",
        marketExpect: "Consistent with benchmark",
        delta: `${trend > 0 ? '+' : ''}${trend}%`,
        reason: "Real-time market quote.",
        evidenceLevel: "第三方监控",
        source: "Market API",
        dataDate: today
      });

      industryAnchors.push({
        variable: varName,
        currentValue: `${c.price} ${c.unit || c.currency || ""}`,
        weight: "High",
        monthlyChange: `${trend}%`,
        logic: "Key cost/revenue driver for the sector."
      });
    }
  });

  // 4. Default Macro Anchors (always relevant)
  const macroNames = ["10年期国债收益率", "美元/离岸人民币", "恐慌指数VIX"];
  commodities.forEach(c => {
    const varName = resolveCommodityVarName(c);
    const trend = c.change30d != null ? c.change30d : c.changePercent;
    if (macroNames.includes(varName) && !targetVarNames.has(varName)) {
      coreVariables.push({
        name: varName,
        value: c.price,
        unit: c.unit || c.currency || "",
        marketExpect: "Normal",
        delta: `${trend}%`,
        reason: "Macro anchor sentiment.",
        evidenceLevel: "第三方监控",
        source: "Market API",
        dataDate: today
      });
    }
  });

  return { coreVariables, industryAnchors };
}
