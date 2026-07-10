/**
 * NewArchCompare — 新架构 (v3.1 七层多智能体) 对比测试页面.
 *
 * 通过 hash 路由 #/v2 进入. 调用 POST /api/analysis/v2-pipeline,
 * 展示新架构结构化输出 (FinalDecision / 证据聚合 / 反思 / Guardrail / Trace / Markdown 报告),
 * 与旧流程 (自由文本 HTML 报告) 做直观对比.
 */
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  ArrowLeft, Loader2, Play, Sparkles, ShieldCheck, GitBranch, Scale,
  Activity, AlertTriangle, CheckCircle2, XCircle, Gauge, FileText, ChevronDown,
} from 'lucide-react';
import { Market } from '../types';

// ── 响应类型 (对应 analysis_v2.py 的 _serialize_pipeline_result) ──────────

interface V2Evidence { claim: string; stance: string; confidence: number; source: string[]; agent: string; }
interface V2Claim { claim: string; consensus: number; supporting: V2Evidence[]; contradicting: V2Evidence[]; }
interface V2Risk { category: string; description: string; severity: string; }
interface V2Decision {
  final_score: number; stance: string; action: string; confidence: number;
  summary: string; can_act: boolean; key_claims: string[]; rationale: string; risks: V2Risk[];
}
interface V2Aggregated {
  claims: V2Claim[];
  conflicts: { claim: string; supporting_n: number; contradicting_n: number }[];
  coverage: Record<string, number>;
}
interface V2Critique {
  can_finalize: boolean; round_num: number;
  issues: { severity: string; description: string }[]; rerun_agents: string[];
}
interface V2Guardrail {
  action: string; passed: boolean;
  issues: { severity: string; rule: string; description: string }[];
}
interface V2AgentResult {
  agent_id: string; role: string; status: string;
  score: number; confidence: number; evidence_count: number;
}
interface V2Result {
  status: string; symbol: string; mock?: boolean; architecture?: string;
  decision: V2Decision | null; aggregated: V2Aggregated | null;
  critique: V2Critique | null; guardrail: V2Guardrail | null;
  report: string; trace_summary: Record<string, any>; agent_results: V2AgentResult[];
}

const MARKETS: Market[] = ['A-Share', 'HK-Share', 'US-Share'];

// 流水线阶段 (对应 analysis_pipeline.run 的 _progress 阶段)
const STAGES: { key: string; label: string }[] = [
  { key: 'planning', label: '规划 (Planner)' },
  { key: 'execution', label: '并行执行 (DAG)' },
  { key: 'aggregation', label: '证据聚合' },
  { key: 'reflection', label: '反思' },
  { key: 'decision', label: '决策' },
  { key: 'guardrail', label: 'Guardrail 校验' },
  { key: 'report', label: '报告生成' },
];

type StageStatus = 'pending' | 'running' | 'done';


const stanceColor = (s: string) =>
  s === 'bullish' ? 'text-emerald-600 bg-emerald-50 border-emerald-200'
    : s === 'bearish' ? 'text-rose-600 bg-rose-50 border-rose-200'
      : 'text-zinc-600 bg-zinc-50 border-zinc-200';

const actionLabel: Record<string, string> = {
  buy: '买入', sell: '卖出', hold: '持有', watch: '观望',
};

const severityColor = (s: string) =>
  s === 'high' ? 'text-rose-600 bg-rose-50'
    : s === 'medium' ? 'text-amber-600 bg-amber-50'
      : 'text-zinc-500 bg-zinc-50';

