export const TECHNICAL_ANALYST_EXAMPLES_ZH = `
【输出示例 (EXAMPLE OUTPUT)】:
\`\`\`JSON
{
  "content": "当前股价处于 $150.25，位于 20 日均线（$148.50）上方。趋势定性为主升浪阶段。MACD 柱状图持续放大，未见背离信号。",
  "sentiment": "Bullish",
  "coreVariables": [
    {
      "name": "20日均线支撑",
      "value": "148.50",
      "unit": "USD",
      "source": "API实时",
      "dataDate": "2026-04-18"
    }
  ],
  "quantifiedRisks": [
    {
      "name": "高位震荡风险",
      "probability": 20,
      "impactPercent": -5,
      "expectedLoss": -1
    }
  ]
}
\`\`\`
`;

export const CHIEF_STRATEGIST_EXAMPLES_ZH = `
【输出示例 (EXAMPLE OUTPUT)】:
\`\`\`JSON
{
  "content": "综合各专家意见，看多逻辑由于护城河加深及技术面突破而得到增强。下行风险可控。",
  "sentiment": "Strong Buy",
  "tradingPlan": {
    "entryPrice": "150.00-151.00",
    "targetPrice": "175.00",
    "stopLoss": "142.50",
    "riskRewardRatio": 3.5,
    "strategy": "波段做多战略"
  }
}
\`\`\`
`;

export const TECHNICAL_ANALYST_EXAMPLES_EN = `
【EXAMPLE OUTPUT】:
\`\`\`JSON
{
  "content": "Price is at $150.25, above the 20-day MA ($148.50). Uptrend confirmed. MACD histogram expanding.",
  "sentiment": "Bullish",
  "coreVariables": [
    {
      "name": "20-day MA Support",
      "value": "148.50",
      "unit": "USD",
      "source": "API Real-time",
      "dataDate": "2026-04-18"
    }
  ],
  "quantifiedRisks": [{ "name": "Volatility Risk", "probability": 20, "impactPercent": -5, "expectedLoss": -1 }]
}
\`\`\`
`;

export const CHIEF_STRATEGIST_EXAMPLES_EN = `
【EXAMPLE OUTPUT】:
\`\`\`JSON
{
  "content": "Bullish thesis reinforced by moat and technical signals.",
  "sentiment": "Strong Buy",
  "tradingPlan": {
    "entryPrice": "150.00-151.00",
    "targetPrice": "175.00",
    "stopLoss": "142.50",
    "riskRewardRatio": 3.5,
    "strategy": "Swing Buy"
  }
}
\`\`\`
`;
