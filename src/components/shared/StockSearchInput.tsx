import React, { useState, useEffect, useRef } from 'react';
import { Search, Zap } from 'lucide-react';

interface Suggestion {
  symbol: string;
  name: string;
  exchange?: string;
  market?: string;
  pinyin?: string;
  source?: string;
  fullSymbol?: string;
}

interface StockSearchInputProps {
  value: string;
  market?: string;
  placeholder?: string;
  className?: string;
  onSelect: (symbol: string, market?: string) => void;
  onSubmit?: (symbol: string) => void;
  onChange?: (value: string) => void;
  /** Additional class for the input element */
  inputClassName?: string;
}

export function StockSearchInput({
  value,
  market = 'US-Share',
  placeholder = '输入股票代码 / 名称 / 拼音',
  className = '',
  onSelect,
  onSubmit,
  onChange,
  inputClassName = '',
}: StockSearchInputProps) {
  const [localValue, setLocalValue] = useState(value);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isComposing, setIsComposing] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Sync external value
  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  // Fetch suggestions with debounce
  useEffect(() => {
    const controller = new AbortController();

    const fetchSuggestions = async () => {
      if (!localValue || localValue.trim().length < 1 || isComposing) {
        setSuggestions([]);
        setShowSuggestions(false);
        return;
      }

      try {
        const params = new URLSearchParams();
        params.set('input', localValue);
        params.set('market', market);

        const res = await fetch(`/api/stock/suggest?${params.toString()}`, {
          signal: controller.signal,
        });
        if (res.ok) {
          const data = await res.json();
          setSuggestions(data);
          setShowSuggestions(data.length > 0);
          setSelectedIndex(-1);
        }
      } catch (e: any) {
        if (e.name !== 'AbortError') {
          console.error('Failed to fetch suggestions:', e);
        }
      }
    };

    const timeout = setTimeout(fetchSuggestions, 150);
    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [localValue, market, isComposing]);

  // Click outside to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectSuggestion = (s: Suggestion) => {
    const finalSym = s.symbol || s.fullSymbol || '';
    setLocalValue(finalSym.toUpperCase());
    setShowSuggestions(false);
    onSelect(finalSym.toUpperCase(), s.market);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions || suggestions.length === 0) {
      if (e.key === 'Enter' && onSubmit && localValue.trim()) {
        e.preventDefault();
        onSubmit(localValue.trim().toUpperCase());
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % suggestions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + suggestions.length) % suggestions.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (selectedIndex >= 0) {
        handleSelectSuggestion(suggestions[selectedIndex]);
      } else if (onSubmit && localValue.trim()) {
        setShowSuggestions(false);
        onSubmit(localValue.trim().toUpperCase());
      }
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none z-10" />
      <input
        type="text"
        value={localValue}
        aria-label={placeholder}
        aria-autocomplete="list"
        aria-expanded={showSuggestions && suggestions.length > 0}
        aria-controls="stock-search-suggestions"
        role="combobox"
        placeholder={placeholder}
        onCompositionStart={() => setIsComposing(true)}
        onCompositionEnd={(e) => {
          setIsComposing(false);
          setLocalValue(e.currentTarget.value);
          onChange?.(e.currentTarget.value);
        }}
        onChange={(e) => {
          setLocalValue(e.target.value);
          onChange?.(e.target.value);
        }}
        onFocus={() => {
          if (suggestions.length > 0) setShowSuggestions(true);
        }}
        onKeyDown={handleKeyDown}
        className={`w-full h-12 pl-11 pr-4 rounded-xl border border-zinc-200 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-600/10 focus:border-indigo-600/40 transition-all ${inputClassName}`}
      />

      {/* Suggestions Dropdown */}
      {showSuggestions && suggestions.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-2 z-[60] overflow-hidden rounded-2xl border border-zinc-100 bg-white/95 backdrop-blur-xl shadow-2xl shadow-indigo-600/10 animate-in fade-in slide-in-from-top-2 duration-200">
          <div className="p-1.5 max-h-[320px] overflow-y-auto" id="stock-search-suggestions" role="listbox" aria-label="Stock suggestions">
            {suggestions.map((s, idx) => (
              <button
                key={`suggestion-${s.symbol}-${idx}`}
                type="button"
                role="option"
                aria-selected={idx === selectedIndex}
                onClick={() => handleSelectSuggestion(s)}
                onMouseEnter={() => setSelectedIndex(idx)}
                className={`flex w-full items-center justify-between px-4 py-3 rounded-xl transition-all ${
                  idx === selectedIndex
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-zinc-700 hover:bg-zinc-50'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                      idx === selectedIndex
                        ? 'bg-indigo-100 text-indigo-600'
                        : 'bg-zinc-100 text-zinc-500'
                    }`}
                  >
                    {s.symbol}
                  </span>
                  <span className="font-bold text-sm">{s.name}</span>
                </div>
                <div className="flex items-center gap-2">
                  {s.exchange && (
                    <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">
                      {s.exchange}
                    </span>
                  )}
                  {idx === selectedIndex && (
                    <Zap size={12} className="text-indigo-400 animate-pulse" />
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
