import { describe, it, expect, beforeEach } from 'vitest';
import { useJobQueueStore, BackgroundJob } from '../useJobQueueStore';

describe('useJobQueueStore', () => {
  beforeEach(() => {
    useJobQueueStore.setState({ jobs: [] });
  });

  describe('addJob', () => {
    it('should add a job with defaults', () => {
      useJobQueueStore.getState().addJob({
        id: 'job-1',
        jobId: 'j1',
        symbol: 'AAPL',
        market: 'US-Share',
        status: 'queued',
      });

      const jobs = useJobQueueStore.getState().jobs;
      expect(jobs).toHaveLength(1);
      expect(jobs[0].id).toBe('job-1');
      expect(jobs[0].notificationVisible).toBe(false);
      expect(jobs[0].expanded).toBe(false);
      expect(jobs[0].createdAt).toBeGreaterThan(0);
    });

    it('should append multiple jobs', () => {
      const { addJob } = useJobQueueStore.getState();
      addJob({ id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'queued' });
      addJob({ id: 'j2', jobId: 'j2', symbol: '600519', market: 'A-Share', status: 'queued' });
      expect(useJobQueueStore.getState().jobs).toHaveLength(2);
    });
  });

  describe('updateJob', () => {
    it('should update job fields', () => {
      useJobQueueStore.getState().addJob({
        id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'queued',
      });

      useJobQueueStore.getState().updateJob('j1', { status: 'running' });
      expect(useJobQueueStore.getState().jobs[0].status).toBe('running');
    });

    it('should auto-show notification on completion', () => {
      useJobQueueStore.getState().addJob({
        id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'running',
      });

      useJobQueueStore.getState().updateJob('j1', { status: 'completed' });
      const job = useJobQueueStore.getState().jobs[0];
      expect(job.notificationVisible).toBe(true);
      expect(job.expanded).toBe(true);
    });

    it('should auto-show notification on failure', () => {
      useJobQueueStore.getState().addJob({
        id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'running',
      });

      useJobQueueStore.getState().updateJob('j1', { status: 'failed', error: 'timeout' });
      const job = useJobQueueStore.getState().jobs[0];
      expect(job.notificationVisible).toBe(true);
      expect(job.error).toBe('timeout');
    });

    it('should not affect other jobs', () => {
      const { addJob } = useJobQueueStore.getState();
      addJob({ id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'running' });
      addJob({ id: 'j2', jobId: 'j2', symbol: 'GOOG', market: 'US-Share', status: 'queued' });

      useJobQueueStore.getState().updateJob('j1', { status: 'completed' });
      expect(useJobQueueStore.getState().jobs[1].status).toBe('queued');
    });
  });

  describe('removeJob', () => {
    it('should remove a job by id', () => {
      useJobQueueStore.getState().addJob({
        id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'completed',
      });

      useJobQueueStore.getState().removeJob('j1');
      expect(useJobQueueStore.getState().jobs).toHaveLength(0);
    });

    it('should not affect other jobs', () => {
      const { addJob } = useJobQueueStore.getState();
      addJob({ id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'completed' });
      addJob({ id: 'j2', jobId: 'j2', symbol: 'GOOG', market: 'US-Share', status: 'running' });

      useJobQueueStore.getState().removeJob('j1');
      const jobs = useJobQueueStore.getState().jobs;
      expect(jobs).toHaveLength(1);
      expect(jobs[0].id).toBe('j2');
    });
  });

  describe('dismissNotification', () => {
    it('should hide notification for specific job', () => {
      useJobQueueStore.getState().addJob({
        id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'running',
      });
      useJobQueueStore.getState().updateJob('j1', { status: 'completed' });
      expect(useJobQueueStore.getState().jobs[0].notificationVisible).toBe(true);

      useJobQueueStore.getState().dismissNotification('j1');
      expect(useJobQueueStore.getState().jobs[0].notificationVisible).toBe(false);
    });
  });

  describe('toggleExpand', () => {
    it('should toggle expanded state', () => {
      useJobQueueStore.getState().addJob({
        id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'completed',
      });

      useJobQueueStore.getState().toggleExpand('j1');
      expect(useJobQueueStore.getState().jobs[0].expanded).toBe(true);

      useJobQueueStore.getState().toggleExpand('j1');
      expect(useJobQueueStore.getState().jobs[0].expanded).toBe(false);
    });
  });

  describe('collapseAll', () => {
    it('should collapse all jobs', () => {
      const { addJob } = useJobQueueStore.getState();
      addJob({ id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'completed' });
      addJob({ id: 'j2', jobId: 'j2', symbol: 'GOOG', market: 'US-Share', status: 'completed' });
      useJobQueueStore.getState().updateJob('j1', { status: 'completed' });
      useJobQueueStore.getState().updateJob('j2', { status: 'completed' });

      useJobQueueStore.getState().collapseAll();
      const jobs = useJobQueueStore.getState().jobs;
      expect(jobs.every(j => j.expanded === false)).toBe(true);
    });
  });

  describe('getNotifications', () => {
    it('should return only visible notifications', () => {
      const { addJob } = useJobQueueStore.getState();
      addJob({ id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'running' });
      addJob({ id: 'j2', jobId: 'j2', symbol: 'GOOG', market: 'US-Share', status: 'running' });

      useJobQueueStore.getState().updateJob('j1', { status: 'completed' });

      const notifications = useJobQueueStore.getState().getNotifications();
      expect(notifications).toHaveLength(1);
      expect(notifications[0].id).toBe('j1');
    });
  });

  describe('getRunningCount', () => {
    it('should count queued and running jobs', () => {
      const { addJob } = useJobQueueStore.getState();
      addJob({ id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'queued' });
      addJob({ id: 'j2', jobId: 'j2', symbol: 'GOOG', market: 'US-Share', status: 'running' });
      addJob({ id: 'j3', jobId: 'j3', symbol: 'TSLA', market: 'US-Share', status: 'completed' });

      expect(useJobQueueStore.getState().getRunningCount()).toBe(2);
    });

    it('should return 0 when no running jobs', () => {
      useJobQueueStore.getState().addJob({
        id: 'j1', jobId: 'j1', symbol: 'AAPL', market: 'US-Share', status: 'completed',
      });
      expect(useJobQueueStore.getState().getRunningCount()).toBe(0);
    });
  });
});
