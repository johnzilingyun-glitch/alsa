import React from 'react';
import { motion } from 'motion/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  Shield, ShieldCheck, ShieldAlert, Award, TrendingUp, Target, 
  Search, AlertTriangle, Calculator, BarChart3, Database, ExternalLink 
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from './utils';
import type { AgentMessage, AgentRole } from '../../types';

interface ExpertReportCardProps {
  message: AgentMessage;
  isExpert?: boolean;
  expertiseArea?: string;
  references?: { title: string; url: string }[];
  isVerified?: boolean;
  auditDetail?: string;
  sentiment?: 'bullish' | 'bearish' | 'neutral';
}

const roleThemes: Record<AgentRole, { color: string; bg: string; border: string; icon: any }> = {
  "Bull Researcher": { color: "text-emerald-600", bg: "bg-emerald-50/50", border: "border-emerald-200/60", icon: TrendingUp },
  "Bear Researcher": { color: "text-slate-600", bg: "bg-slate-50/50", border: "border-slate-200/60", icon: Search },
  "Technical Analyst": { color: "text-indigo-600", bg: "bg-indigo-50/50", border: "border-indigo-200/60", icon: BarChart3 },
  "Fundamental Analyst": { color: "text-blue-600", bg: "bg-blue-50/50", border: "border-blue-200/60", icon: Database },
  "Sentiment Analyst": { color: "text-purple-600", bg: "bg-purple-50/50", border: "border-purple-200/60", icon: Database },
  "Risk Manager": { color: "text-rose-600", bg: "bg-rose-50/50", border: "border-rose-200/60", icon: Shield },
  "Aggressive Risk Analyst": { color: "text-red-600", bg: "bg-red-50/50", border: "border-red-200/60", icon: ShieldAlert },
  "Conservative Risk Analyst": { color: "text-green-600", bg: "bg-green-50/50", border: "border-green-200/60", icon: ShieldCheck },
  "Neutral Risk Analyst": { color: "text-indigo-600", bg: "bg-indigo-50/50", border: "border-indigo-200/60", icon: Shield },
  "Contrarian Strategist": { color: "text-orange-600", bg: "bg-orange-50/50", border: "border-orange-200/60", icon: AlertTriangle },
  "Deep Research Specialist": { color: "text-cyan-600", bg: "bg-cyan-50/50", border: "border-cyan-200/60", icon: Search },
  "Value Investing Sage": { color: "text-teal-600", bg: "bg-teal-50/50", border: "border-teal-200/60", icon: Database },
  "Growth Visionary": { color: "text-fuchsia-600", bg: "bg-fuchsia-50/50", border: "border-fuchsia-200/60", icon: Target },
  "Macro Hedge Titan": { color: "text-cyan-700", bg: "bg-cyan-50/50", border: "border-cyan-200/60", icon: BarChart3 },
  "Chief Strategist": { color: "text-amber-600", bg: "bg-amber-50/50", border: "border-amber-200/60", icon: Award },
  "Professional Reviewer": { color: "text-blue-600", bg: "bg-blue-50/50", border: "border-blue-200/60", icon: ShieldCheck },
  "Moderator": { color: "text-zinc-600", bg: "bg-zinc-50/50", border: "border-zinc-200/60", icon: Search }
};

