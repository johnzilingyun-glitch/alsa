import { create } from 'zustand';

export interface BackgroundJob {
  id: string;
  jobId: string;
  symbol: string;
  market: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  progress?: { stage: string; percent: number; round?: number; total_rounds?: number; message?: string };
  result?: any;
  analysisId?: string;
  error?: string;
  createdAt: number;
  /** Whether the notification bubble is visible */
  notificationVisible: boolean;
  /** Whether the bubble is expanded */
  expanded: boolean;
}

interface JobQueueState {
  jobs: BackgroundJob[];
  addJob: (job: Omit<BackgroundJob, 'notificationVisible' | 'expanded' | 'createdAt'>) => void;
  updateJob: (id: string, patch: Partial<BackgroundJob>) => void;
  removeJob: (id: string) => void;
  dismissNotification: (id: string) => void;
  toggleExpand: (id: string) => void;
  collapseAll: () => void;
  /** Get all jobs with visible notifications (completed/failed) */
  getNotifications: () => BackgroundJob[];
  /** Get count of currently running background jobs */
  getRunningCount: () => number;
}

export const useJobQueueStore = create<JobQueueState>((set, get) => ({
  jobs: [],

  addJob: (job) => set((s) => ({
    jobs: [...s.jobs, { ...job, createdAt: Date.now(), notificationVisible: false, expanded: false }],
  })),

  updateJob: (id, patch) => set((s) => ({
    jobs: s.jobs.map((j) => {
      if (j.id !== id) return j;
      const updated = { ...j, ...patch };
      // Auto-show notification when job completes or fails
      if ((patch.status === 'completed' || patch.status === 'failed') && !j.notificationVisible) {
        updated.notificationVisible = true;
        updated.expanded = true;
      }
      return updated;
    }),
  })),

  removeJob: (id) => set((s) => ({
    jobs: s.jobs.filter((j) => j.id !== id),
  })),

  dismissNotification: (id) => set((s) => ({
    jobs: s.jobs.map((j) => j.id === id ? { ...j, notificationVisible: false } : j),
  })),

  toggleExpand: (id) => set((s) => ({
    jobs: s.jobs.map((j) => j.id === id ? { ...j, expanded: !j.expanded } : j),
  })),

  collapseAll: () => set((s) => ({
    jobs: s.jobs.map((j) => ({ ...j, expanded: false })),
  })),

  getNotifications: () => get().jobs.filter((j) => j.notificationVisible),
  getRunningCount: () => get().jobs.filter((j) => j.status === 'queued' || j.status === 'running').length,
}));
