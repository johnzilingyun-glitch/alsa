import { describe, it, expect, vi, beforeEach } from 'vitest';
import { dedup, clearDedup } from '../requestDedup';

describe('requestDedup', () => {
  beforeEach(() => {
    clearDedup();
  });

  it('should execute the function and return result', async () => {
    const fn = vi.fn().mockResolvedValue('result');
    const result = await dedup('key1', fn);
    expect(result).toBe('result');
    expect(fn).toHaveBeenCalledOnce();
  });

  it('should deduplicate concurrent calls with the same key', async () => {
    let resolvePromise: (value: string) => void;
    const fn = vi.fn().mockImplementation(() => new Promise<string>(r => { resolvePromise = r; }));

    const p1 = dedup('key1', fn);
    const p2 = dedup('key1', fn);

    // Both should return the same promise
    expect(fn).toHaveBeenCalledOnce();

    resolvePromise!('shared-result');
    const [r1, r2] = await Promise.all([p1, p2]);
    expect(r1).toBe('shared-result');
    expect(r2).toBe('shared-result');
  });

  it('should allow new calls after previous one completes', async () => {
    const fn1 = vi.fn().mockResolvedValue('first');
    const fn2 = vi.fn().mockResolvedValue('second');

    const r1 = await dedup('key1', fn1);
    const r2 = await dedup('key1', fn2);

    expect(r1).toBe('first');
    expect(r2).toBe('second');
    expect(fn1).toHaveBeenCalledOnce();
    expect(fn2).toHaveBeenCalledOnce();
  });

  it('should handle different keys independently', async () => {
    const fn1 = vi.fn().mockResolvedValue('a');
    const fn2 = vi.fn().mockResolvedValue('b');

    const [r1, r2] = await Promise.all([
      dedup('key1', fn1),
      dedup('key2', fn2),
    ]);

    expect(r1).toBe('a');
    expect(r2).toBe('b');
    expect(fn1).toHaveBeenCalledOnce();
    expect(fn2).toHaveBeenCalledOnce();
  });

  it('should clean up after rejection and allow retry', async () => {
    const fn1 = vi.fn().mockRejectedValue(new Error('fail'));
    const fn2 = vi.fn().mockResolvedValue('recovered');

    await expect(dedup('key1', fn1)).rejects.toThrow('fail');

    const result = await dedup('key1', fn2);
    expect(result).toBe('recovered');
    expect(fn2).toHaveBeenCalledOnce();
  });

  it('should propagate rejection to all concurrent callers', async () => {
    let rejectPromise: (err: Error) => void;
    const fn = vi.fn().mockImplementation(() => new Promise<string>((_, reject) => { rejectPromise = reject; }));

    const p1 = dedup('key1', fn);
    const p2 = dedup('key1', fn);

    rejectPromise!(new Error('shared-error'));

    await expect(p1).rejects.toThrow('shared-error');
    await expect(p2).rejects.toThrow('shared-error');
  });
});
