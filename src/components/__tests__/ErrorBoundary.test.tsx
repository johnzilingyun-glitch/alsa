import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from '../ErrorBoundary';

function ThrowingChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error('Test render error');
  return <div>正常内容</div>;
}

describe('ErrorBoundary', () => {
  // Suppress console.error for expected errors
  const originalConsoleError = console.error;
  beforeEach(() => { console.error = vi.fn(); });
  afterEach(() => { console.error = originalConsoleError; });

  it('should render children when no error', () => {
    render(
      <ErrorBoundary>
        <div>正常渲染</div>
      </ErrorBoundary>
    );
    expect(screen.getByText('正常渲染')).toBeTruthy();
  });

  it('should render default fallback when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(screen.getByText('组件渲染出错')).toBeTruthy();
    expect(screen.getByText('重试')).toBeTruthy();
  });

  it('should render string fallback when provided', () => {
    render(
      <ErrorBoundary fallback="分析数据加载异常">
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(screen.getByText('分析数据加载异常')).toBeTruthy();
    expect(screen.getByText('重试')).toBeTruthy();
  });

  it('should render custom ReactNode fallback', () => {
    render(
      <ErrorBoundary fallback={<div>自定义错误页</div>}>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(screen.getByText('自定义错误页')).toBeTruthy();
  });

  it('should call onError callback when error occurs', () => {
    const onError = vi.fn();
    render(
      <ErrorBoundary onError={onError}>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(onError).toHaveBeenCalledOnce();
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);
    expect(onError.mock.calls[0][0].message).toBe('Test render error');
  });

  it('should recover when retry is clicked', () => {
    let shouldThrow = true;
    function ConditionalThrow() {
      if (shouldThrow) throw new Error('Test error');
      return <div>正常内容</div>;
    }

    render(
      <ErrorBoundary>
        <ConditionalThrow />
      </ErrorBoundary>
    );
    expect(screen.getByText('组件渲染出错')).toBeTruthy();

    // Stop throwing before clicking retry
    shouldThrow = false;
    fireEvent.click(screen.getByText('重试'));
    expect(screen.getByText('正常内容')).toBeTruthy();
  });
});
