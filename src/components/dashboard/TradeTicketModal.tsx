import { useState, useEffect, useRef } from 'react';
import { X, Search, Activity, DollarSign, Loader2, Zap } from 'lucide-react';
import { executeTrade, type MockAccount } from '../../services/api/mockTradingClient';
import { getQuotes } from '../../services/api/stockClient';

interface TradeTicketModalProps {
  account: MockAccount;
  onClose: () => void;
  onSuccess: () => void;
}

export function TradeTicketModal({ account, onClose, onSuccess }: TradeTicketModalProps) {
  const [symbol, setSymbol] = useState('');
  const [market, setMarket] = useState(account.market === 'Global' ? 'A-Share' : account.market);
  const [action, setAction] = useState<'BUY' | 'SELL'>('BUY');
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET');
  const [shares, setShares] = useState('');
  const [targetPriceInput, setTargetPriceInput] = useState('');
  const [stopLossInput, setStopLossInput] = useState('');
  const [takeProfitInput, setTakeProfitInput] = useState('');
  const [isAdvanced, setIsAdvanced] = useState(false);
  const [price, setPrice] = useState<number | null>(null);
  const [loadingPrice, setLoadingPrice] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  // Suggestions Fetch
  useEffect(() => {
    const controller = new AbortController();
    const fetchSuggestions = async () => {
      if (!symbol || symbol.trim().length < 1 || isComposing) {
        setSuggestions([]);
        setShowSuggestions(false);
        return;
      }
      try {
        const params = new URLSearchParams();
        params.set('input', symbol);
        params.set('market', market);
        const res = await fetch(`/api/stock/suggest?${params.toString()}`, { signal: controller.signal });
        if (res.ok) {
          const data = await res.json();
          setSuggestions(data);
          setShowSuggestions(data.length > 0);
          setSelectedIndex(-1);
        }
      } catch (e: any) {
        if (e.name !== 'AbortError') console.error('Failed to fetch suggestions:', e);
      }
    };
    const timeout = setTimeout(fetchSuggestions, 300);
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [symbol, market, isComposing]);

  // Click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectSuggestion = (s: any) => {
    const finalSym = s.symbol || s.fullSymbol;
    setSymbol(finalSym);
    setShowSuggestions(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex(prev => (prev + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex(prev => (prev - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      handleSelectSuggestion(suggestions[selectedIndex]);
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  // Debounced price fetch with AbortController to prevent stale results
  useEffect(() => {
    if (!symbol || symbol.trim().length < 1) {
      setPrice(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoadingPrice(true);
      setError(null);
      try {
        const quotes = await getQuotes([symbol.toUpperCase()]);
        if (controller.signal.aborted) return;
        if (quotes && quotes.length > 0 && quotes[0].price > 0) {
          setPrice(quotes[0].price);
        } else {
          setPrice(null);
          setError('未找到股票实时价格');
        }
      } catch (e) {
        if (!controller.signal.aborted) {
          setPrice(null);
          setError('获取实时价格失败');
        }
      } finally {
        if (!controller.signal.aborted) setLoadingPrice(false);
      }
    }, 800);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [symbol]);

  const handleTrade = async () => {
    const finalPrice = orderType === 'MARKET' ? price : Number(targetPriceInput);
    if (!symbol || !shares || !finalPrice || Number(shares) <= 0) return;
    setExecuting(true);
    setError(null);
    try {
      await executeTrade(
        account.account_id,
        symbol.toUpperCase(),
        market,
        action,
        Number(shares),
        finalPrice,
        orderType,
        isAdvanced && stopLossInput ? Number(stopLossInput) : undefined,
        'MANUAL'
      );
      onSuccess();
      onClose();
    } catch (e: any) {
      setError(e.message || '交易执行失败 (可能资金/持仓不足)');
    } finally {
      setExecuting(false);
    }
  };

  const estimatedValue = (orderType === 'MARKET' ? price : Number(targetPriceInput)) && shares 
    ? (orderType === 'MARKET' ? price! : Number(targetPriceInput)) * Number(shares) 
    : 0;

  const getEstimatedFee = () => {
    if (!estimatedValue || !shares) return 0;
    const numShares = Number(shares);
    if (market === 'A-Share') {
      const rate = action === 'BUY' ? 0.00015 : 0.00115;
      return Math.max(estimatedValue * rate, 5);
    } else if (market === 'US-Share') {
      return Math.max(numShares * 0.005, 1);
    } else if (market === 'HK-Share') {
      const rate = action === 'BUY' ? 0.001 : 0.002;
      return Math.max(estimatedValue * rate, 15);
    }
    return 0;
  };
  const estimatedFee = getEstimatedFee();

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-zinc-900/30 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-sm bg-white rounded-3xl shadow-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold text-zinc-900 flex items-center gap-2">
            <Activity className="text-indigo-600" size={20} />
            手动交易
          </h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-600 transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-rose-50 text-rose-600 text-xs font-medium">
              {error}
            </div>
          )}

          {/* Action Toggle */}
          <div className="flex bg-zinc-100 p-1 rounded-xl">
            <button
              onClick={() => setAction('BUY')}
              className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${
                action === 'BUY' ? 'bg-white text-emerald-600 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'
              }`}
            >
              买入 (BUY)
            </button>
            <button
              onClick={() => setAction('SELL')}
              className={`flex-1 py-2 rounded-lg text-sm font-bold transition-all ${
                action === 'SELL' ? 'bg-white text-rose-600 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'
              }`}
            >
              卖出 (SELL)
            </button>
          </div>

          <div className="flex gap-2">
            {account.market === 'Global' && (
              <select
                value={market}
                onChange={e => setMarket(e.target.value)}
                className="w-1/3 px-3 py-2.5 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
              >
                <option value="A-Share">A-Share</option>
                <option value="US-Share">US-Share</option>
                <option value="HK-Share">HK-Share</option>
              </select>
            )}
            <div className={`relative ${account.market === 'Global' ? 'w-2/3' : 'w-full'}`} ref={searchContainerRef}>
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" size={16} />
              <input
                placeholder="股票代码/拼音/中文"
                value={symbol}
                onCompositionStart={() => setIsComposing(true)}
                onCompositionEnd={(e) => {
                  setIsComposing(false);
                  setSymbol(e.currentTarget.value);
                }}
                onChange={e => setSymbol(e.target.value)}
                onFocus={() => { if (suggestions.length > 0) setShowSuggestions(true); }}
                onKeyDown={handleKeyDown}
                className="w-full pl-9 pr-4 py-2.5 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
              />
              {showSuggestions && suggestions.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-2 z-[60] overflow-hidden rounded-2xl border border-zinc-100 bg-white shadow-2xl shadow-indigo-600/10">
                  <div className="p-1.5 max-h-48 overflow-y-auto custom-scrollbar">
                    {suggestions.map((s, idx) => (
                      <button
                        key={`sugg-${s.symbol}-${idx}`}
                        type="button"
                        onClick={() => handleSelectSuggestion(s)}
                        onMouseEnter={() => setSelectedIndex(idx)}
                        className={`flex w-full items-center justify-between px-3 py-2 rounded-xl transition-all ${
                          idx === selectedIndex ? 'bg-indigo-50 text-indigo-700' : 'text-zinc-700 hover:bg-zinc-50'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${idx === selectedIndex ? 'bg-indigo-100 text-indigo-600' : 'bg-zinc-100 text-zinc-500'}`}>
                            {s.symbol}
                          </span>
                          <span className="font-bold text-xs truncate max-w-[120px] text-left">{s.name}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex gap-2 p-1 bg-zinc-100 rounded-xl">
            <button
              onClick={() => setOrderType('MARKET')}
              className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${
                orderType === 'MARKET' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'
              }`}
            >
              市价单 (Market)
            </button>
            <button
              onClick={() => setOrderType('LIMIT')}
              className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${
                orderType === 'LIMIT' ? 'bg-white text-zinc-900 shadow-sm' : 'text-zinc-500 hover:text-zinc-700'
              }`}
            >
              限价单 (Limit)
            </button>
          </div>

          <div className="p-4 rounded-xl bg-zinc-50 border border-zinc-100 flex items-center justify-between">
            <span className="text-xs font-bold text-zinc-500">实时价格</span>
            {loadingPrice ? (
              <Loader2 className="animate-spin text-zinc-400" size={16} />
            ) : price ? (
              <span className="text-base font-bold text-zinc-900">{price.toFixed(2)}</span>
            ) : (
              <span className="text-sm text-zinc-400">--</span>
            )}
          </div>
          
          {orderType === 'LIMIT' && (
            <div>
              <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">目标价格 (Limit Price)</label>
              <input
                type="number"
                value={targetPriceInput}
                onChange={e => setTargetPriceInput(e.target.value)}
                placeholder="0.00"
                className="w-full px-4 py-3 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
              />
            </div>
          )}

          {/* Advanced Orders Toggle */}
          <div>
            <button 
              onClick={() => setIsAdvanced(!isAdvanced)}
              className="text-xs font-bold text-indigo-600 hover:text-indigo-700 transition-colors flex items-center gap-1"
            >
              {isAdvanced ? '- 收起高级选项' : '+ 添加止损/止盈 (条件单)'}
            </button>
            
            {isAdvanced && (
              <div className="mt-3 grid grid-cols-2 gap-3 p-3 bg-zinc-50 rounded-xl border border-zinc-100">
                <div>
                  <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">触发止损价</label>
                  <input
                    type="number"
                    value={stopLossInput}
                    onChange={e => setStopLossInput(e.target.value)}
                    placeholder="选填"
                    className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">触发止盈价 (规划中)</label>
                  <input
                    type="number"
                    value={takeProfitInput}
                    onChange={e => setTakeProfitInput(e.target.value)}
                    placeholder="选填"
                    disabled
                    className="w-full px-3 py-2 rounded-lg border border-zinc-200 text-sm bg-zinc-100 text-zinc-400 cursor-not-allowed"
                  />
                </div>
              </div>
            )}
          </div>

          <div>
            <label className="text-[10px] font-bold text-zinc-500 uppercase block mb-1">交易数量 (股)</label>
            <input
              type="number"
              value={shares}
              onChange={e => setShares(e.target.value)}
              placeholder="0"
              className="w-full px-4 py-3 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:border-indigo-400"
            />
          </div>

          <div className="pt-2 border-t border-zinc-100 flex items-center justify-between">
            <span className="text-xs text-zinc-500">预估金额 (不含手续费)</span>
            <span className="text-base font-bold text-zinc-900 flex items-center">
              <DollarSign size={14} className="text-zinc-400 mr-0.5" />
              {estimatedValue.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <div className="flex items-center justify-between pb-2">
            <span className="text-xs text-zinc-500">预估手续费 (印花税+佣金)</span>
            <span className="text-sm font-bold text-zinc-600 flex items-center">
              ≈ <DollarSign size={12} className="text-zinc-400 ml-1 mr-0.5" />
              {estimatedFee.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>

          <button
            onClick={handleTrade}
            disabled={(!price && orderType === 'MARKET') || (!targetPriceInput && orderType === 'LIMIT') || !shares || executing || Number(shares) <= 0}
            className={`w-full py-3.5 rounded-xl text-white text-sm font-bold flex items-center justify-center gap-2 transition-all disabled:opacity-50 ${
              action === 'BUY' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-rose-600 hover:bg-rose-700'
            }`}
          >
            {executing ? <Loader2 size={16} className="animate-spin" /> : null}
            确认{orderType === 'MARKET' ? '' : '挂单'}{action === 'BUY' ? '买入' : '卖出'}
          </button>
        </div>
      </div>
    </div>
  );
}
