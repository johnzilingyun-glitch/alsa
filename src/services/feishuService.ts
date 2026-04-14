import { StockAnalysis, AgentDiscussion } from "../types";
import { useDiscussionStore } from "../stores/useDiscussionStore";

function cleanMarkdown(text: string): string {
  if (!text) return "";
  // Remove # headers and other unwanted markdown symbols that might break Feishu card layout
  return text.replace(/#+/g, "").replace(/>/g, "").replace(/^- /gm, "• ").trim();
}

export async function sendAnalysisToFeishu(analysis: StockAnalysis, webhookUrl: string, discussion?: AgentDiscussion): Promise<boolean> {
  if (!webhookUrl) {
    console.error("Feishu Webhook URL is missing");
    return false;
  }

  const ratingColor = analysis.recommendation?.includes("Buy") ? "green" : 
                      analysis.recommendation?.includes("Sell") ? "red" : "orange";

  // Pull additional data from store if not in analysis object
  const discussionStore = useDiscussionStore.getState();
  const controversialPoints = analysis.controversialPoints || discussion?.controversialPoints || discussionStore.controversialPoints;
  const discussionMessages = analysis.discussion || discussion?.messages || discussionStore.discussionMessages;

  const elements: any[] = [
    {
      tag: "div",
      fields: [
        {
          is_short: true,
          text: {
            content: `**当前价格**\n${analysis.stockInfo.price} ${analysis.stockInfo.currency}`,
            tag: "lark_md"
          }
        },
        {
          is_short: true,
          text: {
            content: `**今日涨跌**\n${analysis.stockInfo.change > 0 ? "📈" : "📉"} ${analysis.stockInfo.change} (${analysis.stockInfo.changePercent}%)`,
            tag: "lark_md"
          }
        }
      ]
    },
    {
      tag: "div",
      text: {
        content: `**决策摘要**: ${cleanMarkdown(analysis.finalConclusion || analysis.summary || "未生成摘要")}`,
        tag: "lark_md"
      }
    },
    {
        tag: "div",
        fields: [
          {
            is_short: true,
            text: {
              content: `**数据信度**\n${analysis.dataQuality?.score || 0}% (${analysis.dataQuality?.isStale ? "⚠️ 延时" : "✅ 实时"})`,
              tag: "lark_md"
            }
          },
          {
            is_short: true,
            text: {
              content: `**AI 评分**\n${analysis.score || 0} / 100`,
              tag: "lark_md"
            }
          }
        ]
    }
  ];

  // 1. AI Core Views (Consistent formatting for all sections)
  elements.push({ tag: "hr" });
  
  const riskMsg = discussionMessages?.find(m => m.role === "Risk Manager");
  const riskView = riskMsg?.content || "见风险提示模块";

  const viewsContent = [
    `🧠 **AI 核心观点摘要**`,
    `**技术面分析**:\n${cleanMarkdown(analysis.technicalAnalysis)}`,
    `**基本面分析**:\n${cleanMarkdown(analysis.fundamentalAnalysis)}`,
    `**风险管理分析**:\n${cleanMarkdown(riskView)}`,
    `**情绪面分析**:\n${cleanMarkdown(analysis.capitalFlow?.marketSentiment || analysis.sentiment || "中性")}`
  ].join('\n\n');

  elements.push({
    tag: "div",
    text: {
      content: viewsContent,
      tag: "lark_md"
    }
  });

  // 2. Discussion Consensus & Disagreement
  if (controversialPoints && controversialPoints.length > 0) {
    elements.push({ tag: "hr" });
    elements.push({
      tag: "div",
      text: {
        content: `🤝 **研讨共识与分歧**\n${controversialPoints.map(p => `• ${cleanMarkdown(p)}`).join('\n')}`,
        tag: "lark_md"
      }
    });
  }

  // 3. Opportunities & Risks
  if ((analysis.keyOpportunities && analysis.keyOpportunities.length > 0) || (analysis.keyRisks && analysis.keyRisks.length > 0)) {
    elements.push({ tag: "hr" });
    let oppRiskContent = `✨ **核心机会与风险提示**\n\n`;
    if (analysis.keyOpportunities && analysis.keyOpportunities.length > 0) {
      oppRiskContent += `**机会**:\n${analysis.keyOpportunities.slice(0, 5).map(o => `• ${cleanMarkdown(o)}`).join('\n')}\n\n`;
    }
    if (analysis.keyRisks && analysis.keyRisks.length > 0) {
      oppRiskContent += `**风险**:\n${analysis.keyRisks.slice(0, 5).map(r => `• ${cleanMarkdown(r)}`).join('\n')}`;
    }
    
    elements.push({
      tag: "div",
      text: {
        content: oppRiskContent,
        tag: "lark_md"
      }
    });
  }

  // 4. Quantified Risks (Risk Matrix)
  if (analysis.quantifiedRisks && analysis.quantifiedRisks.length > 0) {
    const riskContent = analysis.quantifiedRisks.slice(0, 5).map(r => 
      `• **${cleanMarkdown(r.name)}**: 概率 ${r.probability}% | 冲击 ${r.impactPercent}%`
    ).join('\n');
    
    elements.push({
      tag: "div",
      text: {
        content: `📊 **量化风险矩阵**\n${riskContent}`,
        tag: "lark_md"
      }
    });
  }

  // 5. Execution Strategy (Trading Plan)
  elements.push({ tag: "hr" });
  elements.push({
    tag: "div",
    fields: [
      {
        is_short: true,
        text: {
          content: `**建议买入**\n${cleanMarkdown(analysis.tradingPlan?.entryPrice || "N/A")}`,
          tag: "lark_md"
        }
      },
      {
        is_short: true,
        text: {
          content: `**目标/止损**\n${cleanMarkdown(analysis.tradingPlan?.targetPrice || "N/A")} / ${cleanMarkdown(analysis.tradingPlan?.stopLoss || "N/A")}`,
          tag: "lark_md"
        }
      }
    ]
  });

  if (analysis.tradingPlan?.strategy) {
    elements.push({
      tag: "note",
      elements: [{
        content: `策略: ${cleanMarkdown(analysis.tradingPlan.strategy)}`,
        tag: "plain_text"
      }]
    });
  }

  elements.push({
    tag: "hr"
  });
  
  elements.push({
    tag: "note",
    elements: [
      {
        content: `📅 ${new Date().toLocaleString('zh-CN')} | 🤖 TradingAgents 机构决策引擎 | 5-Layer Model`,
        tag: "plain_text"
      }
    ]
  });

  const card = {
    config: { wide_screen_mode: true },
    header: {
      template: ratingColor,
      title: {
        content: `📊 机构联席研判: ${analysis.stockInfo.name} (${analysis.stockInfo.symbol})`,
        tag: "plain_text"
      }
    },
    elements: elements
  };

  try {
    const response = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ msg_type: "interactive", card: card })
    });
    return response.ok;
  } catch (error) {
    console.error("Failed to send to Feishu:", error);
    return false;
  }
}
