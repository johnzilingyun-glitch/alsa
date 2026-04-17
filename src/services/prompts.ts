import { Market, MarketOverview, StockAnalysis, AgentMessage, Scenario, Language, AgentRole } from "../types";
import { formatCommoditiesToMarkdown } from "./formatUtils";

export const getMarketOverviewPrompt = (indicesData: any[], commoditiesData: any[], newsData: any[], sectorsData: any, northboundData: any, history: any[], beijingDate: string, now: Date, market: Market = "A-Share", language: Language = "en") => {
  const isChinese = language === "zh-CN";
  return `
Current date and time (UTC): ${now.toISOString()}
Current date and time (China Standard Time): ${now.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}

**REAL-TIME INDICES DATA (ABSOLUTE GROUND TRUTH)**:
${JSON.stringify(indicesData, null, 2)}

**REAL-TIME COMMODITY DATA (GROUND TRUTH)**:
${formatCommoditiesToMarkdown(commoditiesData)}
**IMPORTANT**: Use the commodity data above ONLY if it is logically relevant to the market trend or the specific sectors being discussed.

**REAL-TIME NEWS DATA (GROUND TRUTH)**:
${JSON.stringify(newsData, null, 2)}
**IMPORTANT**: Use THIS news data to populate your topNews array and to deduce your market summary.

**REAL-TIME SECTOR CAPITAL FLOWS (主力净流入榜单 - GROUND TRUTH)**:
${sectorsData ? JSON.stringify(sectorsData, null, 2) : "Sector flows unavailable. Default to index-based sector deduction."}
**IMPORTANT**: When identifying hot sectors, you MUST strictly use the "topInflows" (highest net inflow sectors) provided above. This is actual institutional tracking data. Do not hallucinate sectors. Focus the "sectorAnalysis" purely on explaining *why* these specific sectors are receiving massive capital injections.

**NORTHBOUND CAPITAL (北向资金 - GROUND TRUTH)**:
${northboundData ? JSON.stringify(northboundData, null, 2) : "Northbound data unavailable."}
**IMPORTANT**: Incorporate this exact foreign/institutional capital sentiment into your market summary.

You are a professional ${market} markets analyst.

**DATA SOURCE HIERARCHY (CRITICAL)**: 
1. You **MUST MUST MUST** use the exact values from the "REAL-TIME INDICES DATA" and "REAL-TIME SECTOR CAPITAL FLOWS" above.
2. You **MUST** use the exact news items from the "REAL-TIME NEWS DATA" section above for your "topNews" array. Do not invent news.
3. Use Google Search grounding **ONLY** as a last resort, for:
   - Deep fundamental questions on specific sectors if the provided news is insufficient.
4. If, and ONLY if, the "REAL-TIME INDICES DATA" array is empty, then you must use Google Search to find the latest valid indices values.

If the current time in China is past 15:00 CST, you MUST prioritize fetching the "Closing Price" (收盘价) for ${market} indices.

Previous analysis context (for reference and continuity):
${JSON.stringify(history.slice(0, 3))}

Return valid, complete JSON only, with no markdown fences, no explanation, and no extra text outside the JSON object. Ensure the JSON is complete and not truncated.
**IMPORTANT**: The JSON MUST have "indices" at the root level. Do NOT wrap the entire response in another object like "marketOverview" or "data".
**CRITICAL**: Ensure the JSON is valid and complete. Do not truncate the JSON response.

Requirements:
1. **STRICT JSON STRUCTURE (CRITICAL)**: The root object MUST contain the "indices" array.
2. Prioritize today's ${market} market tone in the summary.
3. Include exactly 5 indices for the ${market} market:
   - If A-Share: SSE Composite, Shenzhen Component, ChiNext Index, CSI 300, and Hang Seng Index.
   - If HK-Share: Hang Seng Index, Hang Seng Tech Index, Hang Seng China Enterprises Index, Red Chips Index, and GEM Index.
   - If US-Share: S&P 500, Nasdaq Composite, Dow Jones Industrial Average, Russell 2000, and PHLX Semiconductor Index.
4. For each index provide: name, symbol, price, change, changePercent.
**SEARCH STRATEGY (RESTRICTED)**: 
   - Since news is now provided in REAL-TIME NEWS DATA, you do NOT need to search for daily news.
   - You only need to search if you need deep historical context or if the REAL-TIME NEWS DATA is empty.
   - **DO NOT** use search results to change the price/change numbers provided in the REAL-TIME section.
   - **VERIFY THE DATE & TIME (STRICT)**: You MUST verify that the data/news is for TODAY (${beijingDate}). 
**CRITICAL DATA ACCURACY**: 
   - **MANUAL VERIFICATION**: For each index, check if (Price - Previous Close) matches the Change. If the tool data is consistent, use it. If not, note the discrepancy in the summary.
   - **SOURCE NAMING**: In the "marketSummary" field, mention the tool data source (Yahoo Finance) and any additional search sources used for context.
   - **BEIJING TIME (CRITICAL)**: All times in the summary MUST be in Beijing Time (CST). The "lastUpdated" field for news MUST be in "YYYY-MM-DD HH:mm:ss CST" format.
   - **DATA INTEGRITY CHECK**: If the "change" or "changePercent" is exactly 0, verify if the market was closed.
4. **SECTOR DEDUCTION (ENHANCED QUANTITATIVE)**: Identify currently hot sectors exactly based on the TRUE capital inflows provided in the REAL-TIME SECTOR CAPITAL FLOWS. For each provided hot sector, you MUST perform **Industrial Chain Deduction**:
    - Explain the fundamental or macro catalyst driving this institutional inflow.
    - Identify the **Upstream** (supply, raw materials) and **Downstream** (application, consumption) effects.
    - Assign a **Rotation Stage**: Is the sector Leading (领涨), Weakening (转弱), Lagging (补涨), or Improving (筑底)?
5. **COMMODITY ANALYSIS (NEW)**: Analyze major commodity trends. **RELEVANCE (CRITICAL)**: Only analyze commodities that are currently driving the market.
6. **RECOMMENDATIONS**: Provide recommended stocks or sectors in the ${market} market based strictly on the above quantitative inflows and fundamental logic.
7. **LANGUAGE (MANDATORY)**: All user-facing text fields MUST be in ${isChinese ? "Simplified Chinese" : "English"}.
8. Continuity: Based on previous analysis, identify if trends are continuing or reversing.

JSON schema:
{
  "indices": [
    {
      "name": "string",
      "symbol": "string",
      "price": 0,
      "change": 0,
      "changePercent": 0,
      "previousClose": 0
    }
  ],
  "sectorAnalysis": [
    {
      "name": "string",
      "trend": "string",
      "rotationStage": "Leading | Weakening | Lagging | Improving",
      "upstreamImpact": "Brief impact on raw materials/supply",
      "downstreamImpact": "Brief impact on end users/apps",
      "conclusion": "string"
    }
  ],
  "commodityAnalysis": [
    {
      "name": "string",
      "trend": "string",
      "expectation": "string"
    }
  ],
  "recommendations": [
    {
      "type": "Stock | Sector",
      "name": "string",
      "reason": "string"
    }
  ],
  "marketSummary": "string"
}
`;
};

