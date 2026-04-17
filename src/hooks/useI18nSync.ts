import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useConfigStore } from '../stores/useConfigStore';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';
import { translateAnalysis } from '../services/analysisService';
import { translateDiscussion } from '../services/discussionService';

/**
 * Hook to automatically synchronize AI-generated state with the UI language.
 * When language changes, if there is an active analysis or discussion, 
 * it triggers a translation of that data.
 */
export function useI18nSync() {
  const { i18n } = useTranslation();
  const language = useConfigStore((state) => state.language);
  const { analysis, setAnalysis } = useAnalysisStore();
  const { discussionMessages, setDiscussionMessages, setDiscussionState } = useDiscussionStore();
  
  // Track previous language to avoid re-translation on mount
  const prevLang = useRef(language);

  useEffect(() => {
    async function syncContent() {
      if (language === prevLang.current) return;
      
      const targetLang = language;
      prevLang.current = language;

      // Sync Analysis
      if (analysis) {
        console.log(`[i18nSync] Translating analysis to ${targetLang}...`);
        try {
          const translated = await translateAnalysis(analysis, targetLang);
          setAnalysis(translated);
        } catch (err) {
          console.error(`[i18nSync] Analysis translation failed:`, err);
        }
      }

      // Sync Discussion
      // Note: For simplicity, we assume if discussionMessages exist, 
      // there is a full state to translate or we just translate the messages.
      // In a more robust system, we would translate the whole discussion object.
      // But we'll try to translate the essential pieces from the core store.
      const hasDiscussion = discussionMessages.length > 0;
      if (hasDiscussion) {
        console.log(`[i18nSync] Translating discussion to ${targetLang}...`);
        try {
          // We construct a partial AgentDiscussion for translation
          // This is a bit complex as discussionStore is fragmented
          // For now, we'll translate the messages if they exist.
          const discussionObj = {
             messages: discussionMessages,
             finalConclusion: '', // We don't have direct access here easily without more state
             coreVariables: [],
             quantifiedRisks: [],
             scenarios: []
          };
          
          const translated = await translateDiscussion(discussionObj as any, targetLang);
          setDiscussionMessages(translated.messages);
        } catch (err) {
          console.error(`[i18nSync] Discussion translation failed:`, err);
        }
      }
    }

    syncContent();
  }, [language, analysis?.id, setAnalysis, setDiscussionMessages]);
}
