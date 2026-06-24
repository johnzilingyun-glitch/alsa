import { useState, useEffect, useCallback } from 'react';
import {
  Activity, Cpu, Zap, RefreshCw, Square, AlertTriangle, CheckCircle,
  Clock, TrendingUp, Database, Wifi, WifiOff, ChevronDown, ChevronUp,
  BarChart2, Radio, Eye, EyeOff, Trash2, Info, Users, RotateCcw, X
} from 'lucide-react';
import { useConfigStore } from '../../stores/useConfigStore';
import { useUIStore } from '../../stores/useUIStore';
import { useMarketStore } from '../../stores/useMarketStore';
import { useStatsStore } from '../../stores/useStatsStore';

interface BackgroundTask {
  id: string;
  name: string;
  description: string;
  category: 'market' | 'ai' | 'sync' | 'poll';
  status: 'running' | 'idle' | 'error';
  interval?: number; // ms
  lastRun?: number;
  consumesTokens: boolean;
  isControllable: boolean;
}

interface ApiJobInfo {
  job_id: string;
  status: string;
  type: string;
  created_at: string;
  progress?: any;
}

function formatTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function formatTime(ms: number | undefined) {
  if (!ms) return '—';
  const diff = Date.now() - ms;
  if (diff < 60_000) return `${Math.round(diff / 1000)}秒前`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}分钟前`;
  return `${Math.round(diff / 3_600_000)}小时前`;
}

const TASK_REGISTRY: BackgroundTask[] = [
  {
    id: 'price_sync',
    name: '价格实时同步',
    description: '每30秒同步关注列表和搜索记录的实时股价（MarketOverview 组件），调用 /api/market/quotes，不消耗 AI Token',
    category: 'sync',
    status: 'running',
    interval: 30_000,
    consumesTokens: false,
    isControllable: false,
  },
  {
    id: 'market_auto_refresh',
    name: '市场概览自动刷新',
    description: '根据用户设置的间隔（默认关闭）自动重新运行 AI 市场综合分析，此任务消耗大量 Token',
    category: 'ai',
    status: 'idle',
    consumesTokens: true,
    isControllable: true,
  },
  {
    id: 'sector_scan_poll',
    name: '板块扫描轮询',
    description: '板块扫描进行中时，每3秒轮询 /api/sector/run/:jobId 查询进度，不直接消耗前端 Token',
    category: 'poll',
    status: 'idle',
    interval: 3_000,
    consumesTokens: false,
    isControllable: false,
  },
  {
    id: 'sector_analyze_poll',
    name: '板块分析轮询',
    description: '板块深度分析进行中时，每3秒轮询 /api/sector/analyze/:jobId 查询进度，AI Token 由 Python 服务消耗',
    category: 'poll',
    status: 'idle',
    interval: 3_000,
    consumesTokens: false,
    isControllable: false,
  },
  {
    id: 'alert_price_sync',
    name: '价格预警价格同步',
    description: '每30秒同步价格预警列表的实时价格（InstitutionalAlertPanel），调用 /api/alerts/prices，不消耗 AI Token',
    category: 'sync',
    status: 'running',
    interval: 30_000,
    consumesTokens: false,
    isControllable: false,
  },
];

function StatusDot({ status }: { status: 'running' | 'idle' | 'error' }) {
  const colors = {
    running: 'bg-emerald-400 animate-pulse',
    idle: 'bg-zinc-300',
    error: 'bg-red-400',
  };
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status]}`} />;
}