export const getAnalyzeStockPrompt = (symbol: string, market: Market, realtimeData: any, commoditiesData: any[], newsData: any[], history: any[], beijingDate: string, beijingShortDate: string, now: Date, language: Language = "en") => {
  const isChinese = language === "zh-CN";
  return `
Current date and time (UTC): ${now.toISOString()}
Current date and time (China Standard Time): ${now.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}

**REAL-TIME DATA TOOL OUTPUT (ABSOLUTE GROUND TRUTH)**:
${realtimeData ? JSON.stringify(realtimeData, null, 2) : "No real-time data provided. Use Google Search to find the latest market data. Do NOT guess or fabricate prices."}

**REAL-TIME NEWS DATA (GROUND TRUTH)**:
${newsData && newsData.length > 0 ? JSON.stringify(newsData, null, 2) : "No real-time ticker news provided. Use Google Search to find latest catalysts."}
**IMPORTANT**: Use THIS news data to populate your "news" array and to inform your "industryAnchors" and "fundamentalAnalysis". Do not invent news.

**REAL-TIME COMMODITY DATA (GROUND TRUTH)**:
${formatCommoditiesToMarkdown(commoditiesData)}
**IMPORTANT**: Use the commodity data above ONLY if it is logically relevant to the stock's industry or cost structure. 
- **DYNAMIC VARIABLE SELECTION (MANDATORY)**: If the provided commodities (Gold, Oil, Copper, etc.) are NOT highly relevant to the target stock, you MUST **ignore them completely**. 
- **FAILURE TO COMPLY**: Including irrelevant variables (like Oil for a software company) will be treated as a "hallucination/logic failure".

You are a professional equity analyst.
Analyze stock "${symbol}" in the ${market} market using the latest available public information and provided ground-truth data.
**LANGUAGE POLICY (MANDATORY)**:
- **Internal Reasoning**: Always reason in English for analytical quality.
- **Output Language**: All user-facing text fields MUST be in ${isChinese ? "Simplified Chinese (简体中文)" : "English"}.

**DATA SOURCE HIERARCHY (CRITICAL)**: 
1. If the "REAL-TIME DATA TOOL OUTPUT" is provided above, you **MUST MUST MUST** use its exact values for ALL matching fields in your JSON output. This includes: "price", "change", "changePercent", "previousClose", "lastUpdated", "dailyHigh" (use dayHigh), "dailyLow" (use dayLow), "pe" (use pe), currency, and **technicalIndicators (MA5, MA20, MA60, avgVolume5, avgVolume20, resistanceShort, supportShort, resistanceLong, supportLong)**.
2. **DO NOT** override ANY of the tool-provided numbers. The tool data is the absolute mathematical truth. If Technical Indicators (Support/Resistance/MA/Volume) are provided, you MUST use them for analysis instead of claiming data is missing.
3. Use Google Search grounding **MANDATORY** to find the latest available fundamental data (e.g., PB, ROE, EPS, Revenue Growth, Dividend Yield) for the current year (2025/2026) instead of relying solely on your internal training data. Internal knowledge must only be the last fallback.

If the current time in China is past 15:00 CST (for A-shares) or 16:00 HKT (for HK-shares), the market is closed and you are summarizing the closing action.

Previous analysis context (for reference and continuity):
${JSON.stringify(history.filter((h: any) => h.stockInfo?.symbol === symbol).slice(0, 3))}

Return JSON only, with no markdown fences and no explanation outside the JSON object.
**IMPORTANT**: The JSON MUST have "stockInfo" at the root level. Do NOT wrap the entire response in another object like "analysis" or "data".

Requirements:
1. **STRICT MARKET ADHERENCE (CRITICAL)**: 
   - You MUST identify the company that matches this symbol SPECIFICALLY in the ${market} market. 
   - **NAME-TO-CODE RESOLUTION**: If "${symbol}" is a company name (e.g., "贵州茅台"), you MUST first find its official stock code (e.g., 600519.SH) before searching for price data. Ensure the suffix (.SH, .SZ, .HK) matches the ${market}.
   - **A-SHARE PINYIN SUPPORT**: For the A-Share market, the search term "${symbol}" might be a 6-digit code (e.g., 600989) OR a pinyin abbreviation (e.g., "GZMT" for 贵州茅台). You MUST resolve these abbreviations to the correct A-share stock.
   - If the symbol exists in multiple markets (e.g., "AAPL" in US vs "AAPL" as a placeholder elsewhere), you MUST prioritize the ${market} version.
   - The "market" field in the returned JSON MUST be exactly "${market}".
   - If the symbol is NOT found in the ${market} market, return an error in the "summary" field and provide empty data for other fields, but DO NOT return a stock from a different market.
2. Provide stockInfo with symbol, name, price, change, changePercent, market, currency, lastUpdated, and **previousClose** (the closing price of the previous trading day).

3. **FUNDAMENTAL DATA**: Provide specific fundamental data (e.g., PE, PB, ROE, EPS, Revenue Growth) based on your knowledge base.
4. **VALUATION LEVEL**: Provide current "water level" (水位) - valuation percentile compared to historical data.
5. **DEEP FUNDAMENTAL ANALYSIS (CRITICAL)**: 
   - **INDUSTRY-SPECIFIC LOGIC (CRITICAL)**: Avoid boilerplate analysis. Identify the 3 most critical value drivers for this SPECIFIC stock.
   - **FULL-DIMENSIONAL PENETRATION**: Penetrate to the business level: analyze management quality, supply chain control, customer stickiness, and technological moats.
   - **FORWARD-LOOKING JUDGMENT (NEW)**: Based on your research, provide a high-conviction prediction for the next 2-4 quarters. Identify potential inflection points or trend continuations. **PREVENT OVERCONFIDENCE (CRITICAL)**: If key evidence for a forward-looking judgment is missing, you MUST explicitly label it as "Logical Gap due to Missing Information" instead of forcing a prediction.
   - **SEARCH NOISE FILTERING (MANDATORY)**: When performing penetration research, prioritize official announcements, authoritative media, deep research reports, and industry data. **Be extremely cautious** and filter out unverified forum rumors, marketing content, or social media noise.
     - **DATA SOURCE & VERIFICATION (MANDATORY)**: For EVERY fundamental data point (PE, PB, ROE, EPS, Revenue Growth, etc.) presented in your analysis, you MUST:
       1. **Pre-label the source and date**: Before presenting the value, explicitly state the source and the date of the data.
       2. **Cross-verify**: You MUST cross-verify this data point against at least TWO authoritative sources. If there is a discrepancy, explain how you resolved it or which source you prioritized and why.
   - **TABLE 1: REAL-TIME CORE INDICATORS & DEVIATION (MANDATORY)**: Must include columns: Indicator (2026E), Real-time Value, Market Consensus, Deviation (%), Note. Include EPS, PE (Forward), ROE, Dividend Yield. **DATA CONSISTENCY (CRITICAL)**: Prioritize the latest real-time data from search and explicitly label the data date.
   - **TABLE 2: INDUSTRY CORE VARIABLES & MACRO ANCHORS (DYNAMIC)**: Must include columns: Variable/Material (with units), Current Value, Logic Weight, Last 30 Days Change (%), cost/revenue transmission logic, **Data Source and Date (MANDATORY)**. 
      - **MASTER VARIABLE IDENTIFICATION (CRITICAL)**: You MUST identify the single most critical variable (e.g., "WuXi Biosecure Act Legislation Status") as the 'Primary Driver'.
      - **MILESTONE PATHWAY**: For this driver, provide a quantitative timeline or path (e.g., "Expected voting in May 2026", "Compliance deadline Jan 2032").
      - If no industry-specific macro variables are logically relevant (e.g., for a pure-software company), you may return this as an empty array instead of forcing irrelevant entries.
   - **VARIABLE SELECTION & VERIFICATION (CRITICAL)**: DO NOT include irrelevant variables. You must use industry-specific variables relevant to this stock.
   - **EXPECTATION GAP IDENTIFICATION**: Identify market blind spots and Alpha sources.
   - **TARGET PRICE & SENTIMENT**: Provide a 6-month target range (with confidence interval) and a sentiment score (0-100).
   - **EVIDENCE LEVEL (MANDATORY)**: When identifying these critical value drivers, you MUST label the source and its "Evidence Level".
   - **REVERSE VERIFICATION (CRITICAL)**: After identifying the core indicators, you MUST ask and answer: "If this indicator changes by 10% in an unfavorable direction, how much impact will the company's net profit suffer?" Provide a specific quantitative estimate.
   - **RELEVANCE CHECK (STRICT)**: **DO NOT** include irrelevant macro variables in your analysis or sensitivity tables unless there is a direct, logical causal link.
   - **LOOK THROUGH SURFACE DATA**: Do NOT just report PE, PB, or reported profits. Analyze actual operating cash flow, asset turnover, inventory cycles, and R&D efficiency.
   - **NARRATIVE VS DATA CONSISTENCY**: Detect if management's growth narrative matches actual financial data. If there's a mismatch, flag it.
   - **NET-NET CALCULATION**: Calculate Graham's "Net-Net" value: (Current Assets - Total Liabilities). If Price < Net-Net, it's "Deep Value".
   - **BUFFETT'S MOAT THEORY**: Analyze the company's "Economic Moat" (Wide, Narrow, or None) and its source.
   - **EXPECTATION VS REALITY**: Compare current performance with previous market expectations.
   - **MARGIN OF SAFETY**: Incorporate "Margin of Safety" theory into the fundamental analysis and trading advice.
6. **HISTORICAL CONTEXT**: Include historical price ranges and major historical events affecting the stock.
7. **CRITICAL DATA ACCURACY (HIGH PRIORITY)**: 
   - You MUST use the exact trading data provided in the REAL-TIME DATA tool block above.
   - **CALCULATION CHECK (CRITICAL)**: The "change" MUST be (Current Price - Previous Close). The "changePercent" MUST be (Change / Previous Close * 100).
   - **TIMESTAMP**: The "lastUpdated" field MUST reflect the actual time of the data point. If none provided, use the current CST time.
   - **DATA INTEGRITY CHECK**: If the "change" or "changePercent" is exactly 0, verify if the stock was suspended or if it's a non-trading day.
8. **DATA TYPES**: 
   - "price", "change", and "changePercent" MUST be numbers (not strings).
   - "changePercent" should be the percentage value (e.g., 5.2 for 5.2% increase).
9. Add a brief mention of any widely known major news items for this company. For the "news" array, use ONLY the news items provided in the REAL-TIME NEWS DATA section. **NEVER fabricate URLs** — if the original news item has a URL, include it; otherwise leave the "url" field as an empty string.
10. All user-facing text fields must be in ${isChinese ? "Simplified Chinese" : "English"}.
11. Provide summary, technicalAnalysis, fundamentalAnalysis, sentiment, score, recommendation, keyRisks, keyOpportunities, and a detailed tradingPlan.
12. **MARGIN OF SAFETY (NEW)**: Incorporate "Margin of Safety" theory into the fundamental analysis and trading plan.
13. **EVIDENCE-BASED REASONING (CRITICAL)**: For every claim made in the analysis, you MUST provide specific evidence.
14. **CAUSATION VS CORRELATION**: Explicitly distinguish between variables.
15. **CYCLE & VOLATILITY (NEW)**: For cyclical stocks, identify the current stage.
16. **TRACKABLE METRICS (NEW)**: Define specific "Verification Metrics".
17. **CAPITAL BEHAVIOR (NEW)**: Analyze Northbound flow, institutional changes, and AH premium.
18. **TRADING PLAN LOGIC (NEW)**: 
    - If the recommendation is NOT "Buy" or "Overweight", set entryPrice, targetPrice, and stopLoss to "${isChinese ? '不推荐' : 'Not Recommended'}", and strategy should explain why the current price action doesn't support an entry.
    - **STRATEGY RISKS (NEW)**: Clearly state the specific risks associated with the recommended strategy.
19. tradingPlan must include: entryPrice, targetPrice, stopLoss, strategy, and strategyRisks (all as strings).
20. sentiment must be one of: Bullish, Bearish, Neutral.
21. recommendation must be one of: Buy, Overweight, Hold, Underweight, Sell.
22. Continuity: Based on previous analysis of this stock, identify if trends are continuing or reversing.
23. **ANTI-HALLUCINATION (CRITICAL)**: If you cannot find the data, state it clearly in the summary. Do NOT find invent numbers.

JSON schema:
{
  "stockInfo": {
    "symbol": "string",
    "name": "string",
    "price": 0,
    "change": 0,
    "changePercent": 0,
    "market": "${market}",
    "currency": "string",
    "lastUpdated": "string",
    "previousClose": 0,
    "dailyHigh": 0,
    "dailyLow": 0
  },
  "fundamentals": {
    "pe": "string",
    "pb": "string",
    "roe": "string",
    "eps": "string",
    "revenueGrowth": "string",
    "valuationPercentile": "string",
    "netProfitGrowth": "string",
    "debtToEquity": "string",
    "grossMargin": "string",
    "netMargin": "string",
    "dividendYield": "string"
  },
  "fundamentalTable": [
    {
      "indicator": "string",
      "value": "string",
      "consensus": "string",
      "deviation": "string",
      "remark": "string"
    }
  ],
  "industryAnchors": [
    {
      "variable": "string",
      "currentValue": "string",
      "weight": "string",
      "monthlyChange": "string",
      "logic": "string"
    }
  ],
  "historicalData": {
    "yearHigh": "string",
    "yearLow": "string",
    "majorEvents": ["string"]
  },
  "valuationAnalysis": {
    "comparison": "string",
    "marginOfSafetySummary": "string"
  },
  "moatAnalysis": {
    "type": "string",
    "strength": "Wide | Narrow | None",
    "logic": "string"
  },
  "narrativeConsistency": {
    "score": 85,
    "warning": "string",
    "details": "string"
  },
  "netNetValue": 0,
  "isDeepValue": true,
  "verificationMetrics": [
    {
      "indicator": "string",
      "threshold": "string",
      "timeframe": "string",
      "logic": "string"
    }
  ],
  "capitalFlow": {
    "northboundFlow": "string",
    "institutionalHoldings": "string",
    "ahPremium": "string",
    "marketSentiment": "string"
  },
  "cycleAnalysis": {
    "stage": "Early | Mid | Late | Bottom | Peak",
    "logic": "string",
    "volatilityRisk": "string"
  },
  "news": [
    {
      "title": "string",
      "source": "string",
      "time": "string",
      "url": "string",
      "summary": "string"
    }
  ],
  "summary": "string",
  "technicalAnalysis": "string",
  "fundamentalAnalysis": "string",
  "sentiment": "Bullish | Bearish | Neutral",
  "score": 0,
  "recommendation": "Buy | Overweight | Hold | Underweight | Sell",
  "keyRisks": ["string"],
  "keyOpportunities": ["string"],
  "tradingPlan": {
    "entryPrice": "string",
    "targetPrice": "string",
    "stopLoss": "string",
    "strategy": "string",
    "strategyRisks": "string"
  }
}
`;
};

