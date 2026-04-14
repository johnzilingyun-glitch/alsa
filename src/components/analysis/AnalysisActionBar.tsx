import React from 'react';
import {
  ArrowLeft, Download, Share2, Loader2, CheckCircle2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import { useUIStore } from '../../stores/useUIStore';

interface AnalysisActionBarProps {
  onResetToHome: () => void;
  onExportFullReport: () => void;
  onSendStockReport: () => void;
}

export function AnalysisActionBar({
  onResetToHome,
  onExportFullReport,
  onSendStockReport,
}: AnalysisActionBarProps) {
  const { t } = useTranslation();
  const { isGeneratingReport, isSendingReport, reportStatus } = useUIStore();

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
        <button
          onClick={onExportFullReport}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-zinc-200/60 hover:bg-zinc-50 text-zinc-500 text-sm font-medium transition-all"
        >
          <Download size={16} />
          {t('analysis.actions.export_full_report')}
        </button>
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
