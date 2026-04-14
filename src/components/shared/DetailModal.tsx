import { motion, AnimatePresence } from 'motion/react';
import { Zap, Newspaper, Loader2, CheckCircle2, Share2, X } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { useUIStore } from '../../stores/useUIStore';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface DetailModalProps {
  onSendHistoryToFeishu: (data: any) => void;
}

export function DetailModal({ onSendHistoryToFeishu }: DetailModalProps) {
  const { selectedDetail, setSelectedDetail, isSendingReport, reportStatus, isGeneratingReport } = useUIStore();

  if (!selectedDetail) return null;

  return (
    <AnimatePresence>
      {selectedDetail && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 md:p-8">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSelectedDetail(null)}
            className="absolute inset-0 bg-black/40"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="relative w-full max-w-5xl max-h-[90vh] overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm flex flex-col"
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-zinc-200 p-6 md:px-8">
              <div className="flex items-center gap-4">
                <div className={cn(
                  "p-3 rounded-2xl",
                  selectedDetail.type === 'log' ? "bg-indigo-50 text-emerald-500" : "bg-blue-500/10 text-blue-500"
                )}>
                  {selectedDetail.type === 'log' ? <Zap size={24} /> : <Newspaper size={24} />}
                </div>
                <div>
                  <h3 className="text-xl font-medium text-zinc-950">
                    {selectedDetail.type === 'log' ? "优化思考链路日志" : "深度分析备份报告"}
                  </h3>
                  <p className="text-xs font-mono text-zinc-400 uppercase tracking-widest mt-1">
                    {selectedDetail.type === 'log' 
                      ? `FIELD: ${selectedDetail.data.field} • ${new Date(selectedDetail.data.timestamp).toLocaleString()}`
                      : `${selectedDetail.data.stockInfo?.symbol || 'MARKET'} • ${selectedDetail.data.stockInfo?.lastUpdated || 'RECENT'}`
                    }
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {selectedDetail.type === 'history' && (
                  <button
                    onClick={() => onSendHistoryToFeishu(selectedDetail.data)}
                    disabled={isSendingReport}
                    className={cn(
                      "flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-medium transition-all",
                      reportStatus === 'success' 
                        ? "bg-indigo-100 text-indigo-600 border border-indigo-600/50"
                        : reportStatus === 'error'
                        ? "bg-rose-500/20 text-rose-400 border border-rose-500/50"
                        : "bg-zinc-50 border border-zinc-200 hover:bg-zinc-100 text-zinc-500"
                    )}
                  >
                    {isSendingReport ? (
                      <>
                        <Loader2 className="animate-spin" size={14} />
                        发送中...
                      </>
                    ) : reportStatus === 'success' ? (
                      <>
                        <CheckCircle2 size={14} />
                        已发送
                      </>
                    ) : (
                      <>
                        <Share2 size={14} />
                        发送至飞书
                      </>
                    )}
                  </button>
                )}
                <button
                  onClick={() => setSelectedDetail(null)}
                  className="p-2 rounded-xl hover:bg-zinc-50 transition-colors text-zinc-400 hover:text-zinc-950"
                >
                  <X size={24} />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 md:p-8 custom-scrollbar">
              {selectedDetail.type === 'log' ? (
                <div className="space-y-8">
                  <div className="space-y-4">
                    <h4 className="text-sm font-medium uppercase tracking-widest text-zinc-400">操作描述</h4>
                    <p className="text-lg leading-relaxed text-zinc-600">{selectedDetail.data.description}</p>
                  </div>
                  
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="space-y-4">
                      <h4 className="text-sm font-medium uppercase tracking-widest text-zinc-400">优化前 (Old Value)</h4>
                      <div className="rounded-2xl bg-zinc-50 p-6 border border-zinc-200/50">
                        <pre className="text-sm font-mono text-zinc-400 whitespace-pre-wrap leading-relaxed">
                          {typeof selectedDetail.data.oldValue === 'object' 
                            ? JSON.stringify(selectedDetail.data.oldValue, null, 2) 
                            : selectedDetail.data.oldValue}
                        </pre>
                      </div>
                    </div>
                    <div className="space-y-4">
                      <h4 className="text-sm font-medium uppercase tracking-widest text-emerald-900/50">优化后 (New Value)</h4>
                      <div className="rounded-2xl bg-emerald-950/10 p-6 border border-indigo-100">
                        <pre className="text-sm font-mono text-indigo-500/80 whitespace-pre-wrap leading-relaxed">
                          {typeof selectedDetail.data.newValue === 'object' 
                            ? JSON.stringify(selectedDetail.data.newValue, null, 2) 
                            : selectedDetail.data.newValue}
                        </pre>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-8">
                  {selectedDetail.data.stockInfo && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {[
                        { label: '股票名称', value: selectedDetail.data.stockInfo.name, color: 'text-zinc-950' },
                        { label: '当前价格', value: `${selectedDetail.data.stockInfo.price} (${selectedDetail.data.stockInfo.changePercent}%)`, color: selectedDetail.data.stockInfo.change >= 0 ? 'text-indigo-500' : 'text-rose-400' },
                        { label: 'AI 评级', value: selectedDetail.data.recommendation, color: 'text-amber-500' },
                        { label: '市场情绪', value: selectedDetail.data.sentiment, color: 'text-indigo-500' },
                      ].map((stat, i) => (
                        <div key={`stat-${stat.label}-${i}`} className="p-4 rounded-2xl bg-zinc-50/50 border border-zinc-200/60">
                          <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">{stat.label}</p>
                          <p className={cn("text-lg font-medium", stat.color)}>{stat.value}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="space-y-4">
                    <h4 className="text-sm font-medium uppercase tracking-widest text-zinc-400">分析摘要</h4>
                    <p className="text-xl font-medium leading-relaxed text-zinc-950">
                      {selectedDetail.data.summary || selectedDetail.data.marketSummary}
                    </p>
                  </div>

                  {selectedDetail.data.finalConclusion && (
                    <div className="space-y-4">
                      <h4 className="text-sm font-medium uppercase tracking-widest text-emerald-500">首席策略师总结结论</h4>
                      <div className="p-6 rounded-2xl bg-indigo-600/5 border border-indigo-100">
                        <p className="text-lg leading-relaxed text-emerald-100 italic">
                          {selectedDetail.data.finalConclusion}
                        </p>
                      </div>
                    </div>
                  )}

                  {selectedDetail.data.tradingPlan && (
                    <div className="space-y-4">
                      <h4 className="text-sm font-medium uppercase tracking-widest text-emerald-500">交易计划</h4>
                      <div className="rounded-2xl border border-indigo-100 bg-indigo-600/5 p-6">
                        <div className="grid grid-cols-3 gap-4 mb-4">
                          <div className="p-3 rounded-2xl bg-white border border-zinc-200">
                            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">建议买入</p>
                            <p className="text-sm font-medium text-indigo-600">{selectedDetail.data.tradingPlan.entryPrice}</p>
                          </div>
                          <div className="p-3 rounded-2xl bg-white border border-zinc-200">
                            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">目标价位</p>
                            <p className="text-sm font-medium text-indigo-600">{selectedDetail.data.tradingPlan.targetPrice}</p>
                          </div>
                          <div className="p-3 rounded-2xl bg-white border border-zinc-200">
                            <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-1">止损价位</p>
                            <p className="text-sm font-medium text-rose-400">{selectedDetail.data.tradingPlan.stopLoss}</p>
                          </div>
                        </div>
                        <div className="p-4 rounded-2xl bg-white border border-zinc-200">
                          <p className="text-[10px] font-medium uppercase tracking-widest text-zinc-400 mb-2">操作策略</p>
                          <p className="text-sm leading-relaxed text-zinc-500 italic">{selectedDetail.data.tradingPlan.strategy}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {selectedDetail.data.technicalAnalysis && (
                    <div className="space-y-4">
                      <h4 className="text-sm font-medium uppercase tracking-widest text-zinc-400">技术面分析</h4>
                      <p className="text-base leading-relaxed text-zinc-500">{selectedDetail.data.technicalAnalysis}</p>
                    </div>
                  )}

                  {selectedDetail.data.fundamentalAnalysis && (
                    <div className="space-y-4">
                      <h4 className="text-sm font-medium uppercase tracking-widest text-zinc-400">基本面分析</h4>
                      <p className="text-base leading-relaxed text-zinc-500">{selectedDetail.data.fundamentalAnalysis}</p>
                    </div>
                  )}

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {selectedDetail.data.keyOpportunities && selectedDetail.data.keyOpportunities.length > 0 && (
                      <div className="space-y-4">
                        <h4 className="text-sm font-medium uppercase tracking-widest text-indigo-500/50">核心机会</h4>
                        <ul className="list-disc list-inside space-y-2 text-sm text-indigo-500/80">
                          {selectedDetail.data.keyOpportunities.map((opp: string, i: number) => (
                            <li key={`opp-detail-${i}-${opp.substring(0, 10)}`}>{opp}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {selectedDetail.data.keyRisks && selectedDetail.data.keyRisks.length > 0 && (
                      <div className="space-y-4">
                        <h4 className="text-sm font-medium uppercase tracking-widest text-rose-500/50">核心风险</h4>
                        <ul className="list-disc list-inside space-y-2 text-sm text-rose-400/80">
                          {selectedDetail.data.keyRisks.map((risk: string, i: number) => (
                            <li key={`risk-detail-${i}-${risk.substring(0, 10)}`}>{risk}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  <div className="space-y-4">
                    <h4 className="text-sm font-medium uppercase tracking-widest text-zinc-400">原始数据结构 (JSON)</h4>
                    <div className="rounded-2xl bg-zinc-50 p-6 border border-zinc-200/50">
                      <pre className="text-sm font-mono text-zinc-500 whitespace-pre-wrap leading-relaxed">
                        {JSON.stringify(selectedDetail.data, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
