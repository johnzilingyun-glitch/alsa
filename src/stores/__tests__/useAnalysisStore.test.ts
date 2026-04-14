import { describe, it, expect, beforeEach } from 'vitest';
import { useAnalysisStore } from '../../stores/useAnalysisStore';

describe('useAnalysisStore', () => {
  beforeEach(() => {
    useAnalysisStore.setState({
      symbol: '',
      market: 'A-Share',
      analysis: null,
      chatMessage: '',
      chatHistory: [],
    });
  });

  it('should have correct initial state', () => {
    const state = useAnalysisStore.getState();
    expect(state.symbol).toBe('');
    expect(state.market).toBe('A-Share');
    expect(state.analysis).toBeNull();
    expect(state.chatMessage).toBe('');
    expect(state.chatHistory).toEqual([]);
  });

  it('should set symbol', () => {
    useAnalysisStore.getState().setSymbol('600519');
    expect(useAnalysisStore.getState().symbol).toBe('600519');
  });

  it('should set market', () => {
    useAnalysisStore.getState().setMarket('HK-Share');
    expect(useAnalysisStore.getState().market).toBe('HK-Share');
  });

  it('should set analysis with direct value', () => {
    const analysis = { stockInfo: { symbol: 'AAPL', name: 'Apple', price: 150 } } as any;
    useAnalysisStore.getState().setAnalysis(analysis);
    expect(useAnalysisStore.getState().analysis?.stockInfo.symbol).toBe('AAPL');
  });

  it('should set analysis with updater function', () => {
    const initial = { stockInfo: { symbol: 'AAPL', name: 'Apple', price: 150 }, score: 70 } as any;
    useAnalysisStore.getState().setAnalysis(initial);
    useAnalysisStore.getState().setAnalysis((prev) => prev ? { ...prev, score: 85 } : null);
    expect(useAnalysisStore.getState().analysis?.score).toBe(85);
  });

  it('should set chat message', () => {
    useAnalysisStore.getState().setChatMessage('测试消息');
    expect(useAnalysisStore.getState().chatMessage).toBe('测试消息');
  });

  it('should set chat history with array', () => {
    const history = [{ id: '1', role: 'user' as const, content: 'hello' }];
    useAnalysisStore.getState().setChatHistory(history);
    expect(useAnalysisStore.getState().chatHistory).toHaveLength(1);
  });

  it('should set chat history with updater function', () => {
    useAnalysisStore.getState().setChatHistory([{ id: '1', role: 'user' as const, content: 'hi' }]);
    useAnalysisStore.getState().setChatHistory((prev) => [...prev, { id: '2', role: 'ai' as const, content: 'hello' }]);
    expect(useAnalysisStore.getState().chatHistory).toHaveLength(2);
  });

  it('should reset analysis and chat history', () => {
    useAnalysisStore.getState().setAnalysis({ stockInfo: { symbol: 'X' } } as any);
    useAnalysisStore.getState().setChatHistory([{ id: '1', role: 'user', content: 'x' }]);
    useAnalysisStore.getState().resetAnalysis();
    expect(useAnalysisStore.getState().analysis).toBeNull();
    expect(useAnalysisStore.getState().chatHistory).toEqual([]);
  });
});
