import React, { useState, useEffect } from 'react';
import { Activity, Clock, Loader2 } from 'lucide-react';
import { authFetch } from '../../stores/useAuthStore';

interface ActivityItem {
  job_id: string;
  symbol: string;
  market: string;
  status: string;
  analysis_level: string;
  user: string;
  created_at: string | null;
}

const STATUS_COLORS: Record<string, string> = {
  completed: 'bg-emerald-100 text-emerald-700',
  running: 'bg-blue-100 text-blue-700',
  queued: 'bg-zinc-100 text-zinc-600',
  failed: 'bg-rose-100 text-rose-600',
};

export function TeamActivity() {
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchActivity = async () => {
      try {
        const res = await authFetch('/api/admin/team-activity');
        if (res.ok) {
          const data = await res.json();
          setActivities(data.activities || []);
        }
      } catch {}
      setLoading(false);
    };
    fetchActivity();
    const interval = setInterval(fetchActivity, 60000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm p-6">
        <div className="flex items-center justify-center py-8">
          <Loader2 size={20} className="animate-spin text-indigo-500" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-zinc-100 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-violet-100 flex items-center justify-center">
          <Activity size={20} className="text-violet-600" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-zinc-900">Team Activity</h3>
          <p className="text-xs text-zinc-500">Recent analyses by team members</p>
        </div>
      </div>

      {activities.length === 0 ? (
        <div className="px-6 py-8 text-center text-sm text-zinc-400">No recent activity</div>
      ) : (
        <div className="divide-y divide-zinc-50 max-h-[400px] overflow-y-auto">
          {activities.map(a => (
            <div key={a.job_id} className="px-6 py-3 flex items-center justify-between hover:bg-zinc-50 transition-colors">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-zinc-100 flex items-center justify-center text-xs font-bold text-zinc-600">
                  {a.user[0]?.toUpperCase()}
                </div>
                <div>
                  <div className="text-sm font-medium text-zinc-800">
                    <span className="text-indigo-600">{a.symbol}</span>
                    <span className="text-zinc-400 mx-1">·</span>
                    <span className="text-zinc-500 text-xs">{a.market}</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5">
                    by {a.user} · {a.analysis_level}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 text-[10px] font-bold rounded ${STATUS_COLORS[a.status] || 'bg-zinc-100 text-zinc-600'}`}>
                  {a.status}
                </span>
                {a.created_at && (
                  <span className="text-[10px] text-zinc-400 flex items-center gap-0.5">
                    <Clock size={10} />
                    {timeAgo(a.created_at)}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}
