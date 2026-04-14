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
