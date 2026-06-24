import type { DataVerification, SegmentValuation, ExpectationGap, CalculationResult, AnalysisLevel, QuantifiedRisk, AgentMessage, CoreVariable, Scenario, Catalyst, BusinessModel, StockAnalysis, AnalystWeight, TradingPlanVersion, ExpectedValueOutcome, SensitivityFactor, SensitivityMatrixRow, TradingPlan } from './analysis';
import type { IndustryAnchor, Market } from './market';

export type Language = "en" | "zh-CN";

export interface ChatMessage {
  id: string;
  role: "user" | "ai";
  content: string;
}

export type AgentRole =
  | "Technical Analyst"
  | "Fundamental Analyst"
  | "Sentiment Analyst"
  | "Risk Manager"
  | "Aggressive Risk Analyst"
  | "Conservative Risk Analyst"
  | "Neutral Risk Analyst"
  | "Bull Researcher"
  | "Bear Researcher"
  | "Contrarian Strategist"
  | "Deep Research Specialist"
  | "Professional Reviewer"
  | "Chief Strategist"
  | "Value Investing Sage"
  | "Growth Visionary"
  | "Macro Hedge Titan"
  | "Moderator";

export interface MultiRoundProgress {
  currentRound: number;
  totalRounds: number;
  activeExperts: string[]; // Support parallel experts
  currentStep?: 'grounding' | 'reasoning' | 'drafting' | 'reviewing' | 'auditing';
  messages: AgentMessage[];
  partialDiscussion?: Partial<AgentDiscussion>;
  lastReasoning?: string; // Real-time AI feedback snippet
}

export interface AgentDiscussion {
  messages: AgentMessage[];
  finalConclusion: string;
  tradingPlan?: TradingPlan;
  tradingPlanHistory?: TradingPlanVersion[];
  controversialPoints?: string[];
  scenarios?: Scenario[];
  valuationMatrix?: Scenario[];
  stressTestLogic?: string;
  catalystList?: Catalyst[];
  sensitivityFactors?: SensitivityFactor[];
  expectationGap?: ExpectationGap;
  analystWeights?: AnalystWeight[];
  calculations?: CalculationResult[];
  dataFreshnessStatus?: "Fresh" | "Stale" | "Warning";
  dataVerification?: DataVerification[];
  coreVariables?: CoreVariable[];
  businessModel?: BusinessModel;
  moatAnalysis?: {
    type: string;
    strength: "Wide" | "Narrow" | "None";
    logic: string;
  };
  industryAnchors?: IndustryAnchor[];
  quantifiedRisks?: QuantifiedRisk[];
  riskAdjustedValuation?: number;
  expectedValueOutcome?: ExpectedValueOutcome;
  sensitivityMatrix?: SensitivityMatrixRow[];
  backtestResult?: {
    previousDate: string;
    previousRecommendation: string;
    actualReturn: string;
    learningPoint: string;
  };
  verificationMetrics?: {
    indicator: string;
    threshold: string;
    timeframe: string;
    logic: string;
  }[];
  capitalFlow?: {
    northboundFlow: string;
    institutionalHoldings: string;
    ahPremium?: string;
    marketSentiment: string;
  };
  positionManagement?: {
    layeredEntry: string[];
    sizingLogic: string;
    riskAdjustedStance: string;
  };
  timeDimension?: {
    expectedDuration: string;
    keyMilestones: string[];
    exitTriggers: string[];
  };
  legendaryInsights?: {
    valueSage?: { marginOfSafety: string; intrinsicValue: string; moatRating: string };
    growthVisionary?: { tamEstimate: string; innovationScore: string; disruptionPotential: string };
    macroTitan?: { macroSignal: string; liquidityStatus: string; systemicRiskLevel: string };
  };
  consensusBiasScore?: number; // 0-100 (Opinion Drift)
  logicFindings?: { role: string; rule: string; severity: string; finding: string }[];
  sotpMatrix?: SegmentValuation[];
  monteCarloData?: {
    p5: number;
    p50: number;
    p95: number;
    distribution: { price: number; probability: number }[];
  };
  institutionalRisk?: {
    beta: number;
    sharpeProxy: number;
    var95: number;
  };
}

export type BusinessType = "manufacturing" | "saas" | "banking" | "retail" | "healthcare" | "tech" | "other";

export interface LLMConfig {
  model: string;
  apiKey?: string;
  deepseekApiKey?: string;
  deepseekModel?: string;
  feishuWebhookUrl?: string;
  tier?: 'free' | 'paid';
  serviceMode?: 'byok' | 'managed_no_key' | 'copilot_local';
  tokenGuardLevel?: 'none' | 'low' | 'medium' | 'high';
}

export interface ReportPreference {
  detailLevel: 'executive' | 'analyst' | 'trader';
  focusAreas: ('fundamental' | 'technical' | 'risk' | 'scenario' | 'sentiment')[];
  includeBacktest: boolean;
  includeExpertDebate: boolean;
  maxLength: 'brief' | 'standard' | 'full';
}

// === 10.1 Data Freshness ===
export type FreshnessStatus = 'fresh' | 'delayed' | 'stale';

