import { useCallback } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore } from '../stores/useUIStore';
import { useMarketStore } from '../stores/useMarketStore';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';
import { useScenarioStore } from '../stores/useScenarioStore';
import { getStockReport, getChatReport, getDiscussionReport, getDailyReport } from '../services/aiService';
import { sendAnalysisToFeishu } from '../services/feishuService';
import { ReportGeneratorService } from '../services/reportGenerator';

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

    const language = useConfigStore.getState().language === 'en' ? 'en' : 'zh-CN';
    const htmlReport = ReportGeneratorService.generateProfessionalHtmlReport(analysis, language);
    const filename = `EquityResearch_${analysis.stockInfo?.symbol}_${new Date().toISOString().split('T')[0]}.html`;
    
    ReportGeneratorService.downloadReport(htmlReport, filename);
    
    // Log Export
    void fetch('/api/logs/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        field: 'export_html_report',
        oldValue: 'markdown',
        newValue: 'pro_html',
        description: `成功导出专业 HTML 研报: ${analysis.stockInfo?.name}`
      })
    });
  }, [analysis]);

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
