/**
 * ThsKlineChart — 同花顺 K线图组件
 *
 * Reusable candlestick chart using lightweight-charts (same engine as IBKR dashboard).
 * Accepts THS KlineBar[] data and handles rendering, MA lines, volume, and crosshair legend.
 */
import { useRef, useEffect, useState } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
} from 'lightweight-charts';
import { RefreshCw, AlertCircle } from 'lucide-react';
import type { KlineBar } from '../../services/api/thsClient';

interface ThsKlineChartProps {
  data: KlineBar[];
  interval: string;
  onIntervalChange: (interval: string) => void;
  loading: boolean;
  height?: number;
}

export function ThsKlineChart({ data, interval, onIntervalChange, loading, height = 400 }: ThsKlineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const [chartError, setChartError] = useState<string | null>(null);
  const chartRef = useRef<{
    chart: IChartApi;
    candleSeries: ReturnType<IChartApi['addSeries']>;
    volumeSeries: ReturnType<IChartApi['addSeries']>;
    ma5Series: ReturnType<IChartApi['addSeries']>;
    ma20Series: ReturnType<IChartApi['addSeries']>;
    _candleData?: CandlestickData[];
    _maData?: { ma5: LineData[]; ma20: LineData[] };
  } | null>(null);

  // ── 1. Initialize chart once ──────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    let chart: IChartApi;
    try {
      chart = createChart(containerRef.current, {
        autoSize: true,
        layout: {
          background: { type: ColorType.Solid, color: 'white' },
          textColor: '#333',
        },
        grid: {
          vertLines: { color: '#f0f0f0' },
          horzLines: { color: '#f0f0f0' },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#dfdfdf' },
        timeScale: { borderColor: '#dfdfdf', timeVisible: true, secondsVisible: false },
      });
    } catch (e: any) {
      setChartError('图表初始化失败: ' + (e?.message || 'unknown'));
      return;
    }

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#ef4444',
      downColor: '#10b981',
      borderVisible: false,
      wickUpColor: '#ef4444',
      wickDownColor: '#10b981',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const ma5Series = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
      crosshairMarkerVisible: false,
    });
    const ma20Series = chart.addSeries(LineSeries, {
      color: '#8b5cf6',
      lineWidth: 2,
      crosshairMarkerVisible: false,
    });

    // ── Crosshair legend ──
    chart.subscribeCrosshairMove((param) => {
      const el = legendRef.current;
      if (!el) return;

      if (param.time && param.seriesData.has(candleSeries)) {
        const d = param.seriesData.get(candleSeries) as any;
        const m5 = param.seriesData.get(ma5Series) as any;
        const m20 = param.seriesData.get(ma20Series) as any;
        const candleList = chartRef.current?._candleData ?? [];
        let prev: any = null;
        const idx = candleList.findIndex((c) => c.time === param.time);
        if (idx > 0) prev = candleList[idx - 1];
        renderLegend(el, d, prev, m5?.value, m20?.value);
        el.style.opacity = '1';
      } else {
        const candleList = chartRef.current?._candleData ?? [];
        if (candleList.length > 0) {
          const latest = candleList[candleList.length - 1];
          const prev = candleList.length > 1 ? candleList[candleList.length - 2] : null;
          const ma = chartRef.current?._maData;
          const last5 = ma?.ma5?.at(-1);
          const last20 = ma?.ma20?.at(-1);
          renderLegend(el, latest, prev, last5?.value, last20?.value);
          el.style.opacity = '1';
        } else {
          el.style.opacity = '0';
        }
      }
    });

    chartRef.current = { chart, candleSeries, volumeSeries, ma5Series, ma20Series };

    return () => {
      try { chart.remove(); } catch { /* ignore */ }
      chartRef.current = null;
    };
  }, []);

  // ── 2. Apply data when data/interval changes ──────────────
  useEffect(() => {
    const ref = chartRef.current;
    if (!ref) return;

    if (data.length === 0) {
      // Clear old data instead of showing stale candles
      try {
        ref.candleSeries.setData([]);
        ref.volumeSeries.setData([]);
        ref.ma5Series.setData([]);
        ref.ma20Series.setData([]);
      } catch { /* ignore */ }
      ref._candleData = [];
      ref._maData = { ma5: [], ma20: [] };
      return;
    }

    const { chart, candleSeries, volumeSeries, ma5Series, ma20Series } = ref;
    const isIntraday = interval.includes('m');

    const raw: Array<{ time: Time; open: number; high: number; low: number; close: number; volume: number }> = [];

    for (const bar of data) {
      const rawTime = bar['时间'];
      if (rawTime == null || rawTime === '') continue;

      let time: Time;
      if (isIntraday) {
        // Handle "2024-01-15 09:30:00", "2024-01-15T09:30:00",
        //        "2024-01-15T09:30:00+08:00" (with timezone from backend)
        const ts = rawTime.includes('T') ? rawTime : rawTime.replace(' ', 'T');
        const hasTz = /[+-]\d{2}:\d{2}$/.test(ts);
        const ms = new Date(hasTz ? ts : ts + '+08:00').getTime();
        if (isNaN(ms)) continue;
        time = Math.floor(ms / 1000) as Time;
      } else {
        // Handle "2024-01-15", "2024-01-15 00:00:00", "2024-01-15T00:00:00"
        const datePart = rawTime.split(/[T ]/)[0];
        if (!/^\d{4}-\d{2}-\d{2}$/.test(datePart)) continue;
        time = datePart as Time;
      }

      const open = bar['开盘价'];
      const high = bar['最高价'];
      const low = bar['最低价'];
      const close = bar['收盘价'];

      // Validate numeric fields
      if (open == null || high == null || low == null || close == null) continue;
      if (isNaN(open) || isNaN(high) || isNaN(low) || isNaN(close)) continue;

      raw.push({ time, open, high, low, close, volume: bar['成交量'] ?? 0 });
    }

    if (raw.length === 0) {
      setChartError('K线数据格式异常');
      return;
    }

    // Sort by time — ensures monotonically increasing timestamps
    raw.sort((a, b) => {
      if (typeof a.time === 'number' && typeof b.time === 'number') return a.time - b.time;
      return String(a.time).localeCompare(String(b.time));
    });

    // Deduplicate by time
    const seen = new Set<string | number>();
    const candleData: CandlestickData[] = [];
    const volumeData: HistogramData[] = [];

    for (const r of raw) {
      const key = String(r.time);
      if (seen.has(key)) continue;
      seen.add(key);
      candleData.push({ time: r.time, open: r.open, high: r.high, low: r.low, close: r.close });
      volumeData.push({ time: r.time, value: r.volume, color: r.close >= r.open ? '#ef444488' : '#10b98188' });
    }

    if (candleData.length === 0) {
      setChartError('K线数据格式异常');
      return;
    }

    setChartError(null);

    try {
      candleSeries.setData(candleData);
    } catch (e: any) {
      setChartError('蜡烛图渲染失败: ' + (e?.message || ''));
      return;
    }

    try {
      volumeSeries.setData(volumeData);
    } catch (e: any) {
      console.error('[ThsKlineChart] Volume render error:', e);
    }

    // Moving averages (only if enough data)
    const calcMA = (d: CandlestickData[], period: number): LineData[] => {
      if (d.length < period) return [];
      const out: LineData[] = [];
      for (let i = period - 1; i < d.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) sum += d[i - j].close;
        out.push({ time: d[i].time, value: sum / period });
      }
      return out;
    };

    const ma5Data = calcMA(candleData, 5);
    const ma20Data = calcMA(candleData, 20);

    try { ma5Series.setData(ma5Data); } catch { /* skip */ }
    try { ma20Series.setData(ma20Data); } catch { /* skip */ }

    ref._candleData = candleData;
    ref._maData = { ma5: ma5Data, ma20: ma20Data };

    try {
      chart.timeScale().fitContent();
    } catch { /* skip */ }

    // Show latest in legend
    if (legendRef.current) {
      const latest = candleData[candleData.length - 1];
      const prev = candleData.length > 1 ? candleData[candleData.length - 2] : null;
      const last5 = ma5Data.at(-1);
      const last20 = ma20Data.at(-1);
      renderLegend(legendRef.current, latest, prev, last5?.value, last20?.value);
      legendRef.current.style.opacity = '1';
    }
  }, [data, interval]);

  const intervals = ['1m', '5m', '15m', '30m', '60m', 'day'];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-zinc-500">K线图</h3>
        <div className="flex gap-1 bg-zinc-100 p-0.5 rounded-lg">
          {intervals.map((iv) => (
            <button
              key={iv}
              onClick={() => onIntervalChange(iv)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                interval === iv
                  ? 'bg-white text-indigo-600 shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-700'
              }`}
            >
              {iv}
            </button>
          ))}
        </div>
      </div>
      <div className="relative border border-zinc-200 rounded-2xl overflow-hidden" style={{ height }}>
        {/* Floating legend */}
        <div
          ref={legendRef}
          className="absolute top-3 left-3 z-10 pointer-events-none transition-opacity duration-150"
          style={{ opacity: 0 }}
        />
        {/* Chart container */}
        <div ref={containerRef} className="absolute inset-0 bg-white" />
        {loading && (
          <div className="absolute inset-0 bg-white/50 backdrop-blur-sm flex items-center justify-center z-10">
            <RefreshCw size={24} className="animate-spin text-indigo-600" />
          </div>
        )}
        {!loading && chartError && (
          <div className="absolute inset-0 bg-white/80 flex items-center justify-center z-20 text-rose-500 text-sm gap-2">
            <AlertCircle size={16} />
            {chartError}
          </div>
        )}
        {!loading && !chartError && data.length === 0 && (
          <div className="absolute inset-0 bg-white/80 flex items-center justify-center z-20 text-zinc-400 text-sm">
            暂无K线数据
          </div>
        )}
      </div>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────

function renderLegend(
  el: HTMLDivElement,
  data: { open: number; high: number; low: number; close: number } | undefined | null,
  prevData?: { close: number } | null,
  ma5Val?: number,
  ma20Val?: number,
): void {
  el.replaceChildren();
  if (!data) return;

  const safe = (value: number | undefined | null, fallback = '--') => (
    value != null && Number.isFinite(value) ? value.toFixed(2) : fallback
  );
  const open = safe(data.open);
  const high = safe(data.high);
  const low = safe(data.low);
  const close = safe(data.close);

  let change = 0;
  let pct = 0;
  if (Number.isFinite(data.close) && Number.isFinite(data.open)) {
    change = data.close - data.open;
    pct = data.open !== 0 ? (change / data.open) * 100 : 0;
    if (prevData?.close && Number.isFinite(prevData.close)) {
      change = data.close - prevData.close;
      pct = prevData.close !== 0 ? (change / prevData.close) * 100 : 0;
    }
  }

  const isUp = change >= 0;
  const sign = isUp ? '+' : '';
  const valueClass = isUp ? 'text-red-500' : 'text-emerald-500';
  const wrapper = document.createElement('div');
  wrapper.className = 'flex items-center gap-3 bg-white/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-zinc-200 shadow-sm text-[11px] md:text-[13px] font-medium flex-wrap';

  appendLegendMetric(wrapper, '?', open, valueClass);
  appendLegendMetric(wrapper, '?', high, valueClass);
  appendLegendMetric(wrapper, '?', low, valueClass);
  appendLegendMetric(wrapper, '?', close, `${valueClass} font-bold`);
  appendMovingAverage(wrapper, 'MA5', ma5Val, 'text-[#f59e0b] ml-2');
  appendMovingAverage(wrapper, 'MA20', ma20Val, 'text-[#8b5cf6] ml-2');

  const pctNode = document.createElement('span');
  pctNode.className = `${valueClass} ml-1 font-semibold`;
  pctNode.textContent = `${sign}${pct.toFixed(2)}%`;
  wrapper.appendChild(pctNode);
  el.appendChild(wrapper);
}

function appendLegendMetric(parent: HTMLElement, label: string, value: string, valueClass: string): void {
  const item = document.createElement('span');
  const labelNode = document.createElement('span');
  labelNode.className = 'text-zinc-400 mr-1';
  labelNode.textContent = label;
  const valueNode = document.createElement('span');
  valueNode.className = valueClass;
  valueNode.textContent = value;
  item.append(labelNode, valueNode);
  parent.appendChild(item);
}

function appendMovingAverage(parent: HTMLElement, label: string, value: number | undefined, className: string): void {
  if (value == null || !Number.isFinite(value)) return;
  const node = document.createElement('span');
  node.className = className;
  node.textContent = `${label}: ${value.toFixed(2)}`;
  parent.appendChild(node);
}
