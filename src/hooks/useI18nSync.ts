import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useConfigStore } from '../stores/useConfigStore';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';
import { translateAnalysis } from '../services/analysisService';
import { translateDiscussion } from '../services/discussionService';
import { useUIStore } from '../stores/useUIStore';
import { AgentDiscussion } from '../types';

/**
 * Hook to automatically synchronize AI-generated state with the UI language.
 * When language changes, if there is an active analysis or discussion, 
 * it triggers a translation of that data.
 */
export function useI18nSync() {
  const { i18n } = useTranslation();
  const language = useConfigStore((state) => state.language);
  const { analysis, setAnalysis } = useAnalysisStore();
  const { discussionMessages, setDiscussionResults } = useDiscussionStore();
  const setAnalysisStatus = useUIStore((state) => state.setAnalysisStatus);
  
  // Track previous language to avoid re-translation on mount
  const prevLang = useRef(language);

  useEffect(() => {
    async function syncContent() {
      if (language === prevLang.current) return;
      
      const targetLang = language;
      prevLang.current = language;

      // Sync Analysis
      if (analysis) {
        setAnalysisStatus(targetLang === 'zh-CN' ? "正在同步语言分析..." : "Syncing language content...");
        try {
          const translated = await translateAnalysis(analysis, targetLang);
          setAnalysis(translated);
        } catch (err) {
          console.error(`[i18nSync] Analysis translation failed:`, err);
        } finally {
          setAnalysisStatus('');
        }
      }

      // Sync Discussion
      const hasDiscussion = discussionMessages.length > 0;
      if (hasDiscussion) {
        try {
          // Construct a full discussion object for translation
          const discussionObj: AgentDiscussion = {
             messages: discussionMessages,
             finalConclusion: analysis?.finalConclusion || '',
             coreVariables: Array.from(new Set(discussionMessages.flatMap(m => m.references || []))) as any, // placeholder
             quantifiedRisks: [],
             scenarios: []
          };
          
          const translated = await translateDiscussion(discussionObj, targetLang);
          
          // Full store update
          setDiscussionResults(translated);
          
          // Sync translated conclusion back to analysis if it exists
          if (translated.finalConclusion && analysis) {
            setAnalysis({
              ...analysis,
              finalConclusion: translated.finalConclusion,
              tradingPlan: translated.tradingPlan || analysis.tradingPlan
            });
          }
        } catch (err) {
          console.error(`[i18nSync] Discussion translation failed:`, err);
        }
      }
    }

    syncContent();
  }, [language, analysis?.id, setAnalysis, setDiscussionResults, discussionMessages.length, setAnalysisStatus]);
}
