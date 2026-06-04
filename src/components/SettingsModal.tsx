import React, { useEffect } from 'react';
import { X, Settings, ShieldCheck, Cpu, AlertTriangle, Globe, Info, RefreshCw, Loader2, CheckCircle2, Sparkles, Eye, EyeOff, Trash2, Github, ExternalLink, LogOut } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useConfigStore } from '../stores/useConfigStore';
import { useUIStore } from '../stores/useUIStore';
import { fetchAvailableModelsList, type ModelInfo } from '../services/geminiService';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

const AVAILABLE_MODELS = [
  { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash (Latest)', description: '最新一代高速模型，性能全面超越 3.1 Flash，推荐首选。' },
  { id: 'gemini-2.5-flash-lite', name: 'Gemini 2.5 Flash Lite (Unlimited)', description: '旗舰级速率，Paid 层级无限制 RPD，4000 RPM，适合极高频自动化分析。' },
  { id: 'gemini-3.1-flash-lite-preview', name: 'Gemini 3.1 Flash Lite (Ultra Fast)', description: '极速响应模型，Free 配额最高 (15 RPM, 500 RPD)，适合高频实时分析。' },
  { id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash (Fast & Balanced)', description: '平衡型模型，Free 配额受限 (5 RPM, 20 RPD)，适合一般概览场景。' },
  { id: 'gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro (Advanced Reasoning)', description: '顶级推理模型，具备最高逻辑深度 (Paid 25 RPM, 250 RPD)，适合复杂多轮研讨。' },
];


const DEEPSEEK_MODELS = [
  { id: 'deepseek-v4-flash', name: 'DeepSeek-V4 Flash (Efficiency)', description: '极速、高性价比 MoE 模型，原生支持 1M 上下文，适合高吞吐量实时分析与简单摘要。' },
  { id: 'deepseek-v4-pro',   name: 'DeepSeek-V4 Pro (Flagship)',    description: '旗舰级 1.6T MoE 推理模型，具备顶级逻辑深度与 STEM 能力，适合复杂研报。' },
];

export function SettingsModal() {
  const { t } = useTranslation();
  const { config, setConfig, tokenUsage, availableModels, setAvailableModels, feishuWebhookUrl, setFeishuWebhookUrl, debugMode, setDebugMode } = useConfigStore();
  const { isSettingsOpen, setIsSettingsOpen, showConfirm } = useUIStore();
  const [isFetchingModels, setIsFetchingModels] = useState(false);
  const [fetchMessage, setFetchMessage] = useState<{type: 'error' | 'success', text: string} | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);
  const serviceMode = config.serviceMode || 'byok';


  const displayModels = [...(availableModels.length > 0 ? availableModels : AVAILABLE_MODELS), ...DEEPSEEK_MODELS];

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
                </div>
                
                <div className="space-y-4">
                  <div className="group relative flex flex-col gap-2">
                    <div className="relative">
                      <input
                        type={showApiKey ? "text" : "password"}
                        placeholder={serviceMode === 'managed_no_key' ? '托管模式下无需填写（将使用服务端配置）' : 'AIzaSy... (输入您的 Gemini API Key)'}
                        id="api-key-input"
                        value={config.apiKey || ''}
                        onChange={(e) => setConfig({ ...config, apiKey: e.target.value })}
                        disabled={serviceMode === 'managed_no_key'}
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
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                          {serviceMode === 'managed_no_key' ? '托管模式' : config.apiKey?.startsWith('AIzaSy') ? '格式正确' : '格式不合规'}
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
                        : '您的密钥仅保存在本地浏览器中。为了保障分析的深度，请确保该 Key 已启用商业配额或属于 Google Cloud 项目。'}
                    </p>
                  </div>
                  
                  <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-50/50 border border-amber-100/50">
                    <Sparkles size={16} className="text-amber-400 shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-700/80 leading-relaxed">
                      <strong>💡 专业提示</strong>：使用个人 API Key 可有效避免"系统高负载"并大幅提升研报生成速度。您可以访问 Google AI Studio 或 DeepSeek 开放平台获取。
                    </p>
                  </div>
                </div>
              </section>

              {/* DeepSeek API Key Section */}
              <section className="space-y-4 p-6 rounded-2xl bg-zinc-950/5 border border-zinc-950/10 relative overflow-hidden">
                <div className="absolute top-0 right-0 px-3 py-1 bg-zinc-950 text-white text-[9px] font-black uppercase tracking-widest rounded-bl-lg">
                  New Feature
                </div>
                
                <div className="flex items-center gap-2">
                  <Cpu size={16} className="text-zinc-950" />
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-900">DeepSeek 开放平台</span>
                </div>
                
                <div className="space-y-4">
                  <div className="group relative flex flex-col gap-2">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <div className="h-5 w-5 flex items-center justify-center rounded-md bg-zinc-950 text-white text-[10px] font-bold">DS</div>
                        <span className="text-[11px] font-bold text-zinc-600 uppercase tracking-tight">V4 API KEY</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className={`h-1.5 w-1.5 rounded-full ${config.deepseekApiKey?.startsWith('sk-') ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-zinc-300'}`} />
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                          {config.deepseekApiKey?.startsWith('sk-') ? '格式正确' : '未设置'}
                        </span>
                      </div>
                    </div>
                    <div className="relative">
                      <input
                        type={showApiKey ? "text" : "password"}
                        placeholder="sk-... (从 deepseek.com 获取)"
                        id="deepseek-api-key-input"
                        value={config.deepseekApiKey || ''}
                        onChange={(e) => setConfig({ ...config, deepseekApiKey: e.target.value })}
                        className="input-premium pr-24 font-mono w-full bg-white"
                      />
                      <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
                        {config.deepseekApiKey && (
                          <button
                            onClick={() => setConfig({ ...config, deepseekApiKey: '' })}
                            className="p-1.5 text-zinc-300 hover:text-rose-500 transition-colors"
                          >
                            <Trash2 size={16} />
                          </button>
                        )}
                        <button
                          onClick={() => setShowApiKey(!showApiKey)}
                          className="p-1.5 text-zinc-300 hover:text-indigo-600 transition-colors"
                        >
                          {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-start gap-3 p-4 rounded-xl bg-white/50 border border-zinc-200/50">
                    <Info size={16} className="text-zinc-400 shrink-0 mt-0.5" />
                    <p className="text-xs text-zinc-600/70 leading-relaxed">
                      DeepSeek V4 为最新发布的 MoE 架构模型。如果您配置了 DeepSeek Key，系统在执行深度分析时会优先调用 V4 系列模型以确保最佳性价比。
                    </p>
                  </div>
                </div>
              </section>

              {/* Token Guard Level Section */}
              <section className="space-y-4">
                <div className="flex items-center gap-2">
                  <ShieldCheck size={16} className="text-amber-600" />
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">Token 成本控制</span>
                </div>

                <div className="space-y-3">
                  <div className="grid grid-cols-4 gap-2">
                    {([
                      { id: 'none', label: '无', desc: '无限制' },
                      { id: 'low', label: '低', desc: '宽松' },
                      { id: 'medium', label: '中', desc: '平衡' },
                      { id: 'high', label: '高', desc: '严格' },
                    ] as const).map((level) => {
                      const isActive = (config.tokenGuardLevel || 'high') === level.id;
                      return (
                        <button
                          key={level.id}
                          onClick={() => {
                            setConfig({ ...config, tokenGuardLevel: level.id });
                            // Sync to backend
                            fetch('/api/analysis/settings/token-guard', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ level: level.id }),
                            }).catch(() => {});
                          }}
                          className={`flex flex-col items-center gap-0.5 rounded-xl border p-3 transition-all ${
                            isActive
                              ? 'border-amber-500 bg-amber-50 ring-1 ring-amber-500'
                              : 'border-zinc-100 bg-white hover:border-zinc-200 hover:bg-zinc-50'
                          }`}
                        >
                          <span className={`text-sm font-bold ${isActive ? 'text-amber-700' : 'text-zinc-600'}`}>
                            {level.label}
                          </span>
                          <span className={`text-[10px] ${isActive ? 'text-amber-600' : 'text-zinc-400'}`}>
                            {level.desc}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-50/50 border border-amber-100/50">
                    <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
                    <p className="text-xs text-amber-700/80 leading-relaxed">
                      {(config.tokenGuardLevel || 'high') === 'none' 
                        ? '⚠️ 当前为无限制模式，工具返回数据不会被截断。适合本地模型，但云端 API 可能产生高额费用。'
                        : (config.tokenGuardLevel || 'high') === 'low'
                        ? '宽松模式：单轮工具输出上限约 18K tokens，适合大上下文模型 (128K+)。'
                        : (config.tokenGuardLevel || 'high') === 'medium'
                        ? '平衡模式：单轮工具输出上限约 10K tokens，在分析质量和成本间取得平衡。'
                        : '严格模式（推荐）：单轮工具输出上限约 6K tokens，最大化控制云端 API 成本。'}
                    </p>
                  </div>
                </div>
              </section>


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

              {/* Debug & Diagnosis Section */}
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

                <div className="flex items-start gap-4 p-5 rounded-2xl bg-zinc-50 border border-zinc-100 italic">
                  <div className="flex flex-col gap-3 w-full">
                    <div className="flex items-start gap-3">
                      <Cpu size={16} className="text-zinc-400 shrink-0 mt-0.5" />
                      <p className="text-xs text-zinc-500 leading-relaxed">
                        {t('settings.diagnosis.debug_desc')}
                      </p>
                    </div>
                    <div className="flex gap-2 pt-2 border-t border-zinc-200/60">
                      <a 
                        href="/api/logs/debug" 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-zinc-200 text-[10px] font-bold text-zinc-600 hover:bg-zinc-50"
                      >
                        {t('settings.diagnosis.view_logs')}
                      </a>
                      <button 
                        onClick={() => {
                          showConfirm(
                            t('settings.diagnosis.clear_logs'),
                            t('errors.confirm_clear_logs'),
                            async () => {
                              await fetch('/api/logs/debug', { method: 'DELETE' });
                            },
                            'danger'
                          );
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