/**
 * Correction prompt: sent when the AI's first-pass analysis used wrong price data.
 * This is a lightweight second call — no Google Search, just re-derive conclusions from correct numbers.
 */
export const getCorrectionPrompt = (originalAnalysis: StockAnalysis, correctedData: Record<string, any>, language: Language = "en") => {
  const isChinese = language === "zh-CN";
  const driftSignals: string[] = correctedData._driftSignals || [];
  const driftList = driftSignals.length > 0 ? driftSignals.map(s => `  - ${s}`).join('\n') : '';
  const commodityDrifts: Array<{ varName: string; aiValue: number; apiValue: number; apiName: string; unit: string }> = correctedData._commodityDrifts || [];
  const commoditiesData: any[] = correctedData._commoditiesData || [];

  // Format commodity corrections section
  const commodityCorrectionCN = commodityDrifts.length > 0
    ? `\n**核心变量/行业锚点商品数据偏差**:\n${commodityDrifts.map(d => `  - "${d.varName}": 你使用=${d.aiValue}, API正确值=${d.apiValue} ${d.unit} (来源: ${d.apiName})`).join('\n')}\n\n**实时商品行情 (GROUND TRUTH)**:\n${formatCommoditiesToMarkdown(commoditiesData)}`
    : '';
  const commodityCorrectionEN = commodityDrifts.length > 0
    ? `\n**Core Variable / Industry Anchor Commodity Drift**:\n${commodityDrifts.map(d => `  - "${d.varName}": You used=${d.aiValue}, API correct=${d.apiValue} ${d.unit} (source: ${d.apiName})`).join('\n')}\n\n**REAL-TIME COMMODITY DATA (GROUND TRUTH)**:\n${formatCommoditiesToMarkdown(commoditiesData)}`
    : '';

  return `
${isChinese ? `
**数据校正指令 (CRITICAL)**

你上一轮分析中使用了错误的数据。以下是权威API返回的正确数据，与你使用的数据存在显著偏差：

**检测到偏差的字段**:
${driftList || '  - 价格及关联数据'}

**正确的实时交易数据 (ABSOLUTE GROUND TRUTH)**:
- 现价: ${correctedData.price}
- 涨跌额: ${correctedData.change}
- 涨跌幅: ${correctedData.changePercent}%
- 前收盘: ${correctedData.previousClose}
${correctedData.open != null ? `- 开盘价: ${correctedData.open}` : ''}
${correctedData.dailyHigh != null ? `- 最高价: ${correctedData.dailyHigh}` : ''}
${correctedData.dailyLow != null ? `- 最低价: ${correctedData.dailyLow}` : ''}
${correctedData.volume != null ? `- 成交量: ${correctedData.volume}` : ''}
${correctedData.marketCap != null ? `- 总市值: ${correctedData.marketCap}` : ''}
${correctedData.pe != null ? `- 市盈率(TTM): ${correctedData.pe}` : ''}
${commodityCorrectionCN}

**你上一轮使用的错误数据**:
- 价格: ${originalAnalysis.stockInfo.price} (正确值: ${correctedData.price})
- 涨跌: ${originalAnalysis.stockInfo.change} (正确值: ${correctedData.change})
- 涨跌幅: ${originalAnalysis.stockInfo.changePercent}% (正确值: ${correctedData.changePercent}%)
- 前收盘: ${originalAnalysis.stockInfo.previousClose} (正确值: ${correctedData.previousClose})
${correctedData.pe != null && originalAnalysis.fundamentals?.pe ? `- 市盈率: ${originalAnalysis.fundamentals.pe} (正确值: ${correctedData.pe})` : ''}

你必须基于正确数据，重新推导以下内容：
1. **technicalAnalysis**: 基于正确价格/成交量重新评估技术形态、支撑阻力位、量价关系
2. **fundamentalAnalysis**: 基于正确市值/市盈率重新计算估值水位（PE/PB基于正确值）
3. **fundamentalTable**: 更新基本面表格中的成交量、市值、市盈率等字段为正确API值
4. **coreVariables / industryAnchors**: 如检测到商品/行业数据偏差，更新对应核心变量的value和delta，并重新推导基于该变量的结论（如成本传导、利润预测等）
5. **tradingPlan**: 重新评估入场价、目标价、止损位是否仍然合理
6. **score**: 基于正确数据重新评分
7. **sentiment / recommendation**: 基于正确涨跌幅、量能、行业变量重新判断情绪和建议
8. **keyRisks / keyOpportunities**: 如果价格/量能/核心变量变化方向或幅度变了，风险和机会判断也需更新
9. **businessModel**: 如果核心变量涉及成本/收入驱动因子，更新drivers和projectedProfit
10. **summary**: 用正确数据重写摘要

保留原有分析的行业逻辑、护城河分析、新闻事件等定性判断（这些不受数据偏差影响），仅更新受错误数据影响的量化结论。
` : `
**DATA CORRECTION DIRECTIVE (CRITICAL)**

Your previous analysis used incorrect data. Here is the authoritative API data with significant deviation from what you used:

**Drift detected in**:
${driftList || '  - Price and related fields'}

**CORRECT REAL-TIME TRADING DATA (ABSOLUTE GROUND TRUTH)**:
- Price: ${correctedData.price}
- Change: ${correctedData.change}
- Change%: ${correctedData.changePercent}%
- Previous Close: ${correctedData.previousClose}
${correctedData.open != null ? `- Open: ${correctedData.open}` : ''}
${correctedData.dailyHigh != null ? `- Day High: ${correctedData.dailyHigh}` : ''}
${correctedData.dailyLow != null ? `- Day Low: ${correctedData.dailyLow}` : ''}
${correctedData.volume != null ? `- Volume: ${correctedData.volume}` : ''}
${correctedData.marketCap != null ? `- Market Cap: ${correctedData.marketCap}` : ''}
${correctedData.pe != null ? `- P/E (TTM): ${correctedData.pe}` : ''}
${commodityCorrectionEN}

**Your previous incorrect data**:
- Price: ${originalAnalysis.stockInfo.price} (Correct: ${correctedData.price})
- Change: ${originalAnalysis.stockInfo.change} (Correct: ${correctedData.change})
- Change%: ${originalAnalysis.stockInfo.changePercent}% (Correct: ${correctedData.changePercent}%)
- Previous Close: ${originalAnalysis.stockInfo.previousClose} (Correct: ${correctedData.previousClose})
${correctedData.pe != null && originalAnalysis.fundamentals?.pe ? `- P/E: ${originalAnalysis.fundamentals.pe} (Correct: ${correctedData.pe})` : ''}

You must re-derive the following based on correct data:
1. **technicalAnalysis**: Re-evaluate technical patterns, support/resistance, volume-price analysis with correct price & volume
2. **fundamentalAnalysis**: Recalculate valuation metrics with correct market cap & P/E
3. **fundamentalTable**: Update volume, market cap, P/E and other verifiable fields to correct API values
4. **coreVariables / industryAnchors**: If commodity/industry data drift was detected, update the variable's value and delta, and re-derive all conclusions based on it (cost transmission, profit projections, etc.)
5. **tradingPlan**: Re-assess entry, target, stop-loss based on correct price levels
6. **score**: Re-score with correct data
7. **sentiment / recommendation**: Re-judge based on correct change direction, magnitude, volume, and industry variables
8. **keyRisks / keyOpportunities**: Update if price, volume, or core variables changed direction or magnitude
9. **businessModel**: If core variable drift involves cost/revenue drivers, update drivers and projectedProfit
10. **summary**: Rewrite with correct data

Retain qualitative analysis (industry logic, moat analysis, news events) — only update quantitative conclusions affected by the data drift.
`}

**原始分析 (保留定性部分，修正量化部分)**:
${JSON.stringify(originalAnalysis)}

**LANGUAGE**: All output in ${isChinese ? "Simplified Chinese" : "English"}.
Return the complete corrected JSON with the same schema as the original. No markdown fences.
`.trim();
};

