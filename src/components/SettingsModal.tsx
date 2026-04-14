import React from 'react';
import { X, Settings, ShieldCheck, Cpu, AlertTriangle, Globe, Info, RefreshCw, Loader2, CheckCircle2, Sparkles, Eye, EyeOff, Trash2 } from 'lucide-react';
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

export function SettingsModal() {
  const { config, setConfig, tokenUsage, availableModels, setAvailableModels, feishuWebhookUrl, setFeishuWebhookUrl, debugMode, setDebugMode } = useConfigStore();
  const { isSettingsOpen, setIsSettingsOpen } = useUIStore();
  const [isFetchingModels, setIsFetchingModels] = useState(false);
  const [fetchMessage, setFetchMessage] = useState<{type: 'error' | 'success', text: string} | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);

  const displayModels = availableModels.length > 0 ? availableModels : AVAILABLE_MODELS;

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
                  <h2 id="settings-modal-title" className="text-xl font-bold text-zinc-950 tracking-tight">系统配置</h2>
                  <p className="text-xs font-medium text-zinc-400 mt-0.5">Customizing your analytical engine</p>
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
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">API 授权认证</span>
                </div>
                
                <div className="space-y-4">
                  <div className="group relative flex flex-col gap-2">
                    <div className="relative">
                      <input
                        type={showApiKey ? "text" : "password"}
                        placeholder="AIzaSy... (输入您的 Gemini API Key)"
                        id="api-key-input"
                        value={config.apiKey || ''}
                        onChange={(e) => setConfig({ ...config, apiKey: e.target.value })}
                        className="input-premium pr-24 font-mono w-full"
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
                        <div className={`h-1.5 w-1.5 rounded-full ${config.apiKey?.startsWith('AIzaSy') ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]'}`} />
                        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                          {config.apiKey?.startsWith('AIzaSy') ? '格式正确' : '格式不合规'}
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
                      您的密钥仅保存在本地浏览器中。为了保障分析的深度，请确保该 Key 已启用商业配额或属于 Google Cloud 项目。
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

              {/* Feishu Webhook Section */}
              <section className="space-y-4">
                <div className="flex items-center gap-2">
                  <Globe size={16} className="text-indigo-600" />
                  <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">飞书通知配置</span>
                </div>
                
                <div className="space-y-4">
                  <div className="relative group">
                    <input
                      type="text"
                      placeholder="输入飞书 Webhook 链接"
                      id="feishu-webhook-input"
                      value={feishuWebhookUrl}
                      onChange={(e) => setFeishuWebhookUrl(e.target.value)}
                      className="input-premium h-12 pl-4 pr-10 font-mono w-full"
                    />
                  </div>
                  <div className="flex items-start gap-3 p-4 rounded-xl bg-indigo-50/50 border border-indigo-100/50">
                    <Info size={16} className="text-indigo-400 shrink-0 mt-0.5" />
                    <p className="text-xs text-indigo-600/70 leading-relaxed">
                      配置飞书 Webhook 链接，以便在分析完成后接收实时通知。
                    </p>
                  </div>
                </div>
              </section>

              {/* Debug Mode Section */}
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles size={16} className="text-indigo-600" />
                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">系统诊断与优化</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
                      {debugMode ? '调试模式已开启' : '调试模式已关闭'}
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
                
                <div className="flex items-start gap-3 p-4 rounded-xl bg-zinc-50 border border-zinc-100 italic">
                  <Cpu size={16} className="text-zinc-400 shrink-0 mt-0.5" />
                  <div className="space-y-3 w-full">
                    <p className="text-xs text-zinc-500 leading-relaxed">
                      开启后，系统将记录所有后台请求与 API 响应数据。这有助于工程师分析数据偏差、优化 AI 推理逻辑并提高系统整体稳定性。
                    </p>
                    <div className="flex gap-2">
                      <a 
                        href="/api/logs/debug" 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-zinc-200 text-[10px] font-bold text-zinc-600 hover:bg-zinc-50"
                      >
                        查看调试日志
                      </a>
                      <button 
                        onClick={async () => {
                          await fetch('/api/logs/debug', { method: 'DELETE' });
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-zinc-200 text-[10px] font-bold text-rose-500 hover:bg-rose-50"
                      >
                        清除日志
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
                    <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">大语言模型预设</span>
                  </div>
                  <button 
                    onClick={handleFetchModels}
                    disabled={isFetchingModels}
                    className="text-[10px] font-bold uppercase tracking-widest text-indigo-600 hover:text-indigo-700 disabled:opacity-50 flex items-center gap-1.5"
                  >
                    {isFetchingModels ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
                    {isFetchingModels ? '同步中' : '刷新模型列表'}
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
                                配额耗尽
                              </span>
                            )}
                            {isUnavailable && (
                              <span className="flex items-center gap-1 text-[10px] font-bold text-rose-500 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-100">
                                <X size={10} />
                                不可用
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
                保存配置并开始分析
              </button>
              <p className="mt-4 text-center text-[10px] text-zinc-400 font-medium">
                配置将立即生效。如有疑问，请访问 Google AI Studio 检查 Key 状态。
              </p>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
