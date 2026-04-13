import { registerPrompt, getAllVersions } from './promptRegistry';
import { getAnalyzeStockPrompt, getMarketOverviewPrompt, getDiscussionPrompt, getChatMessagePrompt, getStockReportPrompt, getDiscussionReportPrompt, getDailyReportPrompt } from './prompts';

export const PROMPT_NAMES = {
  STOCK_ANALYSIS: 'stock-analysis',
  MARKET_OVERVIEW: 'market-overview',
  DISCUSSION: 'discussion',
  CHAT: 'chat',
  STOCK_REPORT: 'stock-report',
  DISCUSSION_REPORT: 'discussion-report',
  DAILY_REPORT: 'daily-report',
} as const;

let initialized = false;

export function initializePromptRegistry(): void {
  if (initialized) return;

  registerPrompt({
    id: 'stock-analysis-v1.0',
    name: PROMPT_NAMES.STOCK_ANALYSIS,
    version: '1.0',
    template: (...args: any[]) => getAnalyzeStockPrompt(args[0], args[1], args[2], args[3], args[4], args[5], args[6], args[7], args[8], args[9]),
    changelog: 'Initial version with 40+ field output',
    createdAt: '2026-03-27',
    isActive: true,
  });

  registerPrompt({
    id: 'market-overview-v1.0',
    name: PROMPT_NAMES.MARKET_OVERVIEW,
    version: '1.0',
    template: (...args: any[]) => getMarketOverviewPrompt(args[0], args[1], args[2], args[3], args[4], args[5], args[6], args[7], args[8], args[9]),
    changelog: 'Initial market overview prompt',
    createdAt: '2026-03-27',
    isActive: true,
  });

  registerPrompt({
    id: 'discussion-v1.0',
    name: PROMPT_NAMES.DISCUSSION,
    version: '1.0',
    template: (...args: any[]) => getDiscussionPrompt(args[0], args[1], args[2], args[3]),
    changelog: 'Initial 8-expert discussion prompt',
    createdAt: '2026-03-27',
    isActive: true,
  });

  registerPrompt({
    id: 'chat-v1.0',
    name: PROMPT_NAMES.CHAT,
    version: '1.0',
    template: (...args: any[]) => getChatMessagePrompt(args[0], args[1], args[2]),
    changelog: 'Initial chat message prompt',
    createdAt: '2026-03-27',
    isActive: true,
  });

  registerPrompt({
    id: 'stock-report-v1.0',
    name: PROMPT_NAMES.STOCK_REPORT,
    version: '1.0',
    template: (...args: any[]) => getStockReportPrompt(args[0]),
    changelog: 'Initial stock report prompt',
    createdAt: '2026-03-27',
    isActive: true,
  });

  registerPrompt({
    id: 'discussion-report-v1.0',
    name: PROMPT_NAMES.DISCUSSION_REPORT,
    version: '1.0',
    template: (...args: any[]) => getDiscussionReportPrompt(args[0], args[1], args[2], args[3], args[4]),
    changelog: 'Initial discussion report prompt',
    createdAt: '2026-03-27',
    isActive: true,
  });

  registerPrompt({
    id: 'daily-report-v1.0',
    name: PROMPT_NAMES.DAILY_REPORT,
    version: '1.0',
    template: (...args: any[]) => getDailyReportPrompt(args[0], args[1], args[2], args[3]),
    changelog: 'Initial daily report prompt',
    createdAt: '2026-03-27',
    isActive: true,
  });

  initialized = true;
}

export function resetPromptRegistration(): void {
  initialized = false;
}
