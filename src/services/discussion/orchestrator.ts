import type { AgentRole, DiscussionRound, OrchestratorConfig } from '../../types';
import { getSkipRoles } from './skipRules';

// ── Topology definitions ──────────────────────────────────────────

const DEEP_TOPOLOGY: DiscussionRound[] = [
  { round: 1, experts: ['Deep Research Specialist'], parallel: false, dependsOn: [] },
  // TA & FA are independent: both only need DR's output for cross-validation
  { round: 2, experts: ['Technical Analyst', 'Fundamental Analyst'], parallel: true, dependsOn: [1] },
  // SA needs TA + FA to cross-validate "资金面是否支撑技术趋势"
  { round: 3, experts: ['Sentiment Analyst'], parallel: false, dependsOn: [2] },
  // Bull vs Bear structured debate — independent viewpoints from same context
  { round: 4, experts: ['Bull Researcher', 'Bear Researcher'], parallel: true, dependsOn: [3] },
  // Risk management triad — three independent risk perspectives
  { round: 5, experts: ['Aggressive Risk Analyst', 'Conservative Risk Analyst', 'Neutral Risk Analyst'], parallel: true, dependsOn: [4] },
  { round: 6, experts: ['Contrarian Strategist'], parallel: false, dependsOn: [5] },
  { round: 7, experts: ['Professional Reviewer'], parallel: false, dependsOn: [6] },
  // Targeted revision: Bull & Bear refine arguments after all feedback
  { round: 8, experts: ['Bull Researcher', 'Bear Researcher'], parallel: true, dependsOn: [7] },
  // Investment Committee — Legendary Personas provide high-level wisdom
  { round: 9, experts: ['Value Investing Sage', 'Growth Visionary', 'Macro Hedge Titan'], parallel: true, dependsOn: [8] },
  { round: 10, experts: ['Chief Strategist'], parallel: false, dependsOn: [9] },
];

const STANDARD_TOPOLOGY: DiscussionRound[] = [
  { round: 1, experts: ['Deep Research Specialist'], parallel: false, dependsOn: [] },
  // TA & FA independent: both only need DR's output
  { round: 2, experts: ['Technical Analyst', 'Fundamental Analyst'], parallel: true, dependsOn: [1] },
  // Bull vs Bear structured debate — independent viewpoints
  { round: 3, experts: ['Bull Researcher', 'Bear Researcher'], parallel: true, dependsOn: [2] },
  { round: 4, experts: ['Risk Manager'], parallel: false, dependsOn: [3] },
  { round: 5, experts: ['Professional Reviewer'], parallel: false, dependsOn: [4] },
  // Investment Committee — Legendary Personas
  { round: 6, experts: ['Value Investing Sage', 'Growth Visionary', 'Macro Hedge Titan'], parallel: true, dependsOn: [5] },
  { round: 7, experts: ['Chief Strategist'], parallel: false, dependsOn: [6] },
];

const QUICK_TOPOLOGY: DiscussionRound[] = [
  { round: 1, experts: ['Deep Research Specialist'], parallel: false, dependsOn: [] },
  { round: 2, experts: ['Risk Manager'], parallel: false, dependsOn: [1] },
  { round: 3, experts: ['Chief Strategist'], parallel: false, dependsOn: [2] },
];

// ── Public API ─────────────────────────────────────────────────────

export function buildTopology(config: OrchestratorConfig): DiscussionRound[] {
  let template: DiscussionRound[];

  switch (config.level) {
    case 'quick':
      template = QUICK_TOPOLOGY;
      break;
    case 'standard':
      template = STANDARD_TOPOLOGY;
      break;
    case 'deep':
    default:
      template = DEEP_TOPOLOGY;
      break;
  }

  // Determine roles to skip
  const autoSkip = getSkipRoles(config.assetType);
  const manualSkip = config.skipRoles ?? [];
  const skipSet = new Set<AgentRole>([...autoSkip, ...manualSkip]);

  // Filter out skipped roles and remove empty rounds
  const filtered = template
    .map((round) => ({
      ...round,
      experts: round.experts.filter((e) => !skipSet.has(e)),
    }))
    .filter((round) => round.experts.length > 0);

  // Re-number rounds sequentially
  return filtered.map((round, i) => ({
    ...round,
    round: i + 1,
  }));
}
