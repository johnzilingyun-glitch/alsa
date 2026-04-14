import { useCallback } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore } from '../stores/useUIStore';
import { useMarketStore } from '../stores/useMarketStore';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';
import { useScenarioStore } from '../stores/useScenarioStore';
import { getStockReport, getChatReport, getDiscussionReport, getDailyReport } from '../services/aiService';
import { sendAnalysisToFeishu } from '../services/feishuService';

export function useReporting(fetchAdminData: () => Promise<void>) {
  const geminiConfig = useConfigStore(s => s.config);
  const {
    setIsGeneratingReport, setIsSendingReport, setReportStatus,
    setIsTriggeringReport, isGeneratingReport, isSendingReport,
  } = useUIStore();
  const { setDailyReport } = useMarketStore();
  const marketOverviews = useMarketStore(s => s.marketOverviews);
  const overviewMarket = useMarketStore(s => s.overviewMarket);
  const { analysis, chatHistory } = useAnalysisStore();
  const { discussionMessages } = useDiscussionStore();
  const { scenarios, backtestResult } = useScenarioStore();

  const sendReport = useCallback(async (report: string, type: string, data?: any) => {
    const webhookUrl = useConfigStore.getState().feishuWebhookUrl;
    if (!webhookUrl) {
      useUIStore.getState().setIsSettingsOpen(true);
      throw new Error('请先在设置中配置飞书 Webhook 链接');
    }
    setIsSendingReport(true);
    try {
      const response = await fetch('/api/feishu/send-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: report,
          type,
          data,
          feishuWebhookUrl: webhookUrl
        })
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to send report');
      }
      setReportStatus('success');
      setTimeout(() => setReportStatus('idle'), 3000);
      return true;
    } catch (error) {
      console.error('Report Error:', error);
      setReportStatus('error');
      return false;
    } finally {
      setIsSendingReport(false);
    }
  }, [setIsSendingReport, setReportStatus]);

  const handleTriggerDailyReport = useCallback(async () => {
    const marketOverview = marketOverviews[overviewMarket];
    if (!marketOverview) return;
    setIsTriggeringReport(true);
    try {
      const report = await getDailyReport(marketOverview, geminiConfig);
      setDailyReport(report);
      setIsTriggeringReport(false);
      await sendReport(report, 'daily', marketOverview);
    } catch (error) {
      setReportStatus('error');
      setIsTriggeringReport(false);
    }
  }, [marketOverviews, overviewMarket, geminiConfig, setIsTriggeringReport, setDailyReport, setReportStatus, sendReport]);

  const handleSendStockReport = useCallback(async () => {
    if (!analysis) return;
    const webhookUrl = useConfigStore.getState().feishuWebhookUrl;
    if (!webhookUrl) {
      useUIStore.getState().setIsSettingsOpen(true);
      setReportStatus('error');
      return;
    }
    setIsSendingReport(true);
    try {
      const success = await sendAnalysisToFeishu(analysis, webhookUrl);
      if (success) {
        setReportStatus('success');
        setTimeout(() => setReportStatus('idle'), 3000);
      } else {
        throw new Error('Failed to send to Feishu');
      }
    } catch (error) {
      setReportStatus('error');
    } finally {
      setIsSendingReport(false);
    }
  }, [analysis, setIsSendingReport, setReportStatus]);

  const handleSendChatReport = useCallback(async () => {
    if (!analysis || !chatHistory || chatHistory.length === 0) return;
    const webhookUrl = useConfigStore.getState().feishuWebhookUrl;
    if (!webhookUrl) {
      useUIStore.getState().setIsSettingsOpen(true);
      setReportStatus('error');
      return;
    }
    setIsGeneratingReport(true);
    try {
      const report = await getChatReport(analysis.stockInfo?.name || 'Unknown', chatHistory);
      setIsGeneratingReport(false);
      const success = await sendReport(report, 'chat', { stock: analysis.stockInfo?.name || 'Unknown', history: chatHistory });
      if (success) {
        void fetch('/api/logs/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            field: 'feishu_chat_report',
            oldValue: 'standard_format',
            newValue: 'optimized_markdown',
            description: `成功发送优化后的追问研讨报告: ${analysis.stockInfo?.name}`
          })
        });
      }
    } catch (error) {
      setReportStatus('error');
      setIsGeneratingReport(false);
    }
  }, [analysis, chatHistory, geminiConfig, setIsGeneratingReport, setReportStatus, sendReport]);

  const handleSendDiscussionReport = useCallback(async () => {
    if (!analysis || discussionMessages.length === 0) return;
    const webhookUrl = useConfigStore.getState().feishuWebhookUrl;
    if (!webhookUrl) {
      useUIStore.getState().setIsSettingsOpen(true);
      setReportStatus('error');
      return;
    }
    setIsSendingReport(true);
    try {
      const success = await sendAnalysisToFeishu(analysis, webhookUrl);
      if (success) {
        setReportStatus('success');
        setTimeout(() => setReportStatus('idle'), 3000);
        
        void fetch('/api/logs/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            field: 'feishu_discussion_report',
            oldValue: 'standard_format',
            newValue: 'decoupled_structured_card',
            description: `成功发送解耦后的结构化个股研讨报告: ${analysis.stockInfo?.name}`
          })
        });
      } else {
        throw new Error('Failed to send to Feishu');
      }
    } catch (error) {
      setReportStatus('error');
    } finally {
      setIsSendingReport(false);
    }
  }, [analysis, discussionMessages, setIsSendingReport, setReportStatus]);

  const handleSendHistoryToFeishu = useCallback(async (item: any) => {
    try {
      const report = item.stockInfo
        ? await getStockReport(item, geminiConfig)
        : await getDailyReport(item, geminiConfig);
      await sendReport(report, 'history_backup', item);
    } catch (error) {
      setReportStatus('error');
    }
  }, [geminiConfig, setReportStatus, sendReport]);

  const handleExportFullReport = useCallback(() => {
    if (!analysis) return;

    const date = new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
    const md: string[] = [];

    md.push(`# 📊 ${analysis.stockInfo?.name} (${analysis.stockInfo?.symbol}) 深度研报`);
    md.push(`**生成时间**: ${date} | **市场**: ${analysis.stockInfo?.market} | **现价**: ${analysis.stockInfo?.price} ${analysis.stockInfo?.currency}`);
    md.push(`**评级**: ${analysis.recommendation || '暂无'} | **得分**: ${analysis.score || 0}/100\n`);

    md.push(`## 🎯 核心结论`);
    md.push(`> ${analysis.finalConclusion || analysis.summary}\n`);

    if (analysis.tradingPlan) {
      md.push(`### 📈 交易计划`);
      md.push(`- **买入区间**: ${analysis.tradingPlan.entryPrice}`);
      md.push(`- **目标价**: ${analysis.tradingPlan.targetPrice}`);
      md.push(`- **止损位**: ${analysis.tradingPlan.stopLoss}`);
      md.push(`- **策略**: ${analysis.tradingPlan.strategy}\n`);
    }

    if (analysis.moatAnalysis && analysis.moatAnalysis.strength !== 'None') {
      md.push(`### 🛡️ 护城河分析`);
      md.push(`- **类型**: ${analysis.moatAnalysis.type}`);
      md.push(`- **强度**: ${analysis.moatAnalysis.strength === 'Wide' ? '宽阔' : '狭窄'}`);
      md.push(`- **逻辑**: ${analysis.moatAnalysis.logic}\n`);
    }

    md.push(`## 📖 维度分析`);
    md.push(`### 基本面\n${analysis.fundamentalAnalysis}\n`);
    md.push(`### 技术面\n${analysis.technicalAnalysis}\n`);

    if (discussionMessages && discussionMessages.length > 0) {
      md.push(`---\n## 🎙️ AI 专家组研讨记录`);
      discussionMessages.forEach(msg => {
        md.push(`\n### 🧔 ${msg.role}`);
        md.push(`${msg.content}`);
      });
      md.push(`\n`);
    }

    if (chatHistory.length > 0) {
      md.push(`---\n## 💬 深度追问会话 (Q&A)`);
      chatHistory.forEach(c => {
        if (c.role === 'user') md.push(`\n**🙋 投资人**: ${c.content}`);
        if (c.role === 'ai') md.push(`**🤖 分析师**: ${c.content}`);
      });
      md.push(`\n`);
    }

    const blob = new Blob([md.join('\n')], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `DeepResearch_${analysis.stockInfo?.symbol}_${new Date().toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [analysis, discussionMessages, chatHistory]);

  return {
    sendReport,
    handleTriggerDailyReport,
    handleSendStockReport,
    handleSendChatReport,
    handleSendDiscussionReport,
    handleSendHistoryToFeishu,
    handleExportFullReport,
  };
}
