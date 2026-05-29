import { useState } from 'react';
import { X, Combine, Loader2 } from 'lucide-react';
import { mergeAccounts, type MockAccount } from '../../services/api/mockTradingClient';

interface AccountMergeModalProps {
  accounts: MockAccount[];
  onClose: () => void;
  onSuccess: () => void;
}

export function AccountMergeModal({ accounts, onClose, onSuccess }: AccountMergeModalProps) {
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
  const [targetName, setTargetName] = useState('');
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [targetAccountId, setTargetAccountId] = useState(accounts[0]?.account_id || '');

  const toggleSource = (id: string) => {
    const newSet = new Set(selectedSources);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedSources(newSet);
  };

  const handleMerge = async () => {
    if (selectedSources.size === 0) return;
    
    // Simplification for the current flow: pick the first selected as the target, 
    // or actually, let's just pick a target from the dropdown.
    // Wait, the API requires targetAccountId. Let's allow the user to select the Target Account, 
    // and multiple Source Accounts.
    if (!targetAccountId) return;

    setExecuting(true);
    setError(null);
    try {
      await mergeAccounts(Array.from(selectedSources), targetAccountId);
      onSuccess();
      onClose();
    } catch (e: any) {
      setError(e.message || '合并失败');
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-zinc-900/30 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white rounded-3xl shadow-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold text-zinc-900 flex items-center gap-2">
            <Combine className="text-indigo-600" size={20} />
            合并账号
          </h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600 transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-5">
          {error && (
            <div className="p-3 rounded-xl bg-rose-50 text-rose-600 text-xs font-medium">
              {error}
            </div>
          )}

          <div>
            <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-2">目标账号 (保留)</label>
            <select
              value={targetAccountId}
              onChange={e => setTargetAccountId(e.target.value)}
              className="w-full px-4 py-3 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400 font-bold"
            >
              {accounts.map(a => (
                <option key={a.account_id} value={a.account_id}>
                  {a.name} ({a.currency})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-2">源账号 (合并后归档)</label>
            <div className="space-y-2 max-h-48 overflow-y-auto custom-scrollbar border border-zinc-100 rounded-xl p-2 bg-zinc-50">
              {accounts.filter(a => a.account_id !== targetAccountId).length === 0 ? (
                <div className="text-center py-4 text-xs text-zinc-400">没有其他可合并的账号</div>
              ) : (
                accounts.filter(a => a.account_id !== targetAccountId).map(a => (
                  <label key={a.account_id} className="flex items-center gap-3 p-3 bg-white rounded-lg border border-zinc-100 cursor-pointer hover:border-indigo-200 transition-colors">
                    <input
                      type="checkbox"
                      checked={selectedSources.has(a.account_id)}
                      onChange={() => toggleSource(a.account_id)}
                      className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500"
                    />
                    <div>
                      <div className="text-sm font-bold text-zinc-900">{a.name}</div>
                      <div className="text-[10px] text-zinc-500">{a.market} · {a.currency} · 余额 {a.current_cash.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</div>
                    </div>
                  </label>
                ))
              )}
            </div>
          </div>

          <div className="p-4 rounded-xl bg-indigo-50 text-indigo-800 text-xs leading-relaxed">
            合并后，源账号的持仓、现金将按汇率折算并转移至目标账号。源账号的所有交易记录也会迁移。源账号本身将被归档。
          </div>

          <button
            onClick={handleMerge}
            disabled={selectedSources.size === 0 || executing}
            className="w-full py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-50"
          >
            {executing ? <Loader2 size={16} className="animate-spin" /> : null}
            确认合并
          </button>
        </div>
      </div>
    </div>
  );
}
