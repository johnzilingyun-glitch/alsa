import { Coins } from 'lucide-react';
import { useConfigStore } from '../../stores/useConfigStore';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function TokenUsage() {
  const { tokenUsage, serviceStatus } = useConfigStore();

  return (
    <div className="mb-12">
      <div className="premium-card p-8 group transition-all animate-premium overflow-hidden relative">
        <div 
          className="absolute bottom-0 left-0 h-1 bg-indigo-600/10 transition-all duration-1000 ease-out"
          style={{ width: `${Math.min(100, (tokenUsage.totalTokens / 1000000) * 100)}%` }}
        />
        
        <div className="flex flex-col xl:flex-row items-center justify-between gap-10">
          <div className="flex items-center gap-5 w-full xl:w-auto">
            <div className="h-12 w-12 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0 shadow-sm shadow-indigo-600/5 transition-transform group-hover:scale-105">
              <Coins size={22} strokeWidth={1.5} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="section-label mb-0">Resource Monitoring</span>
              </div>
              <h3 className="text-sm font-bold text-zinc-950 tracking-tight">API 额度智能监测</h3>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-12 gap-y-6 w-full xl:w-auto divide-x-0 md:divide-x divide-zinc-100">
            <div className="space-y-1">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Tokens Input</p>
              <p className="text-xl font-mono font-bold text-zinc-950 tabular-nums tracking-tighter">
                {tokenUsage.promptTokens.toLocaleString()}
              </p>
            </div>
            
            <div className="space-y-1 md:pl-10">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Response Sync</p>
              <p className="text-xl font-mono font-bold text-zinc-950 tabular-nums tracking-tighter">
                {tokenUsage.candidatesTokens.toLocaleString()}
              </p>
            </div>
            
            <div className="space-y-1 md:pl-10">
              <p className="text-[10px] font-bold uppercase tracking-widest text-indigo-600">Total Usage</p>
              <p className="text-xl font-mono font-bold text-indigo-600 tabular-nums tracking-tighter">
                {tokenUsage.totalTokens.toLocaleString()}
              </p>
            </div>

            <div className="space-y-1 md:pl-10">
              <div className="flex items-center gap-2">
                <p className={cn(
                  "text-[10px] font-bold uppercase tracking-widest",
                  serviceStatus === 'quota_exhausted' ? "text-rose-500" : 
                  serviceStatus === 'error' ? "text-amber-500" : "text-emerald-600"
                )}>Service Status</p>
                <div className={cn(
                  "h-1.5 w-1.5 rounded-full animate-pulse",
                  serviceStatus === 'quota_exhausted' ? "bg-rose-500" : 
                  serviceStatus === 'error' ? "bg-amber-500" : "bg-emerald-500"
                )} />
              </div>
              <p className={cn(
                "text-sm font-bold tracking-tight uppercase transition-colors duration-300",
                serviceStatus === 'quota_exhausted' ? "text-rose-600" : 
                serviceStatus === 'error' ? "text-amber-600" : "text-emerald-600"
              )}>
                {serviceStatus === 'quota_exhausted' ? 'Quota Exhausted' : 
                 serviceStatus === 'error' ? 'Service Limited' : 'Active / Stable'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
