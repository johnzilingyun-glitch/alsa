import React, { useEffect, useCallback } from 'react';
import { X, Settings, ShieldCheck, Cpu, AlertTriangle, Globe, Info, RefreshCw, Loader2, CheckCircle2, Sparkles, Eye, EyeOff, Trash2, Github, ExternalLink, LogOut } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore } from '../stores/useUIStore';
import { fetchAvailableModelsList, type ModelInfo } from '../services/geminiService';
import { useState } from 'react';

const AVAILABLE_MODELS = [
  { id: 'gemini-2.5-flash-lite', name: 'Gemini 2.5 Flash Lite (Unlimited)', description: '旗舰级速率，Paid 层级无限制 RPD，4000 RPM，适合极高频自动化分析。' },
  { id: 'gemini-3.1-flash-lite-preview', name: 'Gemini 3.1 Flash Lite (Ultra Fast)', description: '极速响应模型，Free 配额最高 (15 RPM, 500 RPD)，适合高频实时分析。' },
  { id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash (Fast & Balanced)', description: '平衡型模型，Free 配额受限 (5 RPM, 20 RPD)，适合一般概览场景。' },
  { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro (Advanced Reasoning)', description: '顶级推理模型，具备最高逻辑深度 (Paid 25 RPM, 250 RPD)，适合复杂多轮研讨。' },
];

const COPILOT_LOCAL_MODELS = [
  { id: 'copilot_auto',    name: 'Copilot Auto (Recommended)',          description: '自动选择当前最稳的可用模型，优先尝试 Claude Opus 4.6，再回退其他高质量模型。' },
  { id: 'gpt-5.4',         name: 'GPT-5.4 (Standard)',                  description: 'OpenAI 最新标准旗舰，均衡速度与质量。' },
  { id: 'claude-opus-4.6', name: 'Claude Opus 4.6 (Premium)',           description: 'Anthropic 顶级推理模型，适合最复杂分析。' },
  { id: 'claude-opus-4.7', name: 'Claude Opus 4.7 (Premium Latest)',    description: 'Opus 最新旗舰版本，最强逻辑链能力。' },
  { id: 'gpt-5.2',         name: 'GPT-5.2 (Standard)',                  description: '上一代 GPT-5，稳定可靠。' },
  { id: 'claude-sonnet-4.6', name: 'Claude Sonnet 4.6 (Standard)',      description: '当前默认 Sonnet，速度与质量最优平衡。' },
  { id: 'gpt-5-mini',      name: 'GPT-5 Mini (Fast/Cheap)',             description: '轻量高速，适合快速预览分析。' },
  { id: 'gpt-5.4-mini',    name: 'GPT-5.4 Mini (Fast/Cheap)',           description: '最新 GPT-5.4 轻量版，低延迟。' },
  { id: 'gpt-4.1',         name: 'GPT-4.1 (Fast/Cheap)',                description: '稳定备选，低成本高频调用。' },
  { id: 'claude-haiku-4.5',name: 'Claude Haiku 4.5 (Fast/Cheap)',      description: '极速响应，适合简单摘要场景。' },
];

export function SettingsModal() {
  const { config, setConfig, tokenUsage, availableModels, setAvailableModels, feishuWebhookUrl, setFeishuWebhookUrl, debugMode, setDebugMode } = useConfigStore();
  const { isSettingsOpen, setIsSettingsOpen } = useUIStore();
  const [isFetchingModels, setIsFetchingModels] = useState(false);
  const [fetchMessage, setFetchMessage] = useState<{type: 'error' | 'success', text: string} | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const serviceMode = config.serviceMode || 'byok';

  // Copilot OAuth auth state
  type CopilotFlowState = 'checking' | 'idle' | 'connecting' | 'waiting_user' | 'connected' | 'error';
  const [copilotFlow, setCopilotFlow] = useState<CopilotFlowState>('checking');
  const [copilotFlowData, setCopilotFlowData] = useState<{
    userCode?: string; verificationUri?: string; deviceCode?: string; interval?: number;
    username?: string; tokenSource?: string; error?: string;
  }>({});
  const [copilotPollRef, setCopilotPollRef] = useState<ReturnType<typeof setInterval> | null>(null);

  const displayModels = serviceMode === 'copilot_local'
    ? COPILOT_LOCAL_MODELS
    : (availableModels.length > 0 ? availableModels : AVAILABLE_MODELS);

  const handleFetchModels = async () => {
    setIsFetchingModels(true);
    setFetchMessage(null);
    try {
      const models = await fetchAvailableModelsList(config);
      setAvailableModels(models);
      const okCount = models.filter(m => m.status === 'available').length;
      const quotaCount = models.filter(m => m.status === 'quota_exhausted').length;
      if (quotaCount > 0) {
        setFetchMessage({ type: 'success', text: `找到 ${okCount} 个可用模型，${quotaCount} 个配额已耗尽。` });
      } else {
        setFetchMessage({ type: 'success', text: `成功接入：找到 ${models.length} 个可用模型。` });
      }
    } catch (e: any) {
      setFetchMessage({ type: 'error', text: e.message || '查询模型失败' });
    } finally {
      setIsFetchingModels(false);
    }
  };

  // Check Copilot auth status whenever the modal opens in copilot_local mode
  const checkCopilotStatus = useCallback(async () => {
    setCopilotFlow('checking');
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);
      const r = await fetch('/api/diagnostics/copilot/auth/status', { signal: controller.signal });
      clearTimeout(timer);
      const data = await r.json();
      if (data.authenticated) {
        // Show connected as long as we have a valid GitHub token.
        // Copilot subscription is verified lazily when an analysis is run.
        setCopilotFlow('connected');
        setCopilotFlowData({ username: data.username, tokenSource: data.tokenSource });
      } else {
        setCopilotFlow('idle');
        setCopilotFlowData({});
      }
    } catch {
      setCopilotFlow('idle');
    }
  }, []);

  useEffect(() => {
    if (isSettingsOpen && serviceMode === 'copilot_local') {
      checkCopilotStatus();
    }
  }, [isSettingsOpen, serviceMode, checkCopilotStatus]);

  // Stop polling when component unmounts or modal closes
  useEffect(() => {
    if (!isSettingsOpen && copilotPollRef) {
      clearInterval(copilotPollRef);
      setCopilotPollRef(null);
    }
  }, [isSettingsOpen, copilotPollRef]);

  const handleCopilotConnect = async () => {
    setCopilotFlow('connecting');
    setCopilotFlowData({});
    try {
      const r = await fetch('/api/diagnostics/copilot/auth/start', { method: 'POST' });
      const data = await r.json();
      if (!data.success) throw new Error(data.error || 'Device flow failed');
      setCopilotFlow('waiting_user');
      setCopilotFlowData({
        userCode: data.user_code,
        verificationUri: data.verification_uri,
        deviceCode: data.device_code,
        interval: data.interval,
      });
      // Start polling
      const intervalMs = (data.interval ?? 5) * 1000;
      const pollId = setInterval(async () => {
        try {
          const pr = await fetch(`/api/diagnostics/copilot/auth/poll?device_code=${data.device_code}`);
          const pd = await pr.json();
          if (pd.status === 'success') {
            clearInterval(pollId);
            setCopilotPollRef(null);
            // Immediately show connected — don't wait for subscription check
            setCopilotFlow('connected');
            setCopilotFlowData({ username: undefined, tokenSource: 'file' });
            // Then refresh in background to get username
            checkCopilotStatus();
          } else if (pd.status === 'expired' || pd.status === 'error') {
            clearInterval(pollId);
            setCopilotPollRef(null);
            setCopilotFlow('error');
            setCopilotFlowData({ error: pd.message || '授权已过期，请重试' });
          }
        } catch {
          // Network error during poll — keep trying
        }
      }, intervalMs);
      setCopilotPollRef(pollId);
    } catch (err: any) {
      setCopilotFlow('error');
      setCopilotFlowData({ error: err?.message || '连接失败' });
    }
  };

  const handleCopilotDisconnect = async () => {
    if (copilotPollRef) { clearInterval(copilotPollRef); setCopilotPollRef(null); }
    await fetch('/api/diagnostics/copilot/auth/token', { method: 'DELETE' });
    setCopilotFlow('idle');
    setCopilotFlowData({});
  };

  const handleOpenKeySelector = async () => {
    const aiStudio = (window as any).aistudio;
    if (aiStudio?.openSelectKey) {
      await aiStudio.openSelectKey();
    } else {
      console.warn('API Key selection is only available in the AI Studio environment.');
    }
  };

  const onClose = () => setIsSettingsOpen(false);

  return (
    <AnimatePresence>
      {isSettingsOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-zinc-900/10 backdrop-blur-md"
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.98, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: 10 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-full max-w-xl overflow-hidden rounded-3xl border border-zinc-200 bg-white shadow-2xl shadow-zinc-900/10"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-modal-title"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-zinc-100 p-8">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-100/50">
                  <Settings size={24} strokeWidth={1.5} />
                </div>
                <div>
                  <h2 id="settings-modal-title" className="text-xl font-bold text-zinc-950 tracking-tight">{t('settings.title')}</h2>
                  <p className="text-xs font-medium text-zinc-400 mt-0.5">{t('settings.subtitle')}</p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="flex h-10 w-10 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-zinc-50 hover:text-zinc-900"
              >
                <X size={20} />
              </button>
            </div>

            {/* Content - Scrollable area */}
            <div className="max-h-[60vh] overflow-y-auto p-8 space-y-10 custom-scrollbar">
              {/* API Key Section */}
              <section className="space-y-4">
                <div className="flex items-center gap-2">
                  <ShieldCheck size={16} className="text-indigo-600" />
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">{t('settings.sections.auth')}</span>
                </div>

                <div className="flex bg-zinc-100 p-1 rounded-lg w-fit">
                  <button
                    onClick={() => setConfig({ ...config, serviceMode: 'byok' })}
                    className={`px-3 py-1 text-[10px] font-bold rounded-md transition-all ${
                      serviceMode === 'byok'
                        ? 'bg-white text-zinc-950 shadow-sm'
                        : 'text-zinc-400 hover:text-zinc-600'
                    }`}
                  >
                    {t('settings.modes.byok')}
                  </button>
                  <button
                    onClick={() => setConfig({ ...config, serviceMode: 'managed_no_key' })}
                    className={`px-3 py-1 text-[10px] font-bold rounded-md transition-all ${
                      serviceMode === 'managed_no_key'
                        ? 'bg-white text-zinc-950 shadow-sm'
                        : 'text-zinc-400 hover:text-zinc-600'
                    }`}
                  >
                    {t('settings.modes.managed')}
                  </button>
                  <button
                    onClick={() => setConfig({ ...config, serviceMode: 'copilot_local', model: 'copilot_auto' })}
                    className={`px-3 py-1 text-[10px] font-bold rounded-md transition-all ${
                      serviceMode === 'copilot_local'
                        ? 'bg-white text-zinc-950 shadow-sm'
                        : 'text-zinc-400 hover:text-zinc-600'
                    }`}
                  >
                    {t('settings.modes.copilot')}
                  </button>
                </div>
                
                <div className="space-y-4">
                  <div className="group relative flex flex-col gap-2">
                    <div className="relative">
                      <input
                        type={showApiKey ? "text" : "password"}
                        placeholder={serviceMode === 'managed_no_key' ? '托管模式下无需填写（将使用服务端配置）' : serviceMode === 'copilot_local' ? '本地 Copilot 模式下无需填写（将使用本机 GitHub 登录态）' : 'AIzaSy... (输入您的 Gemini API Key)'}
                        id="api-key-input"
                        value={config.apiKey || ''}
                        onChange={(e) => setConfig({ ...config, apiKey: e.target.value })}
                        disabled={serviceMode === 'managed_no_key' || serviceMode === 'copilot_local'}
                        className="input-premium pr-24 font-mono w-full disabled:opacity-60 disabled:cursor-not-allowed"
                      />
                      <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
                        {config.apiKey && (
                          <button
                            onClick={() => setConfig({ ...config, apiKey: '' })}
                            className="p-1.5 text-zinc-300 hover:text-rose-500 transition-colors"
                            title="清空"
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                        <button
                          onClick={() => setShowApiKey(!showApiKey)}
                          className="p-1.5 text-zinc-300 hover:text-indigo-600 transition-colors"
                          title={showApiKey ? "隐藏" : "显示"}
                        >
                          {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    </div>
                    
                    {/* Tier Selection */}
                    <div className="flex items-center gap-3 mt-1">
                      <div className="flex bg-zinc-100 p-1 rounded-lg">
                        <button
                          onClick={() => setConfig({ ...config, tier: 'free' })}
                          className={`px-3 py-1 text-[10px] font-bold rounded-md transition-all ${
                            (config.tier || 'free') === 'free'
                              ? 'bg-white text-zinc-950 shadow-sm'
                              : 'text-zinc-400 hover:text-zinc-600'
                          }`}
                        >
                          免费层级 (15 RPM)
                        </button>
                        <button
                          onClick={() => setConfig({ ...config, tier: 'paid' })}
                          className={`px-3 py-1 text-[10px] font-bold rounded-md transition-all ${
                            config.tier === 'paid'
                              ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/20'
                              : 'text-zinc-400 hover:text-zinc-600'
                          }`}
                        >
                          付费/绑定层级 (高速)
                        </button>
                      </div>
                      <div className="flex items-center gap-1.5 ml-auto">
                        <div className={`h-1.5 w-1.5 rounded-full ${serviceMode === 'managed_no_key' ? 'bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)]' : serviceMode === 'copilot_local' ? 'bg-sky-500 shadow-[0_0_8px_rgba(14,165,233,0.5)]' : config.apiKey?.startsWith('AIzaSy') ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]'}`} />
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                          {serviceMode === 'managed_no_key' ? '托管模式' : serviceMode === 'copilot_local' ? 'Copilot 模式' : config.apiKey?.startsWith('AIzaSy') ? '格式正确' : '格式不合规'}
                        </span>
                      </div>
                    </div>
                  </div>
                  
                  {(window as any).aistudio?.openSelectKey && (
                    <button
                      onClick={handleOpenKeySelector}
                      className="flex w-full items-center justify-center gap-2 rounded-xl bg-zinc-950 px-4 py-3 text-sm font-semibold text-white transition-all hover:bg-zinc-800 active:scale-[0.98] shadow-lg shadow-zinc-900/10"
                    >
                      从 Google AI Studio 快速同步
                    </button>
                  )}
                  
                  <div className="flex items-start gap-3 p-4 rounded-xl bg-indigo-50/50 border border-indigo-100/50">
                    <Info size={16} className="text-indigo-400 shrink-0 mt-0.5" />
                    <p className="text-xs text-indigo-600/70 leading-relaxed">
                      {serviceMode === 'managed_no_key'
                        ? '托管模式下不会在浏览器保存个人 Key。系统将使用服务端预配置模型通道。若服务端未配置，将自动提示并可切换回自定义 Key。'
                        : serviceMode === 'copilot_local'
                        ? '本地 Copilot 模式通过后端桥接使用本机 GitHub 登录态（例如 gh auth token）。无需在浏览器保存个人 Gemini Key。'
                        : '您的密钥仅保存在本地浏览器中。为了保障分析的深度，请确保该 Key 已启用商业配额或属于 Google Cloud 项目。'}
                    </p>
                  </div>
                  
                  <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-50/50 border border-amber-100/50">
                    <Sparkles size={16} className="text-amber-400 shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-700/80 leading-relaxed">
                      <strong>💡 专业提示</strong>：使用个人 API Key 可有效避免"系统高负载"并大幅提升研报生成速度。您可以访问 Google AI Studio 免费获取。
                    </p>
                  </div>
                </div>
              </section>

              {/* GitHub Copilot Authentication Section — only in copilot_local mode */}
              {serviceMode === 'copilot_local' && (
                <section className="space-y-4">
                  <div className="flex items-center gap-2">
                    <Github size={16} className="text-sky-600" />
                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">GitHub Copilot 认证</span>
                  </div>

                  {copilotFlow === 'checking' && (
                    <div className="flex items-center gap-3 p-4 rounded-xl bg-zinc-50 border border-zinc-100">
                      <Loader2 size={16} className="text-sky-500 animate-spin" />
                      <span className="text-xs text-zinc-500">检查认证状态…</span>
                    </div>
                  )}

                  {copilotFlow === 'connected' && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between p-4 rounded-xl bg-sky-50 border border-sky-100">
                        <div className="flex items-center gap-3">
                          <CheckCircle2 size={16} className="text-sky-600" />
                          <div>
                            <p className="text-xs font-bold text-sky-800">
                              已连接 {copilotFlowData.username ? `@${copilotFlowData.username}` : ''}
                            </p>
                            {copilotFlowData.tokenSource && (
                              <p className="text-[10px] text-sky-500 mt-0.5">
                                来源: {copilotFlowData.tokenSource === 'env' ? '环境变量' : copilotFlowData.tokenSource === 'file' ? '本地 OAuth' : 'gh CLI'}
                              </p>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={handleCopilotDisconnect}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold text-zinc-500 bg-white border border-zinc-200 hover:border-red-200 hover:text-red-600 transition-colors"
                        >
                          <LogOut size={12} />
                          断开
                        </button>
                      </div>
                    </div>
                  )}

                  {(copilotFlow === 'idle' || copilotFlow === 'error') && (
                    <div className="space-y-3">
                      {copilotFlow === 'error' && (
                        <div className="flex items-start gap-3 p-3 rounded-xl bg-red-50 border border-red-100">
                          <AlertTriangle size={14} className="text-red-400 shrink-0 mt-0.5" />
                          <p className="text-[11px] text-red-600">{copilotFlowData.error}</p>
                        </div>
                      )}
                      <button
                        onClick={handleCopilotConnect}
                        className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-zinc-900 text-white text-xs font-bold hover:bg-zinc-800 transition-colors"
                      >
                        <Github size={14} />
                        通过 GitHub 连接 Copilot
                      </button>
                      <div className="flex items-start gap-3 p-4 rounded-xl bg-sky-50/50 border border-sky-100/50">
                        <Info size={14} className="text-sky-400 shrink-0 mt-0.5" />
                        <p className="text-[11px] text-sky-600/80 leading-relaxed">
                          点击后会生成一个 8 位验证码，在 GitHub.com 上输入即可授权。需要有效的 GitHub Copilot 订阅。
                        </p>
                      </div>
                    </div>
                  )}

                  {copilotFlow === 'connecting' && (
                    <div className="flex items-center gap-3 p-4 rounded-xl bg-zinc-50 border border-zinc-100">
                      <Loader2 size={16} className="text-sky-500 animate-spin" />
                      <span className="text-xs text-zinc-500">正在初始化 GitHub 授权流程…</span>
                    </div>
                  )}

                  {copilotFlow === 'waiting_user' && copilotFlowData.userCode && (
                    <div className="space-y-3">
                      <div className="p-5 rounded-xl bg-zinc-900 text-center space-y-3">
                        <p className="text-[10px] text-zinc-400 uppercase tracking-wider">在浏览器中输入以下验证码</p>
                        <p className="text-3xl font-mono font-bold text-white tracking-[0.3em]">
                          {copilotFlowData.userCode}
                        </p>
                        <a
                          href={copilotFlowData.verificationUri}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 text-[11px] text-sky-400 hover:text-sky-300 transition-colors"
                        >
                          <ExternalLink size={11} />
                          {copilotFlowData.verificationUri}
                        </a>
                      </div>
                      <div className="flex items-center gap-3 p-3 rounded-xl bg-sky-50 border border-sky-100">
                        <Loader2 size={14} className="text-sky-500 animate-spin shrink-0" />
                        <p className="text-[11px] text-sky-700">等待授权确认中，请在上方链接完成验证…</p>
                      </div>
                    </div>
                  )}
                </section>
              )}

              {/* Feishu Webhook Section */}
              <section className="space-y-4">
                <div className="flex items-center gap-2">
                  <Globe size={16} className="text-indigo-600" />
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">{t('settings.sections.feishu')}</span>
                </div>
                
                <div className="space-y-4">
                  <div className="relative group">
                    <input
                      type="text"
                      placeholder={t('settings.feishu.placeholder')}
                      id="feishu-webhook-input"
                      value={feishuWebhookUrl}
                      onChange={(e) => setFeishuWebhookUrl(e.target.value)}
                      className="input-premium h-12 pl-4 pr-10 font-mono w-full"
                    />
                  </div>
                  <div className="flex items-start gap-3 p-4 rounded-xl bg-indigo-50/50 border border-indigo-100/50">
                    <Info size={16} className="text-indigo-400 shrink-0 mt-0.5" />
                    <p className="text-xs text-indigo-600/70 leading-relaxed">
                      {t('settings.feishu.hint')}
                    </p>
                  </div>
                </div>
              </section>

              {/* Debug & Failover Section */}
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles size={16} className="text-indigo-600" />
                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">{t('settings.sections.diagnosis')}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                      {debugMode ? t('settings.diagnosis.debug_on') : t('settings.diagnosis.debug_off')}
                    </span>
                    <button
                      onClick={() => setDebugMode(!debugMode)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                        debugMode ? 'bg-indigo-600' : 'bg-zinc-200'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          debugMode ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Github size={16} className="text-sky-600" />
                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">{t('settings.diagnosis.failover')}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                      {config.enableCopilotFallback ? t('settings.diagnosis.failover_on') : t('settings.diagnosis.failover_off')}
                    </span>
                    <button
                      onClick={() => setConfig({ ...config, enableCopilotFallback: !config.enableCopilotFallback })}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                        config.enableCopilotFallback ? 'bg-sky-500 shadow-[0_0_8px_rgba(14,165,233,0.3)]' : 'bg-zinc-200'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          config.enableCopilotFallback ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>
                </div>
                
                <div className="flex items-start gap-4 p-5 rounded-2xl bg-zinc-50 border border-zinc-100 italic">
                  <div className="flex flex-col gap-3 w-full">
                    <div className="flex items-start gap-3">
                      <Cpu size={16} className="text-zinc-400 shrink-0 mt-0.5" />
                      <p className="text-xs text-zinc-500 leading-relaxed">
                        {t('settings.diagnosis.debug_desc')}
                      </p>
                    </div>
                    <div className="flex items-start gap-3 border-t border-zinc-200/60 pt-3">
                      <Github size={16} className="text-zinc-400 shrink-0 mt-0.5" />
                      <p className="text-xs text-zinc-500 leading-relaxed">
                        {t('settings.diagnosis.failover_desc')}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <a 
                        href="/api/logs/debug" 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-zinc-200 text-[10px] font-bold text-zinc-600 hover:bg-zinc-50"
                      >
                        {t('settings.diagnosis.view_logs')}
                      </a>
                      <button 
                        onClick={async () => {
                          if (!confirm(t('errors.confirm_clear_logs'))) return;
                          await fetch('/api/logs/debug', { method: 'DELETE' });
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-zinc-200 text-[10px] font-bold text-rose-500 hover:bg-rose-50"
                      >
                        {t('settings.diagnosis.clear_logs')}
                      </button>
                    </div>
                  </div>
                </div>
              </section>

              {/* Model Selection Section */}
              <section className="space-y-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Cpu size={16} className="text-indigo-600" />
                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">{t('settings.sections.models')}</span>
                  </div>
                  <button 
                    onClick={handleFetchModels}
                    disabled={isFetchingModels}
                    className="text-[10px] font-bold uppercase tracking-widest text-indigo-600 hover:text-indigo-700 disabled:opacity-50 flex items-center gap-1.5"
                  >
                    {isFetchingModels ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                    {isFetchingModels ? t('settings.models.syncing') : t('settings.models.refresh')}
                  </button>
                </div>

                {fetchMessage && (
                  <p className={`text-[10px] font-bold px-3 py-1 rounded-md ${fetchMessage.type === 'error' ? 'bg-rose-50 text-rose-500' : 'bg-emerald-50 text-emerald-500'}`}>
                    {fetchMessage.text}
                  </p>
                )}
                
                <div className="grid gap-4">
                  {displayModels.map((model) => {
                    const isQuotaExhausted = (model as any).status === 'quota_exhausted';
                    const isUnavailable = (model as any).status === 'unavailable';
                    const isDisabled = isQuotaExhausted || isUnavailable;
                    return (
                      <button
                        key={model.id}
                        onClick={() => !isDisabled && setConfig({ ...config, model: model.id })}
                        disabled={isDisabled}
                        className={`flex flex-col gap-1.5 rounded-2xl border p-5 text-left transition-all group ${
                          isDisabled
                            ? 'border-zinc-100 bg-zinc-50/50 opacity-60 cursor-not-allowed'
                            : config.model === model.id
                            ? 'border-indigo-600 bg-indigo-50/20 ring-1 ring-indigo-600'
                            : 'border-zinc-100 bg-white hover:border-zinc-200 hover:bg-zinc-50'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className={`text-sm font-bold ${isDisabled ? 'text-zinc-400' : config.model === model.id ? 'text-indigo-600' : 'text-zinc-900 group-hover:text-zinc-950'}`}>
                            {model.name}
                          </span>
                          <div className="flex items-center gap-1.5">
                            {isQuotaExhausted && (
                              <span className="flex items-center gap-1 text-[10px] font-bold text-amber-500 bg-amber-50 px-2 py-0.5 rounded-full border border-amber-100">
                                <AlertTriangle size={10} />
                                {t('settings.models.quota_exhausted')}
                              </span>
                            )}
                            {isUnavailable && (
                              <span className="flex items-center gap-1 text-[10px] font-bold text-rose-500 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-100">
                                <X size={10} />
                                {t('settings.models.unavailable')}
                              </span>
                            )}
                            {!isDisabled && config.model === model.id && (
                              <div className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600 text-white">
                                <CheckCircle2 size={12} strokeWidth={3} />
                              </div>
                            )}
                          </div>
                        </div>
                        <p className="text-xs text-zinc-500 leading-relaxed font-medium">
                          {(model as any).statusMessage || model.description || model.id}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </section>
            </div>

            {/* Footer */}
            <div className="border-t border-zinc-100 bg-zinc-50/50 p-8">
              <button
                onClick={onClose}
                className="btn-primary w-full h-14 rounded-2xl text-base shadow-xl shadow-indigo-600/10"
              >
                {t('settings.actions.save')}
              </button>
              <p className="mt-4 text-center text-[10px] text-zinc-400 font-medium">
                {t('settings.actions.footer_hint')}
              </p>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