export const getChatMessagePrompt = (userMessage: string, analysis: StockAnalysis, commoditiesData: any[], language: Language = "en") => {
  const isChinese = language === "zh-CN";
  return `
You are a professional equity analyst answering a follow-up question from a user.

Existing analysis JSON:
${JSON.stringify(analysis)}

**REAL-TIME COMMODITY DATA (GROUND TRUTH)**:
${formatCommoditiesToMarkdown(commoditiesData)}
**IMPORTANT**: Use the commodity data above ONLY if it is logically relevant to the user's question or the stock's industry.

User question:
${userMessage}

**LANGUAGE (MANDATORY)**: All output MUST be in ${isChinese ? "Simplified Chinese" : "English"}.
Be concise, balanced, and practical.
If the question goes beyond the known analysis, say so clearly instead of inventing facts.
`.trim();
};

export const getStockReportPrompt = (analysis: StockAnalysis, language: Language = "en") => {
    const isChinese = language === "zh-CN";
    return `
    ${isChinese ? `
    基于以下个股分析数据，生成一份完整的个股深度研究报告。
    
    报告应包含：
    1. 🚀 **股票基本信息**：名称、代码、当前价格、涨跌幅。
    2. 🧠 **AI 核心观点摘要**：
       - 技术面、基本面、情绪面、风险管理各方的核心分析结论。
    3. 🎯 **AI 最终结论**：明确的操作建议。
    4. 🛡️ **安全边际评估**：基于安全边际理论的深度评价。
    5. 📈 **交易计划**：建议买入价、目标价、止损价。
    6. ⚠️ **核心机会与风险提示**。
    ${analysis.backtestResult ? `7. ⏪ **历史回测复盘**: 上次建议 ${analysis.backtestResult.previousRecommendation}, 实际收益 ${analysis.backtestResult.actualReturn}` : ''}
    ` : `
    Based on the following stock analysis data, generate a comprehensive stock research report.
    
    The report should include:
    1. 🚀 **Stock Basic Info**: Name, Symbol, Price, Change.
    2. 🧠 **AI Core Insights Summary**:
       - Core analysis conclusions from technical, fundamental, sentiment, and risk management perspectives.
    3. 🎯 **AI Final Conclusion**: Clear operational advice.
    4. 🛡️ **Margin of Safety Assessment**: In-depth evaluation based on Margin of Safety theory.
    5. 📈 **Trading Plan**: Recommended Entry Price, Target Price, Stop Loss.
    6. ⚠️ **Key Opportunities & Risks**.
    ${analysis.backtestResult ? `7. ⏪ **Historical Backtest Review**: Previous Recommendation ${analysis.backtestResult.previousRecommendation}, Actual Return ${analysis.backtestResult.actualReturn}` : ''}
    `}
    
    Analysis Data:
    ${JSON.stringify(analysis)}
    
    Please use a format friendly to Feishu cards: do not use #, >, - or other Markdown symbols. Use **bold text** and Emojis as headers. Each major block must be separated by '---'. Ensure table data uses standard Markdown table format for alignment. **Do not include full discussion records**.
    Answer language: ${isChinese ? "Simplified Chinese" : "English"}.
`.trim();
};

