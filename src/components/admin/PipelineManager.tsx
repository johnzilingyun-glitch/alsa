import React, { useState, useEffect } from 'react';
import { GitBranch, Plus, CheckCircle, Activity, AlertCircle } from 'lucide-react';
import { authFetch } from '../../stores/useAuthStore';

interface PipelineVersion {
  id: string;
  name: string;
  status: 'development' | 'production' | 'deprecated';
  config: any;
  release_notes?: string;
  created_at: string;
}

export function PipelineManager() {
  const [versions, setVersions] = useState<PipelineVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [newName, setNewName] = useState('');
  const [newNotes, setNewNotes] = useState('');

  const fetchVersions = async () => {
    setLoading(true);
    try {
      const res = await authFetch('/api/admin/pipeline-versions');
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          setVersions(data.data);
        }
      }
    } catch (e) {
      console.error("Failed to fetch pipeline versions", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchVersions();
  }, []);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const res = await authFetch('/api/admin/pipeline-versions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName, status: 'development', release_notes: newNotes })
      });
      if (res.ok) {
        setNewName('');
        setNewNotes('');
        fetchVersions();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handlePromote = async (id: string) => {
    if (!window.confirm("确定将此测试版本发布到生产环境吗？生产环境的所有用户将立即生效！")) return;
    
    try {
      const res = await authFetch(`/api/admin/pipeline-versions/${id}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'production' })
      });
      if (res.ok) {
        fetchVersions();
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="flex items-center gap-2 text-xl font-medium">
        <GitBranch size={20} className="text-purple-500" />
        AI 管线版本管理 (A/B Routing)
      </h2>
      
      <div className="p-4 rounded-xl border border-zinc-200 bg-white shadow-sm space-y-4">
        <h3 className="font-medium text-sm text-zinc-700">新建开发管线版本</h3>
        <div className="flex gap-4">
          <input 
            type="text" 
            placeholder="版本名称 (例如: v2.0 LangGraph)" 
            className="flex-1 px-4 py-2 text-sm border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500/20"
            value={newName}
            onChange={e => setNewName(e.target.value)}
          />
          <input 
            type="text" 
            placeholder="更新说明" 
            className="flex-1 px-4 py-2 text-sm border border-zinc-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500/20"
            value={newNotes}
            onChange={e => setNewNotes(e.target.value)}
          />
          <button 
            onClick={handleCreate}
            disabled={!newName.trim()}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 flex items-center gap-2 transition-colors"
          >
            <Plus size={16} /> 创建
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {loading ? (
          <div className="text-zinc-500 text-sm">加载中...</div>
        ) : versions.length === 0 ? (
          <div className="p-8 text-center border border-zinc-200 border-dashed rounded-xl text-zinc-500 text-sm">
            暂无自定义管线版本。系统正在使用默认生产管线。
          </div>
        ) : (
          versions.map(v => (
            <div key={v.id} className={`p-4 rounded-xl border flex items-center justify-between transition-colors ${
              v.status === 'production' ? 'border-emerald-500/30 bg-emerald-50/30' :
              v.status === 'development' ? 'border-purple-500/30 bg-purple-50/30' :
              'border-zinc-200 bg-zinc-50/50'
            }`}>
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                  <span className="font-bold text-zinc-800">{v.name}</span>
                  <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-full ${
                    v.status === 'production' ? 'bg-emerald-100 text-emerald-700' :
                    v.status === 'development' ? 'bg-purple-100 text-purple-700' :
                    'bg-zinc-200 text-zinc-500'
                  }`}>
                    {v.status}
                  </span>
                  <span className="text-xs text-zinc-400 font-mono">{v.id}</span>
                </div>
                <div className="text-xs text-zinc-500">
                  {v.release_notes || '无更新说明'} • {new Date(v.created_at).toLocaleString()}
                </div>
              </div>
              
              <div className="flex items-center gap-3">
                {v.status === 'development' && (
                  <button 
                    onClick={() => handlePromote(v.id)}
                    className="px-3 py-1.5 bg-emerald-500 text-white text-xs font-medium rounded hover:bg-emerald-600 flex items-center gap-1.5 transition-colors"
                  >
                    <CheckCircle size={14} /> 一键发布至生产
                  </button>
                )}
                {v.status === 'production' && (
                  <div className="flex items-center gap-1.5 text-emerald-600 text-xs font-medium px-3 py-1.5 bg-emerald-100 rounded">
                    <Activity size={14} className="animate-pulse" /> 正在服役
                  </div>
                )}
                {v.status === 'deprecated' && (
                  <div className="flex items-center gap-1.5 text-zinc-400 text-xs font-medium px-3 py-1.5 bg-zinc-100 rounded">
                    <AlertCircle size={14} /> 已弃用
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
