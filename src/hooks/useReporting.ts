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
  const llmConfig = useConfigStore(s => s.config);
  const setIsGeneratingReport = useUIStore(s => s.setIsGeneratingReport);
  const setIsSendingReport = useUIStore(s => s.setIsSendingReport);
  const setReportStatus = useUIStore(s => s.setReportStatus);
  const setIsTriggeringReport = useUIStore(s => s.setIsTriggeringReport);
  const isGeneratingReport = useUIStore(s => s.isGeneratingReport);
  const isSendingReport = useUIStore(s => s.isSendingReport);
  
  const setDailyReport = useMarketStore(s => s.setDailyReport);
  const marketOverviews = useMarketStore(s => s.marketOverviews);
  const overviewMarket = useMarketStore(s => s.overviewMarket);
  
  const analysis = useAnalysisStore(s => s.analysis);
  const chatHistory = useAnalysisStore(s => s.chatHistory);
  
  const discussionMessages = useDiscussionStore(s => s.discussionMessages);
  
  const scenarios = useScenarioStore(s => s.scenarios);
  const backtestResult = useScenarioStore(s => s.backtestResult);

  const sendReport = useCallback(async (report: string, type: string, data?: any) => {
    
    setIsSendingReport(true);
    try {
      const response = await fetch('/api/feishu/send-report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: report,
          type,
          data,
          feishuWebhookUrl: useConfigStore.getState().feishuWebhookUrl
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
      const report = await getDailyReport(marketOverview, llmConfig);
      setDailyReport(report);
      setIsTriggeringReport(false);
      await sendReport(report, 'daily', marketOverview);
    } catch (error) {
      setReportStatus('error');
      setIsTriggeringReport(false);
    }
  }, [marketOverviews, overviewMarket, llmConfig, setIsTriggeringReport, setDailyReport, setReportStatus, sendReport]);

  const handleSendStockReport = useCallback(async () => {
    if (!analysis) return;
    
    setIsSendingReport(true);
    try {
      const success = await sendAnalysisToFeishu(analysis, useConfigStore.getState().feishuWebhookUrl);
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
    
    setIsGeneratingReport(true);
    try {
      const report = await getChatReport(analysis.stockInfo?.name || 'Unknown', chatHistory);
      setIsGeneratingReport(false);
      const success = await sendReport(report, 'chat', { stock: analysis.stockInfo?.name || 'Unknown', history: chatHistory, feishuWebhookUrl: useConfigStore.getState().feishuWebhookUrl });
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
  }, [analysis, chatHistory, llmConfig, setIsGeneratingReport, setReportStatus, sendReport]);

  const handleSendDiscussionReport = useCallback(async () => {
    if (!analysis || discussionMessages.length === 0) return;
    
    setIsSendingReport(true);
    try {
      const success = await sendAnalysisToFeishu(analysis, useConfigStore.getState().feishuWebhookUrl);
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
        ? await getStockReport(item, llmConfig)
        : await getDailyReport(item, llmConfig);
      await sendReport(report, 'history_backup', item);
    } catch (error) {
      setReportStatus('error');
    }
  }, [llmConfig, setReportStatus, sendReport]);

  const handleExportFullReport = useCallback(async () => {
    if (!analysis) return;

    setIsGeneratingReport(true);
    const { lastJobId, cachedReportHtml, cachedReportJobId } = useAnalysisStore.getState();
    const filename = `EquityResearch_${analysis.stockInfo?.symbol}_${new Date().toISOString().split('T')[0]}.html`;

    try {
      // 1) The deep report (深度研报) is already displayed — export that exact
      //    HTML (same style & content, byte-identical) instead of regenerating.
      if (lastJobId && cachedReportJobId === lastJobId && cachedReportHtml) {
        ReportGeneratorService.downloadReport(cachedReportHtml, filename);
        saveReportToDisk(filename, cachedReportHtml);
        void fetch('/api/logs/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            field: 'export_html_report',
            oldValue: 'markdown',
            newValue: 'deep_report_direct',
            description: `直接导出与页面深度研报一致的 HTML: ${analysis.stockInfo?.name}`
          })
        });
        return;
      }

      // 2) Not rendered yet — fetch from the same backend endpoint the 深度研报
      //    view uses. The backend serves its cached report file, so the export
      //    is identical to what would be displayed on screen.
      if (lastJobId) {
        const config = useConfigStore.getState().config;
        const res = await fetch(`/api/analysis/jobs/${lastJobId}/report`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            deepseekApiKey: config.deepseekApiKey || undefined,
          }),
        });
        if (res.ok) {
          const htmlReport = await res.text();
          useAnalysisStore.getState().setCachedReport(lastJobId, htmlReport);
          ReportGeneratorService.downloadReport(htmlReport, filename);
          saveReportToDisk(filename, htmlReport);
          void fetch('/api/logs/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              field: 'export_html_report',
              oldValue: 'markdown',
              newValue: 'deep_report_backend',
              description: `导出与深度研报同源的 HTML (后端渲染): ${analysis.stockInfo?.name}`
            })
          });
          return;
        }
      }

      // 3) No deep report available — never silently export a different
      //    frontend template (that was the source of the style/content mismatch).
      setReportStatus('error');
      useUIStore.getState().showToast('深度研报尚未生成或生成失败，无法导出', 'error');
    } catch (e) {
      console.error('Export HTML failed:', e);
      setReportStatus('error');
      useUIStore.getState().showToast('导出失败，请稍后重试', 'error');
    } finally {
      setIsGeneratingReport(false);
    }
  }, [analysis, setIsGeneratingReport, setReportStatus]);

  /** Save report HTML to local server disk (reports/ directory) */
  const saveReportToDisk = useCallback((filename: string, content: string) => {
    void fetch('/api/reports/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, content }),
    }).then(r => r.json()).then(d => {
      if (d.success) console.log(`[Report] Local backup: ${d.path}`);
      else console.warn('[Report] Local backup failed:', d.error);
    }).catch(e => console.warn('[Report] Local backup error:', e));
  }, []);

  const handleExportPdf = useCallback(async () => {
    if (!analysis) return;
    const { lastJobId, cachedReportHtml, cachedReportJobId } = useAnalysisStore.getState();
    if (!lastJobId) return;

    setIsGeneratingReport(true);
    try {
      const config = useConfigStore.getState().config;
      const res = await fetch(`/api/analysis/jobs/${lastJobId}/export/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deepseekApiKey: config.deepseekApiKey || undefined,
          // Pass the exact deep-report HTML currently on screen so the PDF is
          // converted from the same content (never a regenerated variant).
          html: cachedReportJobId === lastJobId ? cachedReportHtml : undefined,
        }),
      });
      if (!res.ok) throw new Error(`PDF export failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `EquityResearch_${analysis.stockInfo?.symbol}_${new Date().toISOString().split('T')[0]}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('PDF export failed:', e);
      setReportStatus('error');
    } finally {
      setIsGeneratingReport(false);
    }
  }, [analysis, setIsGeneratingReport, setReportStatus]);

  const handleExportShareCard = useCallback(async () => {
    if (!analysis) return;
    const lastJobId = useAnalysisStore.getState().lastJobId;
    if (!lastJobId) return;

    setIsGeneratingReport(true);
    try {
      const res = await fetch(`/api/analysis/jobs/${lastJobId}/export/share-card`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error(`Share card generation failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ShareCard_${analysis.stockInfo?.symbol}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error('Share card generation failed:', e);
      setReportStatus('error');
    } finally {
      setIsGeneratingReport(false);
    }
  }, [analysis, setIsGeneratingReport, setReportStatus]);

  return {
    sendReport,
    handleTriggerDailyReport,
    handleSendStockReport,
    handleSendChatReport,
    handleSendDiscussionReport,
    handleSendHistoryToFeishu,
    handleExportFullReport,
    handleExportPdf,
    handleExportShareCard,
  };
}