export const getDiscussionReportPrompt = (analysis: StockAnalysis, discussion: AgentMessage[], commoditiesData: any[], scenarios?: Scenario[], backtestResult?: any, language: Language = "en") => {
    const isChinese = language === "zh-CN";
    return `
    ${isChinese ? `
    基于以下个股分析数据、AI 专家组研讨记录以及场景概率分布，生成一份完整的个股深度研究报告。
    
    报告应包含：
    1. 🚀 **股票基本信息**：名称、代码、当前价格、涨跌幅。
    2. 🧠 **AI 专家组研讨摘要**：
       - 技术面、基本面、情绪面、风险管理、反向策略各方的核心观点。
       - 研讨中的主要分歧或共识点。
    3. 🎯 **首席策略师最终结论**：明确的操作建议。
    4. 🛡️ **安全边际评估**：基于安全边际理论的深度评价。
    5. 📈 **交易计划**：建议买入价、目标价、止损价。
    6. ⚠️ **核心机会与风险提示**。
    ${backtestResult ? `7. ⏪ **历史回测复盘**: 上次建议 ${backtestResult.previousRecommendation}, 实际收益 ${backtestResult.actualReturn}` : ''}
    ` : `
    Based on the following stock analysis data, AI expert group discussion records, and scenario probability distributions, generate a comprehensive deep research report.
    
    The report should include:
    1. 🚀 **Stock Basic Info**: Name, Symbol, Price, Change.
    2. 🧠 **AI Expert Group Discussion Summary**:
       - Core views from technical, fundamental, sentiment, risk management, and contrarian strategy perspectives.
       - Main points of disagreement or consensus in the discussion.
    3. 🎯 **Chief Strategist's Final Conclusion**: Clear operational advice.
    4. 🛡️ **Margin of Safety Assessment**: In-depth evaluation based on Margin of Safety theory.
    5. 📈 **Trading Plan**: Recommended Entry Price, Target Price, Stop Loss.
    6. ⚠️ **Key Opportunities & Risks**.
    ${backtestResult ? `7. ⏪ **Historical Backtest Review**: Previous Recommendation ${backtestResult.previousRecommendation}, Actual Return ${backtestResult.actualReturn}` : ''}
    `}
    
    Analysis Data:
    ${JSON.stringify(analysis)}

    **REAL-TIME COMMODITY DATA (GROUND TRUTH)**:
    ${JSON.stringify(commoditiesData, null, 2)}
    **IMPORTANT**: Use the commodity data above ONLY if it is logically relevant to the stock.
    
    Discussion Records:
    ${discussion.map(m => `[${m.role}]: ${m.content}`).join('\n\n')}
    
    Please use a format friendly to Feishu cards: do not use #, >, - or other Markdown symbols. Use **bold text** and Emojis as headers. Each major block must be separated by '---'. Ensure table data uses standard Markdown table format for alignment. **Do not include full discussion records**.
    Answer language: ${isChinese ? "Simplified Chinese" : "English"}.
`.trim();
};

