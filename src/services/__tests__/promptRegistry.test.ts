import { describe, it, expect, beforeEach } from 'vitest';
import {
  registerPrompt,
  getActivePrompt,
  recordPromptMetrics,
  getPromptMetrics,
  getAllVersions,
  clearRegistry,
  PromptVersion,
} from '../promptRegistry';

describe('promptRegistry', () => {
  beforeEach(() => {
    clearRegistry();
  });

  const makePrompt = (overrides: Partial<PromptVersion> = {}): PromptVersion => ({
    id: 'test-v1.0',
    name: 'test-prompt',
    version: '1.0',
    template: (...args: any[]) => `template ${args.join(',')}`,
    changelog: 'initial version',
    createdAt: '2026-04-01',
    isActive: true,
    ...overrides,
  });

  describe('registerPrompt', () => {
    it('should register a prompt version', () => {
      registerPrompt(makePrompt());
      expect(getAllVersions('test-prompt')).toHaveLength(1);
    });

    it('should register multiple versions for the same name', () => {
      registerPrompt(makePrompt({ id: 'test-v1.0', version: '1.0', isActive: false }));
      registerPrompt(makePrompt({ id: 'test-v2.0', version: '2.0', isActive: true }));
      expect(getAllVersions('test-prompt')).toHaveLength(2);
    });
  });

  describe('getActivePrompt', () => {
    it('should return the active version', () => {
      registerPrompt(makePrompt({ id: 'v1', version: '1.0', isActive: false }));
      registerPrompt(makePrompt({ id: 'v2', version: '2.0', isActive: true }));
      const active = getActivePrompt('test-prompt');
      expect(active.id).toBe('v2');
      expect(active.version).toBe('2.0');
    });

    it('should throw when no active version exists', () => {
      registerPrompt(makePrompt({ isActive: false }));
      expect(() => getActivePrompt('test-prompt')).toThrow('No active prompt');
    });

    it('should throw when prompt name not found', () => {
      expect(() => getActivePrompt('nonexistent')).toThrow('No active prompt');
    });
  });

  describe('prompt template', () => {
    it('should execute the template function', () => {
      registerPrompt(makePrompt());
      const active = getActivePrompt('test-prompt');
      expect(active.template('arg1', 'arg2')).toBe('template arg1,arg2');
    });
  });

  describe('recordPromptMetrics & getPromptMetrics', () => {
    it('should return undefined for untracked prompt', () => {
      expect(getPromptMetrics('unknown')).toBeUndefined();
    });

    it('should track a single call', () => {
      recordPromptMetrics('test', 100, 85, 500, false);
      const m = getPromptMetrics('test')!;
      expect(m.callCount).toBe(1);
      expect(m.avgTokenUsage).toBe(100);
      expect(m.avgResponseScore).toBe(85);
      expect(m.avgLatencyMs).toBe(500);
      expect(m.errorRate).toBe(0);
      expect(m.lastUsed).toBeTruthy();
    });

    it('should compute running averages over multiple calls', () => {
      recordPromptMetrics('test', 100, 80, 400, false);
      recordPromptMetrics('test', 200, 90, 600, false);
      const m = getPromptMetrics('test')!;
      expect(m.callCount).toBe(2);
      expect(m.avgTokenUsage).toBe(150);
      expect(m.avgResponseScore).toBe(85);
      expect(m.avgLatencyMs).toBe(500);
      expect(m.errorRate).toBe(0);
    });

    it('should track error rate', () => {
      recordPromptMetrics('test', 100, 80, 400, false);
      recordPromptMetrics('test', 0, 0, 200, true);
      const m = getPromptMetrics('test')!;
      expect(m.errorRate).toBe(0.5);
    });
  });

  describe('getAllVersions', () => {
    it('should return empty array for unknown name', () => {
      expect(getAllVersions('nope')).toEqual([]);
    });
  });
});
