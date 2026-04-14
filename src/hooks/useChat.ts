import { useCallback } from 'react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore } from '../stores/useUIStore';
import { useAnalysisStore } from '../stores/useAnalysisStore';
import { sendChatMessage, saveAnalysisToHistory } from '../services/aiService';
import { StockAnalysis } from '../types';

export function useChat(fetchAdminData: () => Promise<void>) {
  const geminiConfig = useConfigStore(s => s.config);
  const { setChatError, setIsChatting } = useUIStore();
  const { analysis, setAnalysis, chatMessage, setChatMessage, chatHistory, setChatHistory } = useAnalysisStore();

  const handleChat = useCallback(async (messageOverride?: string) => {
    if (!analysis) return;

    const userMsg = (messageOverride ?? chatMessage).trim();
    if (!userMsg) return;

    setChatMessage('');
    setChatError(null);
    const userMsgId = `user-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    setChatHistory((prev) => [...prev, { id: userMsgId, role: 'user', content: userMsg }]);
    setIsChatting(true);

    try {
      const reply = await sendChatMessage(userMsg, analysis, geminiConfig);
      const aiMsgId = `ai-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
      const aiMsg = { id: aiMsgId, role: 'ai' as const, content: reply || '抱歉，我暂时无法回答这个问题。' };

      setChatHistory((prev) => {
        const hasUserMsg = prev.some(m => m.id === userMsgId);
        const baseHistory = hasUserMsg ? prev : [...prev, { id: userMsgId, role: 'user' as const, content: userMsg }];
        return [...baseHistory, aiMsg];
      });

      setAnalysis((prev) => {
        if (!prev) return null;
        const newHistory = [
          ...(prev.chatHistory || []),
          { id: userMsgId, role: 'user', content: userMsg },
          aiMsg
        ];
        const updatedAnalysis: StockAnalysis = {
          ...prev,
          chatHistory: newHistory as any
        };
        void saveAnalysisToHistory('stock', updatedAnalysis);
        return updatedAnalysis;
      });

      void fetchAdminData();
    } catch (err) {
      console.error(err);
      setChatError(err instanceof Error ? err.message : '对话出错，请稍后重试。');
    } finally {
      setIsChatting(false);
    }
  }, [analysis, chatMessage, geminiConfig, setChatMessage, setChatError, setChatHistory, setIsChatting, setAnalysis, fetchAdminData]);

  return { handleChat };
}
