import React, { useState, useRef, useEffect } from 'react';
import {
  ArrowLeft, Download, Share2, Loader2, CheckCircle2, FileText, Image, ChevronDown, Heart,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import { useUIStore } from '../../stores/useUIStore';

interface AnalysisActionBarProps {
  onResetToHome: () => void;
  onExportFullReport: () => void;
  onExportPdf?: () => void;
  onExportShareCard?: () => void;
  onSendStockReport: () => void;
  isStarred?: boolean;
  onToggleWatchlist?: () => void;
}

export function AnalysisActionBar({
  onResetToHome,
  onExportFullReport,
  onExportPdf,
  onExportShareCard,
  onSendStockReport,
  isStarred = false,
  onToggleWatchlist,
}: AnalysisActionBarProps) {
  const { t } = useTranslation();
  const { isGeneratingReport, isSendingReport, reportStatus } = useUIStore();
  const [exportOpen, setExportOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setExportOpen(false);
      }
    };
    if (exportOpen) document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [exportOpen]);

  return (
    <div className="flex items-center justify-between">
      <button
        onClick={onResetToHome}
        className="flex items-center gap-2 text-sm font-medium text-zinc-400 transition-colors hover:text-zinc-950"
      >
        <ArrowLeft size={16} />
        {t('common.back')}
      </button>

      <div className="flex items-center gap-2">
        {onToggleWatchlist && (
          <button
            onClick={onToggleWatchlist}
            className={cn(
              "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all border",
              isStarred
                ? "bg-rose-50/50 text-rose-500 border-rose-200/80 hover:bg-rose-100/50"
                : "bg-white border border-zinc-200/60 hover:bg-zinc-50 text-zinc-500"
            )}
          >
            <Heart size={16} className={cn(isStarred && "fill-rose-500 text-rose-500")} />
            {isStarred ? "已关注" : "添加自选"}
          </button>
        )}

        {/* Export dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setExportOpen(!exportOpen)}
            disabled={isGeneratingReport}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-zinc-200/60 hover:bg-zinc-50 text-zinc-500 text-sm font-medium transition-all"
          >
            {isGeneratingReport ? (
              <Loader2 className="animate-spin" size={16} />
            ) : (
              <Download size={16} />
            )}
            {t('analysis.actions.export_report')}
            <ChevronDown size={14} className={cn("transition-transform", exportOpen && "rotate-180")} />
          </button>

          {exportOpen && (
            <div className="absolute right-0 mt-1 w-52 bg-white rounded-xl border border-zinc-200/60 shadow-lg z-50 py-1 animate-in fade-in slide-in-from-top-1 duration-150">
              <button
                onClick={() => { onExportFullReport(); setExportOpen(false); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50 transition-colors"
              >
                <FileText size={15} className="text-zinc-400" />
                {t('analysis.actions.export_html', '导出 HTML')}
              </button>
              {onExportPdf && (
                <button
                  onClick={() => { onExportPdf(); setExportOpen(false); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50 transition-colors"
                >
                  <Download size={15} className="text-zinc-400" />
                  {t('analysis.actions.export_pdf', '导出 PDF')}
                </button>
              )}
              {onExportShareCard && (
                <button
                  onClick={() => { onExportShareCard(); setExportOpen(false); }}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-zinc-600 hover:bg-zinc-50 transition-colors"
                >
                  <Image size={15} className="text-zinc-400" />
                  {t('analysis.actions.export_share_card', '生成分享卡片')}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Feishu share button */}
        <button
          onClick={onSendStockReport}
          disabled={isGeneratingReport || isSendingReport}
          className={cn(
            "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all",
            reportStatus === 'success'
              ? "bg-indigo-100 text-indigo-600 border border-indigo-600/50"
              : reportStatus === 'error'
              ? "bg-rose-500/20 text-rose-400 border border-rose-500/50"
              : "bg-white border border-zinc-200/60 hover:bg-zinc-50 text-zinc-500"
          )}
        >
          {isGeneratingReport ? (
            <>
              <Loader2 className="animate-spin" size={16} />
              {t('analysis.actions.generating_report')}
            </>
          ) : isSendingReport ? (
            <>
              <Loader2 className="animate-spin" size={16} />
              {t('analysis.actions.sending_to_feishu')}
            </>
          ) : reportStatus === 'success' ? (
            <>
              <CheckCircle2 size={16} />
              {t('analysis.actions.sent')}
            </>
          ) : (
            <>
              <Share2 size={16} />
              {t('analysis.actions.trigger_report')}
            </>
          )}
        </button>
      </div>
    </div>
  );
}
