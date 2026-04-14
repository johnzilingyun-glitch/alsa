import type { AnalysisLevel } from '../types';

export interface AnalysisLevelConfig {
  level: AnalysisLevel;
  includeDiscussion: boolean;
  includeBacktest: boolean;
  includeCommodities: boolean;
  saveHistory: boolean;
  historyLookback: number;
  expertCount: number;
  estimatedTokens: number;
  estimatedLatencyMs: number;
  outputFields: string[];
}

const QUICK_FIELDS = ['stockInfo', 'score', 'sentiment', 'recommendation', 'summary', 'keyRisks', 'keyOpportunities'];

const STANDARD_FIELDS = [
  ...QUICK_FIELDS,
  'fundamentals', 'technicalAnalysis', 'fundamentalAnalysis',
  'tradingPlan', 'scenarios', 'news', 'historicalData',
  'valuationAnalysis', 'coreVariables', 'businessModel',
  'quantifiedRisks', 'capitalFlow',
];

const DEEP_FIELDS = [
  ...STANDARD_FIELDS,
  'discussion', 'finalConclusion', 'backtestResult',
  'tradingPlanHistory', 'controversialPoints',
  'sensitivityFactors', 'expectationGap',
  'analystWeights', 'verificationMetrics',
  'positionManagement', 'timeDimension',
  'moatAnalysis', 'narrativeConsistency',
];

const configs: Record<AnalysisLevel, AnalysisLevelConfig> = {
  quick: {
    level: 'quick',
    includeDiscussion: false,
    includeBacktest: false,
    includeCommodities: false,
    saveHistory: false,
    historyLookback: 0,
    expertCount: 0,
    estimatedTokens: 500,
    estimatedLatencyMs: 3000,
    outputFields: QUICK_FIELDS,
  },
  standard: {
    level: 'standard',
    includeDiscussion: false,
    includeBacktest: false,
    includeCommodities: true,
    saveHistory: true,
    historyLookback: 1,
    expertCount: 0,
    estimatedTokens: 3000,
    estimatedLatencyMs: 15000,
    outputFields: STANDARD_FIELDS,
  },
  deep: {
    level: 'deep',
    includeDiscussion: true,
    includeBacktest: true,
    includeCommodities: true,
    saveHistory: true,
    historyLookback: 3,
    expertCount: 8,
    estimatedTokens: 8000,
    estimatedLatencyMs: 45000,
    outputFields: DEEP_FIELDS,
  },
};

export function getAnalysisLevelConfig(level: AnalysisLevel): AnalysisLevelConfig {
  return configs[level];
}
