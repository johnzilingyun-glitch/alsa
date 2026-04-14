import React, { Component, ReactNode, ErrorInfo } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode | string;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        if (typeof this.props.fallback === 'string') {
          return (
            <div className="p-6 rounded-2xl bg-rose-50 border border-rose-100 text-center">
              <p className="text-sm text-rose-600 font-medium">{this.props.fallback}</p>
              <button
                onClick={this.handleRetry}
                className="mt-3 px-4 py-2 text-xs font-medium rounded-full bg-white border border-rose-200 text-rose-600 hover:bg-rose-50 transition-colors"
              >
                重试
              </button>
            </div>
          );
        }
        return this.props.fallback;
      }

      return (
        <div className="p-6 rounded-2xl bg-rose-50 border border-rose-100 text-center">
          <p className="text-sm text-rose-600 font-medium">组件渲染出错</p>
          <p className="mt-1 text-xs text-rose-400">
            {import.meta.env.DEV ? this.state.error?.message : '请点击重试或刷新页面'}
          </p>
          <button
            onClick={this.handleRetry}
            className="mt-3 px-4 py-2 text-xs font-medium rounded-full bg-white border border-rose-200 text-rose-600 hover:bg-rose-50 transition-colors"
          >
            重试
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
