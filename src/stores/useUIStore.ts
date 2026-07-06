import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AnalysisLevel } from '../types';

type AnalysisActivity = 'idle' | 'analyzing' | 'chatting' | 'discussing' | 'reviewing';

interface UIState {
  // Main activity (mutually exclusive)
  analysisActivity: AnalysisActivity;

  // Independent async operations (concurrent)
  overviewLoading: boolean;
  isGeneratingReport: boolean;
  isSendingReport: boolean;
  isTriggeringReport: boolean;

  // UI panel states
  showDiscussion: boolean;
  isSettingsOpen: boolean;
  showAdminPanel: boolean;
  showAdminManagement: boolean;
  showIBKRDashboard: boolean;
  showMockTradingDashboard: boolean;
  showBacktestPanel: boolean;
  showPredictionDashboard: boolean;
  showThsAnalysis: boolean;
  selectedDetail: { type: 'log' | 'history', data: any } | null;

  // Error states
  analysisError: string | null;
  chatError: string | null;
  overviewError: string | null;
  reportStatus: 'idle' | 'success' | 'error';
  serviceStatus: 'available' | 'quota_exhausted' | 'error';

  // Global Components
  confirmDialog: {
    isOpen: boolean;
    title: string;
    message: string;
    type: 'danger' | 'warning' | 'info';
    onConfirm: () => void;
  } | null;
  toast: {
    isOpen: boolean;
    message: string;
    type: 'success' | 'error' | 'info';
    id: number;
  } | null;

  // Config
  autoRefreshInterval: number;
  analysisStatus: string;
  analysisLogs: { message: string, timestamp: number }[];
  contentCount: number;
  analysisTarget: { symbol: string; market: string } | null;
  analysisStartedAt: number | null;
  analysisLevel: AnalysisLevel;
  verificationMode: 'extreme' | 'quick' | 'quality';
  setAnalysisStatus: (status: string) => void;
  setVerificationMode: (mode: 'extreme' | 'quick' | 'quality') => void;
  setContentCount: (count: number) => void;
  setAnalysisTarget: (target: { symbol: string; market: string } | null) => void;


  // Activity setters (update enum)
  setLoading: (loading: boolean) => void;
  setIsChatting: (is: boolean) => void;
  setIsDiscussing: (is: boolean) => void;
  setIsReviewing: (is: boolean) => void;

  // Independent async setters
  setOverviewLoading: (loading: boolean) => void;
  setIsGeneratingReport: (is: boolean) => void;
  setIsSendingReport: (is: boolean) => void;
  setIsTriggeringReport: (is: boolean) => void;

  // Error setters
  setOverviewError: (error: string | null) => void;
  setAnalysisError: (error: string | null) => void;
  setChatError: (error: string | null) => void;
  setReportStatus: (status: 'idle' | 'success' | 'error') => void;
  resetErrors: () => void;

  // Panel setters
  setShowDiscussion: (show: boolean) => void;
  setIsSettingsOpen: (open: boolean) => void;
  setShowAdminPanel: (show: boolean) => void;
  setShowAdminManagement: (show: boolean) => void;
  setShowIBKRDashboard: (show: boolean) => void;
  setShowMockTradingDashboard: (show: boolean) => void;
  setShowBacktestPanel: (show: boolean) => void;
  setShowPredictionDashboard: (show: boolean) => void;
  setShowThsAnalysis: (show: boolean) => void;
  setSelectedDetail: (detail: { type: 'log' | 'history', data: any } | null) => void;
  setAutoRefreshInterval: (interval: number) => void;
  setAnalysisLevel: (level: AnalysisLevel) => void;
  setServiceStatus: (status: 'available' | 'quota_exhausted' | 'error') => void;

  // Global Component Actions
  showConfirm: (title: string, message: string, onConfirm: () => void, type?: 'danger' | 'warning' | 'info') => void;
  hideConfirm: () => void;
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void;
  hideToast: () => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      analysisActivity: 'idle',
      overviewLoading: false,
      isGeneratingReport: false,
      isSendingReport: false,
      isTriggeringReport: false,
      showDiscussion: false,
      isSettingsOpen: false,
      showAdminPanel: false,
      showAdminManagement: false,
      showIBKRDashboard: false,
      showMockTradingDashboard: false,
      showBacktestPanel: false,
      showPredictionDashboard: false,
      showThsAnalysis: false,
      selectedDetail: null,
      analysisError: null,
      chatError: null,
      overviewError: null,
      reportStatus: 'idle',
      serviceStatus: 'available',
      autoRefreshInterval: 0,
      analysisLevel: 'standard',
      analysisStatus: '',
      analysisLogs: [],
      contentCount: 0,
      analysisTarget: null,
      analysisStartedAt: null,
      verificationMode: 'quick',
      setContentCount: (contentCount) => set({ contentCount }),
      setAnalysisTarget: (analysisTarget) => set({ analysisTarget }),
      setVerificationMode: (verificationMode) => set({ verificationMode }),
      setAnalysisStatus: (analysisStatus) => set((state) => {
        if (!analysisStatus) return { analysisStatus };
        return {
          analysisStatus,
          analysisLogs: [...state.analysisLogs, { message: analysisStatus, timestamp: Date.now() }]
        };
      }),

