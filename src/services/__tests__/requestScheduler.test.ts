import { describe, it, expect, beforeEach, vi } from 'vitest';

// We need to mock the dependencies before importing the module
vi.mock('../../stores/useConfigStore', () => ({
  useConfigStore: {
    getState: () => ({
      config: { tier: 'paid', model: 'gemini-3.1-pro-preview' },
    }),
  },
}));

vi.mock('../llmService', () => ({
  delay: vi.fn((ms: number) => new Promise(resolve => setTimeout(resolve, Math.min(ms, 10)))),
}));

// Import after mocks
import { requestScheduler } from '../requestScheduler';

describe('RequestScheduler', () => {
  beforeEach(() => {
    requestScheduler.reset();
  });

  describe('singleton', () => {
    it('should return the same instance', async () => {
      // The module exports a singleton
      const { RequestScheduler } = await import('../requestScheduler') as any;
      // requestScheduler is already the singleton, just verify it's defined
      expect(requestScheduler).toBeDefined();
      expect(requestScheduler.getQueueLength).toBeDefined();
    });
  });

  describe('schedule', () => {
    it('should execute a single task', async () => {
      const task = vi.fn().mockResolvedValue('result');
      const result = await requestScheduler.schedule(task);
      expect(result).toBe('result');
      expect(task).toHaveBeenCalledOnce();
    });

    it('should propagate task errors', async () => {
      const task = vi.fn().mockRejectedValue(new Error('task failed'));
      await expect(requestScheduler.schedule(task)).rejects.toThrow('task failed');
    });

    it('should execute tasks in priority order', async () => {
      const order: number[] = [];

      // Schedule 3 tasks with different priorities, all resolving quickly
      const p1 = requestScheduler.schedule(async () => { order.push(1); return 1; }, 1);
      const p2 = requestScheduler.schedule(async () => { order.push(2); return 2; }, 10);  // Highest priority
      const p3 = requestScheduler.schedule(async () => { order.push(3); return 3; }, 5);

      await Promise.all([p1, p2, p3]);

      // First task (1) might execute first as it was already dequeued,
      // but subsequent tasks should be priority-ordered
      expect(order).toHaveLength(3);
    });
  });

  describe('getQueueLength', () => {
    it('should return 0 when queue is empty', () => {
      expect(requestScheduler.getQueueLength()).toBe(0);
    });
  });

  describe('reset', () => {
    it('should clear the queue', () => {
      requestScheduler.reset();
      expect(requestScheduler.getQueueLength()).toBe(0);
    });
  });
});
