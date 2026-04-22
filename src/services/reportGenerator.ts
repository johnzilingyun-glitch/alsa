import { StockAnalysis, AgentMessage, Scenario, CoreVariable } from "../types";

/**
 * ReportGeneratorService
 * Generates professional, standalone HTML reports for equity research.
 * Inspired by FinRobot and institutional standards.
 */

export class ReportGeneratorService {
  /**
   * Generates a complete standalone HTML string for a stock analysis.
   */
  public static generateProfessionalHtmlReport(analysis: StockAnalysis, language: 'en' | 'zh-CN' = 'zh-CN'): string {
    const isChinese = language === 'zh-CN';
    const t = (zh: string, en: string) => (isChinese ? zh : en);

    const { stockInfo, fundamentals, summary, scenarios, discussion, finalConclusion, tradingPlan, coreVariables } = analysis;

    // Extract Tagline and Thesis from finalConclusion if possible
    let tagline = analysis.stockInfo.name + " " + t("个股深度研报", "Equity Research Report");
    let thesis = finalConclusion || summary;

    const html = `
<!DOCTYPE html>
<html lang="${language}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${stockInfo.name} (${stockInfo.symbol}) - ${t("深度研究报告", "Research Report")}</title>
    <style>
        :root {
            --primary: #1a365d;
            --secondary: #2c5282;
            --accent: #3182ce;
            --text-main: #1a202c;
            --text-muted: #4a5568;
            --bg-light: #f7fafc;
            --border: #e2e8f0;
            --bull: #e53e3e;
            --bear: #38a169;
            --white: #ffffff;
            --warning: #ed8936;
            --success: #48bb78;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.6;
            color: var(--text-main);
            background-color: #f0f2f5;
            padding: 40px 20px;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: var(--white);
            padding: 50px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.05);
            border-radius: 8px;
        }

        header {
            border-bottom: 2px solid var(--primary);
            padding-bottom: 20px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
        }

        .header-main h1 {
            font-size: 32px;
            color: var(--primary);
            margin-bottom: 5px;
        }

        .header-main .symbol {
            font-size: 18px;
            color: var(--text-muted);
            font-weight: 500;
        }

        .header-meta {
            text-align: right;
            font-size: 14px;
            color: var(--text-muted);
        }

        .header-price {
            font-size: 24px;
            font-weight: 700;
            color: var(--text-main);
        }

        .change-up { color: var(--bull); }
        .change-down { color: var(--bear); }

        .tagline-box {
            background: var(--bg-light);
            border-left: 5px solid var(--accent);
            padding: 20px;
            margin-bottom: 30px;
        }

        .tagline-box h2 {
            font-size: 22px;
            color: var(--secondary);
            margin-bottom: 10px;
        }

        .section-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 30px;
            margin-bottom: 40px;
        }

        h3 {
            font-size: 18px;
            color: var(--primary);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 5px;
            margin-top: 25px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            font-size: 14px;
        }

        th {
            background: var(--bg-light);
            text-align: left;
            padding: 10px;
            border: 1px solid var(--border);
            color: var(--text-muted);
        }

        td {
            padding: 10px;
            border: 1px solid var(--border);
        }

        .metrics-card {
            background: var(--white);
            border: 1px solid var(--border);
            border-radius: 4px;
            padding: 15px;
        }

        .discussion-log {
            background: #fdfdfd;
            border: 1px solid var(--border);
            padding: 20px;
            border-radius: 4px;
            margin-top: 20px;
            max-height: 800px;
            overflow-y: auto;
        }

        .message {
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px dashed var(--border);
        }

        .message:last-child { border-bottom: none; }

        .message-role {
            font-weight: 700;
            font-size: 13px;
            color: var(--accent);
            margin-bottom: 5px;
            display: block;
        }

        .message-content {
            font-size: 14px;
            color: var(--text-main);
        }

        .scenario-container {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 30px;
        }

        .scenario-card {
            border: 1px solid var(--border);
            padding: 15px;
            border-radius: 4px;
            text-align: center;
        }

        .scenario-card.bull { border-top: 4px solid var(--bull); }
        .scenario-card.base { border-top: 4px solid var(--accent); }
        .scenario-card.stress { border-top: 4px solid var(--text-muted); }

        .scenario-prob {
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 5px;
        }

        .scenario-price {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 5px;
        }

        .opp-risk-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }

        .opp-box {
            border-left: 4px solid var(--success);
            padding-left: 15px;
        }

        .risk-box {
            border-left: 4px solid var(--warning);
            padding-left: 15px;
        }

        ul {
            padding-left: 20px;
            font-size: 14px;
        }

        footer {
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
            font-size: 12px;
            color: var(--text-muted);
            text-align: center;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            background: var(--bg-light);
            border: 1px solid var(--border);
        }

        .analysis-text {
            font-size: 15px;
            white-space: pre-wrap;
            margin-bottom: 20px;
            color: var(--text-main);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-main">
                <h1>${stockInfo.name}</h1>
                <span class="symbol">${stockInfo.symbol} | ${stockInfo.market} | ${stockInfo.currency}</span>
            </div>
            <div class="header-meta">
                <div class="header-price">
                    ${stockInfo.price} 
                    <span class="${stockInfo.changePercent > 0 ? 'change-up' : 'change-down'}">
                        (${stockInfo.changePercent > 0 ? '+' : ''}${stockInfo.changePercent}%)
                    </span>
                </div>
                <div>${t("报告生成", "Report Date")}: ${new Date().toLocaleDateString(language)}</div>
            </div>
        </header>

        <section class="tagline-box">
             <h2>${tagline}</h2>
             <div class="analysis-text">${thesis}</div>
        </section>

        <section class="section-grid">
            <div class="main-report">
                <h3>${t("投资机会与核心风险", "Opportunities & Risks")}</h3>
                <div class="opp-risk-container">
                    <div class="opp-box">
                        <h4 style="color:var(--success); margin-bottom:10px;">${t("核心机会", "Key Opportunities")}</h4>
                        <ul>
                            ${analysis.keyOpportunities?.map(opp => `<li>${opp}</li>`).join('') || `<li>${t("未识别显著机会", "No significant opportunities identified")}</li>`}
                        </ul>
                    </div>
                    <div class="risk-box">
                        <h4 style="color:var(--warning); margin-bottom:10px;">${t("关键风险", "Key Risks")}</h4>
                        <ul>
                            ${analysis.keyRisks?.map(risk => `<li>${risk}</li>`).join('') || `<li>${t("未识别显著风险", "No significant risks identified")}</li>`}
                        </ul>
                    </div>
                </div>

                <h3>${t("基本面深度分析", "Fundamental Deep-Dive")}</h3>
                <div class="analysis-text">${analysis.fundamentalAnalysis || t("未提供详细基本面分析", "No detailed fundamental analysis provided")}</div>

                <h3>${t("技术面形态与趋势分析", "Technical Analysis & Trends")}</h3>
                <div class="analysis-text">${analysis.technicalAnalysis || t("未提供详细技术面分析", "No detailed technical analysis provided")}</div>

                <h3>${t("核心财务数据", "Key Financial Indicators")}</h3>
                <table>
                    <thead>
                        <tr>
                            <th>${t("指标", "Indicator")}</th>
                            <th>${t("当前值", "Value")}</th>
                            <th>${t("行业水位/备注", "Benchmarking/Note")}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${[
                            { label: 'PE (TTM)', val: fundamentals?.pe },
                            { label: 'PB', val: fundamentals?.pb },
                            { label: 'ROE', val: fundamentals?.roe },
                            { label: 'EPS', val: fundamentals?.eps },
                            { label: t('营收增长', 'Revenue Growth'), val: fundamentals?.revenueGrowth },
                            { label: t('净利增长', 'Net Profit Growth'), val: fundamentals?.netProfitGrowth },
                            { label: t('毛利率', 'Gross Margin'), val: fundamentals?.grossMargin },
                            { label: t('资产负债率', 'Debt/Equity'), val: fundamentals?.debtToEquity },
                            { label: t('股息率', 'Dividend Yield'), val: fundamentals?.dividendYield },
                        ].filter(item => item.val).map(item => `
                            <tr>
                                <td style="font-weight:600">${item.label}</td>
                                <td>${item.val}</td>
                                <td>${item.label === 'PE (TTM)' ? (fundamentals?.valuationPercentile ? `${t('历史分位', 'Percentile')}: ${fundamentals.valuationPercentile}` : '-') : '-'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>

                <h3>${t("场景模拟与收益概率", "Scenario & ROI Probability")}</h3>
                <div class="scenario-container">
                    ${scenarios?.map((s: Scenario) => `
                        <div class="scenario-card ${s.case === 'Bull' ? 'bull' : s.case === 'Base' ? 'base' : 'stress'}">
                            <div class="scenario-prob">${s.case} (${s.probability}%)</div>
                            <div class="scenario-price">${s.targetPrice}</div>
                            <div style="font-size:11px; color:var(--text-muted); line-height:1.3;">${s.logic}</div>
                        </div>
                    `).join('') || `<p>${t("未生成场景模拟", "No scenario simulation generated")}</p>`}
                </div>
            </div>

            <div class="side-panel">
                <h3>${t("机构级评分", "Institutional Ratings")}</h3>
                <div class="metrics-card">
                    <div style="margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-size:14px; color:var(--text-muted);">${t("综合评分", "Overall")}</span>
                        <span style="font-size:24px; font-weight:800; color:var(--accent);">${analysis.score}</span>
                    </div>
                    <div style="margin-bottom:10px; display:flex; justify-content:space-between;">
                        <span>PE (TTM)</span>
                        <span>${fundamentals?.pe || 'N/A'}</span>
                    </div>
                    <div style="margin-bottom:10px; display:flex; justify-content:space-between;">
                        <span>ROE</span>
                        <span>${fundamentals?.roe || 'N/A'}</span>
                    </div>
                    <div style="margin-bottom:10px; display:flex; justify-content:space-between;">
                        <span>${t("护城河", "Economic Moat")}</span>
                        <span class="badge" style="background:${analysis.moatAnalysis?.strength === 'Wide' ? '#c6f6d5' : '#bee3f8'}">${analysis.moatRating || analysis.moatAnalysis?.strength || 'Narrow'}</span>
                    </div>
                    ${analysis.moatAnalysis ? `<p style="font-size:11px; color:var(--text-muted); margin-top:5px; border-top:1px solid #eee; padding-top:5px;">${analysis.moatAnalysis.logic}</p>` : ''}
                </div>

                <h3>${t("行情数据详情", "Market Quote Details")}</h3>
                <div class="metrics-card">
                    <div style="margin-bottom:8px; display:flex; justify-content:space-between;">
                        <span>${t("昨收", "Prev Close")}</span>
                        <span>${stockInfo.previousClose || 'N/A'}</span>
                    </div>
                    <div style="margin-bottom:8px; display:flex; justify-content:space-between;">
                        <span>${t("当日最高", "Daily High")}</span>
                        <span class="change-up">${stockInfo.dailyHigh || 'N/A'}</span>
                    </div>
                    <div style="margin-bottom:8px; display:flex; justify-content:space-between;">
                        <span>${t("当日最低", "Daily Low")}</span>
                        <span class="change-down">${stockInfo.dailyLow || 'N/A'}</span>
                    </div>
                    <div style="margin-bottom:2px; display:flex; justify-content:space-between; font-size:11px; color:var(--text-muted);">
                        <span>${t("数据更新", "Last Updated")}</span>
                        <span>${new Date(stockInfo.lastUpdated).toLocaleTimeString()}</span>
                    </div>
                </div>

                <h3 style="margin-top:25px">${t("核心变量监测", "Key Variable Monitoring")}</h3>
                <div class="metrics-card">
                    ${coreVariables?.map((v: CoreVariable) => `
                        <div style="margin-bottom:10px; border-bottom:1px solid #f0f0f0; padding-bottom:5px;">
                            <div style="font-size:12px; color:var(--text-muted)">${v.name}</div>
                            <div style="font-size:14px; font-weight:700;">${v.value} ${v.unit} <span style="font-size:11px; color:var(--accent)">(${v.delta})</span></div>
                        </div>
                    `).join('') || `<p style="font-size:12px;">${t("无监测变量", "No variables monitored")}</p>`}
                </div>

                <h3 style="margin-top:25px">${t("交易执行指南", "Trading Execution")}</h3>
                <div class="metrics-card">
                    <p style="margin-bottom:10px;"><strong>${t("评级", "Rating")}:</strong> <span style="color:var(--accent); font-weight:800;">${analysis.recommendation}</span></p>
                    <div style="background:var(--bg-light); padding:12px; border-radius:4px; font-size:13px;">
                        <p style="margin-bottom:5px;"><strong>${t("参考入场", "Entry")}:</strong> ${tradingPlan?.entryPrice || 'N/A'}</p>
                        <p style="margin-bottom:5px;"><strong>${t("参考止盈", "Target")}:</strong> ${tradingPlan?.targetPrice || 'N/A'}</p>
                        <p style="margin-bottom:2px;"><strong>${t("参考止损", "Stop Loss")}:</strong> ${tradingPlan?.stopLoss || 'N/A'}</p>
                    </div>
                    <p style="font-size:12px; color:var(--text-muted); margin-top:10px; line-height:1.4;">${tradingPlan?.strategy || ''}</p>
                </div>
            </div>
        </section>

        <h3>${t("研讨会核心结论与逻辑辩论", "Expert Deliberation & Logic Debate")}</h3>
        <div class="discussion-log">
            ${discussion?.map((m: AgentMessage) => `
                <div class="message">
                    <span class="message-role">${m.role}</span>
                    <div class="message-content">${m.content.replace(/\n/g, '<br>')}</div>
                </div>
            `).join('') || `<p>${t("研讨记录提取失败", "Failed to extract discussion logs")}</p>`}
        </div>

        <footer>
            <p>Generated by ALSA Professional - Institutional Equity Research Pipeline</p>
            <p>${t("本报告仅供参考。投资有风险，入市需谨慎。", "Disclaimer: For information only. Investing involves high risk.")}</p>
        </footer>
    </div>
</body>
</html>
    `;
    return html;
  }

  /**
   * Triggers a browser download of the report.
   */
  public static downloadReport(html: string, filename: string): void {
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }
}