export function ExpertReportCard({ 
  message, isExpert, expertiseArea, references, isVerified, auditDetail, sentiment 
}: ExpertReportCardProps) {
  const { t } = useTranslation();
  const theme = roleThemes[message.role] || roleThemes["Moderator"];
  const RoleIcon = theme.icon;

  const activeSentiment = sentiment || 
    (message.role === 'Bull Researcher' ? 'bullish' : 
     message.role === 'Bear Researcher' ? 'bearish' : 'neutral');

  // Improved parsing logic for sections
  const rawSections = message.content.split(/--- (\d+\. [^:]+):/).filter(s => s !== undefined);
  
  const parsedSections: { title: string; content: string }[] = [];
  
  // If the first element isn't a title (regex capture), treat it as an introduction
  let startIndex = 0;
  if (rawSections[0] && !message.content.startsWith(`--- ${rawSections[0]}:`)) {
    parsedSections.push({ title: "Executive Overview", content: rawSections[0].trim() });
    startIndex = 1;
  }

  for (let i = startIndex; i < rawSections.length; i += 2) {
    const title = rawSections[i]?.trim();
    const content = rawSections[i + 1]?.trim();
    if (title && content) {
      parsedSections.push({ title, content });
    } else if (title) {
        // Handle case where content might be missing for the last section
        parsedSections.push({ title, content: "" });
    }
  }

  if (parsedSections.length === 0) {
    parsedSections.push({ title: "Analysis Report", content: message.content });
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex gap-6 max-w-5xl mx-auto w-full group"
    >
      {/* Icon Sidebar */}
      <div className={cn(
        "flex-shrink-0 w-16 h-16 rounded-[1.5rem] flex items-center justify-center border transition-all duration-500 group-hover:scale-105 shadow-sm",
        theme.bg, theme.border, theme.color
      )}>
        <RoleIcon size={28} strokeWidth={1.5} />
      </div>

      <div className="flex-1 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between items-start">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-3">
              <span className={cn(
                "px-4 py-1.5 rounded-2xl text-[10px] font-bold uppercase tracking-[0.2em] border shadow-sm",
                theme.bg, theme.border, theme.color
              )}>
                {t(`analysis.roles.${message.role}`)}
              </span>
              {isExpert && (
                <div className="px-3 py-1.5 rounded-2xl bg-indigo-600 text-white text-[9px] font-bold uppercase tracking-widest flex items-center gap-2 shadow-lg shadow-indigo-600/20">
                  <Award size={12} />
                  {expertiseArea || "Expert Opinion"}
                </div>
              )}
              {isVerified && (
                <div className="px-3 py-1.5 rounded-2xl bg-emerald-500 text-white text-[9px] font-bold uppercase tracking-widest flex items-center gap-2 shadow-lg shadow-emerald-500/20">
                  <ShieldCheck size={12} />
                  Verified
                </div>
              )}
            </div>
          </div>
          <span className="text-[10px] font-mono text-zinc-400 font-bold bg-zinc-50 px-3 py-1 rounded-lg border border-zinc-100">
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        </div>

        {/* Content Body */}
        <div className={cn(
          "relative bg-white/70 backdrop-blur-xl border border-white/60 rounded-[2.5rem] p-1 shadow-[0_8px_32px_rgba(0,0,0,0.04)]",
          "group-hover:shadow-[0_12px_48px_rgba(0,0,0,0.08)] transition-all duration-500 overflow-hidden",
          activeSentiment === 'bullish' && "ring-1 ring-emerald-500/20",
          activeSentiment === 'bearish' && "ring-1 ring-rose-500/20"
        )}>
          {/* Background accent */}
          <div className={cn(
            "absolute top-0 right-0 w-64 h-64 -mr-32 -mt-32 rounded-full opacity-[0.03] blur-3xl pointer-events-none",
            activeSentiment === 'bullish' ? "bg-emerald-500" : 
            activeSentiment === 'bearish' ? "bg-rose-500" : theme.bg.replace('bg-', 'bg-')
          )} />
          
          <div className="p-8 space-y-10 relative z-10">
            {parsedSections.map((section, idx) => {
              const isKelly = section.title.includes("KELLY");
              const isRisk = section.title.includes("RISK");
              const isPlan = section.title.includes("PLAN");

              return (
                <div key={idx} className={cn(
                  "space-y-4",
                  idx !== 0 && "pt-8 border-t border-zinc-100"
                )}>
                  <div className="flex items-center gap-3">
                    <div className={cn("w-1 h-4 rounded-full", theme.color.replace('text', 'bg'))} />
                    <h5 className="text-[11px] font-bold uppercase tracking-[0.25em] text-zinc-400">
                      {section.title}
                    </h5>
                  </div>

                  {isKelly ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="p-6 rounded-[2rem] bg-indigo-600 text-white shadow-xl shadow-indigo-600/10 flex flex-col items-center justify-center">
                        <Calculator size={32} className="mb-4 opacity-50" />
                        <span className="text-[9px] font-bold uppercase tracking-widest mb-2 opacity-80">Allocation Suggestion</span>
                        {(() => {
                          const allocation = section.content.match(/(\d+\.?\d*)%/);
                          return (
                            <div className="text-4xl font-bold tracking-tighter">
                              {allocation ? allocation[0] : "N/A"}
                            </div>
                          );
                        })()}
                      </div>
                      <div className="p-6 rounded-[2rem] bg-indigo-50/50 border border-indigo-100 flex items-center justify-center">
                        <div className="prose prose-sm prose-indigo italic text-indigo-900/60 font-medium">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{section.content}</ReactMarkdown>
                        </div>
                      </div>
                    </div>
                  ) : isRisk ? (
                    <div className="grid grid-cols-1 gap-4">
                       <div className="p-6 rounded-[2rem] bg-rose-50 border border-rose-100/60">
                         {(() => {
                           const score = section.content.match(/(\d+)\/100/);
                           return score && (
                             <div className="flex items-center gap-6 mb-6">
                               <div className="text-center">
                                 <span className="text-[9px] font-bold text-rose-400 uppercase tracking-widest block mb-1">Risk Score</span>
                                 <span className="text-3xl font-bold text-rose-600 italic leading-none">{score[0]}</span>
                               </div>
                               <div className="flex-1 h-3 bg-rose-200/30 rounded-full overflow-hidden">
                                 <div className="h-full bg-rose-500 rounded-full" style={{ width: `${score[1]}%` }} />
                               </div>
                             </div>
                           );
                         })()}
                         <div className="prose prose-sm prose-rose max-w-none text-rose-900/70">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{section.content.replace(/(\d+)\/100/, '')}</ReactMarkdown>
                         </div>
                       </div>
                    </div>
                  ) : (
                    <div className={cn(
                      "prose prose-zinc max-w-none w-full",
                      "prose-sm sm:prose-base antialiased",
                      // Paragraphs
                      "prose-p:text-zinc-600 prose-p:leading-[1.8] prose-p:mb-5",
                      // Headings
                      "prose-headings:text-zinc-900 prose-headings:font-bold prose-headings:tracking-tight",
                      "prose-h3:text-lg prose-h3:mt-8 prose-h3:mb-4",
                      "prose-h4:text-base prose-h4:mt-6 prose-h4:mb-3",
                      // Typography
                      "prose-strong:text-zinc-900 prose-strong:font-semibold",
                      "prose-em:italic",
                      // Lists
                      "prose-ul:list-outside prose-ul:pl-5 prose-ul:mb-6 prose-ul:space-y-2",
                      "prose-ol:list-decimal prose-ol:list-outside prose-ol:pl-5 prose-ol:mb-6 prose-ol:space-y-2",
                      "prose-li:text-zinc-600 prose-li:leading-relaxed",
                      // Blockquotes (styled dynamically by role theme)
                      "prose-blockquote:border-l-4 prose-blockquote:pl-5 prose-blockquote:py-1 prose-blockquote:not-italic",
                      "prose-blockquote:text-zinc-600 prose-blockquote:bg-zinc-50 prose-blockquote:rounded-r-xl",
                      // Tables (Institutional Grade)
                      "prose-table:w-full prose-table:my-8 prose-table:border-collapse",
                      "prose-table:shadow-sm prose-table:rounded-xl prose-table:overflow-hidden",
                      "prose-thead:bg-zinc-100/80 prose-thead:border-b-2 prose-thead:border-zinc-200",
                      "prose-th:px-4 prose-th:py-3.5 prose-th:text-left prose-th:text-[11px] prose-th:font-bold prose-th:uppercase prose-th:tracking-wider prose-th:text-zinc-500",
                      "prose-tbody:bg-white",
                      "prose-tr:border-b prose-tr:border-zinc-100 hover:prose-tr:bg-zinc-50/50 prose-tr:transition-colors",
                      "prose-td:px-4 prose-td:py-3.5 prose-td:text-sm prose-td:text-zinc-600 prose-td:align-middle",
                      // Links
                      "prose-a:text-indigo-600 prose-a:no-underline hover:prose-a:underline prose-a:font-medium",
                      // Inline Code
                      "prose-code:text-[13px] prose-code:font-mono prose-code:bg-zinc-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:text-zinc-800 before:prose-code:content-none after:prose-code:content-none"
                    )}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{section.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Timestamp Footer for Internal Use */}
          <div className="px-8 py-2 flex justify-end">
            <span className="text-[9px] font-mono text-zinc-300 font-medium italic">
              Verification ID: {message.id || 'ALSA-INT-001'}
            </span>
          </div>

          {/* References */}
          {references && references.length > 0 && (
            <div className="px-8 py-6 bg-zinc-50/50 border-t border-zinc-100 rounded-b-[2.5rem]">
               <div className="flex items-center gap-2 mb-4">
                 <Search size={14} className="text-zinc-400" />
                 <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Institutional Data Sources</span>
               </div>
               <div className="flex flex-wrap gap-2">
                 {references.map((ref, i) => (
                   <a 
                     key={i} 
                     href={ref.url} 
                     target="_blank" 
                     className="px-4 py-2 rounded-xl bg-white border border-zinc-200 text-[11px] font-bold text-zinc-600 flex items-center gap-2 hover:border-indigo-600/30 hover:text-indigo-600 transition-all shadow-sm"
                   >
                     {ref.title.length > 30 ? ref.title.slice(0, 30) + '...' : ref.title}
                     <ExternalLink size={12} className="opacity-50" />
                   </a>
                 ))}
               </div>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
