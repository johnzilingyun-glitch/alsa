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
    if (targetVarNames.has(c.name)) {
      coreVariables.push({
        name: c.name,
        value: c.price,
        unit: c.unit || "",
        marketExpect: "Consistent with benchmark",
        delta: `${c.changePercent > 0 ? '+' : ''}${c.changePercent}%`,
        reason: "Real-time market quote.",
        evidenceLevel: "第三方监控",
        source: "Market API",
        dataDate: today
      });

      industryAnchors.push({
        variable: c.name,
        currentValue: `${c.price} ${c.unit || ""}`,
        weight: "High",
        monthlyChange: `${c.changePercent}%`,
        logic: "Key cost/revenue driver for the sector."
      });
    }
  });

  // 4. Default Macro Anchors (always relevant)
  const macroNames = ["10年期国债收益率", "美元/离岸人民币", "恐慌指数VIX"];
  commodities.forEach(c => {
    if (macroNames.includes(c.name) && !targetVarNames.has(c.name)) {
      coreVariables.push({
        name: c.name,
        value: c.price,
        unit: c.unit || "",
        marketExpect: "Normal",
        delta: `${c.changePercent}%`,
        reason: "Macro anchor sentiment.",
        evidenceLevel: "第三方监控",
        source: "Market API",
        dataDate: today
      });
    }
  });

  return { coreVariables, industryAnchors };
}
