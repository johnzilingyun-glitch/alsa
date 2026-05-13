import React, { useState, useEffect, useRef } from 'react';
import { Loader2, FileText, AlertCircle } from 'lucide-react';
import { useAnalysisStore } from '../../stores/useAnalysisStore';
import { useConfigStore } from '../../stores/useConfigStore';

/**
 * Renders the CLI-quality institutional HTML report from the Python backend.
 * Fetches the report HTML using the job ID and displays it in a sandboxed iframe.
 */
export function InstitutionalReportView() {
  const lastJobId = useAnalysisStore(s => s.lastJobId);
  const cachedReportHtml = useAnalysisStore(s => s.cachedReportHtml);
  const cachedReportJobId = useAnalysisStore(s => s.cachedReportJobId);
  const setCachedReport = useAnalysisStore(s => s.setCachedReport);
  const config = useConfigStore(s => s.config);
  
  // Derive initial state from cache
  const hasCachedReport = cachedReportJobId === lastJobId && !!cachedReportHtml;
  const [html, setHtml] = useState<string | null>(hasCachedReport ? cachedReportHtml : null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Sync html from cache on remount (tab switch) without refetching
  useEffect(() => {
    if (cachedReportJobId === lastJobId && cachedReportHtml) {
      setHtml(cachedReportHtml);
    }
  }, [cachedReportJobId, cachedReportHtml, lastJobId]);

  // Fetch report only if no cache exists for this job
  useEffect(() => {
    if (!lastJobId) {
      setError('无可用的分析任务 ID');
      return;
    }

    // Skip fetch if we already have cached HTML for this job
    if (cachedReportJobId === lastJobId && cachedReportHtml) {
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/analysis/jobs/${lastJobId}/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        deepseekApiKey: config.deepseekApiKey || undefined,
      }),
    })
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`报告生成失败 (${res.status}): ${text}`);
        }
        return res.text();
      })
      .then((text) => {
        if (cancelled || !text) return;
        setHtml(text);
        setCachedReport(lastJobId, text);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message || '报告生成失败');
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [lastJobId, cachedReportJobId]);

  // Auto-resize iframe to content height
  useEffect(() => {
    if (!html || !iframeRef.current) return;
    const iframe = iframeRef.current;
    
    const handleLoad = () => {
      try {
        const doc = iframe.contentDocument || iframe.contentWindow?.document;
        if (doc) {
          const height = doc.documentElement.scrollHeight;
          iframe.style.height = `${height + 40}px`;
        }
      } catch { /* cross-origin, ignore */ }
    };

    iframe.addEventListener('load', handleLoad);
    return () => iframe.removeEventListener('load', handleLoad);
  }, [html]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <div className="relative">
          <Loader2 size={32} className="animate-spin text-indigo-500" />
          <div className="absolute inset-0 blur-xl bg-indigo-100 animate-pulse" />
        </div>
        <p className="text-sm font-medium text-zinc-500">正在生成专业研报...</p>
        <p className="text-[10px] text-zinc-400">后端 AI 正在提炼核心摘要、护城河、宏观分析等</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <AlertCircle size={24} className="text-amber-500" />
        <p className="text-sm font-medium text-zinc-700">{error}</p>
        <p className="text-xs text-zinc-400">可切换到「快速分析」查看已有数据</p>
      </div>
    );
  }

  if (!html) return null;

  return (
    <div className="w-full rounded-2xl border border-zinc-200 overflow-hidden bg-white shadow-sm">
      <iframe
        ref={iframeRef}
        srcDoc={html}
        className="w-full border-0"
        style={{ minHeight: '800px' }}
        sandbox="allow-same-origin"
        title="Institutional Research Report"
      />
    </div>
  );
}
