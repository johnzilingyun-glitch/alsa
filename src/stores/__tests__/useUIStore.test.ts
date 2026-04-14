import { describe, it, expect, beforeEach } from 'vitest';
import { useUIStore, selectLoading, selectIsChatting, selectIsDiscussing, selectIsReviewing, selectIsBusy } from '../../stores/useUIStore';

describe('useUIStore', () => {
  beforeEach(() => {
    useUIStore.setState({
      analysisActivity: 'idle',
      overviewLoading: false,
      isGeneratingReport: false,
      isSendingReport: false,
      isTriggeringReport: false,
      showDiscussion: false,
      isSettingsOpen: false,
      showAdminPanel: false,
      selectedDetail: null,
      analysisError: null,
      chatError: null,
      overviewError: null,
      reportStatus: 'idle',
      autoRefreshInterval: 0,
    });
  });

  describe('activity state transitions (mutually exclusive)', () => {
    it('should set loading → analyzing', () => {
      useUIStore.getState().setLoading(true);
      expect(useUIStore.getState().analysisActivity).toBe('analyzing');
    });

    it('should clear loading → idle', () => {
      useUIStore.getState().setLoading(true);
      useUIStore.getState().setLoading(false);
      expect(useUIStore.getState().analysisActivity).toBe('idle');
    });

    it('should not clear loading if current activity is not analyzing', () => {
      useUIStore.getState().setIsChatting(true);
      useUIStore.getState().setLoading(false); // should not change chatting to idle
      expect(useUIStore.getState().analysisActivity).toBe('chatting');
    });

    it('should set chatting', () => {
      useUIStore.getState().setIsChatting(true);
      expect(useUIStore.getState().analysisActivity).toBe('chatting');
    });

    it('should set discussing', () => {
      useUIStore.getState().setIsDiscussing(true);
      expect(useUIStore.getState().analysisActivity).toBe('discussing');
    });

    it('should set reviewing', () => {
      useUIStore.getState().setIsReviewing(true);
      expect(useUIStore.getState().analysisActivity).toBe('reviewing');
    });
  });

  describe('independent async operations (concurrent)', () => {
    it('should allow overviewLoading concurrent with main activity', () => {
      useUIStore.getState().setIsChatting(true);
      useUIStore.getState().setOverviewLoading(true);
      const state = useUIStore.getState();
      expect(state.analysisActivity).toBe('chatting');
      expect(state.overviewLoading).toBe(true);
    });

    it('should allow report generation concurrent with main activity', () => {
      useUIStore.getState().setIsDiscussing(true);
      useUIStore.getState().setIsGeneratingReport(true);
      const state = useUIStore.getState();
      expect(state.analysisActivity).toBe('discussing');
      expect(state.isGeneratingReport).toBe(true);
    });
  });

  describe('error states', () => {
    it('should set and clear analysis error', () => {
      useUIStore.getState().setAnalysisError('请求失败');
      expect(useUIStore.getState().analysisError).toBe('请求失败');
    });

    it('should set chat error', () => {
      useUIStore.getState().setChatError('AI 无响应');
      expect(useUIStore.getState().chatError).toBe('AI 无响应');
    });

    it('should set overview error', () => {
      useUIStore.getState().setOverviewError('超时');
      expect(useUIStore.getState().overviewError).toBe('超时');
    });

    it('should reset all errors', () => {
      useUIStore.getState().setAnalysisError('err1');
      useUIStore.getState().setChatError('err2');
      useUIStore.getState().setOverviewError('err3');
      useUIStore.getState().resetErrors();

      const state = useUIStore.getState();
      expect(state.analysisError).toBeNull();
      expect(state.chatError).toBeNull();
      expect(state.overviewError).toBeNull();
    });

    it('should set report status', () => {
      useUIStore.getState().setReportStatus('success');
      expect(useUIStore.getState().reportStatus).toBe('success');
    });
  });

  describe('panel states', () => {
    it('should toggle discussion panel', () => {
      useUIStore.getState().setShowDiscussion(true);
      expect(useUIStore.getState().showDiscussion).toBe(true);
    });

    it('should toggle settings modal', () => {
      useUIStore.getState().setIsSettingsOpen(true);
      expect(useUIStore.getState().isSettingsOpen).toBe(true);
    });

    it('should toggle admin panel', () => {
      useUIStore.getState().setShowAdminPanel(true);
      expect(useUIStore.getState().showAdminPanel).toBe(true);
    });

    it('should set selected detail', () => {
      useUIStore.getState().setSelectedDetail({ type: 'history', data: { id: '123' } });
      expect(useUIStore.getState().selectedDetail?.type).toBe('history');
    });
  });

  describe('derived selectors', () => {
    it('selectLoading should return true when analyzing', () => {
      useUIStore.setState({ analysisActivity: 'analyzing' });
      expect(selectLoading(useUIStore.getState())).toBe(true);
    });

    it('selectLoading should return false when idle', () => {
      expect(selectLoading(useUIStore.getState())).toBe(false);
    });

    it('selectIsChatting should return true when chatting', () => {
      useUIStore.setState({ analysisActivity: 'chatting' });
      expect(selectIsChatting(useUIStore.getState())).toBe(true);
    });

    it('selectIsDiscussing should return true when discussing', () => {
      useUIStore.setState({ analysisActivity: 'discussing' });
      expect(selectIsDiscussing(useUIStore.getState())).toBe(true);
    });

    it('selectIsReviewing should return true when reviewing', () => {
      useUIStore.setState({ analysisActivity: 'reviewing' });
      expect(selectIsReviewing(useUIStore.getState())).toBe(true);
    });

    it('selectIsBusy should return true when activity is not idle', () => {
      useUIStore.setState({ analysisActivity: 'analyzing' });
      expect(selectIsBusy(useUIStore.getState())).toBe(true);
    });

    it('selectIsBusy should return true when overviewLoading', () => {
      useUIStore.setState({ analysisActivity: 'idle', overviewLoading: true });
      expect(selectIsBusy(useUIStore.getState())).toBe(true);
    });

    it('selectIsBusy should return true when generating report', () => {
      useUIStore.setState({ analysisActivity: 'idle', isGeneratingReport: true });
      expect(selectIsBusy(useUIStore.getState())).toBe(true);
    });

    it('selectIsBusy should return false when all idle', () => {
      useUIStore.setState({ analysisActivity: 'idle', overviewLoading: false, isGeneratingReport: false });
      expect(selectIsBusy(useUIStore.getState())).toBe(false);
    });
  });
});