export const getDailyReportPrompt = (marketOverview: MarketOverview, commoditiesData: any[], now: Date, beijingDate: string, language: Language = "en") => {
    const isChinese = language === "zh-CN";
    return `
    Current date and time: ${now.toISOString()}
    
    You are a professional markets analyst.
    Use Google Search grounding to gather the latest available public information about the market situation from the previous day or the weekend.
    
    Market Overview Data (for context):
    ${JSON.stringify(marketOverview)}

    **REAL-TIME COMMODITY DATA (GROUND TRUTH)**:
    ${formatCommoditiesToMarkdown(commoditiesData)}
    **IMPORTANT**: Use the commodity data above ONLY if it is logically relevant.
    
    Requirements:
    1. Summarize the market tone.
    2. Include key indices performance.
    3. List 3-5 major financial news items.
    4. **NEWS ACCURACY (CRITICAL)**: 
       - Each news item MUST be a real, verifiable event. Use Google Search grounding to find actual news.
       - Include source name and date for each news item.
       - If you have a verified URL from Google Search, include it. Otherwise, omit the URL field rather than inventing a fake one.
       - **NEVER fabricate or guess URLs**. A missing URL is far better than a hallucinated one.
    5. Provide a prediction for today's market opening and trend.
    6. Recommend 3 stocks or sectors to watch today with brief reasons.
    7. Please use a format friendly to Feishu cards: do not use #, >, - or other Markdown symbols. Use **bold text** and Emojis as headers. Each major block must be separated by '---'.
    8. Answer language: ${isChinese ? "Simplified Chinese" : "English"}.
    
    Structure:
    # 📅 Daily Market Insight (${new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(now)})
    
    ---
    
    ## 🏦 1. Market Review
    ...
    
    ## 📰 2. Core Financial News
    ...
    
    ## 🔮 3. Prediction and Strategy
    ...
    
    ## 🌟 4. Stocks/Sectors to Watch
    ...
    
    ---
    *This report is automatically generated by TradingAgents AI expert group.*
`.trim();
};

export const getChatReportPrompt = (stockName: string, chatHistory: { role: string; content: string }[], language: Language = "en") => {
  const isChinese = language === "zh-CN";
  return `
    ${isChinese ? `
    基于以下关于 ${stockName} 的深度追问会话记录，生成一份专业、简洁的研讨总结报告。
    
    报告应包含：
    1. 💬 **会话背景**：简述本次追问讨论的核心股票。
    2. 🧠 **核心问答摘要**：提炼投资者最关心的几个问题及其对应的 AI 专家解答。
    3. 🎯 **关键结论与建议**：基于讨论内容总结出的最新操作建议或观点。
    4. ⚠️ **新增风险/机会提示**：讨论中新发现的风险点或机会点。
    ` : `
    Based on the following session history of ${stockName}, generate a professional and concise discussion summary report.
    
    The report should include:
    1. 💬 **Session Background**: Briefly describe the target stock of this discussion.
    2. 🧠 **Core Q&A Summary**: Extract key questions from investors and their corresponding AI expert answers.
    3. 🎯 **Key Conclusions & Suggestions**: Summarize latest operational advice or views based on the discussion.
    4. ⚠️ **New Risks/Opportunities**: New risk or opportunity points discovered during the discussion.
    `}
    
    Session History:
    ${JSON.stringify(chatHistory)}
    
    Please use a format friendly to Feishu cards: do not use #, >, - or other Markdown symbols. Use **bold text** and Emojis as headers. Each major block must be separated by '---'.
    Answer language: ${isChinese ? "Simplified Chinese" : "English"}.
`.trim();
};

