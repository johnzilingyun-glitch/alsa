import { describe, it, expect, beforeEach } from 'vitest';
import { UndoManager } from '../undoManager';

interface TestState {
  value: string;
  count: number;
}

describe('UndoManager', () => {
  let undo: UndoManager<TestState>;

  beforeEach(() => {
    undo = new UndoManager<TestState>();
  });

  it('has no previous state initially', () => {
    expect(undo.canUndo()).toBe(false);
    expect(undo.peek()).toBeUndefined();
  });

  it('saves and restores previous state', () => {
    const state: TestState = { value: 'hello', count: 1 };
    undo.save(state);
    expect(undo.canUndo()).toBe(true);
    expect(undo.restore()).toEqual(state);
  });

  it('clears previous state after restore', () => {
    undo.save({ value: 'a', count: 1 });
    undo.restore();
    expect(undo.canUndo()).toBe(false);
    expect(undo.restore()).toBeUndefined();
  });

  it('overwrites previous save (only 1 level of undo)', () => {
    undo.save({ value: 'first', count: 1 });
    undo.save({ value: 'second', count: 2 });
    const restored = undo.restore();
    expect(restored?.value).toBe('second');
  });

  it('peek reads without consuming', () => {
    undo.save({ value: 'peek-test', count: 5 });
    expect(undo.peek()?.value).toBe('peek-test');
    expect(undo.canUndo()).toBe(true); // still available
  });

  it('clear removes saved state', () => {
    undo.save({ value: 'x', count: 0 });
    undo.clear();
    expect(undo.canUndo()).toBe(false);
  });
});