function CategoryBadge({ category }: { category: BackgroundTask['category'] }) {
  const styles = {
    ai: 'bg-violet-100 text-violet-700',
    market: 'bg-blue-100 text-blue-700',
    sync: 'bg-emerald-100 text-emerald-700',
    poll: 'bg-amber-100 text-amber-700',
  };
  const labels = { ai: 'AI分析', market: '市场数据', sync: '价格同步', poll: '进度轮询' };
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${styles[category]}`}>
      {labels[category]}
    </span>
  );
}

export function SystemMonitor() {
  const { tokenUsage, dailyTokenBudget, setDailyTokenBudget, config, resetTokenUsage } = useConfigStore();
  const { autoRefreshInterval, analysisActivity, overviewLoading } = useUIStore();
  const { marketOverviews } = useMarketStore();
  const { stats } = useStatsStore();

  const [apiJobs, setApiJobs] = useState<ApiJobInfo[]>([]);
  const [apiJobsLoading, setApiJobsLoading] = useState(false);
  const [debugLogs, setDebugLogs] = useState<any[]>([]);
  const [showDebugLogs, setShowDebugLogs] = useState(false);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState(Date.now());
  const [isBudgetModalOpen, setIsBudgetModalOpen] = useState(false);
  const [budgetInput, setBudgetInput] = useState('');

  const fetchApiJobs = useCallback(async () => {
    setApiJobsLoading(true);
    try {
      const [sectorRes, analysisRes] = await Promise.allSettled([
        fetch('/api/sector/jobs?limit=10').then(r => r.ok ? r.json() : null),
        fetch('/api/analysis/jobs?limit=10').then(r => r.ok ? r.json() : null),
      ]);

      const jobs: ApiJobInfo[] = [];

      if (sectorRes.status === 'fulfilled' && sectorRes.value?.data) {
        (sectorRes.value.data as any[]).forEach(j => jobs.push({
          job_id: j.job_id,
          status: j.status,
          type: 'sector',
          created_at: j.created_at,
          progress: j.progress,
        }));
      }
      if (analysisRes.status === 'fulfilled' && analysisRes.value?.data) {
        (analysisRes.value.data as any[]).forEach(j => jobs.push({
          job_id: j.job_id || j.id,
          status: j.status,
          type: 'analysis',
          created_at: j.created_at,
          progress: j.progress,
        }));
      }

      setApiJobs(jobs);
    } catch (e) {
      console.error('Failed to fetch API jobs', e);
    } finally {
      setApiJobsLoading(false);
    }
  }, []);

  const fetchDebugLogs = useCallback(async () => {
    try {
      const res = await fetch('/api/logs/debug?limit=20');
      if (res.ok) {
        const data = await res.json();
        setDebugLogs(data?.logs || []);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchApiJobs();
    fetchDebugLogs();
  }, [fetchApiJobs, fetchDebugLogs, lastRefreshed]);

  // Derive actual task statuses from store state
  const tasksWithStatus = TASK_REGISTRY.map(task => {
    let status: 'running' | 'idle' | 'error' = task.status;
    if (task.id === 'market_auto_refresh') {
      status = autoRefreshInterval > 0 ? 'running' : 'idle';
    } else if (task.id === 'price_sync' || task.id === 'alert_price_sync') {
      status = 'running'; // always active when on home page
    }
    return { ...task, status };
  });

  const dailyPct = dailyTokenBudget > 0 ? Math.min(100, (tokenUsage.dailyTotal / dailyTokenBudget) * 100) : 0;
  const runningAiJobs = apiJobs.filter(j => j.status === 'running' || j.status === 'pending');

  return (
    <div className="space-y-8">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-semibold text-zinc-900">
            <Activity size={20} className="text-indigo-500" />
            系统监控后台
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">实时查看后台任务、Token 消耗来源与 API 任务队列</p>
        </div>
        <button
          onClick={() => setLastRefreshed(Date.now())}
          className="flex items-center gap-1.5 text-xs font-medium text-zinc-500 hover:text-zinc-700 px-3 py-1.5 rounded-xl border border-zinc-200 hover:bg-zinc-50 transition-all"
        >
          <RefreshCw size={12} />
          刷新
        </button>
      </div>

      {/* ── Token Usage ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: '本次会话用量', value: formatTokens(tokenUsage.totalTokens), sub: '内存累计（刷新重置）', color: 'text-zinc-900', icon: <Zap size={16} className="text-amber-500" /> },
          { label: '今日用量', value: formatTokens(tokenUsage.dailyTotal), sub: dailyTokenBudget > 0 ? `预算 ${formatTokens(dailyTokenBudget)}` : '无限制', color: dailyPct > 80 ? 'text-red-600' : 'text-zinc-900', icon: <BarChart2 size={16} className="text-indigo-500" /> },
          { label: '本周用量', value: formatTokens(tokenUsage.weeklyTotal), sub: '每周统计（持久化）', color: 'text-zinc-900', icon: <TrendingUp size={16} className="text-emerald-500" /> },
          { label: '本月用量', value: formatTokens(tokenUsage.monthlyTotal), sub: '每月统计（持久化）', color: 'text-zinc-900', icon: <Database size={16} className="text-violet-500" /> },
        ].map(item => (
          <div key={item.label} className="bg-white rounded-2xl border border-zinc-100 p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-2">{item.icon}<p className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">{item.label}</p></div>
            <p className={`text-2xl font-black font-mono ${item.color}`}>{item.value}</p>
            <p className="text-[10px] text-zinc-400 mt-0.5">{item.sub}</p>
          </div>
        ))}
      </div>

      {/* Token reset */}
      <div className="flex justify-end">
        <button
          onClick={() => {
            if (window.confirm('确定要清零所有 Token 统计数据吗？此操作不可撤销。')) {
              resetTokenUsage();
            }
          }}
          className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-red-500 transition-colors px-3 py-1.5 rounded-xl border border-zinc-200 hover:border-red-200 hover:bg-red-50"
        >
          <RotateCcw size={11} />
          清零 Token 统计
        </button>
      </div>

      {/* Daily budget bar */}
      <div className="bg-white rounded-2xl border border-zinc-100 p-4 shadow-sm">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-zinc-600 flex items-center gap-2">
            今日 Token 预算使用率
            <button
              onClick={() => {
                setBudgetInput(dailyTokenBudget > 0 ? String(dailyTokenBudget) : '0');
                setIsBudgetModalOpen(true);
              }}
              className="text-[10px] px-2 py-0.5 rounded border border-zinc-200 text-zinc-500 hover:text-indigo-600 hover:border-indigo-200 hover:bg-indigo-50 transition-colors"
            >
              修改预算
            </button>
          </span>
          <span className={`text-xs font-black ${dailyTokenBudget > 0 && dailyPct > 80 ? 'text-red-600' : 'text-zinc-700'}`}>
            {dailyTokenBudget > 0 ? `${dailyPct.toFixed(1)}%` : '无限制'}
          </span>
        </div>
        <div className="w-full h-2.5 bg-zinc-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${dailyTokenBudget === 0 ? 'bg-zinc-300' : dailyPct > 90 ? 'bg-red-500' : dailyPct > 70 ? 'bg-amber-400' : 'bg-emerald-500'}`}
            style={{ width: dailyTokenBudget > 0 ? `${dailyPct}%` : '100%' }}
          />
        </div>
        <p className="text-[10px] text-zinc-400 mt-1.5 flex items-center justify-between">
          <span>{formatTokens(tokenUsage.dailyTotal)} / {dailyTokenBudget > 0 ? formatTokens(dailyTokenBudget) : '∞'} Tokens</span>
          <span>重置于下一个午夜（北京时间）</span>
        </p>
      </div>

      {/* ── Visit Statistics ── */}
      <div className="bg-white rounded-2xl border border-zinc-100 p-5 shadow-sm space-y-4">
        <h3 className="text-sm font-bold text-zinc-700 flex items-center gap-2">
          <Users size={14} className="text-indigo-500" />
          访问量统计
          <span className="text-[10px] font-normal text-zinc-400 ml-1">（数据持久化，刷新不重置）</span>
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: '今日访问', value: stats.dailySessions, color: 'text-indigo-600', bg: 'bg-indigo-50' },
            { label: '本周访问', value: stats.weeklySessions, color: 'text-emerald-600', bg: 'bg-emerald-50' },
            { label: '本月访问', value: stats.monthlySessions, color: 'text-violet-600', bg: 'bg-violet-50' },
            { label: '累计访问', value: stats.totalSessions, color: 'text-zinc-900', bg: 'bg-zinc-50' },
          ].map(item => (
            <div key={item.label} className={`${item.bg} rounded-xl p-4 text-center`}>
              <p className={`text-3xl font-black font-mono ${item.color}`}>{item.value}</p>
              <p className="text-[10px] font-bold text-zinc-500 mt-1 uppercase tracking-wider">{item.label}</p>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="p-3 bg-zinc-50 rounded-xl">
            <p className="text-zinc-400 font-medium mb-0.5">首次使用</p>
            <p className="font-semibold text-zinc-700">{stats.firstVisit ? new Date(stats.firstVisit).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '—'}</p>
          </div>
          <div className="p-3 bg-zinc-50 rounded-xl">
            <p className="text-zinc-400 font-medium mb-0.5">最近访问</p>
            <p className="font-semibold text-zinc-700">{stats.lastVisit ? new Date(stats.lastVisit).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '—'}</p>
          </div>
        </div>
        <div className="flex justify-end">
          <button
            onClick={() => {
              if (window.confirm('确定要清零访问量统计吗？')) {
                useStatsStore.getState().resetStats();
              }
            }}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-red-500 transition-colors px-3 py-1.5 rounded-xl border border-zinc-200 hover:border-red-200 hover:bg-red-50"
          >
            <RotateCcw size={11} />
            清零访问统计
          </button>
        </div>
      </div>

      {/* ── Active State ── */}
      <div className="bg-white rounded-2xl border border-zinc-100 p-5 shadow-sm space-y-3">
        <h3 className="text-sm font-bold text-zinc-700 flex items-center gap-2"><Cpu size={14} className="text-indigo-500" />当前前端活动状态</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { label: '主任务状态', value: analysisActivity, active: analysisActivity !== 'idle' },
            { label: '市场概览加载', value: overviewLoading ? '加载中' : '空闲', active: overviewLoading },
            { label: '自动刷新间隔', value: autoRefreshInterval > 0 ? `每 ${autoRefreshInterval} 分钟` : '已关闭', active: autoRefreshInterval > 0 },
            { label: '已加载市场', value: Object.keys(marketOverviews).join(', ') || '无', active: false },
            { label: '当前模型', value: config?.model || '未配置', active: false },
            { label: 'AI 后台任务', value: runningAiJobs.length > 0 ? `${runningAiJobs.length} 个运行中` : '无', active: runningAiJobs.length > 0 },
          ].map(item => (
            <div key={item.label} className={`p-3 rounded-xl border text-xs ${item.active ? 'border-amber-200 bg-amber-50' : 'border-zinc-100 bg-zinc-50'}`}>
              <p className="text-zinc-400 font-medium mb-0.5">{item.label}</p>
              <p className={`font-bold ${item.active ? 'text-amber-700' : 'text-zinc-700'}`}>{item.value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Background Tasks ── */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-zinc-700 flex items-center gap-2">
          <Radio size={14} className="text-emerald-500" />
          前端后台任务注册表
          <span className="text-[10px] font-normal text-zinc-400 ml-1">（以下任务在主页打开时持续运行）</span>
        </h3>
        {tasksWithStatus.map(task => (
          <div key={task.id} className="bg-white rounded-2xl border border-zinc-100 shadow-sm overflow-hidden">
            <button
              className="w-full flex items-center gap-3 p-4 text-left hover:bg-zinc-50/50 transition-colors"
              onClick={() => setExpandedTask(expandedTask === task.id ? null : task.id)}
            >
              <StatusDot status={task.status} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-zinc-800">{task.name}</span>
                  <CategoryBadge category={task.category} />
                  {task.consumesTokens && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-100 text-red-600 uppercase tracking-wider flex items-center gap-1">
                      <Zap size={8} />消耗 Token
                    </span>
                  )}
                </div>
                {task.interval && (
                  <p className="text-[10px] text-zinc-400 mt-0.5">间隔: 每 {task.interval / 1000} 秒</p>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs text-zinc-400">
                <span className={`font-semibold ${task.status === 'running' ? 'text-emerald-600' : task.status === 'error' ? 'text-red-500' : 'text-zinc-400'}`}>
                  {task.status === 'running' ? '运行中' : task.status === 'error' ? '异常' : '空闲'}
                </span>
                {expandedTask === task.id ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </div>
            </button>
            {expandedTask === task.id && (
              <div className="px-4 pb-4 pt-0 border-t border-zinc-50">
                <p className="text-xs text-zinc-500 leading-relaxed mt-3">{task.description}</p>
                {task.id === 'market_auto_refresh' && (
                  <div className="mt-3 p-3 bg-amber-50 border border-amber-100 rounded-xl text-xs text-amber-700 flex items-start gap-2">
                    <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
                    <div>
                      <strong>当前状态：</strong>
                      {autoRefreshInterval > 0
                        ? `已开启，每 ${autoRefreshInterval} 分钟自动调用 AI 分析（消耗 Token）。可在主页右上角的刷新间隔下拉框选择「不自动刷新」来关闭。`
                        : '已关闭（推荐）。如需开启，在主页右上角的下拉框中选择刷新间隔。'
                      }
                    </div>
                  </div>
                )}
                {!task.isControllable && (
                  <p className="mt-2 text-[10px] text-zinc-400 flex items-center gap-1"><Info size={10} />此任务为系统必要任务，不可关闭。</p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Python API Jobs ── */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-zinc-700 flex items-center gap-2">
          <Database size={14} className="text-violet-500" />
          Python 服务后台任务队列
          {apiJobsLoading && <RefreshCw size={12} className="animate-spin text-zinc-400" />}
        </h3>
        {apiJobs.length === 0 ? (
          <div className="bg-white rounded-2xl border border-zinc-100 p-6 text-center text-zinc-400 text-sm shadow-sm">
            <CheckCircle size={24} className="mx-auto mb-2 text-emerald-400" />
            暂无后台 AI 任务（板块扫描、板块分析等）
          </div>
        ) : (
          <div className="space-y-2">
            {apiJobs.slice(0, 8).map(job => (
              <div key={job.job_id} className="bg-white rounded-xl border border-zinc-100 px-4 py-3 flex items-center gap-3 shadow-sm">
                <StatusDot status={job.status === 'running' || job.status === 'pending' ? 'running' : job.status === 'failed' ? 'error' : 'idle'} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-zinc-500">{job.job_id.slice(0, 16)}...</span>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                      job.type === 'sector' ? 'bg-indigo-100 text-indigo-700' : 'bg-violet-100 text-violet-700'
                    }`}>{job.type === 'sector' ? '板块任务' : '分析任务'}</span>
                  </div>
                  {job.progress?.message && (
                    <p className="text-[10px] text-zinc-400 truncate mt-0.5">{job.progress.message}</p>
                  )}
                </div>
                <div className="text-right">
                  <p className={`text-xs font-semibold ${
                    job.status === 'running' || job.status === 'pending' ? 'text-amber-600' :
                    job.status === 'completed' ? 'text-emerald-600' :
                    job.status === 'failed' ? 'text-red-500' : 'text-zinc-400'
                  }`}>{job.status}</p>
                  <p className="text-[10px] text-zinc-400">{new Date(job.created_at).toLocaleTimeString('zh-CN')}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Token 消耗根因分析 ── */}
      <div className="bg-white rounded-2xl border border-zinc-100 p-5 shadow-sm space-y-4">
        <h3 className="text-sm font-bold text-zinc-700 flex items-center gap-2">
          <AlertTriangle size={14} className="text-amber-500" />
          Token 消耗根因分析
        </h3>
        <div className="space-y-3 text-xs">
          {[
            {
              title: '✅ 常规操作（主动触发，符合预期）',
              items: [
                '搜索股票 → 调用 AI 个股分析（主要消耗）',
                '触发"每日简报" → 调用 AI 市场分析',
                '开启"专家组研讨" → 多轮 AI 对话（消耗最大）',
                '板块扫描 / Serenity Alpha 研判 → Python 服务后端调用 AI',
              ],
              color: 'text-emerald-700 bg-emerald-50 border-emerald-100',
            },
            {
              title: '⚠️ 可能的非预期消耗（检查这些配置）',
              items: [
                `自动刷新：当前${autoRefreshInterval > 0 ? `已开启（每 ${autoRefreshInterval} 分钟），会定期重新调用 AI 市场分析 → 建议关闭` : '已关闭（正常）'}`,
                '强制刷新：每次点击🔄刷新按钮都会触发完整的 AI 分析',
                '市场首次加载：切换 A/港/美 市场标签页会分别触发一次 AI 分析（有当日缓存机制）',
                '历史记录缺失：如果今日缓存被清除，页面重新打开会重新触发 AI 分析',
              ],
              color: 'text-amber-700 bg-amber-50 border-amber-100',
            },
            {
              title: '🟢 不消耗 Token 的后台任务（正常）',
              items: [
                '价格实时同步（每30秒）→ 仅调用行情 API，无 AI 调用',
                '价格预警监控（每30秒）→ 仅比较价格阈值',
                '板块/分析轮询（每3秒）→ 仅查询任务状态，AI 已在后端完成',
                '市场指数快照（首次加载）→ 调用 AkShare API，无 AI 调用',
              ],
              color: 'text-blue-700 bg-blue-50 border-blue-100',
            },
          ].map(section => (
            <div key={section.title} className={`p-4 rounded-xl border ${section.color}`}>
              <p className="font-bold mb-2">{section.title}</p>
              <ul className="space-y-1">
                {section.items.map((item, i) => (
                  <li key={i} className="leading-relaxed">• {item}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* ── Debug Logs ── */}
      <div className="space-y-3">
        <button
          onClick={() => setShowDebugLogs(!showDebugLogs)}
          className="flex items-center gap-2 text-xs font-bold text-zinc-500 hover:text-zinc-700 transition-colors"
        >
          {showDebugLogs ? <EyeOff size={13} /> : <Eye size={13} />}
          {showDebugLogs ? '隐藏' : '展开'} 调试日志 ({debugLogs.length} 条)
        </button>
        {showDebugLogs && (
          <div className="space-y-1.5 max-h-80 overflow-y-auto">
            {debugLogs.length === 0 ? (
              <p className="text-xs text-zinc-400 text-center py-4">暂无调试日志（可在设置中开启 Debug 模式）</p>
            ) : debugLogs.map((log, i) => (
              <div key={i} className="bg-zinc-900 rounded-lg px-3 py-2 text-[10px] font-mono text-zinc-300">
                <span className="text-zinc-500 mr-2">{new Date(log.timestamp || Date.now()).toLocaleTimeString()}</span>
                <span className="text-violet-400 mr-2">[{log.type || 'LOG'}]</span>
                <span>{JSON.stringify(log.data || log).slice(0, 200)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Budget Modal ── */}
      {isBudgetModalOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-zinc-950/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl w-full max-w-sm overflow-hidden shadow-2xl border border-zinc-100 flex flex-col">
            <div className="px-5 py-4 border-b border-zinc-100 flex items-center justify-between bg-zinc-50/50">
              <h3 className="font-bold text-zinc-800 flex items-center gap-2">
                <Zap size={16} className="text-indigo-500" />
                设置每日 Token 预算
              </h3>
              <button
                onClick={() => setIsBudgetModalOpen(false)}
                className="text-zinc-400 hover:text-zinc-600 transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            
            <div className="p-5 space-y-5">
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-2">
                  自定义预算数量（输入 0 为无限额）
                </label>
                <div className="relative">
                  <input
                    type="number"
                    min="0"
                    value={budgetInput}
                    onChange={e => setBudgetInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        const val = parseInt(budgetInput, 10);
                        if (!isNaN(val) && val >= 0) {
                          setDailyTokenBudget(val);
                          setIsBudgetModalOpen(false);
                        }
                      }
                    }}
                    className="w-full px-4 py-2.5 bg-zinc-50 border border-zinc-200 rounded-xl text-lg font-mono font-bold text-zinc-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all"
                    placeholder="例如: 900000"
                    autoFocus
                  />
                  <div className="absolute inset-y-0 right-0 pr-4 flex items-center pointer-events-none">
                    <span className="text-zinc-400 text-xs font-medium">Tokens</span>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-2">快速选择</label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: '小额 (100K)', value: 100000 },
                    { label: '标准 (500K)', value: 500000 },
                    { label: '推荐 (900K)', value: 900000 },
                    { label: '无限制 (0)', value: 0 },
                  ].map(preset => (
                    <button
                      key={preset.label}
                      onClick={() => setBudgetInput(String(preset.value))}
                      className="px-3 py-2 rounded-xl text-xs font-medium border border-zinc-200 text-zinc-600 hover:bg-zinc-50 hover:border-indigo-200 hover:text-indigo-600 transition-colors text-center"
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="px-5 py-4 border-t border-zinc-100 flex justify-end gap-2 bg-zinc-50/50">
              <button
                onClick={() => setIsBudgetModalOpen(false)}
                className="px-4 py-2 text-xs font-medium text-zinc-600 hover:text-zinc-800 hover:bg-zinc-200/50 rounded-xl transition-colors"
              >
                取消
              </button>
              <button
                onClick={() => {
                  const val = parseInt(budgetInput, 10);
                  if (!isNaN(val) && val >= 0) {
                    setDailyTokenBudget(val);
                    setIsBudgetModalOpen(false);
                  }
                }}
                className="px-4 py-2 text-xs font-medium text-white bg-indigo-500 hover:bg-indigo-600 shadow-sm shadow-indigo-200 rounded-xl transition-colors flex items-center gap-1.5"
              >
                <CheckCircle size={14} />
                确认保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
