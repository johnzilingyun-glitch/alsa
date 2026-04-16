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
  selectedDetail: { type: 'log' | 'history', data: any } | null;

  // Error states
  analysisError: string | null;
  chatError: string | null;
  overviewError: string | null;
  reportStatus: 'idle' | 'success' | 'error';
  serviceStatus: 'available' | 'quota_exhausted' | 'error';

  // Config
  autoRefreshInterval: number;
  analysisLevel: AnalysisLevel;

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
  setSelectedDetail: (detail: { type: 'log' | 'history', data: any } | null) => void;
  setAutoRefreshInterval: (interval: number) => void;
  setAnalysisLevel: (level: AnalysisLevel) => void;
  setServiceStatus: (status: 'available' | 'quota_exhausted' | 'error') => void;
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
      selectedDetail: null,
      analysisError: null,
      chatError: null,
      overviewError: null,
      reportStatus: 'idle',
      serviceStatus: 'available',
      autoRefreshInterval: 0,

      // Activity setters - mutually exclusive via enum
      setLoading: (loading) => set((s) => ({
        analysisActivity: loading ? 'analyzing' : (s.analysisActivity === 'analyzing' ? 'idle' : s.analysisActivity),
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
      setSelectedDetail: (selectedDetail) => set({ selectedDetail }),
      setAutoRefreshInterval: (autoRefreshInterval) => set({ autoRefreshInterval }),
      analysisLevel: 'standard' as AnalysisLevel,
      setAnalysisLevel: (analysisLevel: AnalysisLevel) => set({ analysisLevel }),
      setServiceStatus: (serviceStatus) => set({ serviceStatus }),
    }),
    {
      name: 'ui-storage',
      partialize: (state) => ({ autoRefreshInterval: state.autoRefreshInterval, analysisLevel: state.analysisLevel }),
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
