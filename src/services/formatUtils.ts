/**
 * Formats commodity data into a Markdown table for AI prompts.
 */
export function formatCommoditiesToMarkdown(data: any[]): string {
  if (!data || data.length === 0) return "No real-time commodity data available.";

  let table = "| 商品种类 | 实时价格 | 24h 涨跌幅 | 单位 | 最后更新 |\n";
  table += "| --- | --- | --- | --- | --- |\n";

  data.forEach(item => {
    const change = item.changePercent > 0 ? `+${item.changePercent}%` : `${item.changePercent}%`;
    const priceStr = item.unit === 'CNY' ? `${item.price} CNY` : `$${item.price}`;
    table += `| ${item.name} (${item.symbol}) | ${priceStr} | ${change} | ${item.unit} | ${item.lastUpdated} |\n`;
  });

  return table;
}

/**
 * Format fund flow amount with appropriate unit based on market.
 * A-Share: 亿元 (100 million CNY)
 * HK-Share: 亿港币 (100 million HKD)
 * US-Share: 百万美元 (million USD)
 */
export function formatFundFlow(value: number | string | undefined | null, market?: string): string {
  if (value === undefined || value === null || value === '') return '---';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (isNaN(num)) return String(value);

  if (market === 'US-Share') {
    const millions = num / 1_000_000;
    return `${millions.toFixed(2)}百万美元`;
  }

  if (market === 'HK-Share') {
    const yi = num / 100_000_000;
    return `${yi.toFixed(2)}亿港币`;
  }

  const yi = num / 100_000_000;
  return `${yi.toFixed(2)}亿元`;
}

/**
 * Replace raw large numbers in AI-generated text with human-readable units.
 * Matches patterns like: (4314664960), 资金4314664960, 净流入 4314664960
 * Only formats numbers >= 10 million (1e7) to avoid touching small numbers like dates or percentages.
 */
export function formatNumbersInText(text: string | undefined | null, market?: string): string {
  if (!text) return text || '';
  const isUS = market === 'US-Share';
  const isHK = market === 'HK-Share';

  return text.replace(/(\d{8,})/g, (match) => {
    const num = parseFloat(match);
    if (isNaN(num) || Math.abs(num) < 1e7) return match;

    if (isUS) {
      const millions = num / 1_000_000;
      return `${millions.toFixed(2)}百万美元`;
    }
    if (isHK) {
      const yi = num / 100_000_000;
      return `${yi.toFixed(2)}亿港币`;
    }
    const yi = num / 100_000_000;
    return `${yi.toFixed(2)}亿元`;
  });
}