      // Activity setters - mutually exclusive via enum
      setLoading: (loading) => set((s) => ({
        analysisActivity: loading ? 'analyzing' : (s.analysisActivity === 'analyzing' ? 'idle' : s.analysisActivity),
        analysisLogs: loading ? s.analysisLogs : [], // clear logs when done
        contentCount: loading ? 0 : s.contentCount,
        analysisStartedAt: loading ? Date.now() : null,
        analysisTarget: loading ? s.analysisTarget : null,
      })),
      setIsChatting: (is) => set((s) => ({
        analysisActivity: is ? 'chatting' : (s.analysisActivity === 'chatting' ? 'idle' : s.analysisActivity),
      })),
      setIsDiscussing: (is) => set((s) => ({
        analysisActivity: is ? 'discussing' : (s.analysisActivity === 'discussing' ? 'idle' : s.analysisActivity),
      })),
      setIsReviewing: (is) => set((s) => ({
        analysisActivity: is ? 'reviewing' : (s.analysisActivity === 'reviewing' ? 'idle' : s.analysisActivity),
      })),

      // Independent async setters
      setOverviewLoading: (overviewLoading) => set({ overviewLoading }),
      setIsGeneratingReport: (isGeneratingReport) => set({ isGeneratingReport }),
      setIsSendingReport: (isSendingReport) => set({ isSendingReport }),
      setIsTriggeringReport: (isTriggeringReport) => set({ isTriggeringReport }),

      // Error setters
      setOverviewError: (overviewError) => set({ overviewError }),
      setAnalysisError: (analysisError) => set({ analysisError }),
      setChatError: (chatError) => set({ chatError }),
      setReportStatus: (reportStatus) => set({ reportStatus }),
      resetErrors: () => set({
        overviewError: null,
        analysisError: null,
        chatError: null,
      }),

      // Panel setters
      setShowDiscussion: (showDiscussion) => set({ showDiscussion }),
      setIsSettingsOpen: (isSettingsOpen) => set({ isSettingsOpen }),
      setShowAdminPanel: (showAdminPanel) => set({ showAdminPanel }),
      setShowAdminManagement: (showAdminManagement) => set({ showAdminManagement }),
      setShowIBKRDashboard: (showIBKRDashboard) => set({ showIBKRDashboard }),
      setShowMockTradingDashboard: (showMockTradingDashboard) => set({ showMockTradingDashboard }),
      setShowBacktestPanel: (showBacktestPanel) => set({ showBacktestPanel }),
      setShowPredictionDashboard: (showPredictionDashboard) => set({ showPredictionDashboard }),
      setShowThsAnalysis: (showThsAnalysis) => set({ showThsAnalysis }),
      setSelectedDetail: (selectedDetail) => set({ selectedDetail }),
      setAutoRefreshInterval: (autoRefreshInterval) => set({ autoRefreshInterval }),
      setAnalysisLevel: (analysisLevel: AnalysisLevel) => set({ analysisLevel }),
      setServiceStatus: (serviceStatus) => set({ serviceStatus }),

      // Global Component Actions
      confirmDialog: null,
      toast: null,
      showConfirm: (title, message, onConfirm, type = 'info') => set({
        confirmDialog: { isOpen: true, title, message, onConfirm, type }
      }),
      hideConfirm: () => set((s) => ({
        confirmDialog: s.confirmDialog ? { ...s.confirmDialog, isOpen: false } : null
      })),
      showToast: (message, type = 'success') => {
        const id = Date.now();
        set({ toast: { isOpen: true, message, type, id } });
        setTimeout(() => {
          set((state) => {
            if (state.toast?.id === id) {
              return { toast: { ...state.toast, isOpen: false } };
            }
            return state;
          });
        }, 3000);
      },
      hideToast: () => set((s) => ({
        toast: s.toast ? { ...s.toast, isOpen: false } : null
      })),
    }),
    {
      name: 'ui-storage',
      partialize: (state) => ({ autoRefreshInterval: state.autoRefreshInterval, analysisLevel: state.analysisLevel, verificationMode: state.verificationMode }),
    }
  )
);

// Derived selectors for backward compatibility
export const selectLoading = (s: UIState) => s.analysisActivity === 'analyzing';
export const selectIsChatting = (s: UIState) => s.analysisActivity === 'chatting';
export const selectIsDiscussing = (s: UIState) => s.analysisActivity === 'discussing';
export const selectIsReviewing = (s: UIState) => s.analysisActivity === 'reviewing';
export const selectIsBusy = (s: UIState) =>
  s.analysisActivity !== 'idle' || s.overviewLoading || s.isGeneratingReport;
