import React from 'react';
import { AlertCircle, RefreshCw, Settings, HelpCircle, ExternalLink } from 'lucide-react';

function classifyError(message: string): { hint: string; action?: 'retry' | 'settings' } {
  const lower = message.toLowerCase();
  if (lower.includes('所有 llm 提供商均失败') || lower.includes('llm 提供商均失败') || lower.includes('copilot') || lower.includes('personal access token') || lower.includes('etimedout')) {
    return { hint: '当前 Copilot 模型链路不可用或超时。建议在设置中切换到 copilot_auto / claude-opus-4.6，或重新完成 GitHub Copilot 登录。', action: 'settings' };
  }
  // Model not found: only match explicit 404/not-found indicators (avoid false positive from "所有模型均不可用")
  if (lower.includes('404') || (lower.includes('not found') && lower.includes('模型')))
    return { hint: '当前模型已下线或不存在。请在设置中切换到可用模型。', action: 'settings' };
  if (lower.includes('配额') || lower.includes('quota') || lower.includes('429') || lower.includes('rate')) {
    // If the error already includes diagnostic detail (原因/详情), use it as the hint
    const detailMatch = message.match(/\n(原因|详情)[:：]\s*(.+)/);
    const detail = detailMatch ? detailMatch[0].trim() : '';
    return { hint: detail || '请求过于频繁或配额耗尽。可能是 API 角色额度受限或预付余额不足。', action: 'settings' };
  }
  if (lower.includes('api key') || lower.includes('未配置') || lower.includes('apikey'))
    return { hint: '请在设置中填写 Gemini API Key。', action: 'settings' };
  if (lower.includes('无法获取') || lower.includes('not found') || lower.includes('拼写'))
    return { hint: '请检查股票代码是否正确。例如: 600519, 00700, AAPL' };
  if (lower.includes('网络') || lower.includes('network') || lower.includes('fetch'))
    return { hint: '网络连接异常，请检查网络后重试。', action: 'retry' };
  if (lower.includes('503') || lower.includes('负载') || lower.includes('unavailable'))
    return { hint: 'AI 服务暂时过载，请稍后重试。', action: 'retry' };
  return { hint: '', action: 'retry' };
}

interface ErrorNoticeProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  onOpenSettings?: () => void;
}

export function ErrorNotice({ title, message, onRetry, onOpenSettings }: ErrorNoticeProps) {
  const { hint, action } = classifyError(message);

  return (
    <div className="p-5 rounded-2xl bg-rose-50 border border-rose-100 flex items-start gap-3">
      <AlertCircle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
      <div className="flex-1">
        {title && <p className="text-sm font-bold text-rose-700 mb-1">{title}</p>}
        <p className="text-sm text-rose-600 font-medium">{message}</p>
        {hint && (
          <p className="text-xs text-rose-500/80 mt-2 flex items-center gap-1.5">
            <HelpCircle size={12} className="shrink-0" />
            {hint}
          </p>
        )}
        <div className="flex items-center gap-3 mt-3">
          {onRetry && (
            <button
              onClick={onRetry}
              className="flex items-center gap-1.5 text-xs font-semibold text-rose-600 hover:text-rose-700 transition-colors"
            >
              <RefreshCw size={12} />
              重试
            </button>
          )}
          {action === 'settings' && onOpenSettings && (
            <div className="flex items-center gap-4">
              <button
                onClick={onOpenSettings}
                className="flex items-center gap-1.5 text-xs font-semibold text-rose-500 hover:text-rose-600 transition-colors"
              >
                <Settings size={12} />
                打开设置
              </button>
              {(message.toLowerCase().includes('quota') || message.includes('配额') || message.toLowerCase().includes('depleted')) && (
                <a
                  href="https://aistudio.google.com/app/billing"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
                >
                  <ExternalLink size={12} />
                  管理账单 (AI Studio)
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
