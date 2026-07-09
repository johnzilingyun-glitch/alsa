import { useEffect, useMemo, useState } from 'react';
import {
  Search,
  RefreshCw,
  AlertTriangle,
  List,
  FileText,
  ClipboardList,
  Bug,
  Clock3,
  Server,
} from 'lucide-react';
import { authFetch } from '../../stores/useAuthStore';

type IncidentIndexItem = {
  timestamp_utc?: string;
  incident_id?: string;
  component?: string;
  job_id?: string;
  symbol?: string;
  market?: string;
  stage?: string;
  error_type?: string;
  error_message?: string;
  path?: string;
  provider_used?: string;
  fallback_depth?: number;
  market_detected?: string;
  data_type?: string;
  cache_hit?: boolean;
  quality_score?: number;
  quality_threshold?: number;
};

type IncidentDetail = {
  index?: IncidentIndexItem;
  incident?: Record<string, unknown>;
  context?: Record<string, unknown>;
  traceback?: string;
  diagnostics?: Record<string, unknown>;
};

type IncidentQueryResponse = {
  success?: boolean;
  data?: {
    query?: Record<string, unknown>;
    items?: IncidentIndexItem[];
    latest?: IncidentDetail | null;
  };
};

function formatDate(value?: string) {
  if (!value) return '-';
  try {
    return new Date(value).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZone: 'Asia/Shanghai',
    });
  } catch {
    return value;
  }
}

function toDisplayString(value: unknown, fallback = '-'): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'string') return value || fallback;
  return String(value);
}

function JsonBlock({ title, data }: { title: string; data: unknown }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
      <div className="px-3 py-2 text-xs font-semibold text-zinc-700 bg-zinc-50 border-b border-zinc-100">{title}</div>
      <pre className="p-3 text-[11px] text-zinc-700 overflow-auto max-h-64 leading-relaxed">
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
    </div>
  );
}