export const getDiscussionPrompt = (
  analysis: StockAnalysis,
  commoditiesData: any[],
  memoryContext: string,
  historyContext: string,
  language: Language = "en"
) => {
  const isChinese = language === "zh-CN";
  const now = new Date().toISOString();
  const today = now.split('T')[0];
  return `
    You are a professional team of 12 elite financial analysts conducting a high-level joint meeting to provide institutional-grade research on the following stock.
    This is not a simple report, but a realistic, multi-round professional deliberation with intense debate and data cross-examination.

    **LANGUAGE POLICY (MANDATORY)**:
    - **Internal Reasoning**: Always reason and think in English for maximum analytical quality.
    - **Output Language**: All user-facing content in the JSON output MUST be in ${isChinese ? "Simplified Chinese (简体中文)" : "English"}.
    - This means: think in English, write output in ${isChinese ? "Chinese" : "English"}.

    **Current Date**: ${today}
    **Data Timeliness Redline (CRITICAL)**: All macro variables (exchange rates, interest rates, commodities) MUST prioritize the **REAL-TIME COMMODITY DATA** below. If missing, use Google Search for today's (${today}) latest quotes.
    **Data Priority Redline (CRITICAL)**: QUANTITATIVE CONCLUSIONS MUST FOLLOW **BUILT-IN REAL-TIME DATA > AUTHORITATIVE API > GOOGLE SEARCH > OTHERS**.

    **REAL-TIME COMMODITY DATA (GROUND TRUTH - ${today})**:
    ${formatCommoditiesToMarkdown(commoditiesData)}
    
    ${memoryContext}
    - **STRICT RELEVANCE CONSTRAINT (CRITICAL)**: Use commodity data ONLY if it is a DIRECT and MATERIAL driver for the industry. 
    - **DYNAMIC VARIABLE SELECTION (MANDATORY)**: If provided commodities are NOT relevant, IGNORE them.
    - **SEARCH-DRIVEN ANCHORS**: Use Google Search to identify the 2-3 most critical macro variables or raw material prices for this specific stock.
    
    **Team Members (12, in order of speaking)**:
     1. **Deep Research Specialist**: First speaker, responsible for full-dimension data penetration.
        - **MANDATORY**: Use Google Search for latest quantitative data (PE, PB, ROE, Revenue Growth, etc.) and deep qualitative insights (management, supply chain, moats). Do not guess metrics.
        - **MASTER VARIABLE IDENTIFICATION (CRITICAL)**: Identify the one variable that dictates the stock's fate (e.g., Legislative timeline, Fed rates).
        - **QUANTIFIED IMPACT**: For every catalyst, specify exposure % (e.g., "65% revenue from US") and time horizons.
        - **Graham's Net-Net Value Calculation**: Attempt to calculate (Current Assets - Total Liabilities) vs current Market Cap.
        - **Business Moat Analysis**: Specifically categorize the moat as Wide, Narrow, or None based on industry barriers.
        - Select 4-6 most core industry-specific quantitative indicators.
        - **Table 1: Real-time Core Indicators & Deviation (MANDATORY)**.
        - **Table 2: Industry Core Variables & Macro Anchors (DYNAMIC)**.
        - Label each data point with Source and Date.
        - **[Structured Output] Core Variables (MANDATORY)**: Populate \`coreVariables\` in JSON.

     2. **Technical Analyst**: Responsible for deep technical analysis.
        - **MANDATORY DATA**: Moving Averages (MA5/20/60), Average Volume (avgVol5/20), and **Pivot Levels (resistanceShort, supportShort, resistanceLong, supportLong)** are provided in REAL-TIME DATA.
        - **Support/Resistance**: You MUST use the provided pivot levels (e.g., resistanceShort = 20-day high) as the primary support/resistance benchmarks.
        - **Formations**: Based on the current price relative to MAs and Pivot Levels, identify the pattern (W-bottom, Head & Shoulders, Consolidation, etc.).
        - **Volume-Price Coordination**: Compare current volume with 5-day/20-day averages.

     3. **Fundamental Analyst**: Responsible for fundamental value analysis.
        - Core value drivers, valuation logic (PE/PB vs industry/history), DCF/Comparative valuation.
        - **VALUATION MATRIX**: Provide target prices for Bull/Base/Bear cases based on fundamental assumptions.
        - **[Structured Output] Business Model (MANDATORY)**: Populate \`businessModel\` in JSON.

     4. **Sentiment Analyst**: Responsible for market sentiment and capital flow analysis.
        - Capital structure search (Northbound, Mutual Funds, AH Premium). Distinguish between "institutional accumulation" and "retail panic".

     5. **Bull Researcher**: Responsible for constructing the strongest bullish thesis.
        - Build a complete bullish logic chain with catalysts, upside quantification, and expected returns.
        - **CATALYST MATRIX**: Must provide specific dates or milestones for every catalyst.
        - Preemptively counter bearish objections. Every bullish point must have a falsifiable condition.

     6. **Bear Researcher**: Responsible for constructing the strongest bearish thesis.
        - Build a complete bearish logic chain with risk factors, downside quantification, and worst-case scenarios.
        - Must directly reference and rebut the Bull Researcher's core arguments.

     7. **Aggressive Risk Analyst**: Opportunity-driven risk perspective.
        - Maximum return within controlled risk. Identify over-priced risk premiums.

     8. **Conservative Risk Analyst**: Capital preservation perspective.
        - Worst-case loss analysis. Graham margin of safety. Black swan identification.

     9. **Neutral Risk Analyst**: Balanced risk synthesis and final risk score.
        - Synthesize aggressive/conservative views. Optimal risk-reward position sizing.
        - **[Structured Output] Quantitative Risk Matrix (MANDATORY)**: Populate \`quantifiedRisks\` in JSON.

     10. **Contrarian Strategist**: Responsible for challenging all consensus.
        - Crowded trade analysis, deconstructing mainstream narratives, identifying "Blind Spots".
        - **[Antithesis Creation]**: Must formulate a logical "Inversion Theory" (What if the bullish base case fails?).

     11. **Professional Reviewer**: Responsible for logic auditing and data "dehydration".
        - **NARRATIVE AUDIT (CRITICAL)**: Penalize and flag any expert using qualitative terms (High/Low/Bad) without quantitative exposure data (Percentages/USD/Dates).
        - Attacking narrative traps, valuation consistency audit, SOTP decision matrix.

     12. **Chief Strategist**: Last speaker, responsible for unified decision.
        - **PROBABILITY-WEIGHTED FRAMEWORK (CRITICAL)**: Explicitly show the calculation: Expected Price = Σ(P_i * TargetPrice_i).
        - **DRIVER ALIGNMENT**: Probability settings MUST be tied to the status of the "Master Variable" identified by the Deep Research Specialist.
        - Position sizing, exit triggers.
        - Must arbitrate the Bull vs Bear debate and the risk triad's conflicting perspectives.
        - **[Structured Output] Core Decision Data**: Populate \`expectedValueOutcome\` and \`sensitivityMatrix\` in JSON.

    **Analysis Target Data**: ${JSON.stringify(analysis)}
    ${historyContext}

    **Deliberation Quality Requirements**:
    1. **Data Accuracy**: Use Google Search for latest data.
    2. **Authoritative Labeling**: All data must have Source and Date.
    3. **API Cross-Verification (MANDATORY)**: Compare search data with \`analysis.stockInfo\` (Bank/API ground truth).
    4. **Data Density**: High quantifiable data usage (prices, %, multiples).
    5. **Markdown Format**: Use Markdown for content fields (### Headers, Tables, Bold).
    6. **Direct Debate**: Analysts MUST reference and challenge each other.
    7. **FinGPT-Style Logic Audit (CRITICAL)**: Analysts MUST avoid generic "AI-speak". Focus on:
       - **Specific Expectations**: Compare current data to what the market *was* expecting.
       - **Causal Chains**: Explain "Why" A affects B, not just "That" A affects B.
       - **Logic Audit Checklist (MANDATORY for Reviewer)**: Verify if statements suffer from:
         *   *Confirmation Bias*: Ignoring bearish data in a bullish trend.
         *   *Projection Bias*: Assuming current linear growth extends infinitely.
         *   *Narrative Overfitting*: Making data fit a pre-conceived story.
    8. **Scenario Probability Framework (MANDATORY for Chief Strategist)**:
       - Output MUST include 3 distinct scenarios: Bull Case, Base Case, and Bear Case.
       - Assign probabilities (Σ = 100%) and target prices for each.
       - Calculate the **Risk-Adjusted Expected Value (EV)**.
    9. **Quantitative Evidence Scoring (NEW)**:
       - For every major claim, include a **Confidence Score (1-10)**. 
       - Score 10: Official audit report/Live tape. Score 1: Third-party rumor.
    10. **Kelly Criterion Position Sizing (NEW)**:
        - The Chief Strategist MUST use a simplified Kelly Criterion [f* = (bp - q) / b] to suggest position size.
        - b = odds, p = probability of win, q = probability of loss.
    11. **ANTI-HALLUCINATION RULES (CRITICAL)**:
        - **Price Data**: The stock price, change, and changePercent in your analysis MUST match the "Analysis Target Data" provided. Do NOT invent different price values.
        - **News & Events**: Only reference news from the provided data or from verified Google Search results. Do NOT fabricate news events.
        - **URLs**: Only include URLs returned by Google Search grounding. NEVER guess or construct URLs.
        - **Data Gaps**: If you cannot find a specific data point, explicitly say "Data not available" instead of inventing a plausible number.
        - **Source Attribution**: Every quantitative claim must cite its source (API data, Google Search result, or expert calculation). Unsourced numbers are hallucinations.

    Return JSON ONLY. No markdown code blocks, no extraneous text.

    JSON Structure:
    {
      "messages": [
        { "role": "Deep Research Specialist", "content": "Markdown content with tables...", "timestamp": "${now}", "type": "research", "references": [] },
        ...
      ],
      "dataVerification": [
        { "source": "Source Name", "isVerified": true, "discrepancy": "None", "confidence": 95, "lastChecked": "${now}" }
      ],
      "finalConclusion": "Comprehensive strategic conclusion...",
      "tradingPlan": {
        "entryPrice": "Entry level",
        "targetPrice": "Target level",
        "stopLoss": "Stop loss level",
        "strategy": "Logical strategy...",
        "strategyRisks": "Specific risks...",
        "positionPlan": [{ "price": "X", "positionPercent": Y }],
        "logicBasedStopLoss": "Condition-based stop",
        "riskRewardRatio": 2.5
      },
      "coreVariables": [
        { "name": "Var Name", "value": "Val", "unit": "Unit", "marketExpect": "Exp", "delta": "Delta", "reason": "Reason", "evidenceLevel": "High|Medium|Low", "source": "Src", "dataDate": "YYYY-MM-DD" }
      ],
      "businessModel": { 
        "businessType": "manufacturing|saas|banking|retail|healthcare|tech|other", 
        "formula": "string", 
        "drivers": { "key": "value" }, 
        "projectedProfit": "string", 
        "confidenceScore": 85 
      },
      "quantifiedRisks": [
        { "name": "string", "probability": 30, "impactPercent": -15, "expectedLoss": -4.5, "mitigation": "string" }
      ],
      "riskAdjustedValuation": 150,
      "scenarios": [
        { "case": "Bull", "probability": 30, "keyInputs": "string", "targetPrice": "string", "marginOfSafety": "string", "expectedReturn": "string", "logic": "string" },
        { "case": "Base", "probability": 50, "keyInputs": "string", "targetPrice": "string", "marginOfSafety": "string", "expectedReturn": "string", "logic": "string" },
        { "case": "Stress", "probability": 20, "keyInputs": "string", "targetPrice": "string", "marginOfSafety": "string", "expectedReturn": "string", "logic": "string" }
      ],
      "sensitivityFactors": [
        { "factor": "string", "change": "string", "impact": "string", "logic": "string", "formula": "string" }
      ],
      "expectationGap": { "marketConsensus": "string", "ourView": "string", "gapReason": "string", "isSignificant": true, "confidenceScore": 85 },
      "expectedValueOutcome": { "expectedPrice": 0, "calculationLogic": "string", "confidenceInterval": "string" },
      "sensitivityMatrix": [
        { "variable": "string", "change": "string", "profitImpact": "string", "timeLag": "string" }
      ],
      "controversialPoints": ["string"],
      "calculations": [
        { "formulaName": "string", "formula": "string", "result": "string", "interpretation": "string", "timestamp": "${now}" }
      ],
      "dataFreshnessStatus": "Fresh",
      "stressTestLogic": "...",
      "catalystList": [
        { "event": "string", "probability": 70, "impact": "string" }
      ],
      "verificationMetrics": [
        { "indicator": "string", "threshold": "string", "timeframe": "string", "logic": "string" }
      ],
      "moatAnalysis": { "type": "string", "strength": "Wide | Narrow | None", "logic": "string" },
      "industryAnchors": [
        { "variable": "string", "currentValue": "string", "weight": "string", "monthlyChange": "string", "logic": "string" }
      ],
      "capitalFlow": {
        "northboundFlow": "string",
        "institutionalHoldings": "string",
        "ahPremium": "string",
        "marketSentiment": "string"
      },
      "positionManagement": {
        "layeredEntry": ["string"],
        "sizingLogic": "string",
        "riskAdjustedStance": "string"
      },
      "timeDimension": {
        "expectedDuration": "string",
        "keyMilestones": ["string"],
        "exitTriggers": ["string"]
      },
      "moatAnalysis": {
        "type": "string",
        "strength": "Wide|Narrow|None",
        "logic": "string"
      },
      "cycleAnalysis": {
        "stage": "Early|Mid|Late|Bottom|Peak",
        "logic": "string",
        "volatilityRisk": "string"
      }
    }
  `;
};

