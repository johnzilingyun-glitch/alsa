export class UndoManager<T> {
  private previousState: T | undefined;

  save(state: T): void {
    this.previousState = state;
  }

  canUndo(): boolean {
    return this.previousState !== undefined;
  }

  peek(): T | undefined {
    return this.previousState;
  }

  restore(): T | undefined {
    const state = this.previousState;
    this.previousState = undefined;
    return state;
  }

  clear(): void {
    this.previousState = undefined;
  }
}