export function IncidentConsole() {
  const [jobId, setJobId] = useState('');
  const [incidentId, setIncidentId] = useState('');
  const [marketFilter, setMarketFilter] = useState('all');
  const [providerFilter, setProviderFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<IncidentIndexItem[]>([]);
  const [detail, setDetail] = useState<IncidentDetail | null>(null);

  const hasInput = useMemo(() => jobId.trim() || incidentId.trim(), [jobId, incidentId]);

  useEffect(() => {
    const hash = window.location.hash || '';
    const queryPart = hash.includes('?') ? hash.split('?')[1] : '';
    if (!queryPart) return;
    const params = new URLSearchParams(queryPart);
    const qJobId = params.get('job_id') || '';
    const qIncidentId = params.get('incident_id') || '';
    if (qJobId) setJobId(qJobId);
    if (qIncidentId) setIncidentId(qIncidentId);
  }, []);

  useEffect(() => {
    if (!hasInput) return;
    const hash = window.location.hash || '';
    const queryPart = hash.includes('?') ? hash.split('?')[1] : '';
    const params = new URLSearchParams(queryPart);
    const hashHasQuery = params.has('job_id') || params.has('incident_id');
    if (!hashHasQuery) return;
    void runQuery();
  }, [hasInput]);

  const runQuery = async () => {
    if (!hasInput) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (jobId.trim()) params.set('job_id', jobId.trim());
      if (incidentId.trim()) params.set('incident_id', incidentId.trim());
      params.set('limit', '30');

      const res = await authFetch(`/api/admin/incident-query?${params.toString()}`);
      const payload = (await res.json().catch(() => ({}))) as IncidentQueryResponse;
      if (!res.ok || !payload?.success) {
        throw new Error((payload as any)?.detail || '查询失败，请检查输入条件');
      }

      const data = payload.data || {};
      const indexItems = Array.isArray(data.items) ? data.items : [];
      setItems(indexItems);
      setDetail((data.latest as IncidentDetail | null) || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '查询失败');
      setItems([]);
      setDetail(null);
    } finally {
      setLoading(false);
    }
  };

  const loadDetailByIncident = async (targetIncidentId: string) => {
    if (!targetIncidentId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`/api/admin/incidents/${encodeURIComponent(targetIncidentId)}`);
      const payload = (await res.json().catch(() => ({}))) as { success?: boolean; data?: IncidentDetail; detail?: string };
      if (!res.ok || !payload?.success) {
        throw new Error(payload?.detail || '加载故障详情失败');
      }
      setDetail(payload.data || null);
      setIncidentId(targetIncidentId);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const selectedIncidentId = detail?.index?.incident_id || detail?.incident?.incident_id;
  const marketOptions = useMemo(() => {
    const markets = new Set<string>();
    items.forEach((it) => {
      if (it.market) markets.add(it.market);
    });
    return ['all', ...Array.from(markets).sort()];
  }, [items]);

  const filteredItems = useMemo(() => {
    return items.filter((it) => {
      const marketOk = marketFilter === 'all' || (it.market || it.market_detected || 'Unknown') === marketFilter;
      const providerOk = providerFilter === 'all' || (it.provider_used || 'Unknown') === providerFilter;
      return marketOk && providerOk;
    });
  }, [items, marketFilter, providerFilter]);

  const providerOptions = useMemo(() => {
    const providers = new Set<string>();
    items.forEach((it) => {
      if (it.provider_used) providers.add(it.provider_used);
    });
    return ['all', ...Array.from(providers).sort()];
  }, [items]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold text-zinc-900">
            <Bug size={20} className="text-rose-500" />
            故障快照中心
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">按任务或事故 ID 检索异常现场，支持一键定位 traceback 与上下文</p>
        </div>
        <button
          onClick={runQuery}
          disabled={!hasInput || loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? <RefreshCw size={13} className="animate-spin" /> : <Search size={13} />}
          查询
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="rounded-xl border border-zinc-200 bg-white p-3">
          <label className="text-xs font-medium text-zinc-600">Job ID</label>
          <input
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            placeholder="例如: job_9f3ac7d1"
            className="mt-1 w-full px-3 py-2 text-sm border border-zinc-200 rounded-lg bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          />
        </div>
        <div className="rounded-xl border border-zinc-200 bg-white p-3">
          <label className="text-xs font-medium text-zinc-600">Incident ID</label>
          <input
            value={incidentId}
            onChange={(e) => setIncidentId(e.target.value)}
            placeholder="例如: inc_104500_ab12cd34"
            className="mt-1 w-full px-3 py-2 text-sm border border-zinc-200 rounded-lg bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="rounded-xl border border-zinc-200 bg-white p-3">
          <label className="text-xs font-medium text-zinc-600">市场过滤</label>
          <select
            value={marketFilter}
            onChange={(e) => setMarketFilter(e.target.value)}
            className="mt-1 w-full px-3 py-2 text-sm border border-zinc-200 rounded-lg bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            {marketOptions.map((m) => (
              <option key={m} value={m}>
                {m === 'all' ? '全部市场' : m}
              </option>
            ))}
          </select>
        </div>
        <div className="rounded-xl border border-zinc-200 bg-white p-3">
          <label className="text-xs font-medium text-zinc-600">Provider 过滤</label>
          <select
            value={providerFilter}
            onChange={(e) => setProviderFilter(e.target.value)}
            className="mt-1 w-full px-3 py-2 text-sm border border-zinc-200 rounded-lg bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
          >
            {providerOptions.map((p) => (
              <option key={p} value={p}>
                {p === 'all' ? '全部 Provider' : p}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 text-red-600 px-4 py-3 text-xs flex items-center gap-2">
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
        <div className="xl:col-span-4 space-y-3">
          <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
            <div className="px-3 py-2 border-b border-zinc-100 bg-zinc-50 text-xs font-semibold text-zinc-700 flex items-center gap-1.5">
              <List size={14} />
              关联故障列表
            </div>
            <div className="max-h-[540px] overflow-auto">
              {filteredItems.length === 0 ? (
                <div className="px-4 py-6 text-xs text-zinc-400">输入 Job ID 后可查看该任务的故障记录列表</div>
              ) : (
                filteredItems.map((item, idx) => {
                  const id = item.incident_id || `row-${idx}`;
                  const active = selectedIncidentId && selectedIncidentId === id;
                  return (
                    <button
                      key={id}
                      onClick={() => item.incident_id && loadDetailByIncident(item.incident_id)}
                      className={`w-full text-left px-3 py-3 border-b border-zinc-100 hover:bg-zinc-50 transition-colors ${active ? 'bg-indigo-50/70' : ''}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[11px] font-semibold text-indigo-700 truncate">{item.incident_id || '-'}</span>
                        <span className="text-[10px] text-zinc-400">{formatDate(item.timestamp_utc)}</span>
                      </div>
                      <div className="mt-1 text-[11px] text-zinc-600 truncate">{item.error_type || 'UnknownError'} · {item.component || '-'}</div>
                      <div className="mt-1 text-[11px] text-zinc-600 truncate">市场: {item.market || item.market_detected || 'Unknown'}</div>
                      <div className="mt-1 text-[11px] text-zinc-600 truncate">Provider: {item.provider_used || 'Unknown'} · fallback: {item.fallback_depth ?? '-'}</div>
                      <div className="mt-1 text-[11px] text-zinc-500 line-clamp-2">{item.error_message || '-'}</div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>

        <div className="xl:col-span-8 space-y-3">
          {!detail ? (
            <div className="rounded-xl border border-zinc-200 bg-white px-4 py-8 text-zinc-400 text-sm">
              暂无详情。请输入 Job ID 或 Incident ID 后点击查询。
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="rounded-xl border border-zinc-200 bg-white p-3">
                  <p className="text-[11px] text-zinc-400">Incident ID</p>
                  <p className="text-sm font-semibold text-zinc-900 break-all">{toDisplayString(detail.index?.incident_id ?? detail.incident?.incident_id)}</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-white p-3">
                  <p className="text-[11px] text-zinc-400">Job ID</p>
                  <p className="text-sm font-semibold text-zinc-900 break-all">{toDisplayString(detail.index?.job_id ?? detail.incident?.job_id)}</p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
                <div className="rounded-xl border border-zinc-200 bg-white p-3">
                  <p className="text-[11px] text-zinc-400 flex items-center gap-1"><Clock3 size={12} /> 时间</p>
                  <p className="text-xs text-zinc-700 mt-1">{formatDate(detail.index?.timestamp_utc || (detail.incident?.timestamp_utc as string))}</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-white p-3">
                  <p className="text-[11px] text-zinc-400 flex items-center gap-1"><Server size={12} /> 组件</p>
                  <p className="text-xs text-zinc-700 mt-1">{(detail.index?.component || detail.incident?.component || '-') as string}</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-white p-3">
                  <p className="text-[11px] text-zinc-400 flex items-center gap-1"><ClipboardList size={12} /> 错误类型</p>
                  <p className="text-xs text-zinc-700 mt-1">{(detail.index?.error_type || detail.incident?.error_type || '-') as string}</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-white p-3">
                  <p className="text-[11px] text-zinc-400 flex items-center gap-1"><ClipboardList size={12} /> 市场</p>
                  <p className="text-xs text-zinc-700 mt-1">{(detail.index?.market || detail.index?.market_detected || detail.incident?.market || '-') as string}</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-white p-3">
                  <p className="text-[11px] text-zinc-400 flex items-center gap-1"><ClipboardList size={12} /> Provider</p>
                  <p className="text-xs text-zinc-700 mt-1">{(detail.index?.provider_used || detail.incident?.provider_used || '-') as string}</p>
                </div>
                <div className="rounded-xl border border-zinc-200 bg-white p-3">
                  <p className="text-[11px] text-zinc-400 flex items-center gap-1"><ClipboardList size={12} /> Fallback</p>
                  <p className="text-xs text-zinc-700 mt-1">{toDisplayString(detail.index?.fallback_depth ?? detail.incident?.fallback_depth)}</p>
                </div>
              </div>

              <JsonBlock title="Incident 元信息" data={detail.incident || detail.index || {}} />
              <JsonBlock title="Context 快照（已脱敏）" data={detail.context || {}} />

              <div className="rounded-xl border border-zinc-200 bg-white overflow-hidden">
                <div className="px-3 py-2 text-xs font-semibold text-zinc-700 bg-zinc-50 border-b border-zinc-100 flex items-center gap-1.5">
                  <FileText size={14} />
                  Traceback
                </div>
                <pre className="p-3 text-[11px] text-zinc-700 overflow-auto max-h-[420px] leading-relaxed whitespace-pre-wrap">
                  {detail.traceback || '(empty)'}
                </pre>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