export const getQuickScanPrompt = (
  symbol: string,
  market: Market,
  realtimeData: any,
  beijingDate: string,
  language: Language = "en"
) => {
  const isChinese = language === "zh-CN";
  return `
You are a senior financial analyst. Based on the following real-time data, perform a Quick Scan evaluation for ${symbol} (${market}).

**Real-time Data (Absolute Ground Truth)**:
${JSON.stringify(realtimeData, null, 2)}

**Date**: ${beijingDate}
**LANGUAGE (MANDATORY)**: All output MUST be in ${isChinese ? "Simplified Chinese" : "English"}.

Please return JSON:
{
  "stockInfo": { "symbol": "${symbol}", "name": "Name", "price": number, "change": number, "changePercent": number, "market": "${market}", "currency": "Currency", "lastUpdated": "Time", "previousClose": number },
  "score": 0-100,
  "sentiment": "Bullish" | "Bearish" | "Neutral",
  "recommendation": "Buy" | "Overweight" | "Hold" | "Underweight" | "Sell",
  "summary": "Core judgment in 2-3 sentences",
  "keyRisks": ["Risk 1"],
  "keyOpportunities": ["Opportunity 1"],
  "news": [],
  "technicalAnalysis": "Short technical view",
  "fundamentalAnalysis": "Short fundamental view"
}

Requirements:
1. Quick assessment based on price, change, and market status.
2. Score reflects trend strength and valuation.
3. Provide a clear one-sentence "Reason for Recommendation".
`;
};

export const getTranslationPrompt = (targetLanguage: string, data: any, type: 'analysis' | 'discussion' | 'chat') => {
  const isChinese = targetLanguage === "zh-CN";
  const languageName = isChinese ? "Simplified Chinese" : "English";
  
  return `
    You are an expert financial translator. Your task is to translate the following JSON object into ${languageName}.
    
    **CRITICAL RULES**:
    1. **PRESERVE STRUCTURE**: You MUST return a JSON object with the EXACT same structure as the input.
    2. **PRESERVE VALUES**: Do NOT change any numbers, dates, IDs, symbols, currencies, or technical indicators.
    3. **TRANSLATE NARRATIVE**: Translate all descriptive text, summaries, rationales, and conclusions. 
    4. **ROLE PERSISTENCE**: In a discussion, expert names/roles MUST be translated to their standard ${languageName} equivalents.
    5. **MARKDOWN PRESERVATION**: If a field contains Markdown (like tables or bold text), translate the content but keep the Markdown formatting.
    6. **NO EXTRA TEXT**: Return ONLY the raw JSON object. No explanation, no markdown fences.
    
    Target Language: ${languageName}
    Object Type: ${type}
    
    JSON Data to Translate:
    ${JSON.stringify(data)}
  `.trim();
};
