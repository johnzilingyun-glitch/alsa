import { Zap, Newspaper } from 'lucide-react';
import { useMarketStore } from '../../stores/useMarketStore';
import { useUIStore } from '../../stores/useUIStore';

export function AdminPanel() {
  const { optimizationLogs, historyItems } = useMarketStore();
  const { setSelectedDetail } = useUIStore();

  return (
    <section className="space-y-8 pt-12 border-t border-zinc-200 mt-12">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="space-y-6">
          <h2 className="flex items-center gap-2 text-xl font-medium">
            <Zap size={20} className="text-emerald-500" />
            优化思考链路日志
          </h2>
          <div className="space-y-3 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
            {optimizationLogs.slice().reverse().map((log, i) => (
              <div 
                key={`${log.timestamp}-${log.field}-${i}`} 
                className="p-4 rounded-xl border border-zinc-200 bg-white/30 text-xs cursor-pointer hover:border-indigo-600/30 transition-all group"
                onClick={() => setSelectedDetail({ type: 'log', data: log })}
              >
                <div className="flex justify-between mb-2">
                  <span className="font-medium text-indigo-600 uppercase tracking-wider">{log.field}</span>
                  <span className="text-zinc-400">{new Date(log.timestamp).toLocaleString()}</span>
                </div>
                <p className="text-zinc-500 line-clamp-2 mb-2">{log.description}</p>
                <div className="flex items-center gap-1 text-[10px] text-indigo-500/50 group-hover:text-emerald-500 transition-colors">
                  <Zap size={10} />
                  点击查看完整优化链路
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          <h2 className="flex items-center gap-2 text-xl font-medium">
            <Newspaper size={20} className="text-blue-500" />
            分析备份历史
          </h2>
          <div className="space-y-3 max-h-96 overflow-y-auto pr-2 custom-scrollbar">
            {historyItems.map((item, i) => {
              const itemKey = `history-${i}-${item.id || item.stockInfo?.symbol || 'market'}`;
              return (
                <div 
                  key={itemKey} 
                  className="p-4 rounded-xl border border-zinc-200 bg-white/30 text-xs cursor-pointer hover:border-blue-500/30 transition-all group"
                  onClick={() => setSelectedDetail({ type: 'history', data: item })}
                >
                  <div className="flex justify-between mb-2">
                    <span className="font-medium text-indigo-600 uppercase tracking-wider">
                      {item.stockInfo ? `STOCK: ${item.stockInfo.symbol}` : 'MARKET OVERVIEW'}
                    </span>
                    <span className="text-zinc-400">{item.stockInfo?.lastUpdated || 'RECENT'}</span>
                  </div>
                  <p className="text-zinc-500 line-clamp-2 mb-2">
                    {item.summary || item.marketSummary}
                  </p>
                  <div className="flex items-center gap-1 text-[10px] text-blue-500/50 group-hover:text-blue-500 transition-colors">
                    <Newspaper size={10} />
                    点击展开深度分析报告
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