export interface FreshnessInfo {
  status: FreshnessStatus;
  label: string;     // "🟢 实时" | "🟡 延迟" | "🔴 过时"
  ageMinutes: number;
}

// === 10.2 Analysis Cache ===
export interface CachedAnalysis {
  data: StockAnalysis;
  timestamp: number;
}

// === OPT-1 Discussion Orchestrator ===
export interface DiscussionRound {
  round: number;
  experts: AgentRole[];
  parallel: boolean;
  dependsOn: number[];
}

export interface OrchestratorConfig {
  level: AnalysisLevel;
  assetType: 'stock' | 'etf' | 'index' | 'bond';
  skipRoles?: AgentRole[];
  maxConcurrency: number;
}

// === OPT-2 Backtest Enhancement ===
export interface BacktestTimeSeries {
  symbol: string;
  entries: BacktestEntry[];
  overallAccuracy: number;
  directionAccuracy: number;
  avgHoldingPeriodDays: number;
  profitFactor: number;
  maxConsecutiveLosses: number;
  longestWinStreak: number;
  sharpeRatio: number;
}

export interface BacktestEntry {
  date: string;
  recommendation: string;
  targetPrice: number;
  stopLoss: number;
  actualPrice: number;
  returnPercent: number;
  directionCorrect: boolean;
  targetHit: boolean;
}

export interface ExpertTrackRecord {
  role: AgentRole;
  totalCalls: number;
  directionAccuracy: number;
  targetHitRate: number;
  avgOvershoot: number;
  bestSector: string;
  worstSector: string;
  recentTrend: 'improving' | 'declining' | 'stable';
  last5Accuracy: number[];
}

export interface SystematicBias {
  hasBias: boolean;
  biasType: 'bullish_drift' | 'bearish_drift' | 'target_overshoot' | null;
  severity: 'low' | 'medium' | 'high';
  consecutiveCount: number;
}

// === OPT-6 Analysis Level ===
export interface ExpertOutput {
  role: AgentRole;
  message: AgentMessage;
  structuredData?: Partial<StockAnalysis>;
}

// === NEW-1 Watchlist ===
export interface WatchlistItem {
  id: string;
  symbol: string;
  name: string;
  market: Market;
  addedAt: string;
  notes: string;
  alertThreshold: number;
  scoreHistory: ScoreSnapshot[];
  lastQuickScan?: QuickScanResult;
  alertHistory: WatchlistAlert[];
}

export interface ScoreSnapshot {
  date: string;
  score: number;
  price: number;
  recommendation: string;
}

export interface QuickScanResult {
  score: number;
  sentiment: string;
  recommendation: string;
  summary: string;
  timestamp: string;
}

export interface WatchlistAlert {
  id: string;
  type: 'score_drop' | 'score_rise' | 'price_target' | 'stop_loss';
  message: string;
  triggeredAt: string;
  acknowledged: boolean;
}

// === NEW-2 Sector Rotation ===
export interface SectorRotation {
  sector: string;
  capitalFlowTrend: 'inflow' | 'outflow' | 'neutral';
  flowMagnitude: number;
  clockQuadrant: 'recovery' | 'expansion' | 'overheating' | 'stagflation';
  momentum30d: number;
  topStocks: { symbol: string; name: string; score: number }[];
  updatedAt: string;
}

export interface MarketCycle {
  currentPhase: 'recovery' | 'expansion' | 'overheating' | 'stagflation';
  phaseConfidence: number;
  recommendedSectors: string[];
  avoidSectors: string[];
  logic: string;
}

export interface SectorRotationData {
  rotations: SectorRotation[];
  cycle: MarketCycle;
  generatedAt: string;
}

// === NEW-4 Comparison ===
export interface ComparisonResult {
  stocks: ComparisonStock[];
  sharedIndustry: string;
  verdict: string;
  generatedAt: string;
}

export interface ComparisonStock {
  symbol: string;
  name: string;
  market: Market;
  score: number;
  recommendation: string;
  pe?: string;
  pb?: string;
  roe?: string;
  moatStrength?: 'Wide' | 'Narrow' | 'None';
  riskLevel: 'Low' | 'Medium' | 'High';
}

// === NEW-5 Decision Journal ===
export interface DecisionEntry {
  id: string;
  symbol: string;
  name: string;
  market: Market;
  analysisId: string;
  action: 'buy' | 'hold' | 'sell' | 'add' | 'reduce' | 'watch';
  reasoning: string;
  priceAtDecision: number;
  confidence: number;
  createdAt: string;
  reviewDate: string;
  priceAtReview?: number;
  actualReturn?: number;
  outcome?: 'correct' | 'incorrect' | 'neutral';
  reflection?: string;
  lessonsLearned?: string[];
  biasDetected?: string;
}

export interface DecisionStats {
  totalDecisions: number;
  correctRate: number;
  avgConfidence: number;
  overconfidenceBias: number;
  mostCommonBias: string;
  bestPerformingAction: string;
  worstPerformingAction: string;
  avgReturnByAction: Record<string, number>;
}