export function NewArchCompare() {
  const [symbol, setSymbol] = useState('AAPL');
  const [market, setMarket] = useState<Market>('US-Share');
  const [question, setQuestion] = useState('');
  const [mock, setMock] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<V2Result | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [stageStatus, setStageStatus] = useState<Record<string, StageStatus>>({});

  const run = async () => {
    if (!symbol.trim()) { setError('请输入股票代码或名称'); return; }
    setLoading(true);
    setError('');
    setResult(null);
    setStageStatus({});
    try {
      if (mock) {
        await runMock();
      } else {
        await runStreaming();
      }
    } catch (e: any) {
      setError(e?.message || '执行失败');
    } finally {
      setLoading(false);
    }
  };

  // 演示模式: 单次 POST
  const runMock = async () => {
    const res = await fetch('/api/analysis/v2-pipeline', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: symbol.trim(), market, question: question.trim(), mock: true }),
    });
    const json = await res.json();
    if (!json.success) throw new Error(json.error?.message || '请求失败');
    setResult(json.data as V2Result);
  };

  // 真实模式: SSE 流式进度
  const runStreaming = async () => {
    const res = await fetch('/api/analysis/v2-pipeline/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ symbol: symbol.trim(), market, question: question.trim(), mock: false }),
    });
    if (!res.ok || !res.body) throw new Error(`流式请求失败: ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith('data:')) continue;
        let ev: any;
        try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }
        handleStreamEvent(ev);
      }
    }
  };

  const handleStreamEvent = (ev: any) => {
    if (ev.stage === 'error') {
      setError(ev.error || '流式执行失败');
      return;
    }
    if (ev.stage === 'result') {
      setStageStatus(prev => {
        const next = { ...prev };
        STAGES.forEach(s => { next[s.key] = 'done'; });
        return next;
      });
      setResult(ev.result as V2Result);
      return;
    }
    // 阶段进度事件: {stage, status}
    if (ev.stage && ev.status) {
      setStageStatus(prev => {
        const next = { ...prev };
        if (ev.status === 'start') {
          next[ev.stage] = 'running';
        } else if (ev.status === 'done') {
          next[ev.stage] = 'done';
        }
        // 前序阶段自动标记完成 (兜底)
        const idx = STAGES.findIndex(s => s.key === ev.stage);
        if (idx > 0) {
          for (let i = 0; i < idx; i++) {
            if (next[STAGES[i].key] !== 'done') next[STAGES[i].key] = 'done';
          }
        }
        return next;
      });
    }
  };

  const d = result?.decision;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => { window.location.hash = '#/'; }}
          className="btn-secondary w-11 h-11 p-0 flex items-center justify-center rounded-xl"
          title="返回首页"
        >
          <ArrowLeft size={20} strokeWidth={1.5} />
        </button>
        <div>
          <div className="flex items-center gap-2">
            <Sparkles size={20} className="text-indigo-600" />
            <h1 className="text-2xl font-bold tracking-tight text-zinc-900">新架构对比测试</h1>
            <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-full bg-indigo-100 text-indigo-700">v3.1</span>
          </div>
          <p className="mt-1 text-sm text-zinc-500">
            七层多智能体流水线 · Planner → DAG → 证据聚合 → 反思 → 决策 → Guardrail → 报告
          </p>
        </div>
      </div>

      {/* Old vs New explainer */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-zinc-200 bg-white p-5">
          <h3 className="text-sm font-bold text-zinc-700 mb-2">旧流程 (运行中)</h3>
          <ul className="text-xs text-zinc-500 space-y-1.5 leading-relaxed">
            <li>· 固定拓扑 QUICK/STANDARD/DEEP 多专家讨论</li>
            <li>· 输出自由文本 HTML 报告 (截断 2000 字)</li>
            <li>· 全程 Pro 模型, 上下文只读上一轮</li>
            <li>· 通过 /api/analysis/jobs 异步排队生成</li>
          </ul>
        </div>
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50/40 p-5">
          <h3 className="text-sm font-bold text-indigo-700 mb-2">新架构 (本页测试)</h3>
          <ul className="text-xs text-indigo-600/80 space-y-1.5 leading-relaxed">
            <li>· Planner 动态规划 + DAG 动态并行</li>
            <li>· 结构化 FinalDecision (评分/立场/行动/置信/可执行)</li>
            <li>· 证据可追溯聚合 (stance 维度 + 冲突标记)</li>
            <li>· 可回溯反思 + Guardrail 拦截 + 全链路 Trace</li>
          </ul>
        </div>
      </div>

      {/* Input form */}
      <div className="rounded-2xl border border-zinc-200 bg-white p-5">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
          <div className="md:col-span-3">
            <label className="block text-xs font-medium text-zinc-500 mb-1.5">股票代码 / 名称</label>
            <input
              value={symbol}
              onChange={e => setSymbol(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') run(); }}
              placeholder="AAPL / 600519 / 0700.HK"
              className="w-full px-3 py-2.5 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400"
            />
          </div>
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-zinc-500 mb-1.5">市场</label>
            <select
              value={market}
              onChange={e => setMarket(e.target.value as Market)}
              className="w-full px-3 py-2.5 rounded-xl border border-zinc-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400"
            >
              {MARKETS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="md:col-span-4">
            <label className="block text-xs font-medium text-zinc-500 mb-1.5">分析问题 (可选)</label>
            <input
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') run(); }}
              placeholder="例如: 当前是否适合买入?"
              className="w-full px-3 py-2.5 rounded-xl border border-zinc-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400"
            />
          </div>
          <div className="md:col-span-3 flex items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-zinc-600 cursor-pointer select-none whitespace-nowrap">
              <input type="checkbox" checked={mock} onChange={e => setMock(e.target.checked)} className="rounded" />
              演示模式
            </label>
            <button
              onClick={run}
              disabled={loading}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {loading ? '运行中' : '运行'}
            </button>
          </div>
        </div>
        <p className="mt-3 text-[11px] text-zinc-400">
          {mock
            ? '演示模式: 返回样例结构化输出, 无需 LLM/数据环境, 用于查看新架构输出形态。'
            : '真实模式: 调用 analysis_pipeline.run_streaming() 执行完整流水线, 通过 SSE 实时推送各阶段进度 (需 LLM + 数据环境)。'}
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600 flex items-center gap-2">
          <AlertTriangle size={16} /> {error}
        </div>
      )}

      {/* 实时进度 (真实模式流式) */}
      {!mock && (loading || Object.keys(stageStatus).length > 0) && (
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50/30 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={16} className="text-indigo-600" />
            <span className="text-sm font-bold text-zinc-800">实时进度 (SSE 流式)</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            {STAGES.map((s, i) => {
              const st = stageStatus[s.key] || 'pending';
              return (
                <div key={s.key} className="flex flex-col items-center text-center gap-1.5">
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center transition-colors ${
                    st === 'done' ? 'bg-emerald-100 text-emerald-600'
                      : st === 'running' ? 'bg-indigo-600 text-white'
                        : 'bg-zinc-100 text-zinc-300'
                  }`}>
                    {st === 'done' ? <CheckCircle2 size={16} />
                      : st === 'running' ? <Loader2 size={16} className="animate-spin" />
                        : <span className="text-xs font-bold">{i + 1}</span>}
                  </div>
                  <span className={`text-[10px] leading-tight ${st === 'pending' ? 'text-zinc-400' : 'text-zinc-600 font-medium'}`}>
                    {s.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6">
          {result.architecture && (
            <div className="text-xs text-zinc-400">
              架构: {result.architecture}{result.mock ? ' · 演示数据' : ''}
            </div>
          )}

          {/* Final Decision */}
          {d && (
            <div className="rounded-2xl border border-zinc-200 bg-white overflow-hidden">
              <div className="px-5 py-3 border-b border-zinc-100 flex items-center gap-2">
                <Scale size={16} className="text-indigo-600" />
                <span className="text-sm font-bold text-zinc-800">最终决策 · {result.symbol}</span>
              </div>
              <div className="p-5 space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Metric label="综合评分" value={(d.final_score * 100).toFixed(0)} suffix="/100" />
                  <div>
                    <div className="text-xs text-zinc-400 mb-1">立场</div>
                    <span className={`inline-block px-2.5 py-1 text-xs font-bold rounded-lg border ${stanceColor(d.stance)}`}>
                      {d.stance}
                    </span>
                  </div>
                  <div>
                    <div className="text-xs text-zinc-400 mb-1">行动</div>
                    <span className="text-lg font-bold text-zinc-900">{actionLabel[d.action] || d.action}</span>
                  </div>
                  <Metric label="置信度" value={(d.confidence * 100).toFixed(0)} suffix="%" />
                </div>

                <div className="flex items-center gap-2 text-sm">
                  {d.can_act
                    ? <span className="flex items-center gap-1.5 text-emerald-600 font-medium"><CheckCircle2 size={15} /> 可执行</span>
                    : <span className="flex items-center gap-1.5 text-zinc-400 font-medium"><XCircle size={15} /> 不建议执行</span>}
                </div>

                <p className="text-sm text-zinc-700 leading-relaxed">{d.summary}</p>

                {d.key_claims?.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-zinc-500 mb-2">关键论点</div>
                    <ul className="space-y-1">
                      {d.key_claims.map((c, i) => (
                        <li key={i} className="text-xs text-zinc-600 flex items-start gap-2">
                          <span className="mt-1 h-1 w-1 rounded-full bg-indigo-400 flex-shrink-0" />{c}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {d.rationale && (
                  <div className="rounded-xl bg-zinc-50 px-4 py-3 text-xs text-zinc-500 leading-relaxed">
                    <span className="font-semibold text-zinc-600">决策依据: </span>{d.rationale}
                  </div>
                )}

                {d.risks?.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-zinc-500 mb-2">风险</div>
                    <div className="space-y-1.5">
                      {d.risks.map((r, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <span className={`px-1.5 py-0.5 rounded font-medium ${severityColor(r.severity)}`}>{r.severity}</span>
                          <span className="text-zinc-400">[{r.category}]</span>
                          <span className="text-zinc-600">{r.description}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Agent results */}
          {result.agent_results?.length > 0 && (
            <Section icon={<Activity size={16} className="text-indigo-600" />} title="Agent 执行结果">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {result.agent_results.map((a, i) => (
                  <div key={i} className="rounded-xl border border-zinc-100 bg-zinc-50/50 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-semibold text-zinc-800">{a.role}</span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${a.status === 'ok' ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'}`}>{a.status}</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-zinc-500">
                      <span>评分 <b className="text-zinc-700">{(a.score * 100).toFixed(0)}</b></span>
                      <span>置信 <b className="text-zinc-700">{(a.confidence * 100).toFixed(0)}%</b></span>
                      <span>证据 <b className="text-zinc-700">{a.evidence_count}</b></span>
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {/* Aggregated evidence */}
          {result.aggregated && (
            <Section icon={<GitBranch size={16} className="text-indigo-600" />} title="证据聚合">
              <div className="space-y-3">
                {result.aggregated.claims.map((c, i) => (
                  <div key={i} className="rounded-xl border border-zinc-100 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-zinc-800">{c.claim}</span>
                      <span className="text-xs text-zinc-400">共识 {(c.consensus * 100).toFixed(0)}%</span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      <EvidenceList label="支持" items={c.supporting} tone="emerald" />
                      <EvidenceList label="反对" items={c.contradicting} tone="rose" />
                    </div>
                  </div>
                ))}
                {result.aggregated.conflicts.length > 0 && (
                  <div className="text-xs text-amber-600 flex items-center gap-2">
                    <AlertTriangle size={14} /> 检测到 {result.aggregated.conflicts.length} 处证据冲突
                  </div>
                )}
              </div>
            </Section>
          )}

          {/* Critique + Guardrail */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {result.critique && (
              <Section icon={<Gauge size={16} className="text-indigo-600" />} title={`反思 (第 ${result.critique.round_num} 轮)`}>
                <div className="flex items-center gap-2 mb-3 text-sm">
                  {result.critique.can_finalize
                    ? <span className="flex items-center gap-1.5 text-emerald-600"><CheckCircle2 size={15} /> 可定稿</span>
                    : <span className="flex items-center gap-1.5 text-amber-600"><AlertTriangle size={15} /> 需回溯</span>}
                </div>
                {result.critique.issues.map((iss, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs mb-1.5">
                    <span className={`px-1.5 py-0.5 rounded font-medium ${severityColor(iss.severity)}`}>{iss.severity}</span>
                    <span className="text-zinc-600">{iss.description}</span>
                  </div>
                ))}
                {result.critique.rerun_agents.length > 0 && (
                  <div className="text-xs text-zinc-400 mt-2">需重跑: {result.critique.rerun_agents.join(', ')}</div>
                )}
              </Section>
            )}

            {result.guardrail && (
              <Section icon={<ShieldCheck size={16} className="text-indigo-600" />} title="输出 Guardrail">
                <div className="flex items-center gap-2 mb-3 text-sm">
                  {result.guardrail.passed
                    ? <span className="flex items-center gap-1.5 text-emerald-600"><CheckCircle2 size={15} /> 通过 ({result.guardrail.action})</span>
                    : <span className="flex items-center gap-1.5 text-rose-600"><XCircle size={15} /> 拦截 ({result.guardrail.action})</span>}
                </div>
                {result.guardrail.issues.length === 0
                  ? <p className="text-xs text-zinc-400">无质量问题</p>
                  : result.guardrail.issues.map((iss, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs mb-1.5">
                      <span className={`px-1.5 py-0.5 rounded font-medium ${severityColor(iss.severity)}`}>{iss.severity}</span>
                      <span className="text-zinc-400">[{iss.rule}]</span>
                      <span className="text-zinc-600">{iss.description}</span>
                    </div>
                  ))}
              </Section>
            )}
          </div>

          {/* Trace summary */}
          {result.trace_summary && Object.keys(result.trace_summary).length > 0 && (
            <Section icon={<Activity size={16} className="text-indigo-600" />} title="全链路 Trace">
              <div className="flex flex-wrap items-center gap-4 text-xs text-zinc-500">
                <span>Trace ID: <b className="text-zinc-700">{result.trace_summary.trace_id}</b></span>
                <span>Span 数: <b className="text-zinc-700">{result.trace_summary.span_count}</b></span>
                <span>总耗时: <b className="text-zinc-700">{result.trace_summary.total_duration_ms} ms</b></span>
                {Array.isArray(result.trace_summary.failed_spans) && (
                  <span>失败 Span: <b className="text-zinc-700">{result.trace_summary.failed_spans.length}</b></span>
                )}
              </div>
            </Section>
          )}

          {/* Markdown report */}
          {result.report && (
            <div className="rounded-2xl border border-zinc-200 bg-white overflow-hidden">
              <button
                onClick={() => setShowReport(!showReport)}
                className="w-full px-5 py-3 flex items-center justify-between hover:bg-zinc-50 transition-colors"
              >
                <span className="flex items-center gap-2 text-sm font-bold text-zinc-800">
                  <FileText size={16} className="text-indigo-600" /> Markdown 报告
                </span>
                <ChevronDown size={18} className={`text-zinc-400 transition-transform ${showReport ? 'rotate-180' : ''}`} />
              </button>
              {showReport && (
                <div className="px-6 py-5 border-t border-zinc-100 prose prose-sm prose-zinc max-w-none">
                  <ReactMarkdown>{result.report}</ReactMarkdown>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 子组件 ──────────────────────────────────────────────────────────────

function Metric({ label, value, suffix }: { label: string; value: string; suffix?: string }) {
  return (
    <div>
      <div className="text-xs text-zinc-400 mb-1">{label}</div>
      <div className="text-lg font-bold text-zinc-900">{value}<span className="text-xs font-normal text-zinc-400">{suffix}</span></div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-zinc-200 bg-white overflow-hidden">
      <div className="px-5 py-3 border-b border-zinc-100 flex items-center gap-2">
        {icon}
        <span className="text-sm font-bold text-zinc-800">{title}</span>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function EvidenceList({ label, items, tone }: { label: string; items: V2Evidence[]; tone: 'emerald' | 'rose' }) {
  const c = tone === 'emerald' ? 'text-emerald-600' : 'text-rose-600';
  return (
    <div>
      <div className={`text-[11px] font-semibold mb-1 ${c}`}>{label} ({items.length})</div>
      {items.length === 0
        ? <p className="text-[11px] text-zinc-300">—</p>
        : items.map((e, i) => (
          <div key={i} className="text-[11px] text-zinc-500 mb-1">
            {e.claim} <span className="text-zinc-300">· {(e.confidence * 100).toFixed(0)}%</span>
          </div>
        ))}
    </div>
  );
}
