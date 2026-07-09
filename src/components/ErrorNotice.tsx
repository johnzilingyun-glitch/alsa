import React from 'react';
import { AlertCircle, RefreshCw, Settings, HelpCircle, ExternalLink } from 'lucide-react';
import { useTranslation } from 'react-i18next';

function extractIds(message: string): { jobId: string | null; incidentId: string | null } {
  const jobIdMatch = message.match(/Job ID:\s*([A-Za-z0-9._:-]+)/i);
  const incidentMatch = message.match(/Incident ID:\s*([A-Za-z0-9._:-]+)/i) || message.match(/\[incident_id=([^\]]+)\]/i);
  return {
    jobId: jobIdMatch?.[1] || null,
    incidentId: incidentMatch?.[1] || null,
  };
}

function classifyError(message: string, t: (key: string) => string): { hint: string; action?: 'retry' | 'settings' } {
  const lower = message.toLowerCase();
  if (lower.includes('所有 llm 提供商均失败') || lower.includes('llm 提供商均失败') || lower.includes('etimedout')) {
    return { hint: t('errorNotice.model_unavailable'), action: 'settings' };
  }
  if (lower.includes('404') || (lower.includes('not found') && lower.includes('模型')))
    return { hint: t('errorNotice.model_deprecated'), action: 'settings' };
  if (lower.includes('配额') || lower.includes('quota') || lower.includes('429') || lower.includes('rate')) {
    const detailMatch = message.match(/\n(原因|详情)[:：]\s*(.+)/);
    const detail = detailMatch ? detailMatch[0].trim() : '';
    return { hint: detail || t('errorNotice.rate_limit'), action: 'settings' };
  }
  if (lower.includes('api key') || lower.includes('未配置') || lower.includes('apikey'))
    return { hint: t('errorNotice.no_api_key'), action: 'settings' };
  if (lower.includes('无法获取') || lower.includes('not found') || lower.includes('拼写'))
    return { hint: t('errorNotice.invalid_symbol') };
  if (lower.includes('网络') || lower.includes('network') || lower.includes('fetch'))
    return { hint: t('errorNotice.network_error'), action: 'retry' };
  if (lower.includes('503') || lower.includes('负载') || lower.includes('unavailable'))
    return { hint: t('errorNotice.overloaded'), action: 'retry' };
  return { hint: '', action: 'retry' };
}

interface ErrorNoticeProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  onOpenSettings?: () => void;
}

export function ErrorNotice({ title, message, onRetry, onOpenSettings }: ErrorNoticeProps) {
  const { t } = useTranslation();
  const { hint, action } = classifyError(message, t);
  const { jobId, incidentId } = extractIds(message);
  const canOpenIncident = Boolean(jobId || incidentId);

  const openIncidentConsole = () => {
    const query = new URLSearchParams();
    if (jobId) query.set('job_id', jobId);
    if (incidentId) query.set('incident_id', incidentId);
    window.location.hash = `#/admin/incidents?${query.toString()}`;
  };

  return (
    <div className="p-5 rounded-2xl bg-rose-50 border border-rose-100 flex items-start gap-3">
      <AlertCircle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
      <div className="flex-1">
        {title && <p className="text-sm font-bold text-rose-700 mb-1">{title}</p>}
        <p className="text-sm text-rose-600 font-medium">{message}</p>
        {(jobId || incidentId) && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
            {jobId && (
              <span className="px-2 py-1 rounded-lg bg-rose-100 text-rose-700 font-semibold">Job ID: {jobId}</span>
            )}
            {incidentId && (
              <span className="px-2 py-1 rounded-lg bg-indigo-100 text-indigo-700 font-semibold">Incident ID: {incidentId}</span>
            )}
          </div>
        )}
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
              {t('errorNotice.retry')}
            </button>
          )}
          {action === 'settings' && onOpenSettings && (
            <div className="flex items-center gap-4">
              <button
                onClick={onOpenSettings}
                className="flex items-center gap-1.5 text-xs font-semibold text-rose-500 hover:text-rose-600 transition-colors"
              >
                <Settings size={12} />
                {t('errorNotice.open_settings')}
              </button>
              {(message.toLowerCase().includes('quota') || message.includes('配额') || message.toLowerCase().includes('depleted')) && (
                <a
                  href="https://aistudio.google.com/app/billing"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
                >
                  <ExternalLink size={12} />
                  {t('errorNotice.manage_billing')}
                </a>
              )}
            </div>
          )}
          {canOpenIncident && (
            <button
              onClick={openIncidentConsole}
              className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
            >
              <ExternalLink size={12} />
              查看故障快照
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
