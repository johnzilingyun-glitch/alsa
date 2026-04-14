import { useCallback } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore, selectIsReviewing, selectIsDiscussing } from '../stores/useUIStore';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import { useDiscussionStore } from '../stores/useDiscussionStore';
import { useScenarioStore } from '../stores/useScenarioStore';
import { answerDiscussionQuestion, generateNewConclusion, saveAnalysisToHistory, routeUserQuestion } from '../services/aiService';
import { StockAnalysis, AgentMessage, AgentRole } from '../types';

export function useDiscussion(fetchAdminData: () => Promise<void>) {
  const geminiConfig = useConfigStore(s => s.config);
  const { setIsReviewing } = useUIStore();
  const isReviewing = useUIStore(selectIsReviewing);
  const isDiscussing = useUIStore(selectIsDiscussing);
  const { analysis, setAnalysis } = useAnalysisStore();
  const {
    discussionMessages, setDiscussionMessages,
    setControversialPoints, setTradingPlanHistory,
  } = useDiscussionStore();
  const {
    setScenarios, setSensitivityFactors,
    setVerificationMetrics, setCapitalFlow, setPositionManagement,
    setTimeDimension,
  } = useScenarioStore();

  const handleDiscussionQuestion = useCallback(async (question: string) => {
    if (!analysis || isReviewing || isDiscussing) return;

    setIsReviewing(true);
    const userMsg: AgentMessage = {
      id: `user-q-${Date.now()}`,
      role: "Moderator",
      content: question,
      timestamp: new Date().toISOString(),
      type: "user_question"
    };

    const updatedMessages = [...discussionMessages, userMsg];
    setDiscussionMessages(updatedMessages);

    let selectedRole: AgentRole = 'Professional Reviewer';
    try {
      // Step 1: Route the question to an expert
      selectedRole = await routeUserQuestion(question, analysis, updatedMessages, geminiConfig);
      
      // Step 2: Get the answer from the selected expert
      const answerMsg = await answerDiscussionQuestion(analysis, question, selectedRole, updatedMessages, geminiConfig);
      
      const newMessages = [...updatedMessages, answerMsg];
      setDiscussionMessages(newMessages);

      const finalAnalysis: StockAnalysis = {
        ...analysis,
        discussion: newMessages,
      };
      setAnalysis(finalAnalysis);

      await saveAnalysisToHistory('stock', finalAnalysis);
      void fetchAdminData();
    } catch (err) {
      console.error('Expert failed:', err);
      setDiscussionMessages([...updatedMessages, {
        id: `error-${Date.now()}`,
        role: selectedRole,
        content: `⚠️ ${selectedRole} 暂时无法回答：${err instanceof Error ? err.message : '未知错误'}`,
        timestamp: new Date().toISOString(),
        type: "review"
      }]);
    } finally {
      setIsReviewing(false);
    }
  }, [analysis, isReviewing, isDiscussing, geminiConfig, discussionMessages, setDiscussionMessages, setIsReviewing, setAnalysis, fetchAdminData]);

  const handleGenerateNewConclusion = useCallback(async () => {
    if (!analysis || isReviewing || isDiscussing) return;

    setIsReviewing(true);

    try {
      const { message, finalConclusion } = await generateNewConclusion(analysis, discussionMessages, geminiConfig);
      
      const newMessages = [...discussionMessages, message];
      setDiscussionMessages(newMessages);

      const finalAnalysis: StockAnalysis = {
        ...analysis,
        discussion: newMessages,
        finalConclusion: finalConclusion
      };
      setAnalysis(finalAnalysis);

      await saveAnalysisToHistory('stock', finalAnalysis);
      void fetchAdminData();
    } catch (err) {
      console.error('Chief Strategist failed:', err);
      setDiscussionMessages([...discussionMessages, {
        id: `error-${Date.now()}`,
        role: 'Chief Strategist',
        content: `⚠️ 首席策略师暂时无法总结：${err instanceof Error ? err.message : '未知错误'}`,
        timestamp: new Date().toISOString(),
        type: "review"
      }]);
    } finally {
      setIsReviewing(false);
    }
  }, [analysis, isReviewing, isDiscussing, geminiConfig, discussionMessages, setDiscussionMessages, setIsReviewing, setAnalysis, fetchAdminData]);

  return { handleDiscussionQuestion, handleGenerateNewConclusion };
}
